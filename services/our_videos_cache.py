"""Cache for 'our videos' fetched from a YouTube channel.

Periodically scans the configured channel and keeps the N latest videos
in memory + on disk (for crash recovery).
"""

import json
import threading
import time
from pathlib import Path
from typing import List, Optional

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


def get_our_videos(
    ytdlp: YtDlpClient,
    channel_url: str,
    limit: int,
    scan_interval_seconds: float,
    cache_file: Path,
) -> List[VideoItem]:
    """Return cached video list, refreshing from the channel when stale."""
    global _cached_videos, _last_scan_ts, _cached_channel_url

    if not channel_url:
        return []

    with _lock:
        now = time.time()

        if not _cached_videos:
            _cached_videos, _last_scan_ts, _cached_channel_url = _load_from_disk(cache_file)

        channel_changed = channel_url != _cached_channel_url
        stale = (now - _last_scan_ts) >= scan_interval_seconds

        if _cached_videos and not channel_changed and not stale:
            return list(_cached_videos)

    try:
        videos = ytdlp.fetch_latest_videos(channel_url, limit=limit)
    except Exception as e:
        log_warn(f"Our-videos scan failed ({channel_url}): {e}")
        with _lock:
            return list(_cached_videos)

    with _lock:
        if videos:
            _cached_videos = videos
            _last_scan_ts = time.time()
            _cached_channel_url = channel_url
            _save_to_disk(cache_file, videos, _last_scan_ts, channel_url)
            log_info(
                f"Our-videos refreshed: {len(videos)} videos from {channel_url}"
            )
        return list(_cached_videos)


def peek_cached_videos() -> tuple[List[VideoItem], float, str]:
    """Non-blocking read of the current cache state (for admin status)."""
    with _lock:
        return list(_cached_videos), _last_scan_ts, _cached_channel_url


def invalidate_cache() -> None:
    """Force re-scan on the next call to get_our_videos."""
    global _cached_videos, _last_scan_ts, _cached_channel_url
    with _lock:
        _cached_videos = []
        _last_scan_ts = 0.0
        _cached_channel_url = ""
