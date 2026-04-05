from typing import List, Optional

from services.models import VideoItem
from services.playback_service import is_filler_item


class QueueService:
    def get_next_item(self, queue: List[VideoItem]) -> Optional[VideoItem]:
        if not queue:
            return None
        return queue[0]

    def pop_next_item(self, queue: List[VideoItem]) -> tuple[Optional[VideoItem], List[VideoItem]]:
        if not queue:
            return None, []

        item = queue[0]
        new_queue = queue[1:]
        return item, new_queue

    def has_items(self, queue: List[VideoItem]) -> bool:
        return len(queue) > 0

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