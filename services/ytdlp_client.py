import json
import subprocess
from typing import List, Optional

from services.models import VideoItem


class YtDlpClient:
    def __init__(self, yt_dlp_bin: str = "yt-dlp") -> None:
        self.yt_dlp_bin = yt_dlp_bin

    def fetch_latest_videos(self, channel_url: str, limit: int = 7) -> List[VideoItem]:
        cmd = [
            self.yt_dlp_bin,
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
                f"RAW OUTPUT:\n{result.stdout[:500]}\n"
            )

        entries = data.get("entries", [])
        channel_title = data.get("title")

        videos: List[VideoItem] = []

        for entry in entries:
            video_id = entry.get("id")
            title = entry.get("title") or "Untitled"
            url = entry.get("url") or video_id

            if not video_id:
                continue

            if url and not str(url).startswith("http"):
                url = f"https://www.youtube.com/watch?v={video_id}"

            videos.append(
                VideoItem(
                    video_id=video_id,
                    title=title,
                    url=url,
                    channel_url=channel_url,
                    channel_title=channel_title,
                    duration=entry.get("duration"),
                )
            )

        return videos

    def resolve_playback_url(self, video_page_url: str) -> str:
        """
        Для локального MVP намагаємось взяти ОДИН прямий URL потоку,
        щоб ffplay міг відкрити його без окремого злиття audio/video.

        Пріоритет:
        1. best progressive mp4/webm
        2. будь-який best single-file stream
        """
        format_selector = (
            "best[protocol!=m3u8][ext=mp4]/"
            "best[protocol!=m3u8][ext=webm]/"
            "best"
        )

        cmd = [
            self.yt_dlp_bin,
            "-f",
            format_selector,
            "-g",
            video_page_url,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to resolve playback URL for {video_page_url}\n"
                f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
            )

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]

        if not lines:
            raise RuntimeError(
                f"yt-dlp returned empty playback URL for {video_page_url}\n"
                f"stderr:\n{result.stderr}"
            )

        return lines[0]

    def resolve_title(self, video_page_url: str) -> Optional[str]:
        cmd = [
            self.yt_dlp_bin,
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