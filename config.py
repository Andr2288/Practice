from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"

CHANNELS_FILE = BASE_DIR / "channels.txt"
SEEN_VIDEOS_FILE = STATE_DIR / "seen_videos.json"
QUEUE_FILE = STATE_DIR / "queue.json"
CURRENT_ITEM_FILE = STATE_DIR / "current_item.json"

# За ТЗ перевірка кожні 150 хвилин
POLL_INTERVAL_MINUTES = 150
LAST_VIDEOS_LIMIT = 7

YT_DLP_BIN = "yt-dlp"
FFPLAY_BIN = "ffplay"

# True  -> фейкове відтворення через sleep (для швидкої перевірки логіки)
# False -> реальне локальне відтворення через yt-dlp -> ffplay
TEST_MODE = False
TEST_PLAYBACK_SECONDS = 10

# Після помилок не спамимо цикл
PLAYBACK_ERROR_DELAY_SECONDS = 3
SCAN_ERROR_DELAY_SECONDS = 5

# Filler
FILLER_TITLE = "FILLER_LOOP"
FILLER_VIDEO_ID = "__FILLER__"
FILLER_URL = "filler://loop"
FILLER_SECONDS = 20

# Локальне вікно ffplay
FFPLAY_WIDTH = 1280
FFPLAY_HEIGHT = 720

# Беремо тільки progressive-формати для стабільнішого локального playback.
# Це свідомо компроміс на етапі 1.
YT_DLP_PROGRESSIVE_FORMAT = (
    "best[ext=mp4][protocol!=m3u8]/"
    "best[ext=webm][protocol!=m3u8]/"
    "best[protocol!=m3u8]/"
    "best"
)