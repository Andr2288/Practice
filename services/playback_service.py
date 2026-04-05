import subprocess
import time
from typing import Literal, Optional

from config import (
    FILLER_CHANNEL_URL,
    FILLER_SECONDS,
    FILLER_TITLE,
    FILLER_URL,
    FILLER_VIDEO_ID,
    TEST_MODE,
    TEST_PLAYBACK_SECONDS,
    YT_DLP_BIN,
    get_youtube_rtmp_url,
)
from services.ffmpeg_service import FFmpegService
from services.models import VideoItem
from services.runtime_control import (
    PlaybackCommand,
    clear_command,
    clear_pids,
    read_command_value,
    write_pids,
)
from services.settings_service import load_settings, resolve_logo_path
from services.ytdlp_client import YtDlpClient
from utils.logger import log_blank, log_info, log_play

PlayOutcome = Literal["completed", "skipped", "previous"]

_FILLER_CH_URL = FILLER_CHANNEL_URL.strip().lower()


def is_filler_item(item: VideoItem) -> bool:
    """Вбудований filler або кліп з налаштувань — не в історію для «попереднє»."""
    if item.video_id == FILLER_VIDEO_ID:
        return True
    return (item.channel_url or "").strip().lower() == _FILLER_CH_URL


class PlaybackService:
    def __init__(self) -> None:
        self.ytdlp = YtDlpClient(yt_dlp_bin=YT_DLP_BIN)
        self.ffmpeg = FFmpegService()

    def _effective_logo_path(self):
        return resolve_logo_path(load_settings())

    def _builtin_filler_item(self) -> VideoItem:
        return VideoItem(
            video_id=FILLER_VIDEO_ID,
            title=FILLER_TITLE,
            url=FILLER_URL,
            channel_url=FILLER_CHANNEL_URL,
            channel_title="System",
            duration=FILLER_SECONDS,
        )

    def create_filler_item(self) -> VideoItem:
        settings = load_settings()
        raw = (settings.filler_url or "").strip()
        if not raw:
            return self._builtin_filler_item()

        if raw.startswith("http://") or raw.startswith("https://"):
            try:
                item = self.ytdlp.fetch_video_by_url(raw)
                item.channel_url = FILLER_CHANNEL_URL
                item.channel_title = item.channel_title or "System"
                return item
            except Exception:
                log_info("Filler URL недоступний — вбудований filler")
                return self._builtin_filler_item()

        return self._builtin_filler_item()

    def get_playback_duration(self, item: VideoItem) -> int:
        if TEST_MODE:
            return TEST_PLAYBACK_SECONDS

        if item.duration is not None and item.duration > 0:
            return int(item.duration)

        return 30

    def play(self, item: VideoItem) -> PlayOutcome:
        c = read_command_value()
        if c == PlaybackCommand.SKIP:
            clear_command()
            return "skipped"
        if c == PlaybackCommand.PREVIOUS:
            clear_command()
            return "previous"

        if TEST_MODE:
            return self._play_fake(item)

        if item.video_id == FILLER_VIDEO_ID:
            return self._play_filler()

        return self._play_real_video(item)

    def _poll_command(self) -> Optional[str]:
        c = read_command_value()
        if c in (PlaybackCommand.SKIP, PlaybackCommand.PREVIOUS):
            return c
        return None

    def _play_fake(self, item: VideoItem) -> PlayOutcome:
        seconds = self.get_playback_duration(item)
        end = time.monotonic() + seconds

        log_blank()
        log_play(
            f"START | channel={item.channel_title} | "
            f"title={item.title} | id={item.video_id} | duration={seconds}s"
        )

        while time.monotonic() < end:
            cmd = self._poll_command()
            if cmd == PlaybackCommand.SKIP:
                clear_command()
                log_play(f"SKIP  | id={item.video_id}")
                log_blank()
                return "skipped"
            if cmd == PlaybackCommand.PREVIOUS:
                clear_command()
                log_play(f"PREV  | id={item.video_id}")
                log_blank()
                return "previous"
            time.sleep(0.25)

        log_play(
            f"END   | channel={item.channel_title} | "
            f"title={item.title} | id={item.video_id}"
        )
        log_blank()
        return "completed"

    def _require_youtube_rtmp_url(self) -> str:
        url = get_youtube_rtmp_url()
        if not url:
            raise RuntimeError(
                "YouTube stream is not configured. Set YOUTUBE_RTMP_URL or YOUTUBE_STREAM_KEY "
                "in the environment, or put the stream key in youtube_stream_key.txt (see .gitignore)."
            )
        return url

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

    def _interruptible_wait_two(
        self,
        producer: subprocess.Popen,
        processor: subprocess.Popen,
    ) -> tuple[bytes, bytes, int, int, Optional[str]]:
        """Очікує завершення yt-dlp + ffmpeg, або перериває за SKIP/PREVIOUS."""
        try:
            write_pids(processor.pid, producer.pid)
            while True:
                p_done = producer.poll() is not None
                f_done = processor.poll() is not None
                if p_done and f_done:
                    break
                cmd = self._poll_command()
                if cmd in (PlaybackCommand.SKIP, PlaybackCommand.PREVIOUS):
                    clear_command()
                    self._terminate_process(processor, "ffmpeg")
                    self._terminate_process(producer, "yt-dlp")
                    proc_err = b""
                    prod_err = b""
                    try:
                        if processor.stderr:
                            proc_err = processor.stderr.read() or b""
                    except Exception:
                        pass
                    try:
                        if producer.stderr:
                            prod_err = producer.stderr.read() or b""
                    except Exception:
                        pass
                    return proc_err, prod_err, -1, -1, cmd
                time.sleep(0.35)

            proc_err = processor.communicate()[1] or b""
            prod_err = producer.communicate()[1] or b""
            return proc_err, prod_err, processor.returncode or 0, producer.returncode or 0, None
        finally:
            clear_pids()

    def _interruptible_wait_one(self, processor: subprocess.Popen) -> tuple[bytes, int, Optional[str]]:
        try:
            write_pids(processor.pid, None)
            while True:
                if processor.poll() is not None:
                    break
                cmd = self._poll_command()
                if cmd in (PlaybackCommand.SKIP, PlaybackCommand.PREVIOUS):
                    clear_command()
                    self._terminate_process(processor, "ffmpeg")
                    proc_err = b""
                    try:
                        if processor.stderr:
                            proc_err = processor.stderr.read() or b""
                    except Exception:
                        pass
                    return proc_err, -1, cmd
                time.sleep(0.35)
            proc_err = processor.communicate()[1] or b""
            return proc_err, processor.returncode or 0, None
        finally:
            clear_pids()

    def _play_real_video(self, item: VideoItem) -> PlayOutcome:
        log_blank()
        log_play(
            f"START | channel={item.channel_title} | "
            f"title={item.title} | id={item.video_id}"
        )

        rtmp_url = self._require_youtube_rtmp_url()
        log_info("Output: YouTube Live (RTMP)")

        logo = self._effective_logo_path()
        if logo and self.ffmpeg.logo_available(logo):
            log_info(f"Logo overlay: ENABLED ({logo})")
        else:
            log_info("Logo overlay: DISABLED")

        ytdlp_cmd = self.ytdlp.build_progressive_stream_cmd(item.url)
        ffmpeg_cmd = self.ffmpeg.build_video_pipeline(
            rtmp_url=rtmp_url,
            source_is_pipe=True,
            logo_file=logo,
        )

        producer = None
        processor = None

        try:
            producer = subprocess.Popen(
                ytdlp_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            processor = self.ffmpeg.spawn(
                ffmpeg_cmd,
                stdin_pipe=producer.stdout,
                stdout_pipe=subprocess.DEVNULL,
                stderr_pipe=subprocess.PIPE,
            )

            processor_stderr, producer_stderr, prc, yrc, interrupt = self._interruptible_wait_two(
                producer, processor
            )

            if interrupt == PlaybackCommand.PREVIOUS:
                log_play(f"PREV  | id={item.video_id}")
                log_blank()
                return "previous"

            if interrupt == PlaybackCommand.SKIP:
                log_play(f"SKIP  | id={item.video_id}")
                log_blank()
                return "skipped"

            if prc != 0:
                raise RuntimeError(
                    f"ffmpeg pipeline failed for video_id={item.video_id}, return_code={prc}\n"
                    f"{self._read_stderr_tail(processor_stderr)}"
                )

            if yrc != 0:
                raise RuntimeError(
                    f"yt-dlp stream failed for video_id={item.video_id}, return_code={yrc}\n"
                    f"{self._read_stderr_tail(producer_stderr)}"
                )

        except Exception:
            self._terminate_process(processor, "ffmpeg")
            self._terminate_process(producer, "yt-dlp")
            clear_pids()
            raise

        log_play(
            f"END   | channel={item.channel_title} | "
            f"title={item.title} | id={item.video_id}"
        )
        log_blank()
        return "completed"

    def _play_filler(self) -> PlayOutcome:
        filler_seconds = FILLER_SECONDS

        log_blank()
        log_play(
            f"START | channel=System | title={FILLER_TITLE} | "
            f"id={FILLER_VIDEO_ID} | duration={filler_seconds}s"
        )

        rtmp_url = self._require_youtube_rtmp_url()
        log_info("Output: YouTube Live (RTMP)")

        logo = self._effective_logo_path()
        if logo and self.ffmpeg.logo_available(logo):
            log_info(f"Logo overlay: ENABLED ({logo})")
        else:
            log_info("Logo overlay: DISABLED")

        ffmpeg_cmd = self.ffmpeg.build_filler_pipeline(
            rtmp_url=rtmp_url,
            seconds=filler_seconds,
            logo_file=logo,
        )

        processor = None

        try:
            processor = self.ffmpeg.spawn(
                ffmpeg_cmd,
                stdin_pipe=None,
                stdout_pipe=subprocess.DEVNULL,
                stderr_pipe=subprocess.PIPE,
            )

            processor_stderr, processor_rc, interrupt = self._interruptible_wait_one(processor)

            if interrupt == PlaybackCommand.PREVIOUS:
                log_play(f"PREV  | id={FILLER_VIDEO_ID}")
                log_blank()
                return "previous"

            if interrupt == PlaybackCommand.SKIP:
                log_play(f"SKIP  | id={FILLER_VIDEO_ID}")
                log_blank()
                return "skipped"

            if processor_rc != 0:
                raise RuntimeError(
                    f"ffmpeg filler pipeline failed, return_code={processor_rc}\n"
                    f"{self._read_stderr_tail(processor_stderr)}"
                )

        except Exception:
            self._terminate_process(processor, "ffmpeg")
            clear_pids()
            raise

        log_play(f"END   | channel=System | title={FILLER_TITLE} | id={FILLER_VIDEO_ID}")
        log_blank()
        return "completed"
