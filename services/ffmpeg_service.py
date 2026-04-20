import subprocess
from pathlib import Path
from typing import Optional

from config import (
    AUDIO_FILTER,
    ENABLE_LOGO_OVERLAY,
    FFMPEG_BIN,
    LOGO_FILE,
    LOGO_FIT_MAX_H,
    LOGO_FIT_MAX_W,
    LOGO_OFFSET_X,
    LOGO_OFFSET_Y,
    LOGO_OPACITY,
    LOGO_ZOOM,
    NVENC_PRESET,
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
    VIDEO_ENCODER,
    X264_PRESET,
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

    @staticmethod
    def _logo_preprocess_filter(
        input_pad: str,
        opacity: float,
        zoom: float,
        out_label: str = "lg",
    ) -> str:
        o = max(0.0, min(1.0, float(opacity)))
        z = max(0.05, min(8.0, float(zoom)))
        inp = f"[{input_pad}]"
        parts: list[str] = [
            "format=rgba",
            f"scale=w={LOGO_FIT_MAX_W}:h={LOGO_FIT_MAX_H}:force_original_aspect_ratio=decrease",
        ]
        z_str = format(z, ".6f").rstrip("0").rstrip(".") or "0"
        parts.append(
            f"scale=w=iw*{z_str}:h=-2:flags=lanczos+accurate_rnd+full_chroma_int"
        )
        if o <= 0.001:
            parts.append("geq=r='0':g='0':b='0':a='0'")
        elif o < 0.999:
            o_str = format(o, ".6f").rstrip("0").rstrip(".") or "0"
            parts.append(
                f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*{o_str}'"
            )
        return f"{inp}{','.join(parts)}[{out_label}]"

    def _encoding_args(self) -> list[str]:
        v_common = [
            "-pix_fmt", "yuv420p",
            "-r", str(OUTPUT_FPS),
            "-g", str(OUTPUT_GOP),
            "-b:v", OUTPUT_VIDEO_BITRATE,
            "-maxrate", OUTPUT_MAXRATE,
            "-bufsize", OUTPUT_BUFSIZE,
        ]
        a_common = [
            "-c:a", "aac",
            "-b:a", OUTPUT_AUDIO_BITRATE,
            "-ar", str(OUTPUT_AUDIO_SAMPLE_RATE),
            "-ac", str(OUTPUT_AUDIO_CHANNELS),
        ]
        enc = (VIDEO_ENCODER or "libx264").strip().lower()
        if enc == "h264_nvenc":
            return [
                "-c:v",
                "h264_nvenc",
                "-preset",
                NVENC_PRESET,
                "-tune",
                "ll",
                "-rc",
                "cbr",
                "-bf",
                "0",
                *v_common,
                *a_common,
            ]
        return [
            "-c:v",
            "libx264",
            "-preset",
            X264_PRESET,
            "-tune",
            "zerolatency",
            *v_common,
            *a_common,
        ]

    def _flv_output_args(self, rtmp_url: str) -> list[str]:
        return [
            "-shortest",
            "-flvflags", "no_duration_filesize",
            "-muxdelay", "0",
            "-muxpreload", "0",
            "-f", "flv",
            rtmp_url,
        ]

    def build_video_pipeline(
        self,
        rtmp_url: str,
        source_is_pipe: bool = True,
        logo_file: Optional[Path] = None,
        logo_opacity: float = LOGO_OPACITY,
        logo_zoom: float = LOGO_ZOOM,
        re_input: bool = False,
    ) -> list[str]:
        if not source_is_pipe:
            raise ValueError("Only pipe input is supported in build_video_pipeline().")

        # Pipe від yt-dlp: за замовчуванням без -re (читаємо як є); з re_input=True — -re (темп відео).
        cmd = [
            self.ffmpeg_bin,
            "-hide_banner",
            "-loglevel", "error",
        ]
        if re_input:
            cmd.append("-re")
        cmd += ["-i", "pipe:0"]

        logo_path = self._logo_path(logo_file)
        if logo_path is not None:
            cmd += ["-loop", "1", "-i", str(logo_path)]
            lg = self._logo_preprocess_filter("1:v", logo_opacity, logo_zoom)
            filter_complex = (
                f"[0:v]{self._video_base_filter()}[base];"
                f"{lg};"
                f"[base][lg]overlay=W-w-{LOGO_OFFSET_X}:{LOGO_OFFSET_Y}:format=auto[vout]"
            )
            cmd += [
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-map", "0:a:0?",
            ]
        else:
            cmd += [
                "-vf", self._video_base_filter(),
                "-map", "0:v:0",
                "-map", "0:a:0?",
            ]

        cmd += ["-af", self._audio_filter()]
        cmd += self._encoding_args()
        cmd += self._flv_output_args(rtmp_url)

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
