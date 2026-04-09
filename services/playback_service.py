import subprocess
import threading
import time
from typing import Literal, Optional

from config import (
    FILLER_CHANNEL_URL,
    FILLER_SECONDS,
    FILLER_TITLE,
    FILLER_URL,
    FILLER_VIDEO_ID,
    TELEGRAM_STREAM_KEY_FILE,
    TEST_MODE,
    TEST_PLAYBACK_SECONDS,
    YT_DLP_BIN,
    get_x_rtmp_url,
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
from services.settings_service import AppSettings, load_settings, resolve_logo_path
from services.ytdlp_client import YtDlpClient
from utils.logger import log_blank, log_info, log_play, log_warn

PlayOutcome = Literal["completed", "skipped", "previous"]

_FILLER_CH_URL = FILLER_CHANNEL_URL.strip().lower()


def is_filler_item(item: VideoItem) -> bool:
    if item.video_id == FILLER_VIDEO_ID:
        return True
    return (item.channel_url or "").strip().lower() == _FILLER_CH_URL


class PlaybackService:
    def __init__(self) -> None:
        self.ytdlp = YtDlpClient(yt_dlp_bin=YT_DLP_BIN)
        self.ffmpeg = FFmpegService()

    def _effective_logo_path(self):
        return resolve_logo_path(load_settings())

    def _effective_logo_opacity(self) -> float:
        return max(0.0, min(1.0, float(load_settings().logo_opacity)))

    def _effective_logo_zoom(self) -> float:
        return max(0.05, min(8.0, float(load_settings().logo_zoom)))

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

    # ── Helpers ────────────────────────────────────────────────────

    def _get_telegram_rtmp_url(self, settings: Optional[AppSettings] = None) -> Optional[str]:
        s = settings if settings is not None else load_settings()
        server = s.telegram_server_url.strip().rstrip("/")
        if not server:
            return None
        key = ""
        if TELEGRAM_STREAM_KEY_FILE.is_file():
            try:
                key = TELEGRAM_STREAM_KEY_FILE.read_text(encoding="utf-8").strip().splitlines()[0].strip()
            except OSError:
                key = ""
        if not key:
            return None
        return f"{server}/{key}"

    def _collect_rtmp_urls(self) -> list[str]:
        settings = load_settings()
        urls: list[str] = []
        yt = get_youtube_rtmp_url()
        if yt:
            urls.append(yt)
        tg = self._get_telegram_rtmp_url(settings)
        if tg:
            urls.append(tg)
        x = get_x_rtmp_url(settings.x_stream_server_url)
        if x:
            urls.append(x)
        return urls

    def _require_rtmp_urls(self) -> list[str]:
        urls = self._collect_rtmp_urls()
        if not urls:
            raise RuntimeError(
                "No stream destinations configured. "
                "Set a YouTube stream key, Telegram server URL + stream key, "
                "and/or X stream key (with ingest URL if not default)."
            )
        return urls

    def _label_for_url(self, url: str) -> str:
        low = url.lower()
        if "youtube" in low or "rtmp://a.rtmp" in low:
            return "YouTube"
        if "rtmp.t.me" in low or "telegram" in low:
            return "Telegram"
        if "pscp.tv" in low or "periscope" in low:
            return "X"
        return url[:50]

    def _log_destinations(self, rtmp_urls: list[str]) -> None:
        labels = [self._label_for_url(u) for u in rtmp_urls]
        log_info(f"Destinations: {', '.join(labels)} ({len(rtmp_urls)} independent streams)")

    def _terminate_process(self, proc: Optional[subprocess.Popen], name: str) -> None:
        if proc is None or proc.poll() is not None:
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

    # ── Pump thread: split yt-dlp stdout to multiple ffmpeg stdin ──

    def _start_pump_thread(
        self,
        source_stdout,
        processors: list[subprocess.Popen],
    ) -> threading.Thread:
        """Read chunks from source and write to every processor's stdin.

        If one processor dies (BrokenPipeError), the others keep receiving data.
        """
        def pump():
            alive = list(processors)
            try:
                while True:
                    chunk = source_stdout.read(65536)
                    if not chunk:
                        break
                    dead = []
                    for proc in alive:
                        try:
                            proc.stdin.write(chunk)
                        except (OSError, BrokenPipeError, ValueError):
                            dead.append(proc)
                    for d in dead:
                        alive.remove(d)
                    if not alive:
                        break
            finally:
                for proc in processors:
                    try:
                        proc.stdin.close()
                    except (OSError, BrokenPipeError, ValueError):
                        pass

        t = threading.Thread(target=pump, daemon=True, name="stream-pump")
        t.start()
        return t

    # ── Interruptible wait for N processes ─────────────────────────

    def _interruptible_wait_multi(
        self,
        producer: Optional[subprocess.Popen],
        processors: list[subprocess.Popen],
        pump_thread: Optional[threading.Thread] = None,
    ) -> Optional[str]:
        """Wait for producer + all processors. Returns interrupt command or None."""
        all_pids = []
        if producer:
            all_pids.append(producer.pid)
        all_pids.extend(p.pid for p in processors)

        try:
            write_pids(*all_pids)

            while True:
                prod_done = producer is None or producer.poll() is not None
                all_ff_done = all(p.poll() is not None for p in processors)

                if prod_done and all_ff_done:
                    break

                cmd = self._poll_command()
                if cmd in (PlaybackCommand.SKIP, PlaybackCommand.PREVIOUS):
                    clear_command()
                    for proc in processors:
                        self._terminate_process(proc, "ffmpeg")
                    if producer:
                        self._terminate_process(producer, "yt-dlp")
                    return cmd

                time.sleep(0.35)

            if pump_thread:
                pump_thread.join(timeout=10)

            # Log per-destination errors (non-fatal — other destinations may have succeeded)
            for i, proc in enumerate(processors):
                if proc.returncode and proc.returncode != 0:
                    stderr = b""
                    try:
                        if proc.stderr:
                            stderr = proc.stderr.read() or b""
                    except Exception:
                        pass
                    log_warn(
                        f"ffmpeg[{i}] exited with code {proc.returncode}: "
                        f"{self._read_stderr_tail(stderr, 600)}"
                    )

            if producer and producer.returncode and producer.returncode != 0:
                stderr = b""
                try:
                    if producer.stderr:
                        stderr = producer.stderr.read() or b""
                except Exception:
                    pass
                raise RuntimeError(
                    f"yt-dlp failed with code {producer.returncode}: "
                    f"{self._read_stderr_tail(stderr, 600)}"
                )

            return None
        finally:
            clear_pids()

    # ── Fake / test playback ───────────────────────────────────────

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

    # ── Real video: yt-dlp → N independent ffmpeg processes ────────

    def _play_real_video(self, item: VideoItem) -> PlayOutcome:
        log_blank()
        log_play(
            f"START | channel={item.channel_title} | "
            f"title={item.title} | id={item.video_id}"
        )

        rtmp_urls = self._require_rtmp_urls()
        self._log_destinations(rtmp_urls)

        logo = self._effective_logo_path()
        if logo and self.ffmpeg.logo_available(logo):
            log_info(f"Logo overlay: ENABLED ({logo})")
        else:
            log_info("Logo overlay: DISABLED")

        ytdlp_cmd = self.ytdlp.build_progressive_stream_cmd(item.url)

        ffmpeg_cmds = []
        for url in rtmp_urls:
            ffmpeg_cmds.append(
                self.ffmpeg.build_video_pipeline(
                    rtmp_url=url,
                    source_is_pipe=True,
                    logo_file=logo,
                    logo_opacity=self._effective_logo_opacity(),
                    logo_zoom=self._effective_logo_zoom(),
                )
            )

        producer = None
        processors: list[subprocess.Popen] = []
        pump_thread = None

        try:
            producer = subprocess.Popen(
                ytdlp_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            for cmd in ffmpeg_cmds:
                proc = self.ffmpeg.spawn(
                    cmd,
                    stdin_pipe=subprocess.PIPE,
                    stdout_pipe=subprocess.DEVNULL,
                    stderr_pipe=subprocess.PIPE,
                )
                processors.append(proc)

            pump_thread = self._start_pump_thread(producer.stdout, processors)

            interrupt = self._interruptible_wait_multi(producer, processors, pump_thread)

            if interrupt == PlaybackCommand.PREVIOUS:
                log_play(f"PREV  | id={item.video_id}")
                log_blank()
                return "previous"

            if interrupt == PlaybackCommand.SKIP:
                log_play(f"SKIP  | id={item.video_id}")
                log_blank()
                return "skipped"

        except Exception:
            for proc in processors:
                self._terminate_process(proc, "ffmpeg")
            if producer:
                self._terminate_process(producer, "yt-dlp")
            clear_pids()
            raise

        log_play(
            f"END   | channel={item.channel_title} | "
            f"title={item.title} | id={item.video_id}"
        )
        log_blank()
        return "completed"

    # ── Filler: N independent ffmpeg processes (each generates its own) ──

    def _play_filler(self) -> PlayOutcome:
        filler_seconds = FILLER_SECONDS

        log_blank()
        log_play(
            f"START | channel=System | title={FILLER_TITLE} | "
            f"id={FILLER_VIDEO_ID} | duration={filler_seconds}s"
        )

        rtmp_urls = self._require_rtmp_urls()
        self._log_destinations(rtmp_urls)

        logo = self._effective_logo_path()
        if logo and self.ffmpeg.logo_available(logo):
            log_info(f"Logo overlay: ENABLED ({logo})")
        else:
            log_info("Logo overlay: DISABLED")

        processors: list[subprocess.Popen] = []

        try:
            for url in rtmp_urls:
                cmd = self.ffmpeg.build_filler_pipeline(
                    rtmp_url=url,
                    seconds=filler_seconds,
                    logo_file=logo,
                    logo_opacity=self._effective_logo_opacity(),
                    logo_zoom=self._effective_logo_zoom(),
                )
                proc = self.ffmpeg.spawn(
                    cmd,
                    stdin_pipe=None,
                    stdout_pipe=subprocess.DEVNULL,
                    stderr_pipe=subprocess.PIPE,
                )
                processors.append(proc)

            interrupt = self._interruptible_wait_multi(None, processors)

            if interrupt == PlaybackCommand.PREVIOUS:
                log_play(f"PREV  | id={FILLER_VIDEO_ID}")
                log_blank()
                return "previous"

            if interrupt == PlaybackCommand.SKIP:
                log_play(f"SKIP  | id={FILLER_VIDEO_ID}")
                log_blank()
                return "skipped"

        except Exception:
            for proc in processors:
                self._terminate_process(proc, "ffmpeg")
            clear_pids()
            raise

        log_play(f"END   | channel=System | title={FILLER_TITLE} | id={FILLER_VIDEO_ID}")
        log_blank()
        return "completed"
