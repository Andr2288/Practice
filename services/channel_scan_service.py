"""Робота зі списком каналів у channels.txt."""
from pathlib import Path

def _dedupe_channel_urls(urls: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        s = u.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def read_channels_list(file_path: Path) -> list[str]:
    """Як load_channels, але без винятку якщо файлу ще немає (порожній список)."""
    if not file_path.exists():
        return []
    with file_path.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    return _dedupe_channel_urls(lines)


def save_channels_list(file_path: Path, urls: list[str]) -> None:
    """Записує channels.txt: одне посилання на рядок, без дублікатів, порядок зберігається."""
    normalized = _dedupe_channel_urls([u if isinstance(u, str) else "" for u in urls])
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("\n".join(normalized) + ("\n" if normalized else ""), encoding="utf-8")
