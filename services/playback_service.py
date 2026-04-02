import subprocess
import time

from config import (
    FFPLAY_BIN,
    FFPLAY_HEIGHT,
    FFPLAY_WIDTH,
    FILLER_SECONDS,
    FILLER_TITLE,
    FILLER_URL,
    FILLER_VIDEO_ID,
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
            duration=FILLER_SECONDS,
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
        log_blank()
        log_play(
            f"START | channel={item.channel_title} | "
            f"title={item.title} | id={item.video_id}"
        )

        ytdlp_cmd = self.ytdlp.build_progressive_stream_cmd(item.url)
        ffplay_cmd = [
            FFPLAY_BIN,
            "-autoexit",
            "-window_title",
            item.title,
            "-x",
            str(FFPLAY_WIDTH),
            "-y",
            str(FFPLAY_HEIGHT),
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-i",
            "pipe:0",
        ]

        producer = subprocess.Popen(
            ytdlp_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            consumer = subprocess.Popen(
                ffplay_cmd,
                stdin=producer.stdout,
                stderr=subprocess.PIPE,
            )
        finally:
            if producer.stdout is not None:
                producer.stdout.close()

        consumer_stderr = b""
        producer_stderr = b""

        try:
            consumer_stderr = consumer.communicate()[1] or b""
        finally:
            producer_stderr = producer.communicate()[1] or b""

        consumer_rc = consumer.returncode
        producer_rc = producer.returncode

        if consumer_rc != 0:
            raise RuntimeError(
                f"ffplay failed for video_id={item.video_id}, return_code={consumer_rc}\n"
                f"{consumer_stderr.decode('utf-8', errors='ignore')[-1500:]}"
            )

        # Якщо ffplay дочекався кінця, а yt-dlp теж завершився нормально — ок.
        # Якщо yt-dlp впав, це вже помилка джерела.
        if producer_rc != 0:
            raise RuntimeError(
                f"yt-dlp stream failed for video_id={item.video_id}, return_code={producer_rc}\n"
                f"{producer_stderr.decode('utf-8', errors='ignore')[-1500:]}"
            )

        log_play(
            f"END   | channel={item.channel_title} | "
            f"title={item.title} | id={item.video_id}"
        )
        log_blank()

    def _play_filler(self) -> None:
        filler_seconds = FILLER_SECONDS

        log_blank()
        log_play(
            f"START | channel=System | title={FILLER_TITLE} | "
            f"id={FILLER_VIDEO_ID} | duration={filler_seconds}s"
        )

        cmd = [
            FFPLAY_BIN,
            "-autoexit",
            "-window_title",
            FILLER_TITLE,
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
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"ffplay filler failed, return_code={result.returncode}\n{result.stderr[-1500:]}"
            )

        log_play(f"END   | channel=System | title={FILLER_TITLE} | id={FILLER_VIDEO_ID}")
        log_blank()