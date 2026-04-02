import time
from pathlib import Path

from config import (
    CHANNELS_FILE,
    LAST_VIDEOS_LIMIT,
    POLL_INTERVAL_MINUTES,
    QUEUE_FILE,
    SEEN_VIDEOS_FILE,
    STATE_DIR,
    YT_DLP_BIN,
)
from services.parser_service import ParserService
from services.storage import (
    load_queue,
    load_seen_videos,
    save_queue,
    save_seen_videos,
)
from services.ytdlp_client import YtDlpClient


def load_channels(file_path: Path) -> list[str]:
    if not file_path.exists():
        raise FileNotFoundError(
            f"Channels file not found: {file_path}. Create channels.txt first."
        )

    with file_path.open("r", encoding="utf-8") as f:
        channels = [line.strip() for line in f if line.strip()]

    return channels


def run_once() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    channels = load_channels(CHANNELS_FILE)
    seen = load_seen_videos(SEEN_VIDEOS_FILE)
    queue = load_queue(QUEUE_FILE)

    ytdlp = YtDlpClient(yt_dlp_bin=YT_DLP_BIN)
    parser = ParserService(ytdlp_client=ytdlp)

    print(f"[INFO] Loaded channels: {len(channels)}")
    print(f"[INFO] Seen videos: {len(seen)}")
    print(f"[INFO] Queue length before scan: {len(queue)}")

    new_videos, updated_seen, updated_queue = parser.scan_channels(
        channel_urls=channels,
        seen_video_ids=seen,
        current_queue=queue,
        limit_per_channel=LAST_VIDEOS_LIMIT,
    )

    save_seen_videos(SEEN_VIDEOS_FILE, updated_seen)
    save_queue(QUEUE_FILE, updated_queue)

    print(f"[INFO] New videos found: {len(new_videos)}")
    for idx, video in enumerate(new_videos, start=1):
        print(
            f"  {idx}. [{video.channel_title or 'Unknown channel'}] "
            f"{video.title} ({video.video_id})"
        )

    print(f"[INFO] Queue length after scan: {len(updated_queue)}")


def main() -> None:
    # Для першої перевірки запускаємо одразу.
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"[ERROR] {e}")

        sleep_seconds = POLL_INTERVAL_MINUTES * 60
        print(f"[INFO] Sleeping for {POLL_INTERVAL_MINUTES} minutes...")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()