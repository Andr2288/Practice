import json
from pathlib import Path
from typing import List, Optional, Set

from services.models import VideoItem


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path):
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return None
            return json.loads(content)
    except (json.JSONDecodeError, ValueError, OSError):
        return None


def load_seen_videos(path: Path) -> Set[str]:
    data = _read_json(path)

    if not isinstance(data, list):
        return set()

    return {str(x) for x in data if str(x).strip()}


def save_seen_videos(path: Path, seen: Set[str]) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f, ensure_ascii=False, indent=2)


def load_queue(path: Path) -> List[VideoItem]:
    data = _read_json(path)

    if not isinstance(data, list):
        return []

    queue: List[VideoItem] = []

    for item in data:
        if not isinstance(item, dict):
            continue
        if "video_id" not in item:
            continue
        try:
            queue.append(VideoItem.from_dict(item))
        except Exception:
            continue

    return queue


def save_queue(path: Path, queue: List[VideoItem]) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump([item.to_dict() for item in queue], f, ensure_ascii=False, indent=2)


def load_current_item(path: Path) -> Optional[VideoItem]:
    data = _read_json(path)

    if not isinstance(data, dict):
        return None

    if "video_id" not in data:
        return None

    try:
        return VideoItem.from_dict(data)
    except Exception:
        return None


def save_current_item(path: Path, item: Optional[VideoItem]) -> None:
    ensure_parent_dir(path)

    with path.open("w", encoding="utf-8") as f:
        if item is None:
            json.dump({}, f, ensure_ascii=False, indent=2)
        else:
            json.dump(item.to_dict(), f, ensure_ascii=False, indent=2)