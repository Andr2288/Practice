import subprocess
from pathlib import Path
from typing import Optional

from config import (
    AUDIO_FILTER,
    ENABLE_LOGO_OVERLAY,
    FFMPEG_BIN,
    FILLER_BACKGROUND,
    FILLER_SECONDS,
    FILLER_TEXT,
    FILLER_TONE_FREQUENCY,
    LOGO_FILE,
    LOGO_OFFSET_X,
    LOGO_OFFSET_Y,
    OUTPUT_AUDIO_BITRATE,
    OUTPUT_AUDIO_CHANNELS,
    OUTPUT_AUDIO_SAMPLE_RATE,
    OUTPUT_BUFSIZE,
    OUTPUT_FPS,
    OUTPUT_GOP,
    OUTPUT_HEIGHT,
    OUTPUT_MAXRATE,
    OUTPUT_VIDEO_BITRATE,
    OUTPUT_WIDTH,
)


class FFmpegService:
    def __init__(self, ffmpeg_bin: str = FFMPEG_BIN) -> None:
        self.ffmpeg_bin = ffmpeg_bin

    def logo_available(self, logo_file: Optional[Path] = None) -> bool:
        path = Path(logo_file) if logo_file is not None else Path(LOGO_FILE)
        return ENABLE_LOGO_OVERLAY and path.is_file()

    def _logo_path(self, logo_file: Optional[Path]) -> Optional[Path]:
        if logo_file is not None and Path(logo_file).is_file():
            return Path(logo_file)
        if ENABLE_LOGO_OVERLAY and Path(LOGO_FILE).is_file():
            return Path(LOGO_FILE)
        return None

    def _video_base_filter(self) -> str:
        return (
            f"scale=w={OUTPUT_WIDTH}:h={OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
            f"fps={OUTPUT_FPS},"
            f"format=yuv420p"
        )

    def _audio_filter(self) -> str:
        return AUDIO_FILTER

    def build_video_pipeline(
        self,
        rtmp_url: str,
        source_is_pipe: bool = True,
        logo_file: Optional[Path] = None,
    ) -> list[str]:
        """
        Вхід:
          - stdin (pipe:0) від yt-dlp
        Вихід:
          - FLV на YouTube Live (RTMP)

        Опція -re тримає темп 1× відносно реального часу (важливо для live на YouTube).
        """
        cmd = [
            self.ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
        ]

        if source_is_pipe:
            cmd += ["-re", "-i", "pipe:0"]
        else:
            raise ValueError("Only pipe input is supported in build_video_pipeline().")

        logo_path = self._logo_path(logo_file)
        if logo_path is not None:
            cmd += ["-loop", "1", "-i", str(logo_path)]
            filter_complex = (
                f"[0:v]{self._video_base_filter()}[base];"
                f"[base][1:v]overlay=W-w-{LOGO_OFFSET_X}:{LOGO_OFFSET_Y}:format=auto[vout]"
            )
            cmd += [
                "-filter_complex",
                filter_complex,
                "-map",
                "[vout]",
                "-map",
                "0:a:0?",
            ]
        else:
            cmd += [
                "-vf",
                self._video_base_filter(),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
            ]

        cmd += [
            "-af",
            self._audio_filter(),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-tune",
            "zerolatency",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(OUTPUT_FPS),
            "-g",
            str(OUTPUT_GOP),
            "-b:v",
            OUTPUT_VIDEO_BITRATE,
            "-maxrate",
            OUTPUT_MAXRATE,
            "-bufsize",
            OUTPUT_BUFSIZE,
            "-c:a",
            "aac",
            "-b:a",
            OUTPUT_AUDIO_BITRATE,
            "-ar",
            str(OUTPUT_AUDIO_SAMPLE_RATE),
            "-ac",
            str(OUTPUT_AUDIO_CHANNELS),
            "-shortest",
            "-flvflags",
            "no_duration_filesize",
            "-f",
            "flv",
            rtmp_url,
        ]

        return cmd

    def build_filler_pipeline(
        self,
        rtmp_url: str,
        seconds: Optional[int] = None,
        logo_file: Optional[Path] = None,
    ) -> list[str]:
        duration = int(seconds or FILLER_SECONDS)

        video_src = (
            f"color=c={FILLER_BACKGROUND}:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}:r={OUTPUT_FPS}:d={duration},"
            f"drawtext=text='{FILLER_TEXT}':"
            f"fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2,"
            f"format=yuv420p"
        )
        audio_src = (
            f"sine=frequency={FILLER_TONE_FREQUENCY}:sample_rate={OUTPUT_AUDIO_SAMPLE_RATE}:duration={duration}"
        )

        cmd = [
            self.ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-re",
            "-f",
            "lavfi",
            "-i",
            video_src,
            "-re",
            "-f",
            "lavfi",
            "-i",
            audio_src,
        ]

        logo_path = self._logo_path(logo_file)
        if logo_path is not None:
            cmd += ["-loop", "1", "-i", str(logo_path)]
            filter_complex = (
                f"[0:v][2:v]overlay=W-w-{LOGO_OFFSET_X}:{LOGO_OFFSET_Y}:format=auto[vout]"
            )
            cmd += [
                "-filter_complex",
                filter_complex,
                "-map",
                "[vout]",
                "-map",
                "1:a:0",
            ]
        else:
            cmd += [
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
            ]

        cmd += [
            "-af",
            self._audio_filter(),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-tune",
            "zerolatency",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(OUTPUT_FPS),
            "-g",
            str(OUTPUT_GOP),
            "-b:v",
            OUTPUT_VIDEO_BITRATE,
            "-maxrate",
            OUTPUT_MAXRATE,
            "-bufsize",
            OUTPUT_BUFSIZE,
            "-c:a",
            "aac",
            "-b:a",
            OUTPUT_AUDIO_BITRATE,
            "-ar",
            str(OUTPUT_AUDIO_SAMPLE_RATE),
            "-ac",
            str(OUTPUT_AUDIO_CHANNELS),
            "-shortest",
            "-flvflags",
            "no_duration_filesize",
            "-f",
            "flv",
            rtmp_url,
        ]

        return cmd

    def spawn(
        self,
        cmd: list[str],
        stdin_pipe=None,
        stdout_pipe=subprocess.PIPE,
        stderr_pipe=subprocess.PIPE,
    ) -> subprocess.Popen:
        return subprocess.Popen(
            cmd,
            stdin=stdin_pipe,
            stdout=stdout_pipe,
            stderr=stderr_pipe,
        )