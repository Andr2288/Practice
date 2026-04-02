from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"

CHANNELS_FILE = BASE_DIR / "channels.txt"
SEEN_VIDEOS_FILE = STATE_DIR / "seen_videos.json"
QUEUE_FILE = STATE_DIR / "queue.json"

# За ТЗ: кожні 150 хв
POLL_INTERVAL_MINUTES = 1

# За ТЗ: брати останні 5-7 відео.
# Для MVP візьмемо 7.
LAST_VIDEOS_LIMIT = 7

# yt-dlp binary name
YT_DLP_BIN = "yt-dlp"