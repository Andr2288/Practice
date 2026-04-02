from typing import List, Set

from services.models import VideoItem
from services.ytdlp_client import YtDlpClient


class ParserService:
    def __init__(self, ytdlp_client: YtDlpClient) -> None:
        self.ytdlp_client = ytdlp_client

    def scan_channels(
        self,
        channel_urls: List[str],
        seen_video_ids: Set[str],
        current_queue: List[VideoItem],
        limit_per_channel: int = 7,
    ) -> tuple[List[VideoItem], Set[str], List[VideoItem]]:
        """
        Повертає:
        1. список нових відео
        2. оновлений seen set
        3. оновлену чергу

        За ТЗ нові відео додаються на початок черги.
        """
        newly_found: List[VideoItem] = []
        updated_seen = set(seen_video_ids)

        for channel_url in channel_urls:
            videos = self.ytdlp_client.fetch_latest_videos(
                channel_url=channel_url,
                limit=limit_per_channel,
            )

            # Старіші/новіші можуть приходити в різному порядку.
            # Для MVP залишимо порядок як повернув yt-dlp.
            # У чергу кладемо тільки ті, яких ще не бачили.
            for video in videos:
                if video.video_id not in updated_seen:
                    newly_found.append(video)
                    updated_seen.add(video.video_id)

        # Нові відео мають бути на початку черги.
        # Щоб найсвіжіші були раніше, розвернемо newly_found.
        new_queue = list(reversed(newly_found)) + current_queue

        return newly_found, updated_seen, new_queue