import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR, LOGO_FILE, LOGO_OPACITY, LOGO_ZOOM, STATE_DIR

SETTINGS_FILE = STATE_DIR / "settings.json"


@dataclass
class AppSettings:
    """Параметри, що можна змінювати з адмінки (файл state/settings.json)."""

    # Порожньо → вбудований lavfi-filler; інакше URL (https://...) для свого кліпу.
    filler_url: str = ""
    """Шлях до PNG для накладання (відносно кореня проєкту або абсолютний). Порожньо = config.LOGO_FILE."""
    logo_path: str = ""
    """Множник альфа-каналу логотипу (0…1). У JSON відсутній ключ → config.LOGO_OPACITY."""
    logo_opacity: float = 1.0
    """Множник після підгонки PNG у рамку кадру; 1 = базовий розмір. У JSON немає ключа → config.LOGO_ZOOM."""
    logo_zoom: float = 1.0
    # Telegram RTMP server URL (e.g. rtmp://dc4-1.rtmp.t.me/s/)
    telegram_server_url: str = ""
    # X (Twitter) Live ingest base без ключа (e.g. rtmps://fr.pscp.tv:443/x). Порожньо → config.X_INGEST_BASE.
    x_stream_server_url: str = ""
    # URL YouTube-каналу, з якого беруться «наші відео» (останні N).
    our_channel_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "AppSettings":
        raw = data.get("filler_url")
        if raw is None:
            filler_url = ""
        else:
            filler_url = str(raw).strip()
        raw_lo = data.get("logo_opacity")
        if raw_lo is None:
            logo_opacity = float(LOGO_OPACITY)
        else:
            try:
                logo_opacity = max(0.0, min(1.0, float(raw_lo)))
            except (TypeError, ValueError):
                logo_opacity = float(LOGO_OPACITY)
        raw_lz = data.get("logo_zoom")
        if raw_lz is None:
            logo_zoom = float(LOGO_ZOOM)
        else:
            try:
                logo_zoom = max(0.05, min(8.0, float(raw_lz)))
            except (TypeError, ValueError):
                logo_zoom = float(LOGO_ZOOM)
        raw_tg = data.get("telegram_server_url")
        telegram_server_url = str(raw_tg).strip() if raw_tg else ""

        raw_x = data.get("x_stream_server_url")
        x_stream_server_url = str(raw_x).strip() if raw_x else ""

        raw_ocurl = data.get("our_channel_url")
        our_channel_url = str(raw_ocurl).strip() if raw_ocurl else ""

        return AppSettings(
            filler_url=filler_url,
            logo_path=str(data.get("logo_path") or "").strip(),
            logo_opacity=logo_opacity,
            logo_zoom=logo_zoom,
            telegram_server_url=telegram_server_url,
            x_stream_server_url=x_stream_server_url,
            our_channel_url=our_channel_url,
        )


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> AppSettings:
    _ensure_state_dir()
    if not SETTINGS_FILE.is_file():
        return AppSettings(logo_opacity=float(LOGO_OPACITY), logo_zoom=float(LOGO_ZOOM))

    try:
        raw = SETTINGS_FILE.read_text(encoding="utf-8").strip()
        if not raw:
            return AppSettings(logo_opacity=float(LOGO_OPACITY), logo_zoom=float(LOGO_ZOOM))
        data = json.loads(raw)
        if not isinstance(data, dict):
            return AppSettings(logo_opacity=float(LOGO_OPACITY), logo_zoom=float(LOGO_ZOOM))
        return AppSettings.from_dict(data)
    except (OSError, json.JSONDecodeError, TypeError, KeyError):
        return AppSettings(logo_opacity=float(LOGO_OPACITY), logo_zoom=float(LOGO_ZOOM))


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
        cur.filler_url = str(patch["filler_url"]).strip()
    if "logo_path" in patch and patch["logo_path"] is not None:
        cur.logo_path = str(patch["logo_path"]).strip()
    if "logo_opacity" in patch and patch["logo_opacity"] is not None:
        try:
            cur.logo_opacity = max(0.0, min(1.0, float(patch["logo_opacity"])))
        except (TypeError, ValueError):
            pass
    if "logo_zoom" in patch and patch["logo_zoom"] is not None:
        try:
            cur.logo_zoom = max(0.05, min(8.0, float(patch["logo_zoom"])))
        except (TypeError, ValueError):
            pass
    if "telegram_server_url" in patch and patch["telegram_server_url"] is not None:
        cur.telegram_server_url = str(patch["telegram_server_url"]).strip()
    if "x_stream_server_url" in patch and patch["x_stream_server_url"] is not None:
        cur.x_stream_server_url = str(patch["x_stream_server_url"]).strip()
    if "our_channel_url" in patch and patch["our_channel_url"] is not None:
        cur.our_channel_url = str(patch["our_channel_url"]).strip()
    return cur
