import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR, FILLER_URL, LOGO_FILE, STATE_DIR

SETTINGS_FILE = STATE_DIR / "settings.json"


@dataclass
class AppSettings:
    """Параметри, що можна змінювати з адмінки (файл state/settings.json)."""

    filler_url: str = FILLER_URL
    """Шлях до PNG для накладання (відносно кореня проєкту або абсолютний). Порожньо = config.LOGO_FILE."""
    logo_path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "AppSettings":
        return AppSettings(
            filler_url=str(data.get("filler_url") or FILLER_URL),
            logo_path=str(data.get("logo_path") or "").strip(),
        )


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> AppSettings:
    _ensure_state_dir()
    if not SETTINGS_FILE.is_file():
        return AppSettings()

    try:
        raw = SETTINGS_FILE.read_text(encoding="utf-8").strip()
        if not raw:
            return AppSettings()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return AppSettings()
        return AppSettings.from_dict(data)
    except (OSError, json.JSONDecodeError, TypeError, KeyError):
        return AppSettings()


def save_settings(settings: AppSettings) -> None:
    _ensure_state_dir()
    tmp = SETTINGS_FILE.with_suffix(".json.tmp")
    text = json.dumps(settings.to_dict(), ensure_ascii=False, indent=2)
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(SETTINGS_FILE)


def resolve_logo_path(settings: AppSettings) -> Optional[Path]:
    if settings.logo_path:
        p = Path(settings.logo_path)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p if p.is_file() else None
    return Path(LOGO_FILE) if Path(LOGO_FILE).is_file() else None


def merge_settings_patch(patch: dict[str, Any]) -> AppSettings:
    cur = load_settings()
    if "filler_url" in patch and patch["filler_url"] is not None:
        cur.filler_url = str(patch["filler_url"]).strip() or FILLER_URL
    if "logo_path" in patch and patch["logo_path"] is not None:
        cur.logo_path = str(patch["logo_path"]).strip()
    return cur
