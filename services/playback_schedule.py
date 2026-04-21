"""
Пакетне наповнення queue.json: та сама логіка, що в колишньому playback_cycle_step
(канали в циклі + наші відео після foreign_since_our >= OUR_VIDEO_EVERY_N_CHANNELS, скидання після «нашого»).

Під час планування тримаємо копію BatchState у пам'яті; на диск пишемо лише зміни
при «пропуску» каналу (немає відео / помилка fetch), як у реальному циклі.

Після відтворення авто-роликів стан оновлюється в apply_auto_batch_state_after_play.
"""

from __future__ import annotations

import copy
import random
from dataclasses import replace
from typing import List, Optional

from config import (
    BATCH_STATE_FILE,
    LAST_VIDEOS_LIMIT,
    OUR_VIDEOS_CACHE_FILE,
    OUR_VIDEOS_LIMIT,
    OUR_VIDEO_EVERY_N_CHANNELS,
    QUEUE_FILE,
    SEEN_VIDEOS_FILE,
)
from services.batch_service import BatchState, load_batch_state, save_batch_state, start_new_cycle
from services.models import VideoItem
from services.our_videos_cache import fetch_our_videos_for_playback
from services.runtime_control import is_broadcasting, request_skip
from services.storage import load_queue, load_seen_videos, save_queue


def _foreign_channel_sets_match(channels: List[str], state: BatchState) -> bool:
    """Той самий набір URL, що в channels.txt, що й у поточному циклі (порядок у файлі не важливий)."""
    return set(channels) == set(state.shuffled_channels)


def reload_playback_after_channels_file_changed(channels: List[str]) -> None:
    """Після збереження нового channels.txt: новий shuffle циклу, порожня черга, під час ефіру — skip (перезапуск сегмента).

    Порядок URL у списку враховується лише до shuffle у start_new_cycle; викликати з уже нормалізованим
    списком з диску (read_channels_list).
    """
    state = load_batch_state(BATCH_STATE_FILE) or BatchState()
    if not channels:
        state.shuffled_channels = []
        state.current_index = 0
        state.channel_fail_count = 0
    else:
        ns = start_new_cycle(
            channels,
            prev_our_video_index=state.our_video_index,
            prev_foreign_since_our=state.foreign_since_our,
        )
        state.shuffled_channels = ns.shuffled_channels
        state.current_index = ns.current_index
        state.channel_fail_count = ns.channel_fail_count
        state.our_video_index = ns.our_video_index
        state.foreign_since_our = ns.foreign_since_our
    save_batch_state(BATCH_STATE_FILE, state)
    save_queue(QUEUE_FILE, [])
    if is_broadcasting():
        request_skip()


def prepare_batch_state_for_scheduling(channels: List[str]) -> None:
    state = load_batch_state(BATCH_STATE_FILE) or BatchState()
    if not channels:
        # Режим лише «наш канал»: не лишаємо у стані старий shuffle чужих каналів.
        state.shuffled_channels = []
        state.current_index = 0
        state.channel_fail_count = 0
        save_batch_state(BATCH_STATE_FILE, state)
        return
    # Новий цикл після завершення кола або коли список каналів у файлі змінився (збереження з адмінки).
    if state.is_cycle_complete() or not _foreign_channel_sets_match(channels, state):
        ns = start_new_cycle(
            channels,
            prev_our_video_index=state.our_video_index,
            prev_foreign_since_our=state.foreign_since_our,
        )
        state.shuffled_channels = ns.shuffled_channels
        state.current_index = ns.current_index
        state.channel_fail_count = ns.channel_fail_count
        state.our_video_index = ns.our_video_index
        state.foreign_since_our = ns.foreign_since_our
    save_batch_state(BATCH_STATE_FILE, state)


def _persist_skip_channel(sim: BatchState) -> None:
    sim.current_index += 1
    sim.our_video_index += 1
    sim.foreign_since_our += 1
    save_batch_state(BATCH_STATE_FILE, sim)


def _plan_step_our_channel_only(
    sim: BatchState,
    ytdlp,
    settings,
    our_videos_fixed: Optional[List[VideoItem]],
) -> Optional[VideoItem]:
    channel_url = (settings.our_channel_url or "").strip()
    if not channel_url:
        return None
    if our_videos_fixed is not None:
        our_videos = our_videos_fixed
    else:
        our_videos = fetch_our_videos_for_playback(
            ytdlp=ytdlp,
            channel_url=channel_url,
            limit=OUR_VIDEOS_LIMIT,
            cache_file=OUR_VIDEOS_CACHE_FILE,
        )
    if not our_videos:
        return None
    sim.shuffled_channels = []
    sim.current_index = 0
    idx = sim.our_video_index % len(our_videos)
    item = our_videos[idx]
    sim.our_video_index = sim.our_video_index + 1
    return replace(item, source="auto_our")


