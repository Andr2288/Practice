"""REST API керування трансляцією (Flask). Запускається разом із app.py у фоновому потоці."""

from __future__ import annotations

import os
import threading
import time
import webbrowser
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from PIL import Image, UnidentifiedImageError

from config import (
    ASSETS_DIR,
    BASE_DIR,
    BATCH_STATE_FILE,
    CHANNELS_FILE,
    CURRENT_ITEM_FILE,
    OUR_VIDEOS_CACHE_FILE,
    OUR_VIDEOS_LIMIT,
    QUEUE_FILE,
    TELEGRAM_STREAM_KEY_FILE,
    X_STREAM_KEY_FILE,
    YOUTUBE_STREAM_KEY_FILE,
    YT_DLP_BIN,
)
from services.batch_service import load_batch_state
from services.models import VideoItem
from services.our_videos_cache import peek_cached_videos, rescan_our_videos_cache
from services.queue_service import QueueService
from services.runtime_control import (
    is_broadcasting,
    load_control,
    request_skip,
    start_broadcasting,
    stop_broadcasting,
)
from services.settings_service import load_settings, merge_settings_patch, save_settings
from services.storage import (
    load_current_item,
    load_queue,
    save_queue,
)
from services.channel_scan_service import read_channels_list, save_channels_list
from services.ytdlp_client import YtDlpClient


