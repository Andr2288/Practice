"""Batch cycle management: round-robin through shuffled channels with our-video interleaving."""

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class BatchState:
    shuffled_channels: List[str] = field(default_factory=list)
    current_index: int = 0
    pending_our_video: bool = False
    channel_fail_count: int = 0

    def is_cycle_complete(self) -> bool:
        return self.current_index >= len(self.shuffled_channels)

    def current_channel(self) -> Optional[str]:
        if self.is_cycle_complete():
            return None
        return self.shuffled_channels[self.current_index]

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "BatchState":
        return BatchState(
            shuffled_channels=data.get("shuffled_channels", []),
            current_index=int(data.get("current_index", 0)),
            pending_our_video=bool(data.get("pending_our_video", False)),
            channel_fail_count=int(data.get("channel_fail_count", 0)),
        )


def load_batch_state(path: Path) -> Optional[BatchState]:
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        data = json.loads(raw)
        if not isinstance(data, dict) or "shuffled_channels" not in data:
            return None
        return BatchState.from_dict(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def save_batch_state(path: Path, state: BatchState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def start_new_cycle(channels: List[str]) -> BatchState:
    """Shuffle channels and create a fresh batch state for a new cycle."""
    shuffled = list(channels)
    random.shuffle(shuffled)
    return BatchState(shuffled_channels=shuffled, current_index=0, pending_our_video=False)


