from typing import List, Set

from services.models import VideoItem
from services.queue_service import QueueService
from services.ytdlp_client import YtDlpClient


class ParserService:
    def __init__(self, ytdlp_client: YtDlpClient) -> None:
        self.ytdlp_client = ytdlp_client
        self.queue_service = QueueService()

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

        За ТЗ нові відео додаються на початок черги без переривання поточного відео.
        """
        newly_found: List[VideoItem] = []
        updated_seen = set(seen_video_ids)

        # Щоб не дублювати те, що вже стоїть у черзі
        queue_ids = {item.video_id for item in current_queue}

        for channel_url in channel_urls:
            videos = self.ytdlp_client.fetch_latest_videos(
                channel_url=channel_url,
                limit=limit_per_channel,
            )

            for video in videos:
                if video.video_id in updated_seen:
                    continue
                if video.video_id in queue_ids:
                    continue

                newly_found.append(video)
                updated_seen.add(video.video_id)
                queue_ids.add(video.video_id)

        # Нові відео пріоритетні: додаємо на початок.
        # reverse() лишає відносний порядок свіжості більш природним для flat-playlist.
        new_queue = list(reversed(newly_found)) + current_queue
        new_queue = self.queue_service.dedupe_queue(new_queue)

        return newly_found, updated_seen, new_queue