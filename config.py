from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"

CHANNELS_FILE = BASE_DIR / "channels.txt"
SEEN_VIDEOS_FILE = STATE_DIR / "seen_videos.json"
QUEUE_FILE = STATE_DIR / "queue.json"
CURRENT_ITEM_FILE = STATE_DIR / "current_item.json"

POLL_INTERVAL_MINUTES = 0.5
LAST_VIDEOS_LIMIT = 7

YT_DLP_BIN = "yt-dlp"
FFPLAY_BIN = "ffplay"

# Режим відтворення:
# True  -> fake playback через time.sleep
# False -> реальне локальне playback через ffplay
TEST_MODE = False
TEST_PLAYBACK_SECONDS = 10

# Filler-заставка
FILLER_TITLE = "FILLER_LOOP"
FILLER_VIDEO_ID = "__FILLER__"
FILLER_URL = "filler://loop"

# Локальне тестове вікно ffplay
FFPLAY_WIDTH = 1280
FFPLAY_HEIGHT = 720