import subprocess
import time
from typing import Optional

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
from services.ffmpeg_service import FFmpegService
from services.models import VideoItem
from services.ytdlp_client import YtDlpClient
from utils.logger import log_blank, log_info, log_play


class PlaybackService:
    def __init__(self) -> None:
        self.ytdlp = YtDlpClient(yt_dlp_bin=YT_DLP_BIN)
        self.ffmpeg = FFmpegService()

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

    def _build_ffplay_preview_cmd(self, window_title: str) -> list[str]:
        return [
            FFPLAY_BIN,
            "-autoexit",
            "-window_title",
            window_title,
            "-x",
            str(FFPLAY_WIDTH),
            "-y",
            str(FFPLAY_HEIGHT),
            "-i",
            "pipe:0",
        ]

    def _terminate_process(self, proc: Optional[subprocess.Popen], name: str) -> None:
        if proc is None:
            return

        if proc.poll() is not None:
            return

        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _read_stderr_tail(self, stderr_data: bytes, max_chars: int = 1500) -> str:
        return stderr_data.decode("utf-8", errors="ignore")[-max_chars:]

    def _play_real_video(self, item: VideoItem) -> None:
        log_blank()
        log_play(
            f"START | channel={item.channel_title} | "
            f"title={item.title} | id={item.video_id}"
        )

        if self.ffmpeg.logo_available():
            log_info("Logo overlay: ENABLED")
        else:
            log_info("Logo overlay: DISABLED (assets/logo.png not found)")

        ytdlp_cmd = self.ytdlp.build_progressive_stream_cmd(item.url)
        ffmpeg_cmd = self.ffmpeg.build_video_pipeline(source_is_pipe=True)
        ffplay_cmd = self._build_ffplay_preview_cmd(item.title)

        producer = None
        processor = None
        consumer = None

        try:
            # Запускаємо yt-dlp
            producer = subprocess.Popen(
                ytdlp_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Запускаємо ffmpeg з stdin від producer
            processor = self.ffmpeg.spawn(
                ffmpeg_cmd,
                stdin_pipe=producer.stdout,
                stdout_pipe=subprocess.PIPE,
                stderr_pipe=subprocess.PIPE,
            )

            # Запускаємо ffplay з stdin від processor
            consumer = subprocess.Popen(
                ffplay_cmd,
                stdin=processor.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            # Чекаємо завершення consumer (ffplay)
            consumer_stderr = consumer.communicate()[1] or b""
            consumer_rc = consumer.returncode

            # Чекаємо завершення processor (ffmpeg)
            processor_stderr = processor.communicate()[1] or b""
            processor_rc = processor.returncode

            # Чекаємо завершення producer (yt-dlp)
            producer_stderr = producer.communicate()[1] or b""
            producer_rc = producer.returncode

            # Перевірка помилок
            if consumer_rc != 0:
                raise RuntimeError(
                    f"ffplay failed for video_id={item.video_id}, return_code={consumer_rc}\n"
                    f"{self._read_stderr_tail(consumer_stderr)}"
                )

            if processor_rc != 0:
                raise RuntimeError(
                    f"ffmpeg pipeline failed for video_id={item.video_id}, return_code={processor_rc}\n"
                    f"{self._read_stderr_tail(processor_stderr)}"
                )

            if producer_rc != 0:
                raise RuntimeError(
                    f"yt-dlp stream failed for video_id={item.video_id}, return_code={producer_rc}\n"
                    f"{self._read_stderr_tail(producer_stderr)}"
                )

        except Exception as e:
            # У разі помилки завершуємо всі процеси
            self._terminate_process(consumer, "ffplay")
            self._terminate_process(processor, "ffmpeg")
            self._terminate_process(producer, "yt-dlp")
            raise

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

        if self.ffmpeg.logo_available():
            log_info("Logo overlay: ENABLED")
        else:
            log_info("Logo overlay: DISABLED (assets/logo.png not found)")

        ffmpeg_cmd = self.ffmpeg.build_filler_pipeline(seconds=filler_seconds)
        ffplay_cmd = self._build_ffplay_preview_cmd(FILLER_TITLE)

        processor = None
        consumer = None

        try:
            # Запускаємо ffmpeg
            processor = self.ffmpeg.spawn(
                ffmpeg_cmd,
                stdin_pipe=None,
                stdout_pipe=subprocess.PIPE,
                stderr_pipe=subprocess.PIPE,
            )

            # Запускаємо ffplay
            consumer = subprocess.Popen(
                ffplay_cmd,
                stdin=processor.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            # Чекаємо завершення consumer
            consumer_stderr = consumer.communicate()[1] or b""
            consumer_rc = consumer.returncode

            # Чекаємо завершення processor
            processor_stderr = processor.communicate()[1] or b""
            processor_rc = processor.returncode

            # Перевірка помилок
            if consumer_rc != 0:
                raise RuntimeError(
                    f"ffplay filler failed, return_code={consumer_rc}\n"
                    f"{self._read_stderr_tail(consumer_stderr)}"
                )

            if processor_rc != 0:
                raise RuntimeError(
                    f"ffmpeg filler pipeline failed, return_code={processor_rc}\n"
                    f"{self._read_stderr_tail(processor_stderr)}"
                )

        except Exception as e:
            # У разі помилки завершуємо всі процеси
            self._terminate_process(consumer, "ffplay")
            self._terminate_process(processor, "ffmpeg")
            raise

        log_play(f"END   | channel=System | title={FILLER_TITLE} | id={FILLER_VIDEO_ID}")
        log_blank()