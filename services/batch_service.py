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
    channel_fail_count: int = 0
    our_video_index: int = 0
    # Чужі ролики підряд після останнього «нашого»; після відтворення нашого скидається в apply.
    foreign_since_our: int = 0

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
            channel_fail_count=int(data.get("channel_fail_count", 0)),
            our_video_index=int(data.get("our_video_index", 0)),
            foreign_since_our=int(data.get("foreign_since_our", 0)),
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


def reset_foreign_since_our_for_new_broadcast(path: Path) -> None:
    """Скидає foreign_since_our на старті нового сеансу ефіру.

    Інакше лічильник з попереднього сеансу лишається у batch_state.json:
    наприклад при foreign_since_our==2 перший спланований чужий ролик
    «добиває» ліміт до N і наше відео потрапляє в чергу одразу другим.
    """
    st = load_batch_state(path)
    if st is None:
        return
    st.foreign_since_our = 0
    save_batch_state(path, st)


def start_new_cycle(
    channels: List[str],
    prev_our_video_index: int = 0,
    prev_foreign_since_our: int = 0,
) -> BatchState:
    """Shuffle channels and create a fresh batch state for a new cycle.

    our_video_index is carried over from the previous cycle so sequential
    playback of 'our videos' continues where it left off.
    foreign_since_our carries the running count toward the next our-video slot.
    """
    shuffled = list(channels)
    random.shuffle(shuffled)
    return BatchState(
        shuffled_channels=shuffled,
        current_index=0,
        our_video_index=prev_our_video_index,
        foreign_since_our=prev_foreign_since_our,
    )
