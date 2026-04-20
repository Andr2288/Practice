import json
import time
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from config import CURRENT_ITEM_FILE, QUEUE_FILE, STATE_DIR
from services.storage import save_current_item, save_queue

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
    if not isinstance(data, dict):
        data = {}
    paused = bool(data.get("paused", False))
    broadcasting = bool(data.get("broadcasting", False))
    cmd = str(data.get("command") or "").strip().lower()
    allowed = ("", PlaybackCommand.SKIP.value, PlaybackCommand.PREVIOUS.value)
    if cmd not in allowed:
        cmd = ""
    out = dict(data)
    out["paused"] = paused
    out["command"] = cmd
    out["broadcasting"] = broadcasting
    return out


def save_control(
    paused: Optional[bool] = None,
    command: Optional[str] = None,
    broadcasting: Optional[bool] = None,
) -> None:
    cur = load_control()
    if paused is not None:
        cur["paused"] = paused
    if command is not None:
        cur["command"] = command
    if broadcasting is not None:
        cur["broadcasting"] = broadcasting
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


def is_broadcasting() -> bool:
    return bool(load_control().get("broadcasting"))


def start_broadcasting() -> None:
    """Новий сеанс ефіру: таймер з 0; попередня «заморожена» тривалість скидається."""
    cur = load_control()
    cur["broadcasting"] = True
    cur["command"] = PlaybackCommand.NONE.value
    cur["broadcast_segment_started_at"] = time.time()
    cur["broadcast_last_elapsed_sec"] = None
    _atomic_write_json(CONTROL_FILE, cur)


def stop_broadcasting() -> None:
    """Зупинка ефіру: зберігаємо тривалість сеансу, не обнуляємо її для відображення."""
    cur = load_control()
    started = cur.get("broadcast_segment_started_at")
    if started is not None:
        cur["broadcast_last_elapsed_sec"] = max(0.0, time.time() - float(started))
    cur["broadcasting"] = False
    cur["command"] = PlaybackCommand.NONE.value
    cur["broadcast_segment_started_at"] = None
    _atomic_write_json(CONTROL_FILE, cur)
    kill_playback_processes()
    save_queue(QUEUE_FILE, [])
    save_current_item(CURRENT_ITEM_FILE, None)


def write_pids(*pids: int) -> None:
    """Track active process PIDs (any number of ffmpeg + yt-dlp processes)."""
    valid = [int(p) for p in pids if p is not None]
    _atomic_write_json(PIDS_FILE, {"pids": valid})


def clear_pids() -> None:
    _atomic_write_json(PIDS_FILE, {"pids": []})


def load_pids() -> list[int]:
    data = _read_json(PIDS_FILE)
    if not data:
        return []
    if "pids" in data and isinstance(data["pids"], list):
        return [int(p) for p in data["pids"] if p is not None]
    result: list[int] = []
    if data.get("ffmpeg_pid") is not None:
        result.append(int(data["ffmpeg_pid"]))
    if data.get("ytdlp_pid") is not None:
        result.append(int(data["ytdlp_pid"]))
    return result


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
    for pid in load_pids():
        _kill_pid(pid)
    clear_pids()
