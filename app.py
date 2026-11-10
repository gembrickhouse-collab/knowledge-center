import os, time, threading
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, request, render_template_string
import knowledge_engine as ke

app = Flask(__name__)
MT_ZONE = ZoneInfo("America/Denver")
SCHED_STATE = {"last_check": "--", "status": "BOOTING"}


def _bg_scheduler():
    while True:
        try:
            now_s = datetime.now(MT_ZONE).strftime("%Y-%m-%d %H:%M:%S MT")
            has_key = bool(os.getenv("GEMINI_API_KEY", "").strip())
            if has_key:
                ke.check_and_run_daily_drop()
                SCHED_STATE["status"] = "ONLINE • 08:30 MT Auto-Drop Armed (Art + Universe + Matrix)"
            else:
                SCHED_STATE["status"] = "STANDBY • Missing GEMINI_API_KEY"
            SCHED_STATE["last_check"] = now_s
        except Exception as e:
            SCHED_STATE["status"] = f"WARN: {e}"
        time.sleep(60)


threading.Thread(target=_bg_scheduler, daemon=True).start()


@app.route("/health")
def health():
    return jsonify({"ok": True, "scheduler": SCHED_STATE})


@app.route("/state")
def state():
    return jsonify({"ok": True, "scheduler": SCHED_STATE, "curriculum": ke.load_curriculum()})


@app.route("/api/deep_dive", methods=["POST"])
def api_deep_dive():
    b = request.get_json(force=True)
    try:
        les = ke.generate_deep_dive_for_lesson(b["track"], int(b["seq"]))
        return jsonify({"ok": True, "lesson": les})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/gallery", methods=["POST"])
def api_gallery():
    b = request.get_json(force=True)
    try:
        les = ke.generate_gallery_for_lesson(b["track"], int(b["seq"]))
        return jsonify({"ok": True, "lesson": les})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ask", methods=["POST"])
