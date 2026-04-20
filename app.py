from __future__ import annotations

import os
import threading
import time

from config import (
    CHANNELS_FILE,
    CURRENT_ITEM_FILE,
    HISTORY_FILE,
    OUR_VIDEOS_CACHE_FILE,
    PLAYBACK_ERROR_DELAY_SECONDS,
    QUEUE_BATCH_SIZE,
    QUEUE_FILE,
    SEEN_VIDEOS_FILE,
    STATE_DIR,
    YT_DLP_BIN,
)
from services.channel_scan_service import read_channels_list
from services.models import VideoItem
from services.our_videos_cache import warm_cache_from_disk
from services.playback_schedule import (
    apply_auto_batch_state_after_play,
    refill_automated_queue_if_empty,
)
from services.playback_service import PlaybackService
from services.runtime_control import is_broadcasting
from services.settings_service import load_settings
from services.storage import (
    append_history,
    load_seen_videos,
    pop_queue_head,
    save_current_item,
    save_seen_videos,
)
from services.ytdlp_client import YtDlpClient
from utils.logger import log_blank, log_block, log_error, log_warn


def _play_and_record(
    playback: PlaybackService,
    item: VideoItem,
    record_history: bool = True,
) -> str:
    save_current_item(CURRENT_ITEM_FILE, item)
    try:
        outcome = playback.play(item)
    finally:
        save_current_item(CURRENT_ITEM_FILE, None)

    if outcome == "completed" and record_history:
        append_history(HISTORY_FILE, item)
        seen = load_seen_videos(SEEN_VIDEOS_FILE)
        seen.add(item.video_id)
        save_seen_videos(SEEN_VIDEOS_FILE, seen)

    return outcome


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
    warm_cache_from_disk(OUR_VIDEOS_CACHE_FILE)

    _start_admin_server()

    playback = PlaybackService()
    ytdlp = YtDlpClient(yt_dlp_bin=YT_DLP_BIN)

    log_block("MEDIAHUB READY — waiting for broadcast start via admin panel")

    while True:
        if not is_broadcasting():
            time.sleep(0.5)
            continue

        log_block("BROADCAST STARTED")

        while is_broadcasting():
            item: VideoItem | None = None
            try:
                channels = read_channels_list(CHANNELS_FILE)
                settings = load_settings()
                refill_automated_queue_if_empty(
                    ytdlp, settings, channels, QUEUE_BATCH_SIZE
                )
                item = pop_queue_head(QUEUE_FILE)
                if item is None:
                    time.sleep(1)
                    continue

                record_history = item.source != "auto_our"
                _play_and_record(playback, item, record_history=record_history)
                apply_auto_batch_state_after_play(item, had_exception=False)

            except Exception as e:
                if not is_broadcasting():
                    break
                if item is not None:
                    src = item.source or ""
                    if src == "auto_foreign":
                        seen = load_seen_videos(SEEN_VIDEOS_FILE)
                        seen.add(item.video_id)
                        save_seen_videos(SEEN_VIDEOS_FILE, seen)
                    apply_auto_batch_state_after_play(item, had_exception=True)
                err = str(e).strip()
                if len(err) > 400:
                    err = err[:400] + "…"
                log_blank()
                log_error(f"PLAYBACK FAILED: {err}")
                log_blank()
                time.sleep(PLAYBACK_ERROR_DELAY_SECONDS)

        log_block("BROADCAST STOPPED")


if __name__ == "__main__":
    main()
