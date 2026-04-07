import os
import random
import threading
import time

from config import (
    BATCH_STATE_FILE,
    CHANNELS_FILE,
    CURRENT_ITEM_FILE,
    HISTORY_FILE,
    LAST_VIDEOS_LIMIT,
    MAX_CHANNEL_RETRIES,
    OUR_VIDEOS_CACHE_FILE,
    OUR_VIDEOS_LIMIT,
    PLAYBACK_ERROR_DELAY_SECONDS,
    SEEN_VIDEOS_FILE,
    STATE_DIR,
    YT_DLP_BIN,
)
from services.batch_service import (
    load_batch_state,
    save_batch_state,
    start_new_cycle,
)
from services.channel_scan_service import read_channels_list
from services.models import VideoItem
from services.our_videos_cache import get_our_videos
from services.playback_service import PlaybackService, is_filler_item
from services.runtime_control import (
    PlaybackCommand,
    clear_command,
    is_paused,
    load_control,
)
from services.settings_service import load_settings
from services.storage import (
    append_history,
    load_current_item,
    load_seen_videos,
    save_current_item,
    save_seen_videos,
)
from services.ytdlp_client import YtDlpClient
from utils.logger import log_blank, log_block, log_error, log_info, log_play, log_warn


def _play_and_record(
    playback: PlaybackService,
    item: VideoItem,
    record_history: bool = True,
) -> str:
    """Play a video item, persist current_item for crash recovery, return outcome."""
    save_current_item(CURRENT_ITEM_FILE, item)
    try:
        outcome = playback.play(item)
    finally:
        save_current_item(CURRENT_ITEM_FILE, None)

    if outcome == "completed" and record_history and not is_filler_item(item):
        append_history(HISTORY_FILE, item)
        seen = load_seen_videos(SEEN_VIDEOS_FILE)
        seen.add(item.video_id)
        save_seen_videos(SEEN_VIDEOS_FILE, seen)

    return outcome


def _pick_and_play_our_video(
    playback: PlaybackService,
    our_videos: list[VideoItem],
) -> str:
    """Pick a random 'our' video from the cached channel list, play it, return outcome."""
    if not our_videos:
        item = playback.create_filler_item()
    else:
        item = random.choice(our_videos)

    return _play_and_record(playback, item, record_history=False)


def _handle_paused_commands() -> None:
    """Drain skip/previous commands that arrive while paused."""
    cmd = (load_control().get("command") or "").strip().lower()
    if cmd in (PlaybackCommand.SKIP.value, PlaybackCommand.PREVIOUS.value):
        clear_command()


def playback_cycle_step(
    playback: PlaybackService,
    ytdlp: YtDlpClient,
) -> None:
    """One step of the batch cycle: play one channel video + one 'our' video."""
    channels = read_channels_list(CHANNELS_FILE)

    settings = load_settings()
    our_videos = get_our_videos(
        ytdlp=ytdlp,
        channel_url=settings.our_channel_url,
        limit=OUR_VIDEOS_LIMIT,
        scan_interval_seconds=settings.our_videos_scan_interval_minutes * 60,
        cache_file=OUR_VIDEOS_CACHE_FILE,
    )

    if not channels:
        log_warn("No channels configured — playing filler")
        filler = playback.create_filler_item()
        _play_and_record(playback, filler, record_history=False)
        return

    state = load_batch_state(BATCH_STATE_FILE)

    if state is None or state.is_cycle_complete():
        state = start_new_cycle(channels)
        save_batch_state(BATCH_STATE_FILE, state)
        log_block(f"NEW CYCLE: {len(state.shuffled_channels)} channels (shuffled)")

    # Recovery: channel video played, but our video didn't finish before crash
    if state.pending_our_video:
        log_info("Recovery: playing pending 'our video'")
        _pick_and_play_our_video(playback, our_videos)
        state.pending_our_video = False
        state.current_index += 1
        save_batch_state(BATCH_STATE_FILE, state)
        return

    channel_url = state.current_channel()
    if channel_url is None:
        return

    idx = state.current_index
    total = len(state.shuffled_channels)
    log_info(f"Channel {idx + 1}/{total}: {channel_url}")

    try:
        videos = ytdlp.fetch_latest_videos(channel_url, limit=LAST_VIDEOS_LIMIT)
    except Exception as e:
        err = str(e).strip()
        if len(err) > 400:
            err = err[:400] + "…"
        log_warn(f"Channel skipped (fetch error): {channel_url}\n{err}")
        state.current_index += 1
        save_batch_state(BATCH_STATE_FILE, state)
        return

    if not videos:
        log_warn(f"Channel skipped (0 videos): {channel_url}")
        state.current_index += 1
        save_batch_state(BATCH_STATE_FILE, state)
        return

    seen = load_seen_videos(SEEN_VIDEOS_FILE)
    unseen = [v for v in videos if v.video_id not in seen]
    pool = unseen if unseen else videos
    video = random.choice(pool)
    log_play(
        f"Selected: {video.title} ({video.video_id}) "
        f"from {len(pool)} candidates ({len(videos) - len(pool)} seen) "
        f"on {video.channel_title or channel_url}"
    )

    # 1) Play channel video
    try:
        _play_and_record(playback, video, record_history=True)
    except Exception as e:
        state.channel_fail_count += 1
        err = str(e).strip()
        if len(err) > 400:
            err = err[:400] + "…"

        if state.channel_fail_count >= MAX_CHANNEL_RETRIES:
            log_warn(
                f"Channel skipped after {state.channel_fail_count} failures: "
                f"{channel_url}\n{err}"
            )
            state.channel_fail_count = 0
            state.current_index += 1
        else:
            log_warn(
                f"Playback failed ({state.channel_fail_count}/{MAX_CHANNEL_RETRIES}), "
                f"will retry channel: {channel_url}\n{err}"
            )

        save_batch_state(BATCH_STATE_FILE, state)
        time.sleep(PLAYBACK_ERROR_DELAY_SECONDS)
        return

    state.channel_fail_count = 0

    # Mark pending so crash recovery plays our video if we restart mid-pair
    state.pending_our_video = True
    save_batch_state(BATCH_STATE_FILE, state)

    # 2) Play our video
    try:
        _pick_and_play_our_video(playback, our_videos)
    except Exception as e:
        log_warn(f"Our video playback failed, continuing: {e}")

    # Advance to next channel
    state.pending_our_video = False
    state.current_index += 1
    save_batch_state(BATCH_STATE_FILE, state)


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

    playback = PlaybackService()
    ytdlp = YtDlpClient(yt_dlp_bin=YT_DLP_BIN)

    # Crash recovery: replay interrupted video
    current = load_current_item(CURRENT_ITEM_FILE)
    if current is not None:
        log_warn(f"Recovery: replaying {current.title} ({current.video_id})")
        _play_and_record(playback, current)

    while True:
        if is_paused():
            _handle_paused_commands()
            time.sleep(0.3)
            continue

        try:
            playback_cycle_step(playback, ytdlp)
        except Exception as e:
            log_blank()
            log_error(f"PLAYBACK FAILED: {e}")
            log_blank()
            time.sleep(PLAYBACK_ERROR_DELAY_SECONDS)


if __name__ == "__main__":
    main()