def api_ask():
    b = request.get_json(force=True)
    try:
        les = ke.ask_architect_on_lesson(b["track"], int(b["seq"]), b.get("question", ""))
        return jsonify({"ok": True, "lesson": les})
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
  header { padding: 16px; border-bottom: 1px solid var(--border); background: #090d13; text-align: center; }
  h1 { margin: 0; font-size: 1.15rem; color: var(--accent); letter-spacing: 0.5px; }
  .sub { font-size: 0.76rem; color: var(--muted); margin-top: 5px; }
  .tabs { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; padding: 12px 16px; }
  .tab { background: var(--card); color: var(--fg); border: 1px solid var(--border); padding: 8px 14px; border-radius: 6px; cursor: pointer; font-family: inherit; font-weight: bold; font-size: 0.82rem; text-decoration: none; }
  .tab.active { background: var(--accent); color: #090d13; border-color: var(--accent); }
  .wrap { max-width: 1120px; margin: 0 auto; padding: 8px 14px 48px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 14px; margin-bottom: 14px; }
  .card-grid { display: flex; gap: 16px; align-items: flex-start; }
  @media (max-width: 740px) { .card-grid { flex-direction: column; } .plate-box { width: 100% !important; } }
  .card-main { flex: 1; min-width: 0; }
  .meta { font-size: 0.75rem; color: var(--muted); margin-bottom: 6px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .pill { background: #2d2208; color: var(--amber); border: 1px solid var(--amber); padding: 1px 6px; border-radius: 4px; font-weight: bold; font-size: 0.7rem; }
  .title { font-size: 1.02rem; font-weight: bold; color: #f0f6fc; margin-bottom: 8px; }
  .core { font-size: 0.86rem; line-height: 1.55; color: #c9d1d9; margin-bottom: 8px; }
  .maker { font-size: 0.82rem; line-height: 1.5; color: var(--amber); background: #141921; border-left: 3px solid var(--amber); padding: 8px 10px; border-radius: 4px; }
  .plate-box { width: 255px; flex-shrink: 0; background: #090d13; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; cursor: pointer; }
  .plate-box img { width: 100%; height: 175px; object-fit: cover; display: block; background: #090d13; }
  .plate-cap { font-size: 0.7rem; color: var(--muted); padding: 6px 8px; line-height: 1.35; }
  .schem-box { border-color: #238636 !important; background: #060d0a !important; }
  .schem-box svg { width: 100%; height: auto; display: block; }
  pre.code { background: #090d13; border: 1px solid #238636; color: #7ee787; padding: 10px; border-radius: 6px; overflow-x: auto; font-size: 0.78rem; line-height: 1.45; margin-top: 10px; }
  .decode-row { background: #0b1017; border-left: 3px solid var(--green); padding: 6px 10px; margin-top: 6px; font-size: 0.79rem; }
  .decode-code { color: #79c0ff; font-weight: bold; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  .btn { background: #21262d; color: var(--fg); border: 1px solid var(--border); border-radius: 5px; padding: 6px 11px; font-family: inherit; font-size: 0.77rem; font-weight: bold; cursor: pointer; }
  .btn:hover { border-color: var(--accent); color: var(--accent); }
  .drawer { margin-top: 12px; padding: 12px; background: #090d13; border: 1px solid var(--border); border-radius: 6px; font-size: 0.84rem; line-height: 1.65; white-space: pre-wrap; color: #d0d7de; }
  .gal-strip { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; margin-top: 12px; }
  .gal-item { background: #090d13; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; cursor: pointer; }
  .gal-item img { width: 100%; height: 130px; object-fit: cover; display: block; }
  .gal-item div { padding: 6px; font-size: 0.7rem; color: var(--muted); }
  .ask-bar { display: flex; gap: 6px; margin-top: 10px; }
  .ask-bar input { flex: 1; background: #090d13; color: var(--fg); border: 1px solid var(--border); border-radius: 5px; padding: 7px 10px; font-family: inherit; font-size: 0.8rem; }
  .qa-item { margin-top: 8px; padding: 9px 11px; background: #0c131d; border-left: 3px solid var(--purple); border-radius: 4px; font-size: 0.81rem; line-height: 1.55; white-space: pre-wrap; }
  #lightbox { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.88); z-index:999; align-items:center; justify-content:center; flex-direction:column; padding:18px; }
  #lightbox img { max-width:94vw; max-height:80vh; border:1px solid var(--border); border-radius:6px; }
  #lightbox p { color:var(--fg); font-size:0.82rem; max-width:760px; text-align:center; margin-top:10px; }
</style>
</head>
<body>
<header>
  <h1>{{ header_icon }} {{ page_title }}</h1>
  <div class="sub" id="sched">Syncing telemetry...</div>
</header>
<div class="tabs">
  {% if mode == 'matrix' %}
    <button class="tab active" onclick="switchTrack('matrix')">🧬 MATRIX CODE ANATOMY</button>
    <a class="tab" href="/">🎨 SWITCH TO KNOWLEDGE CENTER (ART + UNIVERSE) ↗</a>
  {% else %}
    <button class="tab active" id="tab-art" onclick="switchTrack('art')">🎨 ART ENDURANCE</button>
    <button class="tab" id="tab-universe" onclick="switchTrack('universe')">🌌 PHYSICS OF TIME</button>
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
let CUR_TRACK = "{{ default_track }}";
let OPEN_DD = {};
let OPEN_GAL = {};

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

async function loadState() {
  const r = await fetch('/state');
  const j = await r.json();
  DATA = j.curriculum;
  document.getElementById('sched').textContent = j.scheduler.status + '  |  Last Check: ' + j.scheduler.last_check;
  if (document.getElementById('tab-art') && DATA.tracks.art) {
    document.getElementById('tab-art').textContent = `🎨 ART ENDURANCE (${DATA.tracks.art.lessons.length})`;
    document.getElementById('tab-universe').textContent = `🌌 PHYSICS OF TIME (${DATA.tracks.universe.lessons.length})`;
  }
  renderFeed();
}

function switchTrack(t) {
  CUR_TRACK = t;
  document.querySelectorAll('button.tab').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('tab-' + t);
  if (btn) btn.classList.add('active');
  renderFeed();
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function renderFeed() {
  const feed = document.getElementById('feed');
  const lessons = ((DATA.tracks[CUR_TRACK] || {}).lessons || []).slice().reverse();
  feed.innerHTML = lessons.map(l => {
    const key = CUR_TRACK + '_' + l.seq;
    const plate = (CUR_TRACK === 'matrix') ? `
      <div class="plate-box schem-box" onclick="zoomSvg('${esc(l.diagram_type || 'pipeline')}', '${esc(l.title)}')">
        ${buildSchematicSvg(l.diagram_type || 'pipeline')}
        <div class="plate-cap" style="color:#7ee787;background:#0d1914;">📐 Data-Flow Blueprint • 🔍 Tap to Zoom</div>
      </div>` : (l.image_url ? `
      <div class="plate-box" onclick="zoomImg('${esc(l.image_url)}', '${esc(l.image_caption || l.title)}')">
        <img src="${esc(l.image_url)}" loading="lazy">
        <div class="plate-cap">📸 ${esc(l.image_caption || l.title)} • 🔍 Zoom</div>
      </div>` : '');
    const codeBlk = l.code_snippet ? `<pre class="code">${esc(l.code_snippet)}</pre>` : '';
    const decodes = (OPEN_DD[key] && l.line_decode) ? l.line_decode.map(d =>
      `<div class="decode-row"><span class="decode-code">${esc(d.code)}</span> → ${esc(d.meaning)}</div>`
    ).join('') : '';
    const ddBlk = (OPEN_DD[key] && l.deep_dive) ? `<div class="drawer"><strong>📖 MONOGRAPH / ARCHITECT DECODE:</strong>\n\n${esc(l.deep_dive)}</div>${decodes}` : '';
    const galBlk = (OPEN_GAL[key] && l.gallery && l.gallery.length) ? `<div class="gal-strip">${l.gallery.map(g => `
      <div class="gal-item" onclick="zoomImg('${esc(g.url)}','${esc((g.caption||'') + (g.study_note ? ' — ' + g.study_note : ''))}')">
        <img src="${esc(g.url)}" loading="lazy">
        <div>${esc(g.caption || '')}${g.study_note ? '<br><span style="color:#fbbf24">' + esc(g.study_note) + '</span>' : ''}</div>
      </div>`).join('')}</div>` : '';
    const qas = (l.qa_log || []).map(q => `<div class="qa-item"><strong style="color:#d2a8ff">Q: ${esc(q.q)}</strong> <span class="pill">[ ${esc(q.model)} ]</span>\n${esc(q.a)}</div>`).join('');

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
        ${CUR_TRACK !== 'matrix' ? `<button class="btn" id="galbtn-${key}" onclick="toggleGallery('${CUR_TRACK}', ${l.seq})">🖼️ ${(l.gallery && l.gallery.length >= 3) ? (OPEN_GAL[key] ? 'Hide Plates' : `More Plates (${l.gallery.length})`) : 'Curate 5 Plates'}</button>` : ''}
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

function updateLessonInMem(track, updated) {
  const arr = DATA.tracks[track].lessons;
  const idx = arr.findIndex(x => x.seq === updated.seq);
  if (idx >= 0) arr[idx] = updated;
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
  if (j.ok) { updateLessonInMem(track, j.lesson); OPEN_DD[key] = true; renderFeed(); }
  else { btn.textContent = '⚠️ Retry Deep Dive'; alert(j.error); }
}

async function toggleGallery(track, seq) {
  const key = track + '_' + seq;
  const les = DATA.tracks[track].lessons.find(x => x.seq === seq);
  if (les.gallery && les.gallery.length >= 3) {
    OPEN_GAL[key] = !OPEN_GAL[key];
    renderFeed();
    return;
  }
  const btn = document.getElementById('galbtn-' + key);
  btn.textContent = '⏳ Pulling Museum & Commons Plates...';
  const r = await fetch('/api/gallery', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({track, seq})});
  const j = await r.json();
  if (j.ok) { updateLessonInMem(track, j.lesson); OPEN_GAL[key] = true; renderFeed(); }
  else { btn.textContent = '⚠️ Retry Plates'; }
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
  if (j.ok) { updateLessonInMem(track, j.lesson); renderFeed(); }
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