def _stream_key_configured(path) -> bool:
    try:
        return path.is_file() and bool(path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def _admin_ui_html_path() -> Path | None:
    """HTML лежить у `Practice/remixed-…` або поруч із цим модулем у `backend/`."""
    for base in (BASE_DIR.parent, BASE_DIR):
        p = base / "remixed-fc9a4896.html"
        if p.is_file():
            return p
    return None


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(BASE_DIR / "static"),
    )

    @app.get("/")
    def index_html():
        """Головна адмін-сторінка (той самий origin, що й `/api/*`)."""
        p = _admin_ui_html_path()
        if p is None:
            return (
                "<!DOCTYPE html><html lang='uk'><meta charset='utf-8'><title>RadioStream</title>"
                "<body style='font-family:system-ui;padding:2rem'>"
                "<h1>Файл інтерфейсу не знайдено</h1>"
                "<p>Покладіть <code>remixed-fc9a4896.html</code> у корінь проєкту або в папку <code>backend</code>.</p>"
                "</body></html>",
                404,
                {"Content-Type": "text/html; charset=utf-8"},
            )
        return send_from_directory(str(p.parent), p.name)

    @app.after_request
    def _cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        return response

    def _status_payload():
        cur = load_current_item(CURRENT_ITEM_FILE)
        ctrl = load_control()
        settings = load_settings()
        yt_key = _stream_key_configured(YOUTUBE_STREAM_KEY_FILE)
        tg_key = _stream_key_configured(TELEGRAM_STREAM_KEY_FILE)
        x_key = _stream_key_configured(X_STREAM_KEY_FILE)
        batch = load_batch_state(BATCH_STATE_FILE)
        cached_vids, last_scan_ts, cached_ch = peek_cached_videos()
        q = load_queue(QUEUE_FILE)
        return {
            "current": cur.to_dict() if cur else None,
            "broadcasting": bool(ctrl.get("broadcasting")),
            "server_time": time.time(),
            "broadcast_segment_started_at": ctrl.get("broadcast_segment_started_at"),
            "broadcast_last_elapsed_sec": ctrl.get("broadcast_last_elapsed_sec"),
            "command": ctrl.get("command") or "",
            "channels": read_channels_list(CHANNELS_FILE),
            "queue": [v.to_dict() for v in q],
            "our_videos_cache": {
                "videos": [v.to_dict() for v in cached_vids],
                "last_scan_ts": last_scan_ts,
                "channel_url": cached_ch,
            },
            "batch": batch.to_dict() if batch else None,
            "settings": {
                "logo_path": settings.logo_path,
                "logo_opacity": settings.logo_opacity,
                "logo_zoom": settings.logo_zoom,
                "telegram_server_url": settings.telegram_server_url,
                "x_stream_server_url": settings.x_stream_server_url,
                "our_channel_url": settings.our_channel_url,
                "youtube_enabled": settings.youtube_enabled,
                "telegram_enabled": settings.telegram_enabled,
                "x_enabled": settings.x_enabled,
                "ffmpeg_re_input": settings.ffmpeg_re_input,
            },
            "youtube_stream_key_configured": yt_key,
            "telegram_stream_key_configured": tg_key,
            "x_stream_key_configured": x_key,
        }

    @app.get("/api/status")
    def api_status():
        return jsonify(_status_payload())

    @app.get("/api/logo")
    def api_logo_image():
        """Поточний файл логотипу (для прев’ю на вкладці «Вигляд»)."""
        from services.settings_service import load_settings, resolve_logo_path

        p = resolve_logo_path(load_settings())
        if p is None or not p.is_file():
            return ("", 404)
        return send_file(p, max_age=0)

    # ── Broadcast control ──────────────────────────────────────────────

    @app.post("/api/broadcast/start")
    def api_broadcast_start():
        start_broadcasting()
        return jsonify({"ok": True, **_status_payload()})

    @app.post("/api/broadcast/stop")
    def api_broadcast_stop():
        stop_broadcasting()
        return jsonify({"ok": True, **_status_payload()})

    @app.post("/api/control/next")
    def api_next():
        request_skip()
        return jsonify({"ok": True, **_status_payload()})

    # ── Channels ───────────────────────────────────────────────────────

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
        return jsonify({"ok": True, **_status_payload()})

    # ── Our videos ─────────────────────────────────────────────────────

    @app.post("/api/our-videos/rescan")
    def api_our_videos_rescan():
        settings = load_settings()
        channel_url = (settings.our_channel_url or "").strip()
        if not channel_url:
            return jsonify(
                {
                    "ok": False,
                    "error": "Задайте «URL нашого каналу» у розділі Налаштування",
                }
            ), 400
        ytdlp = YtDlpClient(yt_dlp_bin=YT_DLP_BIN)
        try:
            rescan_our_videos_cache(
                ytdlp=ytdlp,
                channel_url=channel_url,
                limit=OUR_VIDEOS_LIMIT,
                cache_file=OUR_VIDEOS_CACHE_FILE,
            )
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify({"ok": True, **_status_payload()})

    # ── Queue ──────────────────────────────────────────────────────────

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
        return jsonify({"ok": True, **_status_payload()})

    @app.delete("/api/queue/<int:idx>")
    def api_queue_delete(idx: int):
        q = load_queue(QUEUE_FILE)
        if idx < 0 or idx >= len(q):
            return jsonify({"ok": False, "error": "Index out of range"}), 400
        del q[idx]
        save_queue(QUEUE_FILE, QueueService().dedupe_queue(q))
        return jsonify({"ok": True, **_status_payload()})

    @app.post("/api/queue/add")
    def api_queue_add():
        data = request.get_json(silent=True) or {}
        q = QueueService().dedupe_queue(load_queue(QUEUE_FILE))

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
        return jsonify({"ok": True, **_status_payload()})

    # ── Settings ───────────────────────────────────────────────────────

    @app.get("/api/settings")
    def api_settings_get():
        settings = load_settings()
        yt_key = _stream_key_configured(YOUTUBE_STREAM_KEY_FILE)
        tg_key = _stream_key_configured(TELEGRAM_STREAM_KEY_FILE)
        x_key = _stream_key_configured(X_STREAM_KEY_FILE)
        return jsonify(
            {
                "logo_path": settings.logo_path,
                "logo_opacity": settings.logo_opacity,
                "logo_zoom": settings.logo_zoom,
                "telegram_server_url": settings.telegram_server_url,
                "x_stream_server_url": settings.x_stream_server_url,
                "our_channel_url": settings.our_channel_url,
                "youtube_enabled": settings.youtube_enabled,
                "telegram_enabled": settings.telegram_enabled,
                "x_enabled": settings.x_enabled,
                "ffmpeg_re_input": settings.ffmpeg_re_input,
                "youtube_stream_key_configured": yt_key,
                "telegram_stream_key_configured": tg_key,
                "x_stream_key_configured": x_key,
            }
        )

    @app.post("/api/settings")
    def api_settings_post():
        data = request.get_json(silent=True) or {}
        old_settings = load_settings()
        if "ffmpeg_re_input" in data and data["ffmpeg_re_input"] is not None:
            new_re = bool(data["ffmpeg_re_input"])
            if is_broadcasting() and new_re != old_settings.ffmpeg_re_input:
                return jsonify(
                    {
                        "ok": False,
                        "error": "Параметр ffmpeg -re можна змінювати лише коли ефір вимкнено.",
                    }
                ), 400
        settings = merge_settings_patch(data)
        save_settings(settings)

        yt_key = (data.get("youtube_stream_key") or "").strip()
        if yt_key:
            YOUTUBE_STREAM_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
            YOUTUBE_STREAM_KEY_FILE.write_text(yt_key + "\n", encoding="utf-8")

        tg_key = (data.get("telegram_stream_key") or "").strip()
        if tg_key:
            TELEGRAM_STREAM_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
            TELEGRAM_STREAM_KEY_FILE.write_text(tg_key + "\n", encoding="utf-8")

        x_key = (data.get("x_stream_key") or "").strip()
        if x_key:
            X_STREAM_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
            X_STREAM_KEY_FILE.write_text(x_key + "\n", encoding="utf-8")

        # Під час ефіру: skip перезапускає ffmpeg з актуальними налаштуваннями
        # (виходи, логотип, прозорість, масштаб).
        destination_flags_changed = (
            old_settings.youtube_enabled != settings.youtube_enabled
            or old_settings.telegram_enabled != settings.telegram_enabled
            or old_settings.x_enabled != settings.x_enabled
        )
        logo_or_look_changed = (
            old_settings.logo_path != settings.logo_path
            or old_settings.logo_opacity != settings.logo_opacity
            or old_settings.logo_zoom != settings.logo_zoom
        )
        if is_broadcasting() and (
            destination_flags_changed or logo_or_look_changed
        ):
            request_skip()

        return jsonify({"ok": True, **_status_payload()})

    @app.post("/api/settings/logo")
    def api_logo_upload():
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "file field required"}), 400
        f = request.files["file"]
        if not f.filename:
            return jsonify({"ok": False, "error": "empty filename"}), 400
        raw = f.read()
        if len(raw) < 8:
            return jsonify({"ok": False, "error": "Файл порожній або пошкоджений"}), 400
        try:
            img = Image.open(BytesIO(raw))
            img.load()
            rgba = img.convert("RGBA")
        except UnidentifiedImageError:
            return jsonify({"ok": False, "error": "Непідтримуваний формат зображення"}), 400
        except OSError as e:
            return jsonify({"ok": False, "error": f"Не вдалося прочитати зображення: {e}"}), 400
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        dest = ASSETS_DIR / "logo.png"
        try:
            rgba.save(dest, format="PNG", optimize=True)
        except OSError as e:
            return jsonify({"ok": False, "error": f"Не вдалося зберегти файл: {e}"}), 500
        try:
            logo_rel = str(dest.relative_to(BASE_DIR))
        except ValueError:
            logo_rel = str(dest)
        settings = merge_settings_patch({"logo_path": logo_rel})
        save_settings(settings)
        if is_broadcasting():
            request_skip()
        return jsonify({"ok": True, **_status_payload()})

    return app


def run_admin(host: str = "127.0.0.1", port: int = 8765) -> None:
    app = create_app()
    app.run(host=host, port=port, threaded=True, use_reloader=False)


def _browser_url(host: str, port: int) -> str:
    open_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    return f"http://{open_host}:{port}/"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Адмінка RadioStream + REST API (без повного app.py).")
    parser.add_argument(
        "--host",
        default=os.environ.get("MEDIAHUB_ADMIN_HOST", "127.0.0.1").strip() or "127.0.0.1",
        help="Адреса сервера (за замовчуванням лише цей ПК).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MEDIAHUB_ADMIN_PORT", "8765")),
        help="Порт (за замовчуванням 8765).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Не відкривати браузер автоматично.",
    )
    args = parser.parse_args()
    url = _browser_url(args.host, args.port)

    if not args.no_browser:

        def _open_when_ready() -> None:
            time.sleep(0.5)
            webbrowser.open(url)

        threading.Thread(target=_open_when_ready, daemon=True).start()

    print(f"RadioStream admin: {url}")
    print("Зупинка: Ctrl+C у цьому вікні.")
    run_admin(host=args.host, port=args.port)
