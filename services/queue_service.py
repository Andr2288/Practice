from typing import List

from services.models import VideoItem
from services.playback_service import is_filler_item


class QueueService:
    def dedupe_queue(self, queue: List[VideoItem]) -> List[VideoItem]:
        """Дублікати за video_id прибираються; filler можна ставити кілька разів підряд (один і той самий кліп)."""
        seen_ids = set()
        result: List[VideoItem] = []

        for item in queue:
            if is_filler_item(item):
                result.append(item)
                continue
            if item.video_id in seen_ids:
                continue
            seen_ids.add(item.video_id)
            result.append(item)

        return result