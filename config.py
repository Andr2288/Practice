import os
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
YOUTUBE_STREAM_KEY_FILE = BASE_DIR / "youtube_stream_key.txt"

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

# За ТЗ перевірка кожні 150 хв
POLL_INTERVAL_MINUTES = 150
LAST_VIDEOS_LIMIT = 7

YT_DLP_BIN = "yt-dlp"
FFMPEG_BIN = "ffmpeg"

# True  -> тестова імітація sleep
# False -> реальна обробка yt-dlp -> ffmpeg -> YouTube Live (RTMP)
TEST_MODE = False
TEST_PLAYBACK_SECONDS = 10

PLAYBACK_ERROR_DELAY_SECONDS = 3
SCAN_ERROR_DELAY_SECONDS = 5

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
