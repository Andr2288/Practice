from typing import List, Sequence, Set

from services.models import VideoItem
from services.queue_service import QueueService
from services.ytdlp_client import YtDlpClient
from utils.logger import log_warn


class ParserService:
    def __init__(self, ytdlp_client: YtDlpClient) -> None:
        self.ytdlp_client = ytdlp_client
        self.queue_service = QueueService()

    @staticmethod
    def _round_robin_take(rows: Sequence[List[VideoItem]], limit: int) -> List[VideoItem]:
        """Бере до `limit` елементів, по черзі з кожного рядка (справедливо між каналами)."""
        buckets = [list(r) for r in rows]
        out: List[VideoItem] = []
        while len(out) < limit:
            progressed = False
            for row in buckets:
                if len(out) >= limit:
                    break
                if row:
                    out.append(row.pop(0))
                    progressed = True
            if not progressed:
                break
        return out

    def scan_channels(
        self,
        channel_urls: List[str],
        seen_video_ids: Set[str],
        current_queue: List[VideoItem],
        limit_per_channel: int = 7,
        max_new_total: int = 7,
    ) -> tuple[List[VideoItem], Set[str], List[VideoItem]]:
        """
        Повертає:
        1. список нових відео (не більше max_new_total за один скан)
        2. оновлений seen set
        3. оновлену чергу

        Нові відео додаються в кінець черги. Між каналами кандидати змішуються round-robin.
        """
        updated_seen = set(seen_video_ids)
        queue_ids = {item.video_id for item in current_queue}

        per_channel: List[List[VideoItem]] = []

        for channel_url in channel_urls:
            try:
                videos = self.ytdlp_client.fetch_latest_videos(
                    channel_url=channel_url,
                    limit=limit_per_channel,
                )
            except Exception as e:
                err = str(e).strip()
                if len(err) > 800:
                    err = err[:800] + "…"
                log_warn(
                    f"Канал пропущено (перевірте посилання або доступність): {channel_url}\n{err}"
                )
                per_channel.append([])
                continue

            row: List[VideoItem] = []
            for video in videos:
                if video.video_id in updated_seen:
                    continue
                if video.video_id in queue_ids:
                    continue
                row.append(video)
            per_channel.append(row)

        cap = max(0, int(max_new_total))
        newly_found = self._round_robin_take(per_channel, cap)

        for video in newly_found:
            updated_seen.add(video.video_id)
            queue_ids.add(video.video_id)

        new_queue = current_queue + newly_found
        new_queue = self.queue_service.dedupe_queue(new_queue)

        return newly_found, updated_seen, new_queue