"""Cache for 'our videos' fetched from a YouTube channel.

Same idea as foreign channels in playback: fetch the latest N from the channel
when an insert is due. Results are kept in memory and on disk for admin display
and fallback if a fetch fails.
"""

import json
import threading
import time
from pathlib import Path
from typing import List

from config import OUR_VIDEOS_CACHE_FILE
from services.models import VideoItem
from services.ytdlp_client import YtDlpClient
from utils.logger import log_info, log_warn

_lock = threading.Lock()
_cached_videos: List[VideoItem] = []
_last_scan_ts: float = 0.0
_cached_channel_url: str = ""


def _load_from_disk(cache_file: Path) -> tuple[List[VideoItem], float, str]:
    if not cache_file.is_file():
        return [], 0.0, ""
    try:
        raw = cache_file.read_text(encoding="utf-8").strip()
        if not raw:
            return [], 0.0, ""
        data = json.loads(raw)
        ts = float(data.get("last_scan_ts", 0.0))
        ch = str(data.get("channel_url", ""))
        entries = data.get("videos", [])
        videos = [VideoItem.from_dict(e) for e in entries if isinstance(e, dict)]
        return videos, ts, ch
    except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
        return [], 0.0, ""


def _save_to_disk(cache_file: Path, videos: List[VideoItem], ts: float, channel_url: str) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "channel_url": channel_url,
        "last_scan_ts": ts,
        "videos": [v.to_dict() for v in videos],
    }
    tmp = cache_file.with_suffix(cache_file.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(cache_file)


def warm_cache_from_disk(cache_file: Path = OUR_VIDEOS_CACHE_FILE) -> None:
    """Load last saved list into memory (e.g. on startup) so admin shows something before the first fetch."""
    global _cached_videos, _last_scan_ts, _cached_channel_url
    with _lock:
        if not _cached_videos:
            _cached_videos, _last_scan_ts, _cached_channel_url = _load_from_disk(cache_file)


def fetch_our_videos_for_playback(
    ytdlp: YtDlpClient,
    channel_url: str,
    limit: int,
    cache_file: Path,
) -> List[VideoItem]:
    """Fetch latest videos from the channel (always). Updates cache and disk on success."""
    global _cached_videos, _last_scan_ts, _cached_channel_url

    if not channel_url:
        return []

    try:
        videos = ytdlp.fetch_latest_videos(channel_url, limit=limit)
    except Exception as e:
        log_warn(f"Our-videos scan failed ({channel_url}): {e}")
        with _lock:
            if not _cached_videos:
                _cached_videos, _last_scan_ts, _cached_channel_url = _load_from_disk(cache_file)
            return list(_cached_videos)

    with _lock:
        _cached_videos = list(videos)
        _last_scan_ts = time.time()
        _cached_channel_url = channel_url
        _save_to_disk(cache_file, _cached_videos, _last_scan_ts, channel_url)
        log_info(f"Our-videos refreshed: {len(_cached_videos)} videos from {channel_url}")
        return list(_cached_videos)


def peek_cached_videos() -> tuple[List[VideoItem], float, str]:
    """Non-blocking read of the current cache state (for admin status)."""
    with _lock:
        return list(_cached_videos), _last_scan_ts, _cached_channel_url


def invalidate_cache(cache_file: Path = OUR_VIDEOS_CACHE_FILE) -> None:
    """Clear memory cache and delete the on-disk snapshot (next fetch replaces it)."""
    global _cached_videos, _last_scan_ts, _cached_channel_url
    with _lock:
        _cached_videos = []
        _last_scan_ts = 0.0
        _cached_channel_url = ""
    try:
        if cache_file.is_file():
            cache_file.unlink()
    except OSError:
        pass
