"""Легкий веб-інтерфейс керування (Flask). Запускається разом із app.py у фоновому потоці."""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from config import (
    ASSETS_DIR,
    BASE_DIR,
    BATCH_STATE_FILE,
    CHANNELS_FILE,
    CURRENT_ITEM_FILE,
    HISTORY_FILE,
    QUEUE_FILE,
    YOUTUBE_STREAM_KEY_FILE,
    YT_DLP_BIN,
)
from services.batch_service import load_batch_state
from services.models import VideoItem
from services.our_videos_cache import invalidate_cache, peek_cached_videos
from services.playback_service import PlaybackService
from services.queue_service import QueueService
from services.runtime_control import (
    is_paused,
    load_control,
    request_previous,
    request_skip,
    save_control,
)
from services.settings_service import load_settings, merge_settings_patch, save_settings
from services.storage import (
    load_current_item,
    load_queue,
    pop_history_last_non_filler,
    save_queue,
)
from services.channel_scan_service import read_channels_list, save_channels_list
from services.ytdlp_client import YtDlpClient


def _stream_key_configured() -> bool:
    try:
        return YOUTUBE_STREAM_KEY_FILE.is_file() and bool(
            YOUTUBE_STREAM_KEY_FILE.read_text(encoding="utf-8").strip()
        )
    except OSError:
        return False


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )

    @app.get("/")
    def index():
        return render_template("admin.html")

    def _queue_payload():
        cur = load_current_item(CURRENT_ITEM_FILE)
        ctrl = load_control()
        settings = load_settings()
        key_present = _stream_key_configured()
        batch = load_batch_state(BATCH_STATE_FILE)
        cached_vids, last_scan_ts, cached_ch = peek_cached_videos()
        return {
            "current": cur.to_dict() if cur else None,
            "paused": bool(ctrl.get("paused")),
            "command": ctrl.get("command") or "",
            "channels": read_channels_list(CHANNELS_FILE),
            "our_videos_cache": {
                "videos": [v.to_dict() for v in cached_vids],
                "last_scan_ts": last_scan_ts,
                "channel_url": cached_ch,
            },
            "batch": batch.to_dict() if batch else None,
            "settings": {
                "filler_url": settings.filler_url,
                "logo_path": settings.logo_path,
                "logo_opacity": settings.logo_opacity,
                "logo_zoom": settings.logo_zoom,
                "our_channel_url": settings.our_channel_url,
                "our_videos_scan_interval_minutes": settings.our_videos_scan_interval_minutes,
            },
            "youtube_stream_key_configured": key_present,
        }

    @app.get("/api/status")
    def api_status():
        return jsonify(_queue_payload())

    @app.put("/api/channels")
    def api_channels_put():
        data = request.get_json(silent=True) or {}
        raw = data.get("channels")
        if not isinstance(raw, list):
            return jsonify({"ok": False, "error": "Expected { channels: [...] }"}), 400
        urls: list[str] = []
        for x in raw:
            if isinstance(x, str):
                s = x.strip()
                if s:
                    urls.append(s)
        save_channels_list(CHANNELS_FILE, urls)
        return jsonify({"ok": True, **_queue_payload()})

    @app.post("/api/our-videos/rescan")
    def api_our_videos_rescan():
        """Force re-scan of 'our videos' channel on the next playback cycle."""
        invalidate_cache()
        return jsonify({"ok": True, **_queue_payload()})

    @app.post("/api/scan")
    def api_scan_channels():
        try:
            from services.channel_scan_service import run_channel_scan

            added = run_channel_scan()
            return jsonify({"ok": True, "added": added, **_queue_payload()})
        except RuntimeError as e:
            return jsonify({"ok": False, "error": str(e)}), 409
        except FileNotFoundError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.put("/api/queue")
    def api_queue_replace():
        data = request.get_json(silent=True) or {}
        items = data.get("queue")
        if not isinstance(items, list):
            return jsonify({"ok": False, "error": "Expected { queue: [...] }"}), 400
        out: list[VideoItem] = []
        for it in items:
            if not isinstance(it, dict) or "video_id" not in it:
                continue
            try:
                out.append(VideoItem.from_dict(it))
            except Exception:
                continue
        save_queue(QUEUE_FILE, QueueService().dedupe_queue(out))
        return jsonify({"ok": True, **_queue_payload()})

    @app.delete("/api/queue/<int:index>")
    def api_queue_delete(index: int):
        q = load_queue(QUEUE_FILE)
        if index < 0 or index >= len(q):
            return jsonify({"ok": False, "error": "Index out of range"}), 400
        del q[index]
        save_queue(QUEUE_FILE, QueueService().dedupe_queue(q))
        return jsonify({"ok": True, **_queue_payload()})

    @app.post("/api/queue/add")
    def api_queue_add():
        data = request.get_json(silent=True) or {}
        kind = (data.get("type") or "url").strip().lower()
        q = QueueService().dedupe_queue(load_queue(QUEUE_FILE))

        if kind == "filler":
            item = PlaybackService().create_filler_item()
        else:
            url = (data.get("url") or "").strip()
            if not url:
                return jsonify({"ok": False, "error": "url is required"}), 400
            ytdlp = YtDlpClient(yt_dlp_bin=YT_DLP_BIN)
            try:
                item = ytdlp.fetch_video_by_url(url)
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 400

        pos = data.get("position")
        if pos == "front":
            q = [item] + q
        else:
            q = q + [item]
        save_queue(QUEUE_FILE, QueueService().dedupe_queue(q))
        return jsonify({"ok": True, **_queue_payload()})

    @app.post("/api/queue/move")
    def api_queue_move():
        data = request.get_json(silent=True) or {}
        try:
            from_idx = int(data.get("from"))
            to_idx = int(data.get("to"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "from and to must be integers"}), 400
        q = load_queue(QUEUE_FILE)
        if from_idx < 0 or from_idx >= len(q) or to_idx < 0 or to_idx >= len(q):
            return jsonify({"ok": False, "error": "Index out of range"}), 400
        item = q.pop(from_idx)
        q.insert(to_idx, item)
        save_queue(QUEUE_FILE, QueueService().dedupe_queue(q))
        return jsonify({"ok": True, **_queue_payload()})

    @app.post("/api/control/pause")
    def api_pause():
        save_control(paused=True)
        return jsonify({"ok": True, **_queue_payload()})

    @app.post("/api/control/resume")
    def api_resume():
        save_control(paused=False)
        return jsonify({"ok": True, **_queue_payload()})

    @app.post("/api/control/next")
    def api_next():
        request_skip()
        return jsonify({"ok": True, **_queue_payload()})

    @app.post("/api/control/previous")
    def api_previous():
        request_previous()
        return jsonify({"ok": True, **_queue_payload()})

    @app.get("/api/settings")
    def api_settings_get():
        settings = load_settings()
        key_present = _stream_key_configured()
        return jsonify(
            {
                "filler_url": settings.filler_url,
                "logo_path": settings.logo_path,
                "logo_opacity": settings.logo_opacity,
                "logo_zoom": settings.logo_zoom,
                "our_channel_url": settings.our_channel_url,
                "our_videos_scan_interval_minutes": settings.our_videos_scan_interval_minutes,
                "youtube_stream_key_configured": key_present,
            }
        )

    @app.post("/api/settings")
    def api_settings_post():
        data = request.get_json(silent=True) or {}
        settings = merge_settings_patch(data)
        save_settings(settings)
        key = (data.get("youtube_stream_key") or "").strip()
        if key:
            YOUTUBE_STREAM_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
            YOUTUBE_STREAM_KEY_FILE.write_text(key + "\n", encoding="utf-8")
        return jsonify({"ok": True, **_queue_payload()})

    @app.post("/api/settings/logo")
    def api_logo_upload():
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "file field required"}), 400
        f = request.files["file"]
        if not f.filename:
            return jsonify({"ok": False, "error": "empty filename"}), 400
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        dest = ASSETS_DIR / "logo.png"
        f.save(dest)
        try:
            logo_rel = str(dest.relative_to(BASE_DIR))
        except ValueError:
            logo_rel = str(dest)
        settings = merge_settings_patch({"logo_path": logo_rel})
        save_settings(settings)
        return jsonify({"ok": True, **_queue_payload()})

    return app


def run_admin(host: str = "127.0.0.1", port: int = 8765) -> None:
    app = create_app()
    app.run(host=host, port=port, threaded=True, use_reloader=False)
