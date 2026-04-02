import json
from pathlib import Path
from typing import List, Optional, Set

from services.models import VideoItem


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_seen_videos(path: Path) -> Set[str]:
    if not path.exists():
        return set()

    try:
        with path.open("r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return set()
            data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return set()

    if not isinstance(data, list):
        return set()

    return set(str(x) for x in data)


def save_seen_videos(path: Path, seen: Set[str]) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f, ensure_ascii=False, indent=2)


def load_queue(path: Path) -> List[VideoItem]:
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return []

    if not isinstance(data, list):
        return []

    return [VideoItem.from_dict(item) for item in data]


def save_queue(path: Path, queue: List[VideoItem]) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump([item.to_dict() for item in queue], f, ensure_ascii=False, indent=2)


def load_current_item(path: Path) -> Optional[VideoItem]:
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return None
            data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    # 🔥 КЛЮЧОВИЙ ФІКС
    if "video_id" not in data:
        return None

    return VideoItem.from_dict(data)


def save_current_item(path: Path, item: Optional[VideoItem]) -> None:
    ensure_parent_dir(path)

    with path.open("w", encoding="utf-8") as f:
        if item is None:
            json.dump({}, f, ensure_ascii=False, indent=2)
        else:
            json.dump(item.to_dict(), f, ensure_ascii=False, indent=2)