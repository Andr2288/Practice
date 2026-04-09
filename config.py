import os
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
YOUTUBE_STREAM_KEY_FILE = BASE_DIR / "youtube_stream_key.txt"
TELEGRAM_STREAM_KEY_FILE = BASE_DIR / "telegram_stream_key.txt"

# Повний RTMP URL (пріоритет), або лише ключ — тоді використовується стандартний ingest YouTube.
YOUTUBE_RTMP_URL = os.environ.get("YOUTUBE_RTMP_URL", "").strip()
YOUTUBE_STREAM_KEY = os.environ.get("YOUTUBE_STREAM_KEY", "").strip()
YOUTUBE_INGEST_BASE = "rtmp://a.rtmp.youtube.com/live2/"
STATE_DIR = BASE_DIR / "state"
ASSETS_DIR = BASE_DIR / "assets"

CHANNELS_FILE = BASE_DIR / "channels.txt"
SEEN_VIDEOS_FILE = STATE_DIR / "seen_videos.json"
QUEUE_FILE = STATE_DIR / "queue.json"
CURRENT_ITEM_FILE = STATE_DIR / "current_item.json"
HISTORY_FILE = STATE_DIR / "history.json"
BATCH_STATE_FILE = STATE_DIR / "batch_state.json"
OUR_VIDEOS_CACHE_FILE = STATE_DIR / "our_videos_cache.json"

# За ТЗ перевірка кожні 150 хв
POLL_INTERVAL_MINUTES = 150
# Скільки останніх записів знімати з кожного каналу (кандидати на додавання)
LAST_VIDEOS_LIMIT = 7
# Скільки нових відео максимум додати в чергу за один скан (усі канали разом)
SCAN_MAX_NEW_VIDEOS_PER_RUN = 7

# «Наші відео»: з каналу беремо N останніх; інтервал повторного сканування (хв).
OUR_VIDEOS_LIMIT = 7
OUR_VIDEOS_SCAN_INTERVAL_MINUTES = 60
# Наше відео вставляється після кожних N каналів (D → A → F → Наше → B → E → C → Наше → …)
OUR_VIDEO_EVERY_N_CHANNELS = 3

YT_DLP_BIN = "yt-dlp"
FFMPEG_BIN = "ffmpeg"

# True  -> тестова імітація sleep
# False -> реальна обробка yt-dlp -> ffmpeg -> YouTube Live (RTMP)
TEST_MODE = False
TEST_PLAYBACK_SECONDS = 10

PLAYBACK_ERROR_DELAY_SECONDS = 3
SCAN_ERROR_DELAY_SECONDS = 5
MAX_CHANNEL_RETRIES = 3

# Filler
FILLER_TITLE = "FILLER_LOOP"
FILLER_VIDEO_ID = "__FILLER__"
FILLER_URL = "filler://loop"
# Усі варіанти filler у черзі позначаються цим channel_url (не потрапляють в історію для «попереднє»).
FILLER_CHANNEL_URL = "local://filler"
FILLER_SECONDS = 20

# Формат, який yt-dlp стрімить у stdout.
# Для локального MVP краще брати progressive/single stream, щоб менше ламалось.
YT_DLP_PROGRESSIVE_FORMAT = (
    "best[ext=mp4][protocol!=m3u8]/"
    "best[ext=webm][protocol!=m3u8]/"
    "best[protocol!=m3u8]/"
    "best"
)

# Вихідний стандарт ефіру
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
OUTPUT_FPS = 25
# Для 1080p YouTube очікує стабільний потік; занадто низький бітрейт або слабкий upload → попередження
# «Потік надходить недостатньо швидко». Підлаштування без редагування коду:
#   MEDIAHUB_VIDEO_BITRATE=5500k  MEDIAHUB_VIDEO_MAXRATE=5500k  MEDIAHUB_VIDEO_BUFSIZE=11000k
# Якщо інтернет вузький — зменшіть роздільну здатність (OUTPUT_WIDTH/HEIGHT) або бітрейт.
def _env_bitrate(name: str, default: str) -> str:
    v = os.environ.get(name, "").strip()
    return v if v else default


