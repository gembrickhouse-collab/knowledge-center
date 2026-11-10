import os
import json
import time
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, render_template_string
import knowledge_engine as ke

app = Flask(__name__)
MT_TZ = ZoneInfo("America/Denver")
scheduler_state = {"status": "ARMED (08:30 MT Daily Auto-Drop)", "last_check": "--"}


def _daily_scheduler():
    while True:
        try:
            now_mt = datetime.now(MT_TZ)
            scheduler_state["last_check"] = now_mt.strftime("%Y-%m-%d %H:%M:%S MT")
            if os.getenv("GEMINI_API_KEY", "").strip():
                ke.check_and_run_daily_drop(force=False)
                scheduler_state["status"] = "ONLINE • 08:30 MT Auto-Drop Armed"
            else:
                scheduler_state["status"] = "ARCHIVE MODE (Add GEMINI_API_KEY on Render for 08:30 MT Auto-Drop)"
        except Exception as e:
            scheduler_state["status"] = f"WARN: {str(e)[:80]}"
        time.sleep(60)


threading.Thread(target=_daily_scheduler, daemon=True).start()


@app.route("/health")
def health():
    return jsonify({"ok": True, "scheduler": scheduler_state})


@app.route("/state")
def state():
    return jsonify({"scheduler": scheduler_state, "curriculum": ke.load_data()})


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Knowledge Command Center // Keyshawn</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; padding: 16px; background: #0d1117; color: #e6edf3; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
  .wrap { max-width: 1020px; margin: 0 auto; }
  .hdr { text-align: center; margin-bottom: 14px; }
  .hdr h1 { margin: 0; font-size: 1.3rem; color: #58a6ff; }
  .sub { font-size: 0.8rem; color: #8b949e; margin-top: 5px; }
  .bar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px; background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 10px 12px; margin-bottom: 14px; }
  .tabs { display: flex; flex-wrap: wrap; gap: 8px; }
  .tab-btn { cursor: pointer; background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 8px; padding: 7px 13px; font-weight: 700; font-size: 0.84rem; font-family: inherit; }
  .tab-btn.active { background: #1f6feb; color: #fff; border-color: #388bfd; }
  .controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .search-in { background: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 7px; padding: 6px 10px; font-size: 0.82rem; font-family: inherit; width: 190px; }
  .study-btn { cursor: pointer; background: rgba(245, 158, 11, 0.16); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.65); border-radius: 8px; padding: 6px 12px; font-weight: 700; font-size: 0.8rem; font-family: inherit; }
  .study-btn.active { background: #fbbf24; color: #0d1117; }
  .track-desc { background: #161b22; border-left: 3px solid #58a6ff; padding: 9px 12px; border-radius: 6px; font-size: 0.83rem; color: #c9d1d9; margin-bottom: 12px; }
  .lesson-card { background: #161b22; border: 1px solid #21262d; border-radius: 9px; margin-bottom: 8px; overflow: hidden; }
  .lesson-card summary { list-style: none; cursor: pointer; padding: 11px 14px; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px; font-size: 0.88rem; font-weight: 700; }
  .lesson-card summary::-webkit-details-marker { display: none; }
  .lesson-card summary:hover { background: #1c222b; }
  .amber-pill { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; color: #fbbf24; background: rgba(245, 158, 11, 0.18); border: 1px solid rgba(245, 158, 11, 0.65); }
  .tag-pill { display: inline-block; padding: 1px 7px; border-radius: 5px; font-size: 0.72rem; color: #8b949e; background: #0d1117; border: 1px solid #30363d; margin-left: 4px; font-weight: 400; }
  .l-body { padding: 12px 15px; background: #090d13; border-top: 1px solid #21262d; font-size: 0.85rem; line-height: 1.58; color: #c9d1d9; }
  .maker-box { margin-top: 10px; padding: 9px 12px; background: #161b22; border-left: 3px solid #fbbf24; border-radius: 6px; color: #e6edf3; }
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>🧠 KNOWLEDGE COMMAND CENTER</h1>
    <div class="sub">{{ sched.status }} &bull; Checked: {{ sched.last_check }}</div>
  </div>

  <div class="bar">
    <div class="tabs">
      {% for k, tr in data.tracks.items() %}
      <button class="tab-btn" id="tab-{{ k }}" onclick="selectTrack('{{ k }}')">{{ tr.icon }} {{ tr.title }} ({{ tr.lessons|length }})</button>
      {% endfor %}
    </div>
    <div class="controls">
      <input class="search-in" id="q-in" type="text" placeholder="Filter lessons/tags..." oninput="filterCards()">
      <button class="study-btn" id="study-btn" onclick="toggleStudy()">📚 Study Mode: Expand All</button>
    </div>
  </div>

  {% for k, tr in data.tracks.items() %}
  <div class="track-pane" id="pane-{{ k }}" style="display:none;">
    <div class="track-desc" style="border-left-color: {{ tr.accent }};">
      <strong>{{ tr.icon }} {{ tr.title }}:</strong> {{ tr.description }}
    </div>
    {% for item in tr.lessons|reverse %}
    <details class="lesson-card" data-search="{{ (item.title ~ ' ' ~ item.core ~ ' ' ~ item.maker ~ ' ' ~ (item.tags|join(' ')))|lower }}">
      <summary>
        <span>
          <span style="color:{{ tr.accent }};">#{{ "%03d"|format(item.seq) }}</span> &nbsp;{{ item.title }}
          {% for tg in item.tags %}<span class="tag-pill">#{{ tg }}</span>{% endfor %}
        </span>
        <span>
          <span style="color:#8b949e;font-weight:400;font-size:0.78rem;margin-right:6px;">{{ item.date }}</span>
          <span class="amber-pill">{{ item.model }}</span>
        </span>
      </summary>
      <div class="l-body">
        <div><strong>📖 Core Mechanics:</strong> {{ item.core }}</div>
        <div class="maker-box"><strong>🧵 Studio &amp; Systems Lens:</strong> {{ item.maker }}</div>
      </div>
    </details>
    {% endfor %}
  </div>
  {% endfor %}
</div>

<script>
var tracks = {{ data.tracks.keys()|list|tojson }};
function selectTrack(k) {
  localStorage.setItem("kc_track", k);
  tracks.forEach(function(t) {
    document.getElementById("pane-" + t).style.display = (t === k) ? "block" : "none";
    document.getElementById("tab-" + t).classList.toggle("active", t === k);
  });
  filterCards();
}
function applyStudy() {
  var on = localStorage.getItem("kc_study") === "1";
  var btn = document.getElementById("study-btn");
  btn.classList.toggle("active", on);
  btn.textContent = on ? "📚 Study Mode: ON (Collapse All)" : "📚 Study Mode: Expand All";
  document.querySelectorAll(".lesson-card").forEach(function(c) { c.open = on; });
}
function toggleStudy() {
  localStorage.setItem("kc_study", localStorage.getItem("kc_study") === "1" ? "0" : "1");
  applyStudy();
}
function filterCards() {
  var q = document.getElementById("q-in").value.toLowerCase().trim();
  document.querySelectorAll(".lesson-card").forEach(function(c) {
    var hay = c.getAttribute("data-search") || "";
    c.style.display = (!q || hay.indexOf(q) !== -1) ? "block" : "none";
  });
}
var savedTrack = localStorage.getItem("kc_track");
selectTrack(tracks.indexOf(savedTrack) !== -1 ? savedTrack : tracks[0]);
applyStudy();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML, data=ke.load_data(), sched=scheduler_state)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10001))
    app.run(host="0.0.0.0", port=port)
