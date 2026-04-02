import time

from config import (
    FILLER_TITLE,
    FILLER_URL,
    FILLER_VIDEO_ID,
    TEST_MODE,
    TEST_PLAYBACK_SECONDS,
)
from services.models import VideoItem
from utils.logger import log_play, log_blank


class PlaybackService:
    def create_filler_item(self) -> VideoItem:
        return VideoItem(
            video_id=FILLER_VIDEO_ID,
            title=FILLER_TITLE,
            url=FILLER_URL,
            channel_url="local://filler",
            channel_title="System",
            duration=None,
        )

    def get_playback_duration(self, item: VideoItem) -> int:
        if TEST_MODE:
            return TEST_PLAYBACK_SECONDS

        if item.duration is not None and item.duration > 0:
            return int(item.duration)

        return 30

    def play(self, item: VideoItem) -> None:
        seconds = self.get_playback_duration(item)

        log_blank()
        log_play(
            f"START | channel={item.channel_title} | "
            f"title={item.title} | id={item.video_id} | duration={seconds}s"
        )

        time.sleep(seconds)

        log_play(
            f"END   | channel={item.channel_title} | "
            f"title={item.title} | id={item.video_id}"
        )
        log_blank()