def _plan_one_cycle_like_app(
    sim: BatchState,
    ytdlp,
    settings,
    channels: List[str],
    our_videos_fixed: Optional[List[VideoItem]],
) -> List[VideoItem]:
    """Як playback_cycle_step, але замість відтворення — список VideoItem."""
    if sim is None or sim.is_cycle_complete():
        prev_our_idx = sim.our_video_index if sim else 0
        prev_foreign = sim.foreign_since_our if sim else 0
        ns = start_new_cycle(
            channels,
            prev_our_video_index=prev_our_idx,
            prev_foreign_since_our=prev_foreign,
        )
        sim.shuffled_channels = ns.shuffled_channels
        sim.current_index = ns.current_index
        sim.channel_fail_count = ns.channel_fail_count
        sim.our_video_index = ns.our_video_index
        sim.foreign_since_our = ns.foreign_since_our

    channel_url = sim.current_channel()
    if channel_url is None:
        return []

    try:
        videos = ytdlp.fetch_latest_videos(channel_url, limit=LAST_VIDEOS_LIMIT)
    except Exception:
        _persist_skip_channel(sim)
        return []

    if not videos:
        _persist_skip_channel(sim)
        return []

    seen = load_seen_videos(SEEN_VIDEOS_FILE)
    unseen = [v for v in videos if v.video_id not in seen]
    pool = unseen if unseen else videos
    video = random.choice(pool)

    out: List[VideoItem] = [replace(video, source="auto_foreign")]
    sim.channel_fail_count = 0
    sim.current_index += 1
    # Разом із чужим слотом зсуваємо й послідовність «наших» (як після пропуску/програвання чужого)
    sim.our_video_index += 1
    sim.foreign_since_our += 1

    if sim.foreign_since_our >= OUR_VIDEO_EVERY_N_CHANNELS:
        our_ch = (settings.our_channel_url or "").strip()
        if our_ch:
            if our_videos_fixed is not None and len(our_videos_fixed) > 0:
                our_videos = our_videos_fixed
            else:
                our_videos = fetch_our_videos_for_playback(
                    ytdlp=ytdlp,
                    channel_url=our_ch,
                    limit=OUR_VIDEOS_LIMIT,
                    cache_file=OUR_VIDEOS_CACHE_FILE,
                )
            if our_videos:
                oi = sim.our_video_index % len(our_videos)
                ov = our_videos[oi]
                sim.our_video_index = sim.our_video_index + 1
                out.append(replace(ov, source="auto_our"))
                sim.foreign_since_our = 0

    return out


def schedule_automated_queue_batch(
    ytdlp,
    settings,
    channels: List[str],
    batch_size: int,
) -> List[VideoItem]:
    prepare_batch_state_for_scheduling(channels)
    sim = copy.deepcopy(load_batch_state(BATCH_STATE_FILE) or BatchState())

    # Один знімок «наших» відео на весь пакет черги — інакше кожен виклик fetch зміщує список
    # останніх OUR_VIDEOS_LIMIT роликів і порушує послідовність за our_video_index.
    our_snap: Optional[List[VideoItem]] = None
    och = (settings.our_channel_url or "").strip()
    if och:
        fetched = fetch_our_videos_for_playback(
            ytdlp=ytdlp,
            channel_url=och,
            limit=OUR_VIDEOS_LIMIT,
            cache_file=OUR_VIDEOS_CACHE_FILE,
        )
        our_snap = fetched if fetched else None

    out: List[VideoItem] = []
    iterations = 0
    max_iter = max(batch_size * 400, 400)

    if not channels:
        while len(out) < batch_size and iterations < max_iter:
            iterations += 1
            one = _plan_step_our_channel_only(sim, ytdlp, settings, our_snap)
            if one:
                out.append(one)
            else:
                break
        return out

    while len(out) < batch_size and iterations < max_iter:
        iterations += 1
        chunk = _plan_one_cycle_like_app(
            sim, ytdlp, settings, channels, our_snap
        )
        if chunk:
            out.extend(chunk)

    return out


def refill_automated_queue_if_empty(
    ytdlp,
    settings,
    channels: List[str],
    batch_size: int,
) -> int:
    q = load_queue(QUEUE_FILE)
    if q:
        return 0
    new_items = schedule_automated_queue_batch(ytdlp, settings, channels, batch_size)
    if not new_items:
        return 0
    save_queue(QUEUE_FILE, new_items)
    return len(new_items)


def apply_auto_batch_state_after_play(item: VideoItem, *, had_exception: bool) -> None:
    """Після спроби відтворення: чужий ролик зсуває слот циклу; після «нашого» лічильник чужих скидається."""
    src = item.source or ""
    if src == "auto_foreign":
        st = load_batch_state(BATCH_STATE_FILE) or BatchState()
        st.current_index += 1
        st.our_video_index += 1
        st.foreign_since_our += 1
        st.channel_fail_count = 0
        save_batch_state(BATCH_STATE_FILE, st)
        return
    if src == "auto_our" and not had_exception:
        st = load_batch_state(BATCH_STATE_FILE) or BatchState()
        st.our_video_index = st.our_video_index + 1
        st.foreign_since_our = 0
        save_batch_state(BATCH_STATE_FILE, st)
