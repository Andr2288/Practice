import json
import subprocess
from typing import List

from services.models import VideoItem


class YtDlpClient:
    def __init__(self, yt_dlp_bin: str = "yt-dlp") -> None:
        self.yt_dlp_bin = yt_dlp_bin

    def fetch_latest_videos(self, channel_url: str, limit: int = 7) -> List[VideoItem]:
        cmd = [
            "python",
            "-m",
            "yt_dlp",
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