import json
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from config import STATE_DIR

CONTROL_FILE = STATE_DIR / "playback_control.json"
PIDS_FILE = STATE_DIR / "playback_pids.json"


class PlaybackCommand(str, Enum):
    NONE = ""
    SKIP = "skip"
    PREVIOUS = "previous"


def _read_json(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_control() -> dict[str, Any]:
    data = _read_json(CONTROL_FILE)
    if not data:
        return {"paused": False, "command": PlaybackCommand.NONE.value}
    paused = bool(data.get("paused", False))
    cmd = str(data.get("command") or "").strip().lower()
    allowed = ("", PlaybackCommand.SKIP.value, PlaybackCommand.PREVIOUS.value)
    if cmd not in allowed:
        cmd = ""
    return {"paused": paused, "command": cmd}


def save_control(paused: Optional[bool] = None, command: Optional[str] = None) -> None:
    cur = load_control()
    if paused is not None:
        cur["paused"] = paused
    if command is not None:
        cur["command"] = command
    _atomic_write_json(CONTROL_FILE, cur)


def clear_command() -> None:
    save_control(command=PlaybackCommand.NONE.value)


def request_skip() -> None:
    save_control(command=PlaybackCommand.SKIP.value)


def request_previous() -> None:
    save_control(command=PlaybackCommand.PREVIOUS.value)


def read_command_value() -> str:
    return str(load_control().get("command") or "")


def is_paused() -> bool:
    return bool(load_control().get("paused"))


def write_pids(ffmpeg_pid: Optional[int], ytdlp_pid: Optional[int]) -> None:
    data = {}
    if ffmpeg_pid is not None:
        data["ffmpeg_pid"] = int(ffmpeg_pid)
    if ytdlp_pid is not None:
        data["ytdlp_pid"] = int(ytdlp_pid)
    if not data:
        _atomic_write_json(PIDS_FILE, {})
        return
    _atomic_write_json(PIDS_FILE, data)


def clear_pids() -> None:
    write_pids(None, None)


def load_pids() -> tuple[Optional[int], Optional[int]]:
    data = _read_json(PIDS_FILE)
    if not data:
        return None, None
    ff = data.get("ffmpeg_pid")
    yt = data.get("ytdlp_pid")
    return (int(ff) if ff is not None else None, int(yt) if yt is not None else None)


def _kill_pid(pid: int) -> None:
    import os
    import signal
    import subprocess
    import sys

    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception:
            pass


def kill_playback_processes() -> None:
    ff, yt = load_pids()
    for pid in (yt, ff):
        if pid is None:
            continue
        _kill_pid(int(pid))
    clear_pids()
