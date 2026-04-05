import os
import threading
import time

from config import (
    CURRENT_ITEM_FILE,
    HISTORY_FILE,
    PLAYBACK_ERROR_DELAY_SECONDS,
    POLL_INTERVAL_MINUTES,
    QUEUE_FILE,
    SCAN_ERROR_DELAY_SECONDS,
    STATE_DIR,
)
from services.channel_scan_service import run_channel_scan
from services.models import VideoItem
from services.playback_service import PlayOutcome, PlaybackService, is_filler_item
from services.queue_service import QueueService
from services.runtime_control import (
    PlaybackCommand,
    clear_command,
    is_paused,
    load_control,
)
from services.storage import (
    append_history,
    load_current_item,
    load_queue,
    pop_history_last_non_filler,
    save_current_item,
    save_queue,
)
from utils.logger import log_blank, log_error, log_play, log_warn


def scan_for_new_videos() -> None:
    run_channel_scan()


def _apply_playback_outcome(item: VideoItem, outcome: PlayOutcome) -> None:
    if outcome == "completed":
        if not is_filler_item(item):
            append_history(HISTORY_FILE, item)
        return

    if outcome == "skipped":
        return

    if outcome == "previous":
        prev = pop_history_last_non_filler(HISTORY_FILE)
        q = load_queue(QUEUE_FILE)
        if prev:
            q = [prev, item] + q
        else:
            q = [item] + q
        save_queue(QUEUE_FILE, q)


def _handle_idle_transport_commands(queue: list) -> bool:
    """Коли нічого не відтворюється: обробити skip/prev з адмінки. Повертає True, якщо крок завершено."""
    cmd = (load_control().get("command") or "").strip().lower()
    if cmd == PlaybackCommand.SKIP.value:
        if queue:
            save_queue(QUEUE_FILE, queue[1:])
        clear_command()
        return True
    if cmd == PlaybackCommand.PREVIOUS.value:
        prev = pop_history_last_non_filler(HISTORY_FILE)
        if prev:
            q = load_queue(QUEUE_FILE)
            save_queue(QUEUE_FILE, [prev] + q)
        clear_command()
        return True
    return False


def playback_step() -> None:
    queue_service = QueueService()
    playback_service = PlaybackService()

    current_item = load_current_item(CURRENT_ITEM_FILE)
    queue = load_queue(QUEUE_FILE)
    queue = queue_service.dedupe_queue(queue)

    if current_item is None and _handle_idle_transport_commands(queue):
        return

    if current_item is not None:
        log_warn(
            f"Recovery playback detected: {current_item.title} ({current_item.video_id})"
        )
        try:
            outcome = playback_service.play(current_item)
        finally:
            save_current_item(CURRENT_ITEM_FILE, None)
        _apply_playback_outcome(current_item, outcome)
        return

    next_item, new_queue = queue_service.pop_next_item(queue)

    if next_item is None:
        log_play("Queue is empty -> using filler")
        next_item = playback_service.create_filler_item()
    else:
        save_queue(QUEUE_FILE, new_queue)

    save_current_item(CURRENT_ITEM_FILE, next_item)

    try:
        outcome = playback_service.play(next_item)
    finally:
        save_current_item(CURRENT_ITEM_FILE, None)

    _apply_playback_outcome(next_item, outcome)


def _start_admin_server() -> None:
    if os.environ.get("MEDIAHUB_NO_ADMIN", "").strip().lower() in ("1", "true", "yes"):
        return

    try:
        from admin_server import run_admin

        host = os.environ.get("MEDIAHUB_ADMIN_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = int(os.environ.get("MEDIAHUB_ADMIN_PORT", "8765"))
        thread = threading.Thread(
            target=lambda: run_admin(host=host, port=port),
            name="admin-server",
            daemon=True,
        )
        thread.start()
        log_warn(f"Admin UI: http://{host}:{port}/")
    except Exception as e:
        log_warn(f"Admin UI failed to start: {e}")


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    _start_admin_server()

    last_scan_time = 0.0
    scan_interval_seconds = POLL_INTERVAL_MINUTES * 60

    while True:
        now = time.time()

        if now - last_scan_time >= scan_interval_seconds:
            try:
                scan_for_new_videos()
            except Exception as e:
                log_blank()
                log_error(f"SCAN FAILED: {e}")
                log_blank()
                time.sleep(SCAN_ERROR_DELAY_SECONDS)
            finally:
                last_scan_time = now

        if is_paused():
            time.sleep(0.3)
            continue

        try:
            playback_step()
        except Exception as e:
            log_blank()
            log_error(f"PLAYBACK FAILED: {e}")
            log_blank()
            time.sleep(PLAYBACK_ERROR_DELAY_SECONDS)


if __name__ == "__main__":
    main()
