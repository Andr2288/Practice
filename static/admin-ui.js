(function () {
  "use strict";

  let last = null;
  let pollTimer = null;
  /** Різниця серверного часу й браузера (сек), щоб відлік ефіру збігався з бекендом */
  let serverSkewSec = 0;

  function $(id) {
    return document.getElementById(id);
  }

  function toast(msg) {
    if (typeof window.toast === "function" && window.toast !== toast) {
      window.toast(msg);
      return;
    }
    alert(msg);
  }

  async function api(method, path, body) {
    const opt = { method, headers: {} };
    if (body !== undefined) {
      opt.headers["Content-Type"] = "application/json";
      opt.body = JSON.stringify(body);
    }
    const r = await fetch(path, opt);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const err = data.error || data.message || r.statusText;
      throw new Error(typeof err === "string" ? err : JSON.stringify(err));
    }
    return data;
  }

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function nowSyncSec() {
    return Date.now() / 1000 + serverSkewSec;
  }

  function syncServerClock(st) {
    if (st && st.server_time != null && !Number.isNaN(Number(st.server_time))) {
      serverSkewSec = Number(st.server_time) - Date.now() / 1000;
    }
  }

  /** Тривалість для бейджа ефіру: завжди ГГ:ХХ:СС */
  function fmtClockDur(sec) {
    if (sec == null || sec === "" || Number.isNaN(Number(sec))) return "00:00:00";
    const s = Math.max(0, Math.floor(Number(sec)));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const r = s % 60;
    return pad2(h) + ":" + pad2(m) + ":" + pad2(r);
  }

  function fmtDur(sec) {
    if (sec == null || sec === "" || Number.isNaN(Number(sec))) return "—";
    const s = Math.max(0, Math.floor(Number(sec)));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const r = s % 60;
    if (h > 0) return h + ":" + pad2(m) + ":" + pad2(r);
    return m + ":" + pad2(r);
  }

  function setText(id, text) {
    const el = $(id);
    if (el) el.textContent = text;
  }

  function updateBroadcastTimer(st) {
    const on = !!st.broadcasting;
    const dt = $("d-timer");
    const mt = $("m-timer");
    const tag = $("d-live-tag");
    const mtag = $("m-live-tag");
    const dot = tag && tag.querySelector(".live-dot");
    const mdot = mtag && mtag.querySelector(".live-dot");

    let line = "";
    if (on) {
      const started = st.broadcast_segment_started_at;
      const sec =
        started != null && !Number.isNaN(Number(started))
          ? Math.max(0, Math.floor(nowSyncSec() - Number(started)))
          : 0;
      line = "В ЕФІРІ · " + fmtClockDur(sec);
    } else {
      const frozen = st.broadcast_last_elapsed_sec;
      if (frozen != null && !Number.isNaN(Number(frozen)) && Number(frozen) >= 0) {
        line = "Ефір зупинено · " + fmtClockDur(frozen);
      } else {
        line = "Ефір зупинено";
      }
    }

    if (dt) dt.textContent = line;
    if (mt) mt.textContent = line;

    if (tag) {
      tag.style.opacity = on ? "1" : "0.55";
      if (dot) dot.style.display = on ? "" : "none";
    }
    if (mtag) {
      mtag.style.opacity = on ? "1" : "0.55";
      if (mdot) mdot.style.display = on ? "" : "none";
    }
  }

  function renderPlatforms(st) {
    const s = st.settings || {};
    const ytOn = !!s.youtube_enabled;
    const tgOn = !!s.telegram_enabled;
    const xOn = !!s.x_enabled;
    const ytKey = !!st.youtube_stream_key_configured;
    const tgKey = !!st.telegram_stream_key_configured;
    const xKey = !!st.x_stream_key_configured;

    function applyRow(prefix, key, enabled, keyOk) {
      const tgl = $(prefix + "-" + key + "-tgl");
      const dot = $(prefix + "-" + key + "-dot");
      const sub = $(prefix + "-" + key + "-sub");
      const view = $(prefix + "-" + key + "-view");
      if (tgl) {
        tgl.classList.toggle("on", enabled);
        tgl.dataset.enabled = enabled ? "1" : "0";
      }
      if (dot) {
        dot.className = "sdot " + (enabled && keyOk ? "ok" : !keyOk ? "err" : "off");
      }
      if (sub) {
        if (!keyOk) sub.textContent = "Ключ не задано";
        else sub.textContent = enabled ? "Увімкнено" : "Вимкнено";
      }
      if (view) view.textContent = keyOk ? "RTMP · ключ" : "RTMP · немає ключа";
    }

    applyRow("d", "yt", ytOn, ytKey);
    applyRow("d", "tg", tgOn, tgKey);
    applyRow("d", "x", xOn, xKey);
    applyRow("m", "yt", ytOn, ytKey);
    applyRow("m", "tg", tgOn, tgKey);
    applyRow("m", "x", xOn, xKey);
  }

  function renderFfmpegReToggle(st) {
    const on = !!(st.settings && st.settings.ffmpeg_re_input);
    const live = !!st.broadcasting;
    ["d-ffmpeg-re-tgl", "m-ffmpeg-re-tgl"].forEach(function (id) {
      const tgl = $(id);
      if (tgl) {
        tgl.classList.toggle("on", on);
        tgl.dataset.enabled = on ? "1" : "0";
        tgl.disabled = live;
        tgl.setAttribute("aria-disabled", live ? "true" : "false");
        tgl.style.opacity = live ? "0.5" : "";
        tgl.style.cursor = live ? "not-allowed" : "";
        tgl.title = live
          ? "Змінюйте лише коли ефір вимкнено"
          : "Увімкнути -re для stdin від yt-dlp";
      }
    });
    const hd = $("d-ffmpeg-re-lock-hint");
    const hm = $("m-ffmpeg-re-lock-hint");
    if (hd) hd.style.display = live ? "block" : "none";
    if (hm) hm.style.display = live ? "block" : "none";
  }

  function queueRowState(item, current) {
    const live = current && item && item.video_id === current.video_id;
    if (live) return { tag: "q-live", label: "В ефірі", dot: true };
    return { tag: "q-pend", label: "Очікує", dot: false };
  }

  function renderQueue(st) {
    const q = st.queue || [];
    const cur = st.current;
    const tb = $("d-queue-tbody");
    if (tb) {
      tb.innerHTML = q
        .map((item, idx) => {
          const stt = queueRowState(item, cur);
          const dot = stt.dot
            ? '<span class="q-live-dot"></span>'
            : "";
          return (
            "<tr>" +
            '<td style="color:var(--t2);font-family:Geist Mono,monospace;font-size:11px">' +
            (idx + 1) +
            "</td>" +
            "<td><div class=\"q-title\">" +
            esc(item.title) +
            '</div><div class="q-channel">' +
            esc(item.channel_title || item.channel_url || "") +
            "</div></td>" +
            '<td><span class="mono" style="font-size:12px;color:var(--t1)">' +
            fmtDur(item.duration) +
            "</span></td>" +
            '<td><span class="q-tag ' +
            stt.tag +
            '">' +
            dot +
            esc(stt.label) +
            "</span></td>" +
            "<td>" +
            (stt.dot
              ? '<button type="button" class="np-btn np-btn-skip" style="font-size:11px;padding:5px 10px" data-mh="skip">⏭</button>'
              : '<button type="button" class="ib del" title="Видалити" data-mh="del" data-idx="' +
                idx +
                '">✕</button>') +
            "</td>" +
            "</tr>"
          );
        })
        .join("");
    }

    const mob = $("m-queue-list");
    if (mob) {
      mob.innerHTML = q
        .map((item, idx) => {
          const stt = queueRowState(item, cur);
          const dot = stt.dot ? "🔴" : "📰";
          const bg = stt.dot ? "#E3F1EB" : "var(--blue-l)";
          return (
            '<div class="m-qi">' +
            '<span class="m-qi-num">' +
            (idx + 1) +
            '</span><div class="m-qi-thumb" style="background:' +
            bg +
            '">' +
            dot +
            '</div><div class="m-qi-info"><div class="m-qi-title">' +
            esc(item.title) +
            '</div><div class="m-qi-meta"><span>' +
            esc(item.channel_title || "") +
            '</span>·<span class="mono">' +
            fmtDur(item.duration) +
            "</span></div></div>" +
            '<div class="m-qi-r"><span class="m-qi-tag ' +
            stt.tag +
            '">' +
            esc(stt.label) +
            "</span>" +
            (stt.dot
              ? '<button type="button" class="ib" data-mh="skip">⏭</button>'
              : '<button type="button" class="ib del" data-mh="del" data-idx="' +
                idx +
                '">✕</button>') +
            "</div></div>"
          );
        })
        .join("");
    }

    const n = q.length;
    setText("d-foot-total", String(n));
    setText("m-foot-total", String(n));
    const bq = $("d-nav-queue-badge");
    if (bq) bq.textContent = n > 99 ? "99+" : String(n);
    const mb = $("m-nav-queue-badge");
    if (mb) mb.textContent = n > 99 ? "99+" : String(n);
  }

  function esc(s) {
    if (!s) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderBatchLine(st) {
    const b = st.batch;
    let txt = "";
    if (b && b.shuffled_channels && b.shuffled_channels.length) {
      const i = Math.min(b.current_index + 1, b.shuffled_channels.length);
      const t = b.shuffled_channels.length;
      const ch = b.shuffled_channels[b.current_index] || "";
      const short = ch.length > 48 ? ch.slice(0, 45) + "…" : ch;
      txt = "Цикл каналів: " + i + "/" + t + (short ? " · " + short : "");
    } else if ((st.channels || []).length) {
      txt = "Каналів у списку: " + st.channels.length;
    } else {
      txt =
        "Чужі канали не задані — ефір лише з «нашого каналу» (якщо URL задано й є відео)";
    }
    setText("d-url", txt);
    setText("m-url", txt);
    $("d-url") && ($("d-url").className = "np-url-timer");
    $("m-url") && ($("m-url").className = "m-url-timer");
  }

  function renderNow(st) {
    const c = st.current;
    const on = !!st.broadcasting;
    updateBroadcastTimer(st);

    if (c) {
      setText("d-np-title", c.title || "—");
      setText("m-np-title", c.title || "—");
      const chLine =
        (c.channel_title || "") +
        (c.channel_url ? " · " + c.channel_url : "");
      setText("d-np-ch", chLine || "—");
      setText("m-np-ch", chLine || "—");
    } else {
      setText("d-np-title", on ? "Очікування…" : "Ефір вимкнено");
      setText("m-np-title", on ? "Очікування…" : "Ефір вимкнено");
      setText("d-np-ch", "");
      setText("m-np-ch", "");
    }

    const dur = c && c.duration != null ? fmtDur(c.duration) : "—";
    setText("d-np-dur", "Тривалість: " + dur);
    setText("m-np-dur", "Тривалість: " + dur);

    const startD = $("d-btn-start");
    const startM = $("m-btn-start");
    const skipD = $("d-btn-skip");
    const skipM = $("m-btn-skip");
    const stopD = $("d-btn-stop");
    const stopM = $("m-btn-stop");
    [startD, startM].forEach((b) => {
      if (b) b.style.display = on ? "none" : "";
    });
    [skipD, skipM, stopD, stopM].forEach((b) => {
      if (b) b.style.display = on ? "" : "none";
    });
  }

  /** Парні поля десктоп (acc-*) і мобільні (m-acc-*) */
  const ACC_IDS = {
    "tg-url": ["acc-tg-url", "m-acc-tg-url"],
    "x-url": ["acc-x-url", "m-acc-x-url"],
    "yt-key": ["acc-yt-key", "m-acc-yt-key"],
    "tg-key": ["acc-tg-key", "m-acc-tg-key"],
    "x-key": ["acc-x-key", "m-acc-x-key"],
    "logo-op": ["acc-logo-op", "m-acc-logo-op"],
    "logo-zoom": ["acc-logo-zoom", "m-acc-logo-zoom"],
  };

  function chOurEls() {
    return [ $("ch-our-channel"), $("m-ch-our-channel") ].filter(Boolean);
  }

  function chOurVal() {
    const els = chOurEls();
    if (!els.length) return "";
    const a = (els[0].value || "").trim();
    const b = els[1] ? (els[1].value || "").trim() : "";
    return a || b;
  }

  function chSetOur(val) {
    const v = val == null ? "" : String(val);
    for (const el of chOurEls()) {
      if (document.activeElement === el) continue;
      el.value = v;
    }
  }

  function chListEls() {
    return [ $("ch-channels-ta"), $("m-ch-channels-ta") ].filter(Boolean);
  }

  function chSetListLines(channels) {
    const text = Array.isArray(channels) ? channels.join("\n") : "";
    for (const el of chListEls()) {
      if (document.activeElement === el) continue;
      el.value = text;
    }
  }

  function chListVal() {
    const els = chListEls();
    if (!els.length) return "";
    if (els.length === 1) return els[0].value || "";
    if (document.activeElement === els[1]) return els[1].value || "";
    if (document.activeElement === els[0]) return els[0].value || "";
    return (els[0].value || els[1].value || "");
  }

  function setAdminTab(tab) {
    const allowed = ["home", "channels", "look"];
    const t = allowed.indexOf(tab) >= 0 ? tab : "home";
    const homeD = $("d-view-home");
    const chD = $("d-view-channels");
    const lookD = $("d-view-look");
    if (homeD) homeD.hidden = t !== "home";
    if (chD) chD.hidden = t !== "channels";
    if (lookD) lookD.hidden = t !== "look";
    const mHome = $("m-view-home");
    const mCh = $("m-view-channels");
    const mLook = $("m-view-look");
    if (mHome) mHome.hidden = t !== "home";
    if (mCh) mCh.hidden = t !== "channels";
    if (mLook) mLook.hidden = t !== "look";
    document.querySelectorAll("[data-admin-tab]").forEach((a) => {
      a.classList.toggle("on", a.getAttribute("data-admin-tab") === t);
    });
    document.querySelectorAll(".m-nav-item[data-mnav]").forEach((a) => {
      a.classList.toggle("on", a.getAttribute("data-mnav") === t);
    });
    const mt = $("m-page-title");
    if (mt) {
      if (t === "channels") mt.textContent = "📻 Канали";
      else if (t === "look") mt.textContent = "📻 Вигляд";
      else mt.textContent = "📻 RadioStream";
    }
  }

  function accEls(name) {
    const ids = ACC_IDS[name];
    if (!ids) return [];
    return ids.map((id) => $(id)).filter(Boolean);
  }

  function accPairVal(name) {
    const els = accEls(name);
    if (!els.length) return "";
    const a = (els[0].value || "").trim();
    const b = els[1] ? (els[1].value || "").trim() : "";
    return a || b;
  }

  function accSetPair(name, val) {
    const v = val == null ? "" : String(val);
    for (const el of accEls(name)) {
      if (document.activeElement === el) continue;
      el.value = v;
    }
  }

  function accClear(name) {
    for (const el of accEls(name)) el.value = "";
  }

  function renderAccFormFields(st) {
    const s = st.settings || {};
    accSetPair("tg-url", s.telegram_server_url || "");
    accSetPair("x-url", s.x_stream_server_url || "");
    if (s.logo_opacity != null) accSetPair("logo-op", String(s.logo_opacity));
    if (s.logo_zoom != null) accSetPair("logo-zoom", String(s.logo_zoom));

    const lo =
      s.logo_opacity != null && !Number.isNaN(Number(s.logo_opacity))
        ? Number(s.logo_opacity)
        : "—";
    const lz =
      s.logo_zoom != null && !Number.isNaN(Number(s.logo_zoom))
        ? Number(s.logo_zoom)
        : "—";
    setText(
      "d-look-summary",
      "Логотип: прозорість " + lo + ", масштаб " + lz
    );
    setText("m-look-summary", "Лого: " + lo + " · " + lz);
  }

  /** Прев’ю файлу логотипу з /api/logo (bust — оновити кеш після завантаження нового файлу). */
  function updateLogoPreview(bust) {
    const qs = bust != null ? "?t=" + bust : "";
    const url = "/api/logo" + qs;
    function wire(idImg, idPh) {
      const img = $(idImg);
      const ph = $(idPh);
      if (!img) return;
      img.onload = function () {
        img.style.display = "";
        if (ph) ph.style.display = "none";
      };
      img.onerror = function () {
        img.style.display = "none";
        if (ph) ph.style.display = "";
      };
      img.src = url;
    }
    wire("d-look-logo-preview", "d-look-logo-placeholder");
    wire("m-look-logo-preview", "m-look-logo-placeholder");
  }

  async function saveLogoLookFromInputs() {
    const patch = {};
    const lo = accPairVal("logo-op");
    const lz = accPairVal("logo-zoom");
    if (lo !== "") {
      const n = parseFloat(lo.replace(",", "."));
      if (!Number.isNaN(n)) patch.logo_opacity = Math.max(0, Math.min(1, n));
    }
    if (lz !== "") {
      const n = parseFloat(lz.replace(",", "."));
      if (!Number.isNaN(n)) patch.logo_zoom = Math.max(0.05, Math.min(8, n));
    }
    if (Object.keys(patch).length === 0) return;
    try {
      await api("POST", "/api/settings", patch);
      await refresh();
    } catch (err) {
      toast(err.message);
    }
  }

  async function uploadLogoFromFileInput(ev) {
    const inp = ev.target;
    if (!inp || !inp.files || !inp.files[0]) return;
    try {
      const fd = new FormData();
      fd.append("file", inp.files[0]);
      const r = await fetch("/api/settings/logo", { method: "POST", body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.error || r.statusText);
      inp.value = "";
      const other = inp.id === "acc-logo-file" ? $("m-acc-logo-file") : $("acc-logo-file");
      if (other) other.value = "";
      await refresh();
      updateLogoPreview(Date.now());
      toast("Логотип збережено");
    } catch (err) {
      toast(err.message);
    }
  }

  function debounce(fn, ms) {
    let t = null;
    return function () {
      const args = arguments;
      const self = this;
      clearTimeout(t);
      t = setTimeout(function () {
        fn.apply(self, args);
      }, ms);
    };
  }

  const debouncedSaveLogoLook = debounce(saveLogoLookFromInputs, 400);

  function bindLookPanelAutoSave() {
    accEls("logo-op").forEach((el) => {
      el.addEventListener("input", function () {
        debouncedSaveLogoLook();
      });
    });
    accEls("logo-zoom").forEach((el) => {
      el.addEventListener("input", function () {
        debouncedSaveLogoLook();
      });
    });
    const f1 = $("acc-logo-file");
    const f2 = $("m-acc-logo-file");
    [f1, f2].forEach((inp) => {
      if (inp) inp.addEventListener("change", uploadLogoFromFileInput);
    });
  }

  function renderChannelsFields(st) {
    const s = st.settings || {};
    chSetOur(s.our_channel_url || "");
    chSetListLines(st.channels || []);
  }

  function render(st) {
    last = st;
    syncServerClock(st);
    renderNow(st);
    renderQueue(st);
    renderPlatforms(st);
    renderFfmpegReToggle(st);
    renderAccFormFields(st);
    renderChannelsFields(st);
    renderBatchLine(st);
  }

  async function refresh() {
    try {
      const st = await api("GET", "/api/status");
      render(st);
    } catch (e) {
      toast("API: " + e.message);
    }
  }

  async function apiSkip() {
    try {
      await api("POST", "/api/control/next", {});
      toast("Наступне");
      await refresh();
    } catch (e) {
      toast(e.message);
    }
  }

  async function apiStop() {
    try {
      await api("POST", "/api/broadcast/stop", {});
      toast("Ефір зупинено");
      await refresh();
    } catch (e) {
      toast(e.message);
    }
  }

  async function apiStart() {
    try {
      await api("POST", "/api/broadcast/start", {});
      toast("Ефір запущено");
      await refresh();
    } catch (e) {
      toast(e.message);
    }
  }

  async function rescanOurVideos() {
    try {
      await api("POST", "/api/our-videos/rescan", {});
      toast("Кеш «наших відео» оновлено");
      await refresh();
    } catch (e) {
      toast(e.message);
    }
  }

  async function postSetting(patch) {
    try {
      await api("POST", "/api/settings", patch);
      await refresh();
    } catch (e) {
      toast(e.message);
    }
  }

  async function delQueueIdx(idx) {
    try {
      await api("DELETE", "/api/queue/" + idx, undefined);
      toast("Видалено з черги");
      await refresh();
    } catch (e) {
      toast(e.message);
    }
  }

  function MH_addToQueue() {
    const inp = $("add-url-inp");
    const url = inp && inp.value.trim();
    if (!url) {
      toast("Введіть посилання");
      return;
    }
    const pri = window._mh_pri || "med";
    const position = pri === "high" ? "front" : "back";
    api("POST", "/api/queue/add", { type: "url", url: url, position: position })
      .then(() => {
        toast("Додано до черги");
        if (inp) inp.value = "";
        if (typeof closeDrawer === "function") closeDrawer();
        return refresh();
      })
      .catch((e) => toast(e.message));
  }

  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-mh]");
    if (!t) return;
    const act = t.getAttribute("data-mh");
    if (act === "skip") {
      e.preventDefault();
      apiSkip();
    }
    if (act === "del") {
      e.preventDefault();
      const idx = parseInt(t.getAttribute("data-idx"), 10);
      if (!Number.isNaN(idx)) delQueueIdx(idx);
    }
  });

  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-setting-key]");
    if (!t) return;
    if (t.disabled) return;
    const key = t.getAttribute("data-setting-key");
    if (!last || !key) return;
    if (key === "ffmpeg_re_input" && last.broadcasting) return;
    const cur = !!last.settings[key];
    const patch = {};
    patch[key] = !cur;
    postSetting(patch);
  });

  document.addEventListener("click", (e) => {
    const h = e.target.closest(".acc-head");
    if (!h) return;
    e.preventDefault();
    const item = h.closest(".acc-item");
    if (!item) return;
    const open = item.classList.toggle("open");
    h.setAttribute("aria-expanded", open ? "true" : "false");
  });

  async function accSaveYt() {
    const k = accPairVal("yt-key");
    if (!k) {
      toast("Введіть стрім-ключ");
      return;
    }
    try {
      await api("POST", "/api/settings", { youtube_stream_key: k });
      accClear("yt-key");
      toast("YouTube: ключ збережено");
      await refresh();
    } catch (err) {
      toast(err.message);
    }
  }

  async function accSaveTgUrl() {
    const url = accPairVal("tg-url");
    try {
      await api("POST", "/api/settings", { telegram_server_url: url });
      toast("Telegram: URL збережено");
      await refresh();
    } catch (err) {
      toast(err.message);
    }
  }

  async function accSaveTgKey() {
    const k = accPairVal("tg-key");
    if (!k) {
      toast("Введіть стрім-ключ");
      return;
    }
    try {
      await api("POST", "/api/settings", { telegram_stream_key: k });
      accClear("tg-key");
      toast("Telegram: ключ збережено");
      await refresh();
    } catch (err) {
      toast(err.message);
    }
  }

  async function accSaveXUrl() {
    const url = accPairVal("x-url");
    try {
      await api("POST", "/api/settings", { x_stream_server_url: url });
      toast("X: ingest URL збережено");
      await refresh();
    } catch (err) {
      toast(err.message);
    }
  }

  async function accSaveXKey() {
    const k = accPairVal("x-key");
    if (!k) {
      toast("Введіть стрім-ключ");
      return;
    }
    try {
      await api("POST", "/api/settings", { x_stream_key: k });
      accClear("x-key");
      toast("X: ключ збережено");
      await refresh();
    } catch (err) {
      toast(err.message);
    }
  }

  async function chSaveOurChannel() {
    const url = chOurVal();
    try {
      await api("POST", "/api/settings", { our_channel_url: url });
      toast("Посилання на наш канал збережено");
      await refresh();
    } catch (err) {
      toast(err.message);
    }
  }

  async function chSaveChannelsList() {
    const raw = chListVal();
    const lines = raw
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      await api("PUT", "/api/channels", { channels: lines });
      toast("Список каналів збережено");
      await refresh();
    } catch (err) {
      toast(err.message);
    }
  }

  window.apiSkip = apiSkip;
  window.apiStop = apiStop;
  window.apiStart = apiStart;
  window.rescanOurVideos = rescanOurVideos;
  window.MH_addToQueue = MH_addToQueue;
  window.accSaveYt = accSaveYt;
  window.accSaveTgUrl = accSaveTgUrl;
  window.accSaveTgKey = accSaveTgKey;
  window.accSaveXUrl = accSaveXUrl;
  window.accSaveXKey = accSaveXKey;
  window.chSaveOurChannel = chSaveOurChannel;
  window.chSaveChannelsList = chSaveChannelsList;
  window.setAdminTab = setAdminTab;

  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-admin-tab]");
    if (!a) return;
    e.preventDefault();
    setAdminTab(a.getAttribute("data-admin-tab") || "home");
  });

  function tickClock() {
    if (last) updateBroadcastTimer(last);
  }

  function init() {
    bindLookPanelAutoSave();
    refresh().then(function () {
      updateLogoPreview(Date.now());
    });
    pollTimer = setInterval(refresh, 2500);
    setInterval(tickClock, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
