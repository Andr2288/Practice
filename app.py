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
    OUR_VIDEO_EVERY_N_CHANNELS,
    OUR_VIDEOS_CACHE_FILE,
    OUR_VIDEOS_LIMIT,
    PLAYBACK_ERROR_DELAY_SECONDS,
    SEEN_VIDEOS_FILE,
    STATE_DIR,
    YT_DLP_BIN,
)
from services.batch_service import (
    BatchState,
    load_batch_state,
    save_batch_state,
    start_new_cycle,
)
from services.channel_scan_service import read_channels_list
from services.models import VideoItem
from services.our_videos_cache import fetch_our_videos_for_playback, warm_cache_from_disk
from services.playback_service import PlaybackService, is_filler_item
from services.runtime_control import (
    is_broadcasting,
)
from services.settings_service import load_settings
from services.storage import (
    append_history,
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


def _play_our_video_sequential(
    playback: PlaybackService,
    our_videos: list[VideoItem],
    state: BatchState,
) -> str:
    """Play the next 'our video' in order (cyclic). Advances state.our_video_index."""
    if not our_videos:
        item = playback.create_filler_item()
    else:
        idx = state.our_video_index % len(our_videos)
        item = our_videos[idx]
        state.our_video_index = idx + 1
        log_play(
            f"Our video [{idx + 1}/{len(our_videos)}]: {item.title} ({item.video_id})"
        )

    return _play_and_record(playback, item, record_history=False)


def playback_cycle_step(
    playback: PlaybackService,
    ytdlp: YtDlpClient,
) -> None:
    """One step of the batch cycle.

    Pattern: Channel → Channel → Channel → Our video → Channel → … (every N channels).
    Our videos: fetch latest N from our channel before each insert (like foreign channels);
    playback order is sequential, cycling back to the start.
    """
    if not is_broadcasting():
        return

    channels = read_channels_list(CHANNELS_FILE)

    settings = load_settings()

    if not channels:
        log_warn("No channels configured — playing filler")
        filler = playback.create_filler_item()
        _play_and_record(playback, filler, record_history=False)
        return

    state = load_batch_state(BATCH_STATE_FILE)

    if state is None or state.is_cycle_complete():
        prev_our_idx = state.our_video_index if state else 0
        state = start_new_cycle(
            channels,
            prev_our_video_index=prev_our_idx,
        )
        save_batch_state(BATCH_STATE_FILE, state)
        log_block(f"NEW CYCLE: {len(state.shuffled_channels)} channels (shuffled)")

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
        outcome = _play_and_record(playback, video, record_history=True)
    except Exception as e:
        err = str(e).strip()
        if len(err) > 400:
            err = err[:400] + "…"
        seen.add(video.video_id)
        save_seen_videos(SEEN_VIDEOS_FILE, seen)
        log_warn(
            f"Playback failed — video marked seen, channel skipped: "
            f"{video.video_id} | {channel_url}\n{err}"
        )
        state.channel_fail_count = 0
        state.current_index += 1
        save_batch_state(BATCH_STATE_FILE, state)
        return

    state.channel_fail_count = 0
    state.current_index += 1

    # 2) Every N channels — play our video (sequentially); fresh fetch like foreign channels
    if state.current_index % OUR_VIDEO_EVERY_N_CHANNELS == 0:
        our_videos = fetch_our_videos_for_playback(
            ytdlp=ytdlp,
            channel_url=settings.our_channel_url,
            limit=OUR_VIDEOS_LIMIT,
            cache_file=OUR_VIDEOS_CACHE_FILE,
        )
        if our_videos:
            our_outcome = "skipped"
            try:
                our_outcome = _play_our_video_sequential(playback, our_videos, state)
            except Exception as e:
                log_warn(f"Our video playback failed, continuing: {e}")

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
            try:
                playback_cycle_step(playback, ytdlp)
            except Exception as e:
                if not is_broadcasting():
                    break
                log_blank()
                log_error(f"PLAYBACK FAILED: {e}")
                log_blank()
                time.sleep(PLAYBACK_ERROR_DELAY_SECONDS)

        log_block("BROADCAST STOPPED")


if __name__ == "__main__":
    main()
