import subprocess
import time

from config import (
    FILLER_TITLE,
    FILLER_URL,
    FILLER_VIDEO_ID,
    FFPLAY_BIN,
    FFPLAY_HEIGHT,
    FFPLAY_WIDTH,
    TEST_MODE,
    TEST_PLAYBACK_SECONDS,
    YT_DLP_BIN,
)
from services.models import VideoItem
from services.ytdlp_client import YtDlpClient
from utils.logger import log_blank, log_play


class PlaybackService:
    def __init__(self) -> None:
        self.ytdlp = YtDlpClient(yt_dlp_bin=YT_DLP_BIN)

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
        if TEST_MODE:
            self._play_fake(item)
            return

        if item.video_id == FILLER_VIDEO_ID:
            self._play_filler()
            return

        self._play_real_video(item)

    def _play_fake(self, item: VideoItem) -> None:
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

    def _play_real_video(self, item: VideoItem) -> None:
        playback_url = self.ytdlp.resolve_playback_url(item.url)

        log_blank()
        log_play(
            f"START | channel={item.channel_title} | "
            f"title={item.title} | id={item.video_id}"
        )

        cmd = [
            FFPLAY_BIN,
            "-autoexit",
            "-window_title",
            item.title,
            "-x",
            str(FFPLAY_WIDTH),
            "-y",
            str(FFPLAY_HEIGHT),
            playback_url,
        ]

        result = subprocess.run(
            cmd,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"ffplay failed for video_id={item.video_id}, return code={result.returncode}"
            )

        log_play(
            f"END   | channel={item.channel_title} | "
            f"title={item.title} | id={item.video_id}"
        )
        log_blank()

    def _play_filler(self) -> None:
        filler_seconds = TEST_PLAYBACK_SECONDS

        log_blank()
        log_play(
            f"START | channel=System | title=FILLER_LOOP | "
            f"id=__FILLER__ | duration={filler_seconds}s"
        )

        cmd = [
            FFPLAY_BIN,
            "-autoexit",
            "-window_title",
            "FILLER_LOOP",
            "-x",
            str(FFPLAY_WIDTH),
            "-y",
            str(FFPLAY_HEIGHT),
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=1280x720:rate=25:duration={filler_seconds},format=yuv420p",
        ]

        result = subprocess.run(
            cmd,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(f"ffplay filler failed, return code={result.returncode}")

        log_play("END   | channel=System | title=FILLER_LOOP | id=__FILLER__")
        log_blank()