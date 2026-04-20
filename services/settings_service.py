import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR, LOGO_FILE, LOGO_OPACITY, LOGO_ZOOM, STATE_DIR

SETTINGS_FILE = STATE_DIR / "settings.json"


@dataclass
class AppSettings:
    """Параметри, що можна змінювати з адмінки (файл state/settings.json)."""

    # Шлях до PNG (відносно кореня проєкту або абсолютний). Порожньо = config.LOGO_FILE.
    logo_path: str = ""
    # Множник альфа (0…1). У JSON немає ключа → config.LOGO_OPACITY.
    logo_opacity: float = 1.0
    # Множник після підгонки PNG у рамку; 1 = базовий розмір. У JSON немає ключа → config.LOGO_ZOOM.
    logo_zoom: float = 1.0
    # Telegram RTMP server URL (e.g. rtmp://dc4-1.rtmp.t.me/s/)
    telegram_server_url: str = ""
    # X (Twitter) Live ingest base без ключа (e.g. rtmps://fr.pscp.tv:443/x). Порожньо → config.X_INGEST_BASE.
    x_stream_server_url: str = ""
    # URL YouTube-каналу, з якого беруться «наші відео» (останні N).
    our_channel_url: str = ""
    # Enable/disable destinations
    youtube_enabled: bool = True
    telegram_enabled: bool = True
    x_enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "AppSettings":
        def _as_bool(value: Any, default: bool = True) -> bool:
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            s = str(value).strip().lower()
            if s in {"1", "true", "yes", "on"}:
                return True
            if s in {"0", "false", "no", "off"}:
                return False
            return default

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
            logo_path=str(data.get("logo_path") or "").strip(),
            logo_opacity=logo_opacity,
            logo_zoom=logo_zoom,
            telegram_server_url=telegram_server_url,
            x_stream_server_url=x_stream_server_url,
            our_channel_url=our_channel_url,
            youtube_enabled=_as_bool(data.get("youtube_enabled"), True),
            telegram_enabled=_as_bool(data.get("telegram_enabled"), True),
            x_enabled=_as_bool(data.get("x_enabled"), True),
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
    if "youtube_enabled" in patch and patch["youtube_enabled"] is not None:
        cur.youtube_enabled = bool(patch["youtube_enabled"])
    if "telegram_enabled" in patch and patch["telegram_enabled"] is not None:
        cur.telegram_enabled = bool(patch["telegram_enabled"])
    if "x_enabled" in patch and patch["x_enabled"] is not None:
        cur.x_enabled = bool(patch["x_enabled"])
    return cur
