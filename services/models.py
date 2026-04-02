from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class VideoItem:
    video_id: str
    title: str
    url: str
    channel_url: str
    channel_title: Optional[str] = None
    duration: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "VideoItem":
        return VideoItem(
            video_id=str(data["video_id"]),
            title=str(data["title"]),
            url=str(data["url"]),
            channel_url=str(data["channel_url"]),
            channel_title=data.get("channel_title"),
            duration=data.get("duration"),
        )