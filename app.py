import os, time, threading
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, request, render_template_string
import knowledge_engine as ke

app = Flask(__name__)
MT_ZONE = ZoneInfo("America/Denver")
SCHED_STATE = {"last_check": "--", "status": "BOOTING", "worker_pid": 0}
_SCHED_PID_LOCK = threading.Lock()


def _bg_scheduler():
    ke.sync_curriculum_from_github()
    while True:
        try:
            now_s = datetime.now(MT_ZONE).strftime("%Y-%m-%d %H:%M:%S MT")
            has_key = bool(os.getenv("GEMINI_API_KEY", "").strip())
            SCHED_STATE["last_check"] = now_s
            if has_key:
                today_s = datetime.now(MT_ZONE).strftime("%Y-%m-%d")
                curr = ke.load_curriculum()
                missing = [
                    tk for tk in ("art", "universe", "matrix")
                    if not any(l.get("date") == today_s for l in curr.get("tracks", {}).get(tk, {}).get("lessons", []))
                ]
                now_hm = (datetime.now(MT_ZONE).hour, datetime.now(MT_ZONE).minute)
                if missing and now_hm >= (8, 30):
                    SCHED_STATE["status"] = f"ONLINE • Generating {today_s} Drop ({', '.join(missing)})..."
                    res = ke.check_and_run_daily_drop(force=False)
                    if res.get("errors"):
                        err_preview = "; ".join(f"{k}:{v[:40]}" for k, v in res["errors"].items())
                        SCHED_STATE["status"] = f"WARN • Drop Issue ({err_preview})"
                    else:
                        SCHED_STATE["status"] = "ONLINE • 08:30 MT Auto-Drop Complete & Armed"
                else:
                    SCHED_STATE["status"] = "ONLINE • 08:30 MT Auto-Drop Armed (Art + Universe + Matrix)"
            else:
                SCHED_STATE["status"] = "STANDBY • Missing GEMINI_API_KEY"
            SCHED_STATE["last_check"] = datetime.now(MT_ZONE).strftime("%Y-%m-%d %H:%M:%S MT")
        except Exception as e:
            SCHED_STATE["status"] = f"WARN: {e}"
        time.sleep(60)


def ensure_scheduler_started():
    pid = os.getpid()
    with _SCHED_PID_LOCK:
        if SCHED_STATE.get("worker_pid") != pid:
            SCHED_STATE["worker_pid"] = pid
            threading.Thread(target=_bg_scheduler, daemon=True).start()


@app.before_request
def _hook_sched():
    ensure_scheduler_started()


@app.route("/health")
def health():
    return jsonify({"ok": True, "scheduler": SCHED_STATE})


@app.route("/state")
def state():
    curr = ke.load_curriculum()
    curr.setdefault("favorites", [])
    return jsonify({
        "ok": True,
        "scheduler": SCHED_STATE,
        "curriculum": curr,
        "capacity": ke.get_capacity_telemetry(curr),
    })


@app.route("/api/sync_drop", methods=["POST"])
def api_sync_drop():
    ensure_scheduler_started()
    b = request.get_json(silent=True) or {}
    force_flag = bool(b.get("force", True))
    SCHED_STATE["status"] = "ONLINE • Running Manual Sync Drop..."
    res = ke.check_and_run_daily_drop(force=force_flag)
    SCHED_STATE["last_check"] = datetime.now(MT_ZONE).strftime("%Y-%m-%d %H:%M:%S MT")
    if res.get("errors"):
        SCHED_STATE["status"] = "WARN • Partial Drop: " + "; ".join(res["errors"].keys())
    else:
        SCHED_STATE["status"] = "ONLINE • 08:30 MT Auto-Drop Complete & Armed"
    curr = ke.load_curriculum()
    curr.setdefault("favorites", [])
    return jsonify({
        "ok": True,
        "result": res,
        "scheduler": SCHED_STATE,
        "curriculum": curr,
        "capacity": ke.get_capacity_telemetry(curr),
    })