def _env_float_01(name: str, default: float) -> float:
    v = os.environ.get(name, "").strip().replace(",", ".")
    if not v:
        return default
    try:
        return max(0.0, min(1.0, float(v)))
    except ValueError:
        return default


def _env_float_zoom(name: str, default: float) -> float:
    """Множник розміру логотипу (1 = оригінал). Обмеження щоб не зламати ffmpeg/пам'ять."""
    v = os.environ.get(name, "").strip().replace(",", ".")
    if not v:
        return default
    try:
        return max(0.05, min(8.0, float(v)))
    except ValueError:
        return default


OUTPUT_VIDEO_BITRATE = _env_bitrate("MEDIAHUB_VIDEO_BITRATE", "3500k")
OUTPUT_MAXRATE = _env_bitrate("MEDIAHUB_VIDEO_MAXRATE", OUTPUT_VIDEO_BITRATE)
OUTPUT_BUFSIZE = _env_bitrate("MEDIAHUB_VIDEO_BUFSIZE", "7000k")
OUTPUT_AUDIO_BITRATE = "128k"
OUTPUT_AUDIO_SAMPLE_RATE = 48000
OUTPUT_AUDIO_CHANNELS = 2
OUTPUT_GOP = 50  # 25 fps * 2 sec

# Логотип
LOGO_FILE = ASSETS_DIR / "logo.png"
LOGO_OFFSET_X = 50
LOGO_OFFSET_Y = 50
# Прозорість накладеного PNG: 0 = невидимо, 1 = як у файлі. Перекривається state/settings.json (logo_opacity), якщо задано.
LOGO_OPACITY = _env_float_01("MEDIAHUB_LOGO_OPACITY", 0.5)
# Спочатку PNG вміщується в прямокутник (частка кадру), зберігаючи пропорції (без розтягування).
# Великі файли зменшуються; малі лишаються як є. Потім застосовується logo_zoom як множник.
def _env_logo_fit_fraction() -> float:
    v = os.environ.get("MEDIAHUB_LOGO_FIT_FRACTION", "").strip().replace(",", ".")
    if not v:
        return 0.25
    try:
        return max(0.05, min(1.0, float(v)))
    except ValueError:
        return 0.25


LOGO_FIT_FRACTION = _env_logo_fit_fraction()
LOGO_FIT_MAX_W = max(64, int(OUTPUT_WIDTH * LOGO_FIT_FRACTION))
LOGO_FIT_MAX_H = max(64, int(OUTPUT_HEIGHT * LOGO_FIT_FRACTION))

# Масштаб після підгонки: 1 = розмір «як у рамці»; <1 — менше, >1 — більше. Див. logo_zoom у settings.json.
LOGO_ZOOM = _env_float_zoom("MEDIAHUB_LOGO_ZOOM", 1.0)

# Якщо logo.png відсутній — система працює без нього
ENABLE_LOGO_OVERLAY = True

# Audio normalization
AUDIO_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=async=1:min_hard_comp=0.100:first_pts=0"

# Filler visual/audio
FILLER_BACKGROUND = "black"
FILLER_TEXT = "MEDIAHUB UOS - FILLER"
FILLER_FONT_SIZE = 48
FILLER_TONE_FREQUENCY = 440


def get_youtube_rtmp_url() -> Optional[str]:
    """RTMP URL для YouTube Live. Ключ: YOUTUBE_RTMP_URL, YOUTUBE_STREAM_KEY або youtube_stream_key.txt."""
    if YOUTUBE_RTMP_URL:
        return YOUTUBE_RTMP_URL
    key = YOUTUBE_STREAM_KEY
    if not key and YOUTUBE_STREAM_KEY_FILE.is_file():
        try:
            key = YOUTUBE_STREAM_KEY_FILE.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        except OSError:
            key = ""
    if key:
        return f"{YOUTUBE_INGEST_BASE}{key}"
    return None
