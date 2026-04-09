import json
import subprocess
from typing import List, Optional

from config import YT_DLP_PROGRESSIVE_FORMAT
from services.models import VideoItem


class YtDlpClient:
    def __init__(self, yt_dlp_bin: str = "yt-dlp") -> None:
        self.yt_dlp_bin = yt_dlp_bin

    def fetch_latest_videos(self, channel_url: str, limit: int = 7) -> List[VideoItem]:
        cmd = [
            self.yt_dlp_bin,
            "--extractor-retries",
            "0",
            "--flat-playlist",
            "--dump-single-json",
            "--playlist-end",
            str(limit),
            channel_url,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"\n[yt-dlp ERROR]\n"
                f"Channel: {channel_url}\n"
                f"Return code: {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}\n"
            )

        if not result.stdout.strip():
            raise RuntimeError(
                f"\n[yt-dlp EMPTY OUTPUT]\n"
                f"Channel: {channel_url}\n"
                f"STDERR:\n{result.stderr}\n"
            )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"\n[yt-dlp INVALID JSON]\n"
                f"Channel: {channel_url}\n"
                f"RAW OUTPUT:\n{result.stdout[:1000]}\n"
            )

        entries = data.get("entries", [])
        channel_title = data.get("title")

        videos: List[VideoItem] = []

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            video_id = entry.get("id")
            title = entry.get("title") or "Untitled"
            url = entry.get("url") or video_id

            if not video_id:
                continue

            if url and not str(url).startswith("http"):
                url = f"https://www.youtube.com/watch?v={video_id}"

            dur = entry.get("duration")
            if dur is not None:
                try:
                    dur = int(dur)
                except (TypeError, ValueError):
                    dur = None

            videos.append(
                VideoItem(
                    video_id=str(video_id),
                    title=str(title),
                    url=str(url),
                    channel_url=channel_url,
                    channel_title=channel_title,
                    duration=dur,
                )
            )

        return videos

    def build_progressive_stream_cmd(self, video_page_url: str) -> list[str]:
        return [
            self.yt_dlp_bin,
            "-f",
            YT_DLP_PROGRESSIVE_FORMAT,
            "-o",
            "-",
            "--no-part",
            "--quiet",
            video_page_url,
        ]

    def resolve_title(self, video_page_url: str) -> Optional[str]:
        cmd = [
            self.yt_dlp_bin,
            "--extractor-retries",
            "0",
            "--print",
            "%(title)s",
            video_page_url,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            return None

        title = result.stdout.strip()
        return title or None

    def fetch_video_by_url(self, page_url: str) -> VideoItem:
        """Метадані одного відео за посиланням (watch, youtu.be, shorts)."""
        cmd = [
            self.yt_dlp_bin,
            "--extractor-retries",
            "0",
            "--dump-json",
            "--no-playlist",
            page_url,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"yt-dlp не зміг прочитати відео: {err[:800]}")

        raw = result.stdout.strip()
        if not raw:
            raise RuntimeError("yt-dlp повернув порожній вивід")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Невалідний JSON від yt-dlp: {e}") from e

        if not isinstance(data, dict):
            raise RuntimeError("Неочікуваний формат від yt-dlp")

        video_id = data.get("id")
        title = data.get("title") or "Untitled"
        if not video_id:
            raise RuntimeError("Не вдалося визначити id відео")

        url = data.get("webpage_url") or data.get("url") or page_url
        if url and not str(url).startswith("http"):
            url = f"https://www.youtube.com/watch?v={video_id}"

        channel_url = data.get("channel_url") or data.get("uploader_url") or ""
        channel_title = data.get("channel") or data.get("uploader")

        duration = data.get("duration")
        if duration is not None:
            duration = int(duration)

        return VideoItem(
            video_id=str(video_id),
            title=str(title),
            url=str(url),
            channel_url=str(channel_url or "https://www.youtube.com/"),
            channel_title=str(channel_title) if channel_title else None,
            duration=duration,
        )