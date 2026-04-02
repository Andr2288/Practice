from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"
ASSETS_DIR = BASE_DIR / "assets"

CHANNELS_FILE = BASE_DIR / "channels.txt"
SEEN_VIDEOS_FILE = STATE_DIR / "seen_videos.json"
QUEUE_FILE = STATE_DIR / "queue.json"
CURRENT_ITEM_FILE = STATE_DIR / "current_item.json"

# За ТЗ перевірка кожні 150 хв
POLL_INTERVAL_MINUTES = 150
LAST_VIDEOS_LIMIT = 7

YT_DLP_BIN = "yt-dlp"
FFMPEG_BIN = "ffmpeg"
FFPLAY_BIN = "ffplay"

# True  -> тестова імітація sleep
# False -> реальна обробка yt-dlp -> ffmpeg -> ffplay
TEST_MODE = False
TEST_PLAYBACK_SECONDS = 10

PLAYBACK_ERROR_DELAY_SECONDS = 3
SCAN_ERROR_DELAY_SECONDS = 5

# Filler
FILLER_TITLE = "FILLER_LOOP"
FILLER_VIDEO_ID = "__FILLER__"
FILLER_URL = "filler://loop"
FILLER_SECONDS = 20

# Preview window
FFPLAY_WIDTH = 1280
FFPLAY_HEIGHT = 720

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
OUTPUT_VIDEO_BITRATE = "3500k"
OUTPUT_MAXRATE = "3500k"
OUTPUT_BUFSIZE = "7000k"
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