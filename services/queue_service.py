from typing import List

from services.models import VideoItem


class QueueService:
    def dedupe_queue(self, queue: List[VideoItem]) -> List[VideoItem]:
        """Дублікати за video_id прибираються."""
        seen_ids = set()
        result: List[VideoItem] = []

        for item in queue:
            if item.video_id in seen_ids:
                continue
            seen_ids.add(item.video_id)
            result.append(item)

        return result