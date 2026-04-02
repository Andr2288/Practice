from typing import List, Optional

from services.models import VideoItem


class QueueService:
    def get_next_item(self, queue: List[VideoItem]) -> Optional[VideoItem]:
        if not queue:
            return None
        return queue[0]

    def pop_next_item(self, queue: List[VideoItem]) -> tuple[Optional[VideoItem], List[VideoItem]]:
        if not queue:
            return None, queue

        item = queue[0]
        new_queue = queue[1:]
        return item, new_queue

    def has_items(self, queue: List[VideoItem]) -> bool:
        return len(queue) > 0