@app.route("/api/deep_dive", methods=["POST"])
def api_deep_dive():
    b = request.get_json(force=True)
    try:
        les = ke.generate_deep_dive_for_lesson(b["track"], int(b["seq"]))
        return jsonify({"ok": True, "lesson": les, "capacity": ke.get_capacity_telemetry()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/gallery", methods=["POST"])
def api_gallery():
    b = request.get_json(force=True)
    try:
        les = ke.generate_gallery_for_lesson(
            b["track"],
            int(b["seq"]),
            append=bool(b.get("append", False)),
            custom_query=b.get("query", ""),
        )
        return jsonify({"ok": True, "lesson": les, "capacity": ke.get_capacity_telemetry()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/favorite", methods=["POST"])
def api_favorite():
    b = request.get_json(force=True)
    try:
        res = ke.toggle_favorite_plate(
            b.get("track", "art"),
            int(b.get("seq", 1)),
            b.get("url", ""),
            caption=b.get("caption", ""),
            study_note=b.get("study_note", ""),
            source=b.get("source", ""),
        )
        return jsonify({
            "ok": True,
            "favorited": res["favorited"],
            "favorites": res["favorites"],
            "capacity": ke.get_capacity_telemetry(),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/delete_plate", methods=["POST"])
def api_delete_plate():
    b = request.get_json(force=True)
    try:
        res = ke.delete_gallery_plate(b.get("track", "art"), int(b.get("seq", 1)), b.get("url", ""))
        return jsonify({"ok": True, "lesson": res["lesson"], "favorites": res["favorites"], "capacity": ke.get_capacity_telemetry()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ask", methods=["POST"])
def api_ask():
    b = request.get_json(force=True)
    try:
        les = ke.ask_architect_on_lesson(b["track"], int(b["seq"]), b.get("question", ""))
        return jsonify({"ok": True, "lesson": les, "capacity": ke.get_capacity_telemetry()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


WEB_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ page_title }}</title>
<style>
  :root {
    --bg: #0d1117; --card: #161b22; --border: #30363d; --fg: #e6edf3;
    --muted: #8b949e; --accent: {{ accent }}; --amber: #fbbf24; --green: #3fb950; --purple: #d2a8ff;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--fg); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
  header { padding: 14px 16px; border-bottom: 1px solid var(--border); background: #090d13; text-align: center; }
  h1 { margin: 0; font-size: 1.15rem; color: var(--accent); letter-spacing: 0.5px; }
  .sub { font-size: 0.75rem; color: var(--muted); margin-top: 5px; }
  .cap-bar { display: inline-flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: center; margin-top: 8px; padding: 5px 12px; background: #111720; border: 1px solid var(--border); border-radius: 999px; font-size: 0.71rem; color: #c9d1d9; }
  .cap-meter { width: 72px; height: 7px; background: #21262d; border-radius: 99px; overflow: hidden; display: inline-block; vertical-align: middle; border: 1px solid #30363d; }
  .cap-fill { height: 100%; background: linear-gradient(90deg, #3fb950, #fbbf24); transition: width 0.3s; }
  .tabs { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; padding: 12px 16px; }
  .tab { background: var(--card); color: var(--fg); border: 1px solid var(--border); padding: 8px 14px; border-radius: 6px; cursor: pointer; font-family: inherit; font-weight: bold; font-size: 0.82rem; text-decoration: none; }
  .tab.active { background: var(--accent); color: #090d13; border-color: var(--accent); }
  .wrap { max-width: 1120px; margin: 0 auto; padding: 8px 14px 48px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 14px; margin-bottom: 14px; transition: border-color 0.35s, box-shadow 0.35s; }
  .card.flash-jump { border-color: var(--amber); box-shadow: 0 0 0 2px rgba(251,191,36,0.35); }
  .card-grid { display: flex; gap: 16px; align-items: flex-start; }
  @media (max-width: 740px) { .card-grid { flex-direction: column; } .plate-box { width: 100% !important; } }
  .card-main { flex: 1; min-width: 0; }
  .meta { font-size: 0.75rem; color: var(--muted); margin-bottom: 6px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .pill { background: #2d2208; color: var(--amber); border: 1px solid var(--amber); padding: 1px 6px; border-radius: 4px; font-weight: bold; font-size: 0.7rem; }
  .title { font-size: 1.02rem; font-weight: bold; color: #f0f6fc; margin-bottom: 8px; }
  .core { font-size: 0.86rem; line-height: 1.55; color: #c9d1d9; margin-bottom: 8px; }
  .maker { font-size: 0.82rem; line-height: 1.5; color: var(--amber); background: #141921; border-left: 3px solid var(--amber); padding: 8px 10px; border-radius: 4px; }
  .plate-box { position: relative; width: 255px; flex-shrink: 0; background: #090d13; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; cursor: pointer; }
  .plate-box img { width: 100%; height: 175px; object-fit: cover; display: block; background: #090d13; }
  .plate-cap { font-size: 0.7rem; color: var(--muted); padding: 6px 8px; line-height: 1.35; }
  .star-btn { position: absolute; top: 7px; right: 7px; z-index: 4; background: rgba(9,13,19,0.84); color: #8b949e; border: 1px solid #30363d; border-radius: 999px; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; font-size: 0.92rem; cursor: pointer; transition: transform 0.15s, border-color 0.15s; }
  .star-btn:hover { transform: scale(1.1); border-color: var(--amber); color: var(--amber); }
  .star-btn.starred { color: var(--amber); border-color: var(--amber); background: rgba(45,34,8,0.9); }
  .schem-box { border-color: #238636 !important; background: #060d0a !important; }
  .schem-box svg { width: 100%; height: auto; display: block; }
  pre.code { background: #090d13; border: 1px solid #238636; color: #7ee787; padding: 10px; border-radius: 6px; overflow-x: auto; font-size: 0.78rem; line-height: 1.45; margin-top: 10px; }
  .decode-row { background: #0b1017; border-left: 3px solid var(--green); padding: 6px 10px; margin-top: 6px; font-size: 0.79rem; }
  .decode-code { color: #79c0ff; font-weight: bold; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  .btn { background: #21262d; color: var(--fg); border: 1px solid var(--border); border-radius: 5px; padding: 6px 11px; font-family: inherit; font-size: 0.77rem; font-weight: bold; cursor: pointer; }
  .btn:hover { border-color: var(--accent); color: var(--accent); }
  .drawer { margin-top: 12px; padding: 12px; background: #090d13; border: 1px solid var(--border); border-radius: 6px; font-size: 0.84rem; line-height: 1.65; white-space: pre-wrap; color: #d0d7de; }
  .gal-strip { display: grid; grid-template-columns: repeat(auto-fill, minmax(185px, 1fr)); gap: 10px; margin-top: 12px; }
  .gal-item { position: relative; background: #090d13; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; cursor: pointer; display: flex; flex-direction: column; }
  .gal-item img { width: 100%; height: 135px; object-fit: cover; display: block; background: #06090e; }
  .gal-item .gal-cap { padding: 6px 8px; font-size: 0.7rem; color: var(--muted); line-height: 1.35; flex: 1; }
  .gal-src { display: inline-block; margin-top: 3px; font-size: 0.64rem; color: #58a6ff; }
  .curate-bar { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; padding: 8px; background: #0b1017; border: 1px dashed #30363d; border-radius: 6px; align-items: center; }
  .curate-bar input { flex: 1; min-width: 200px; background: #090d13; color: var(--fg); border: 1px solid var(--border); border-radius: 5px; padding: 6px 10px; font-family: inherit; font-size: 0.78rem; }
  .fav-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 14px; }
  .fav-card { position: relative; background: var(--card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
  .fav-card img { width: 100%; height: 185px; object-fit: cover; cursor: pointer; display: block; background: #090d13; }
  .fav-body { padding: 10px; font-size: 0.76rem; flex: 1; display: flex; flex-direction: column; justify-content: space-between; gap: 8px; }
  .ask-bar { display: flex; gap: 6px; margin-top: 10px; }
  .ask-bar input { flex: 1; background: #090d13; color: var(--fg); border: 1px solid var(--border); border-radius: 5px; padding: 7px 10px; font-family: inherit; font-size: 0.8rem; }
  .qa-item { margin-top: 8px; padding: 9px 11px; background: #0c131d; border-left: 3px solid var(--purple); border-radius: 4px; font-size: 0.81rem; line-height: 1.55; white-space: pre-wrap; }
  #lightbox { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.88); z-index:999; align-items:center; justify-content:center; flex-direction:column; padding:18px; }
  #lightbox img { max-width:94vw; max-height:80vh; border:1px solid var(--border); border-radius:6px; }
  #lightbox p { color:var(--fg); font-size:0.82rem; max-width:760px; text-align:center; margin-top:10px; }
  .del-btn { position:absolute; top:8px; left:8px; width:28px; height:28px; border-radius:50%; background:rgba(9,13,19,0.84); border:1px solid #30363d; color:#8b949e; font-size:15px; font-weight:bold; line-height:1; cursor:pointer; display:flex; align-items:center; justify-content:center; z-index:4; transition:all 0.15s ease; }
  .del-btn:hover { background:#f85149; border-color:#ff7b72; color:#fff; transform:scale(1.08); }
</style>
</head>
<body>
<header>
  <h1>{{ header_icon }} {{ page_title }}</h1>
  <div class="sub" id="sched">Syncing telemetry...</div>
  <div class="cap-bar" id="cap-bar" style="display:none"></div>
</header>
<div class="tabs">
  {% if mode == 'matrix' %}
    <button class="tab active" id="tab-matrix" onclick="switchTrack('matrix')">🧬 MATRIX CODE ANATOMY</button>
    <a class="tab" href="/">🎨 SWITCH TO KNOWLEDGE CENTER (ART + UNIVERSE) ↗</a>
  {% else %}
    <button class="tab active" id="tab-art" onclick="switchTrack('art')">🎨 ART ENDURANCE</button>
    <button class="tab" id="tab-universe" onclick="switchTrack('universe')">🌌 PHYSICS OF TIME</button>
    <button class="tab" id="tab-favorites" onclick="switchTrack('favorites')" style="border-color:#fbbf24;">⭐ KEY'S FAVORITES (0)</button>
    <a class="tab" href="/matrix" style="border-color:#3fb950;color:#3fb950;">🧬 OPEN MATRIX CENTER ↗</a>
  {% endif %}
</div>
<div class="wrap" id="feed"></div>

<div id="lightbox" onclick="this.style.display='none'">
  <img id="lb-img" src="">
  <p id="lb-cap"></p>
</div>

<script>
let DATA = null;
let CAP = null;
let CUR_TRACK = "{{ default_track }}";
let OPEN_DD = {};
let OPEN_GAL = {};
let PLATE_REG = [];

const SCHEMATICS = {
  telemetry_bus: [["OANDA v20 API","#fbbf24"],["Render Cloud Loop","#3fb950"],["/state JSON Bus","#58a6ff"],["Daemon Thread (10s)","#d2a8ff"],["Keyless Ubuntu HUD","#3fb950"]],
  five_gate: [["G1 Clock/Spread","#3fb950"],["G2 9>21>200+ATR","#3fb950"],["G3 21EMA Zone","#3fb950"],["G4 RSI Trigger","#3fb950"],["G5 1% + Gemini","#fbbf24"]],
  canvas_coords: [["28 M15 OHLC[]","#58a6ff"],["Bounds Filter","#d2a8ff"],["py() Invert Y","#fbbf24"],["px() Slot X","#3fb950"],["tk.Canvas Pixels","#3fb950"]],
  git_loop: [["08:30 MT Trigger","#fbbf24"],["Gemini JSON","#d2a8ff"],["Base64 + SHA","#58a6ff"],["PUT GitHub API","#3fb950"],["Permanent Repo","#3fb950"]],
  cascade: [["Prompt + Schema","#58a6ff"],["3.8-Flash Try","#fbbf24"],["429/503 Catch","#f85149"],["3.5-Lite Fallback","#3fb950"],["Parsed Dict","#3fb950"]],
  cron_budget: [["GH Runner UTC","#58a6ff"],["08:32 Wake Pulse","#fbbf24"],["65s Tick Hold","#d2a8ff"],["Idle 15m Sleep","#8b949e"],["730h Saved!","#3fb950"]],
  desktop_gui: [[".desktop SVG","#3fb950"],["WM_CLASS Bind","#58a6ff"],["Label Hook","#fbbf24"],["Thread Lock","#d2a8ff"],["60fps X11 HUD","#3fb950"]],
  vault_crypto: [["Ciphertext SSD","#f85149"],["unlock (scrypt)","#fbbf24"],["FUSE RAM Mount","#58a6ff"],["git push TLS","#3fb950"],["lock (Unmount)","#3fb950"]]
};

function buildSchematicSvg(dtype) {
  const nodes = SCHEMATICS[dtype] || [["Input Stream","#58a6ff"],["Core Engine","#fbbf24"],["Guardrail","#d2a8ff"],["Persistence","#3fb950"]];
  const w = 320, h = 242, cx = 160, bw = 264, padY = 34;
  const slotH = (h - padY - 10) / nodes.length;
  let grid = '';
  for (let gx = 0; gx <= w; gx += 24) grid += `<line x1="${gx}" y1="0" x2="${gx}" y2="${h}" stroke="#0d1612" stroke-width="1"/>`;
  for (let gy = 0; gy <= h; gy += 24) grid += `<line x1="0" y1="${gy}" x2="${w}" y2="${gy}" stroke="#0d1612" stroke-width="1"/>`;
  let body = '';
  nodes.forEach((item, i) => {
    const label = esc(item[0]), col = item[1];
    const cy = Math.round(padY + (i + 0.45) * slotH);
    const bh = Math.min(26, Math.round(slotH * 0.66));
    body += `<rect x="${cx - bw/2}" y="${cy - bh/2}" width="${bw}" height="${bh}" rx="4" fill="#0d1914" stroke="${col}" stroke-width="1.3"/>`;
    body += `<text x="${cx}" y="${cy + 4}" fill="${col}" font-family="ui-monospace,monospace" font-size="10.5" font-weight="bold" text-anchor="middle">[${i+1}] ${label}</text>`;
    if (i < nodes.length - 1) {
      const y1 = cy + bh/2;
      const y2 = Math.round(padY + (i + 1.45) * slotH) - bh/2;
      body += `<line x1="${cx}" y1="${y1}" x2="${cx}" y2="${y2 - 3}" stroke="#3fb950" stroke-width="2"/>`;
      body += `<polygon points="${cx},${y2} ${cx-4},${y2-6} ${cx+4},${y2-6}" fill="#3fb950"/>`;
    }
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}">
    <rect width="${w}" height="${h}" fill="#060d0a"/>
    ${grid}
    <text x="12" y="18" fill="#3fb950" font-family="ui-monospace,monospace" font-size="9.5" font-weight="bold">⚡ BLUEPRINT // ${esc((dtype||'pipeline').toUpperCase())}</text>
    ${body}
  </svg>`;
}

function zoomSvg(dtype, title) {
  const svgStr = buildSchematicSvg(dtype);
  const uri = 'data:image/svg+xml;utf8,' + encodeURIComponent(svgStr);
  zoomImg(uri, '📐 Data-Flow Architecture Blueprint — ' + title);
}

function zoomImg(url, cap) {
  document.getElementById('lb-img').src = url;
  document.getElementById('lb-cap').textContent = cap || '';
  document.getElementById('lightbox').style.display = 'flex';
}

function zoomReg(idx) {
  const p = PLATE_REG[idx];
  if (!p) return;
  zoomImg(p.url, p.caption + (p.study_note ? ' — ' + p.study_note : ''));
}

function regPlate(obj) {
  const idx = PLATE_REG.length;
  PLATE_REG.push(obj);
  return idx;
}

function isStarred(url) {
  return ((DATA && DATA.favorites) || []).some(f => f.url === url);
}

function renderHeaderStats() {
  if (!DATA) return;
  if (document.getElementById('tab-art') && DATA.tracks.art) {
    document.getElementById('tab-art').textContent = `🎨 ART ENDURANCE (${DATA.tracks.art.lessons.length})`;
    document.getElementById('tab-universe').textContent = `🌌 PHYSICS OF TIME (${DATA.tracks.universe.lessons.length})`;
  }
  const favBtn = document.getElementById('tab-favorites');
  if (favBtn) {
    favBtn.textContent = `⭐ KEY'S FAVORITES (${(DATA.favorites || []).length})`;
  }
  const cb = document.getElementById('cap-bar');
  if (cb && CAP) {
    cb.style.display = 'inline-flex';
    const wPct = Math.max(2, Math.min(100, CAP.gh_pct * 4));
    const ramTxt = CAP.ram_mb ? `⚡ Render RAM: <strong>${CAP.ram_mb}/${CAP.ram_limit_mb} MB</strong> (${CAP.ram_pct}%)` : `⚡ Cloud State: <strong>Synced</strong>`;
    cb.innerHTML = `
      <span>💾 GitHub Vault: <strong>${CAP.json_kb} KB</strong> / ${CAP.gh_limit_mb} MB (${CAP.gh_pct}%) <span class="cap-meter"><span class="cap-fill" style="width:${wPct}%"></span></span></span>
      <span>•</span>
      <span>${ramTxt}</span>
      <span>•</span>
      <span style="color:#3fb950">🛣️ Auto-Drop Runway: <strong>~${CAP.runway_years} yrs</strong></span>
    `;
  }
}

async function loadState() {
  const r = await fetch('/state');
  const j = await r.json();
  DATA = j.curriculum;
  DATA.favorites = DATA.favorites || [];
  if (j.capacity) CAP = j.capacity;
  document.getElementById('sched').textContent = j.scheduler.status + '  |  Last Check: ' + j.scheduler.last_check;
  renderHeaderStats();
  renderFeed();
}

function switchTrack(t) {
  CUR_TRACK = t;
  document.querySelectorAll('button.tab').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('tab-' + t);
  if (btn) btn.classList.add('active');
  renderFeed();
}

function jumpToLesson(track, seq) {
  switchTrack(track);
  setTimeout(() => {
    const el = document.getElementById('card-' + track + '_' + seq);
    if (el) {
      el.scrollIntoView({behavior: 'smooth', block: 'center'});
      el.classList.add('flash-jump');
      setTimeout(() => el.classList.remove('flash-jump'), 2200);
    }
  }, 60);
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

async function deletePlateIdx(ev, idx) {
  ev.stopPropagation();
  const p = PLATE_REG[idx];
  if (!p) return;
  if (ev.currentTarget) { ev.currentTarget.textContent = "…"; }
  const r = await fetch("/api/delete_plate", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({track: p.track, seq: p.seq, url: p.url}) });
  const j = await r.json();
  if (j.ok) {
    const target = ((DATA.tracks[p.track] || {}).lessons || []).find(x => Number(x.seq) === Number(p.seq));
    if (target && j.lesson) target.gallery = j.lesson.gallery || [];
    DATA.favorites = j.favorites || [];
    if (j.capacity) CAP = j.capacity;
    GALLERY_OPEN[p.track + "_" + p.seq] = true;
    renderHeaderStats();
    renderFeed();
  }
}

async function toggleStarIdx(ev, idx) {
  ev.stopPropagation();
  const p = PLATE_REG[idx];
  if (!p) return;
  const r = await fetch('/api/favorite', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(p)
  });
  const j = await r.json();
  if (j.ok) {
    DATA.favorites = j.favorites;
    if (j.capacity) CAP = j.capacity;
    renderHeaderStats();
    renderFeed();
  }
}

function renderFavoritesView() {
  const feed = document.getElementById('feed');
  const favs = DATA.favorites || [];
  if (!favs.length) {
    feed.innerHTML = `<div class="card" style="text-align:center;padding:34px 18px;color:var(--muted);">
      <div style="font-size:1.5rem;margin-bottom:8px;">⭐</div>
      <strong style="color:var(--fg);">Key's Favorites Vault is empty right now.</strong><br><br>
      Tap the <strong>☆</strong> button in the top-right corner of any Art or Physics plate (or any curated gallery plate) to pin it permanently to GitHub with one-click Jump-to-Lesson recall.
    </div>`;
    return;
  }
  feed.innerHTML = `<div class="fav-grid">${favs.map(f => {
    const idx = regPlate({
      track: f.track, seq: f.seq, url: f.url,
      caption: f.caption || '', study_note: f.study_note || '', source: f.source || 'Archive'
    });
    return `<div class="fav-card">
      <button class="star-btn starred" title="Remove from Favorites" onclick="toggleStarIdx(event, ${idx})">⭐</button>
      <img src="${esc(f.url)}" loading="lazy" onclick="zoomReg(${idx})">
      <div class="fav-body">
        <div>
          <div style="color:#f0f6fc;font-weight:bold;line-height:1.35;">${esc(f.caption)}</div>
          ${f.study_note ? `<div style="color:#fbbf24;margin-top:4px;line-height:1.35;">${esc(f.study_note)}</div>` : ''}
          <div style="color:var(--muted);font-size:0.68rem;margin-top:5px;">${esc((f.track || '').toUpperCase())} #${String(f.seq).padStart(3,'0')} • ${esc(f.source || 'Archive')}</div>
        </div>
        <button class="btn" style="width:100%;border-color:#fbbf24;color:#fbbf24;" onclick="jumpToLesson('${esc(f.track)}', ${Number(f.seq)})">↗ Jump to #${String(f.seq).padStart(3,'0')}: ${esc((f.lesson_title || '').slice(0, 30))}</button>
      </div>
    </div>`;
  }).join('')}</div>`;
}

function renderFeed() {
  PLATE_REG = [];
  if (CUR_TRACK === 'favorites') {
    renderFavoritesView();
    return;
  }
  const feed = document.getElementById('feed');
  const lessons = ((DATA.tracks[CUR_TRACK] || {}).lessons || []).slice().reverse();
  feed.innerHTML = lessons.map(l => {
    const key = CUR_TRACK + '_' + l.seq;
    let plate = '';
    if (CUR_TRACK === 'matrix') {
      plate = `
      <div class="plate-box schem-box" onclick="zoomSvg('${esc(l.diagram_type || 'pipeline')}', '${esc(l.title)}')">
        ${buildSchematicSvg(l.diagram_type || 'pipeline')}
        <div class="plate-cap" style="color:#7ee787;background:#0d1914;">📐 Data-Flow Blueprint • 🔍 Tap to Zoom</div>
      </div>`;
    } else if (l.image_url) {
      const pIdx = regPlate({
        track: CUR_TRACK, seq: l.seq, url: l.image_url,
        caption: l.image_caption || l.title, study_note: '', source: l.image_source || 'Lead Plate'
      });
      const st = isStarred(l.image_url);
      plate = `
      <div class="plate-box" onclick="zoomReg(${pIdx})">
        <button class="star-btn ${st ? 'starred' : ''}" title="${st ? 'Saved in Favorites' : 'Star to Key&#39;s Favorites'}" onclick="toggleStarIdx(event, ${pIdx})">${st ? '⭐' : '☆'}</button>
        <img src="${esc(l.image_url)}" loading="lazy">
        <div class="plate-cap">📸 ${esc(l.image_caption || l.title)} • 🔍 Zoom</div>
      </div>`;
    }

    const codeBlk = l.code_snippet ? `<pre class="code">${esc(l.code_snippet)}</pre>` : '';
    const decodes = (OPEN_DD[key] && l.line_decode) ? l.line_decode.map(d =>
      `<div class="decode-row"><span class="decode-code">${esc(d.code)}</span> → ${esc(d.meaning)}</div>`
    ).join('') : '';
    const ddBlk = (OPEN_DD[key] && l.deep_dive) ? `<div class="drawer"><strong>📖 MONOGRAPH / ARCHITECT DECODE:</strong>

${esc(l.deep_dive)}</div>${decodes}` : '';

    const hasGal = l.gallery && l.gallery.length > 0;
    let galBlk = '';
    if (CUR_TRACK !== 'matrix' && OPEN_GAL[key]) {
      const itemsHtml = (l.gallery || []).map(g => {
        const gIdx = regPlate({
          track: CUR_TRACK, seq: l.seq, url: g.url,
          caption: g.caption || l.title, study_note: g.study_note || '', source: g.source || 'Archive'
        });
        const gst = isStarred(g.url);
        return `<div class="gal-item" onclick="zoomReg(${gIdx})">
          <button class="del-btn" title="Prune plate" onclick="deletePlateIdx(event, ${gIdx})">&times;</button><button class="star-btn ${gst ? 'starred' : ''}" title="${gst ? 'Saved in Favorites' : 'Star to Key&#39;s Favorites'}" onclick="toggleStarIdx(event, ${gIdx})">${gst ? '⭐' : '☆'}</button>
          <img src="${esc(g.url)}" loading="lazy">
          <div class="gal-cap">
            ${esc(g.caption || '')}
            ${g.study_note ? '<br><span style="color:#fbbf24">' + esc(g.study_note) + '</span>' : ''}
            ${g.source ? '<br><span class="gal-src">🏛️ ' + esc(g.source) + '</span>' : ''}
          </div>
        </div>`;
      }).join('');

      galBlk = `
        ${itemsHtml ? `<div class="gal-strip">${itemsHtml}</div>` : ''}
        <div class="curate-bar">
          <input id="curq-${key}" placeholder="Optional custom target (e.g. 'Ralph Steadman Fear and Loathing' or 'close-up texture')..." onkeydown="if(event.key==='Enter')curateMore('${CUR_TRACK}',${l.seq})">
          <button class="btn" id="morebtn-${key}" onclick="curateMore('${CUR_TRACK}', ${l.seq})" style="border-color:#fbbf24;color:#fbbf24;">➕ Curate 5 More Plates</button>
        </div>
      `;
    }

    const qas = (l.qa_log || []).map(q => `<div class="qa-item"><strong style="color:#d2a8ff">Q: ${esc(q.q)}</strong> <span class="pill">[ ${esc(q.model)} ]</span>
${esc(q.a)}</div>`).join('');

    return `<div class="card" id="card-${key}">
      <div class="card-grid">
        <div class="card-main">
          <div class="meta">
            <span>#${String(l.seq).padStart(3,'0')} • ${esc(l.date)}</span>
            <span class="pill">[ ${esc(l.model || 'ARCHIVE')} ]</span>
            ${l.file_ref ? `<span style="color:#3fb950">📂 ${esc(l.file_ref)}</span>` : ''}
          </div>
          <div class="title">${esc(l.title)}</div>
          <div class="core">${esc(l.core)}</div>
          <div class="maker">🧵 Studio / Craft Lens: ${esc(l.maker)}</div>
          ${codeBlk}
        </div>
        ${plate}
      </div>
      <div class="actions">
        <button class="btn" id="ddbtn-${key}" onclick="toggleDeepDive('${CUR_TRACK}', ${l.seq})">📖 ${l.deep_dive ? (OPEN_DD[key] ? 'Hide Deep Dive' : 'Deep Dive') : 'Generate Deep Dive (Gemini)'}</button>
        ${CUR_TRACK !== 'matrix' ? `<button class="btn" id="galbtn-${key}" onclick="toggleGallery('${CUR_TRACK}', ${l.seq})">🖼️ ${hasGal ? (OPEN_GAL[key] ? `Hide Plates (${l.gallery.length})` : `Plates (${l.gallery.length}) • +Curate`) : 'Curate 5 Plates'}</button>` : ''}
      </div>
      ${ddBlk}
      ${galBlk}
      ${qas}
      <div class="ask-bar">
        <input id="ask-${key}" placeholder="Ask Gemini Architect anything about #${String(l.seq).padStart(3,'0')}..." onkeydown="if(event.key==='Enter')sendAsk('${CUR_TRACK}',${l.seq})">
        <button class="btn" id="askbtn-${key}" onclick="sendAsk('${CUR_TRACK}', ${l.seq})" style="border-color:#d2a8ff;color:#d2a8ff;">💬 Ask Gemini</button>
      </div>
    </div>`;
  }).join('');
}

function updateLessonInMem(track, updated, cap) {
  const arr = DATA.tracks[track].lessons;
  const idx = arr.findIndex(x => x.seq === updated.seq);
  if (idx >= 0) arr[idx] = updated;
  if (cap) CAP = cap;
  renderHeaderStats();
}

async function toggleDeepDive(track, seq) {
  const key = track + '_' + seq;
  const les = DATA.tracks[track].lessons.find(x => x.seq === seq);
  if (les.deep_dive && les.deep_dive.length > 120) {
    OPEN_DD[key] = !OPEN_DD[key];
    renderFeed();
    return;
  }
  const btn = document.getElementById('ddbtn-' + key);
  btn.textContent = '⏳ Synthesizing Deep Dive via Gemini...';
  const r = await fetch('/api/deep_dive', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({track, seq})});
  const j = await r.json();
  if (j.ok) { updateLessonInMem(track, j.lesson, j.capacity); OPEN_DD[key] = true; renderFeed(); }
  else { btn.textContent = '⚠️ Retry Deep Dive'; alert(j.error); }
}

async function toggleGallery(track, seq) {
  const key = track + '_' + seq;
  const les = DATA.tracks[track].lessons.find(x => x.seq === seq);
  if (les.gallery && les.gallery.length >= 1) {
    OPEN_GAL[key] = !OPEN_GAL[key];
    renderFeed();
    return;
  }
  const btn = document.getElementById('galbtn-' + key);
  btn.textContent = '⏳ Pulling Multi-Archive Plates...';
  const r = await fetch('/api/gallery', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({track, seq, append:false})});
  const j = await r.json();
  if (j.ok) { updateLessonInMem(track, j.lesson, j.capacity); OPEN_GAL[key] = true; renderFeed(); }
  else { btn.textContent = '⚠️ Retry Plates'; }
}

async function curateMore(track, seq) {
  const key = track + '_' + seq;
  const inp = document.getElementById('curq-' + key);
  const q = inp ? inp.value.trim() : '';
  const btn = document.getElementById('morebtn-' + key);
  if (btn) { btn.textContent = '⏳ Curating 5 Fresh Plates...'; btn.disabled = true; }
  if (inp) inp.disabled = true;
  const r = await fetch('/api/gallery', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({track, seq, append: true, query: q})
  });
  const j = await r.json();
  if (j.ok) {
    updateLessonInMem(track, j.lesson, j.capacity);
    OPEN_GAL[key] = true;
    renderFeed();
  } else {
    if (btn) { btn.textContent = '⚠️ Retry +5 Plates'; btn.disabled = false; }
    if (inp) inp.disabled = false;
    alert(j.error || 'Failed to curate plates');
  }
}

async function sendAsk(track, seq) {
  const key = track + '_' + seq;
  const inp = document.getElementById('ask-' + key);
  const q = inp.value.trim();
  if (!q) return;
  const btn = document.getElementById('askbtn-' + key);
  btn.textContent = '⏳ Thinking...';
  inp.disabled = true;
  const r = await fetch('/api/ask', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({track, seq, question: q})});
  const j = await r.json();
  if (j.ok) { updateLessonInMem(track, j.lesson, j.capacity); renderFeed(); }
  else { btn.textContent = '💬 Ask Gemini'; inp.disabled = false; alert(j.error); }
}

loadState();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(
        WEB_TEMPLATE,
        mode="knowledge",
        default_track="art",
        page_title="KNOWLEDGE COMMAND CENTER // KEYSHAWN",
        header_icon="🧠",
        accent="#fbbf24",
    )


@app.route("/matrix")
def matrix_portal():
    return render_template_string(
        WEB_TEMPLATE,
        mode="matrix",
        default_track="matrix",
        page_title="MATRIX SYSTEMS COMMAND CENTER // KEYSHAWN",
        header_icon="🧬",
        accent="#3fb950",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5055")))
