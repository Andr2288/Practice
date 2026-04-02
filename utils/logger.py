from datetime import datetime


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log_block(title: str) -> None:
    print()
    print("=" * 70)
    print(f"[{_ts()}] {title}")
    print("=" * 70)


def log_scan(message: str) -> None:
    print(f"[{_ts()}] [SCAN] {message}")


def log_play(message: str) -> None:
    print(f"[{_ts()}] [PLAY] {message}")


def log_info(message: str) -> None:
    print(f"[{_ts()}] [INFO] {message}")


def log_warn(message: str) -> None:
    print(f"[{_ts()}] [WARN] {message}")


def log_error(message: str) -> None:
    print(f"[{_ts()}] [ERROR] {message}")


def log_blank() -> None:
    print()