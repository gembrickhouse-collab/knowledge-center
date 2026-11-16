import os
import json
import time
import threading
import subprocess
from flask import Blueprint, jsonify, render_template_string

oanda_bp = Blueprint("oanda_bp", __name__)
bot_status = {"running": False, "restarts": 0, "last_start": None, "worker_pid": None}
_oanda_lock = threading.Lock()

def run_trade_loop():
    """Runs trade_loop.py continuously and auto-restarts if it ever crashes."""
    while True:
        bot_status["running"] = True
        bot_status["last_start"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        print(f"--- [RENDER WORKER] Starting trade_loop.py at {bot_status['last_start']} ---", flush=True)
        
        process = subprocess.Popen(["python3", "-u", "trade_loop.py"])
        process.wait()
        
        bot_status["running"] = False
        bot_status["restarts"] += 1
        print(f"--- [RENDER WORKER] trade_loop.py exited (code {process.returncode}). Restarting in 10s... ---", flush=True)
        time.sleep(10)

def ensure_oanda_started():
    pid = os.getpid()
    with _oanda_lock:
        if bot_status.get("worker_pid") != pid:
            bot_status["worker_pid"] = pid
            threading.Thread(target=run_trade_loop, daemon=True).start()

def load_bot_state():
    if os.path.exists("bot_state.json"):
        try:
            with open("bot_state.json", "r") as f:
                return json.load(f)
        except Exception as e:
            return {"status": f"ERROR reading state: {e}", "account": {}, "open_trades": [], "pairs": {}}
    return {"status": "BOOTING (Waiting for first 15s scan...)", "account": {}, "open_trades": [], "pairs": {}}

@oanda_bp.route("/api/ping", methods=["GET", "POST", "HEAD"])
@oanda_bp.route("/ping", methods=["GET", "POST", "HEAD"])
def lightweight_ping():
    return jsonify({"ok": 1, "run": bot_status.get("running", False)}), 200

@oanda_bp.route("/health")
def health():
    return jsonify({
        "status": "online",
        "service": "oanda-5-gate-bot",
        "bot_thread": bot_status
    }), 200

@oanda_bp.route("/state")
def state():
    return jsonify({
        "status": "online",
        "bot_thread": bot_status,
        "telemetry": load_bot_state()
    }), 200

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="15">
    <title>OANDA 5-Gate Command Center</title>
    <style>
        :root {
            --bg: #090d16;
            --panel: #111827;
            --card: #1f2937;
            --border: #374151;
            --text: #f3f4f6;
            --muted: #9ca3af;
            --green: #10b981;
            --green-bg: rgba(16, 185, 129, 0.14);
            --red: #ef4444;
            --red-bg: rgba(239, 68, 68, 0.14);
            --amber: #f59e0b;
            --amber-bg: rgba(245, 158, 11, 0.14);
            --cyan: #38bdf8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: var(--bg);
            color: var(--text);
            font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
            padding: 18px;
            max-width: 1400px;
            margin: 0 auto;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px 20px;
            margin-bottom: 16px;
        }
        .title-block h1 {
            font-size: 1.25rem;
            color: var(--cyan);
            letter-spacing: 0.5px;
        }
        .title-block .sub {
            font-size: 0.78rem;
            color: var(--muted);
            margin-top: 4px;
        }
        .pulse-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: bold;
            background: var(--green-bg);
            color: var(--green);
            border: 1px solid var(--green);
        }
        .pulse-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--green);
            box-shadow: 0 0 8px var(--green);
        }
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin-bottom: 18px;
        }
        .kpi-card {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 14px 16px;
        }
        .kpi-label {
            font-size: 0.72rem;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }
        .kpi-val {
            font-size: 1.3rem;
            font-weight: bold;
            margin-top: 6px;
        }
        .pos-green { color: var(--green); }
        .pos-red { color: var(--red); }
        .pos-cyan { color: var(--cyan); }
        .section-title {
            font-size: 0.85rem;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }
        .trades-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }
        .trade-pill {
            background: var(--panel);
            border-left: 4px solid var(--green);
            border-top: 1px solid var(--border);
            border-right: 1px solid var(--border);
            border-bottom: 1px solid var(--border);
            border-radius: 6px;
            padding: 12px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .trade-pill.short { border-left-color: var(--red); }
        .pair-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
            gap: 16px;
            margin-bottom: 22px;
        }
        .pair-card {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .pair-top {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            border-bottom: 1px solid var(--border);
            padding-bottom: 10px;
        }
        .pair-name { font-size: 1.2rem; font-weight: bold; }
        .pair-price { font-size: 1.15rem; color: var(--cyan); font-weight: bold; }
        .bias-badge {
            padding: 3px 9px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: bold;
        }
        .bias-LONG { background: var(--green-bg); color: var(--green); border: 1px solid var(--green); }
        .bias-SHORT { background: var(--red-bg); color: var(--red); border: 1px solid var(--red); }
        .bias-NEUTRAL { background: var(--card); color: var(--muted); border: 1px solid var(--border); }
        .ind-row {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            background: var(--bg);
            padding: 10px;
            border-radius: 6px;
            border: 1px solid var(--border);
            font-size: 0.76rem;
        }
        .ind-box span { display: block; color: var(--muted); font-size: 0.68rem; }
        .ind-box strong { color: var(--text); font-size: 0.84rem; }
        .gates-list { display: flex; flex-direction: column; gap: 7px; }
        .gate-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 10px;
            border-radius: 6px;
            font-size: 0.78rem;
            background: var(--bg);
            border: 1px solid var(--border);
        }
        .gate-pass { border-left: 3px solid var(--green); }
        .gate-wait { border-left: 3px solid var(--amber); }
        .gate-label { font-weight: bold; color: var(--muted); min-width: 65px; }
        .gate-msg { text-align: right; word-break: break-word; }
        .gate-pass .gate-msg { color: var(--green); }
        .gate-wait .gate-msg { color: var(--amber); }
        .ai-box {
            background: rgba(56, 189, 248, 0.07);
            border: 1px dashed var(--cyan);
            border-radius: 6px;
            padding: 9px 12px;
            font-size: 0.76rem;
            color: var(--cyan);
        }
        details {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px 16px;
        }
        summary { cursor: pointer; color: var(--muted); font-size: 0.82rem; font-weight: bold; }
        pre {
            margin-top: 12px;
            color: #d1d5db;
            font-size: 0.75rem;
            overflow-x: auto;
        }
    </style>
</head>
<body>
    {% set acc = tel.get('account', {}) %}
    {% set nav = acc.get('nav', 0)|float %}
    {% set bal = acc.get('balance', 0)|float %}
    {% set upl = acc.get('unrealized_pl', 0)|float %}
    {% set risk = acc.get('risk_1pct', nav * 0.01)|float %}
    {% set trades = tel.get('open_trades', []) %}
    {% set pairs = tel.get('pairs', {}) %}

    <div class="header">
        <div class="title-block">
            <h1>🛰️ OANDA 5-GATE COMMAND CENTER</h1>
            <div class="sub">
                Account: {{ acc.get('id', '101-001-40528994-003') }} |
                Last Scan: {{ tel.get('timestamp', 'Syncing...') }} |
                Worker Restarts: {{ bot.get('restarts', 0) }} |
                Auto-Refresh: 15s
            </div>
        </div>
        <div style="display:flex; align-items:center; gap:14px;">
            <div style="position:relative; width:36px; height:36px;" title="15s Auto-Refresh Countdown">
                <svg width="36" height="36" style="transform:rotate(-90deg);">
                    <circle cx="18" cy="18" r="14" stroke="#374151" stroke-width="3.5" fill="none"/>
                    <circle id="ring" cx="18" cy="18" r="14" stroke="#38bdf8" stroke-width="3.5" fill="none"
                        stroke-dasharray="88" stroke-dashoffset="0" stroke-linecap="round"
                        style="transition:stroke-dashoffset 0.2s linear;"/>
                </svg>
                <span id="cd-txt" style="position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:0.65rem; color:#9ca3af; font-weight:bold;">15s</span>
            </div>
            <div class="pulse-badge">
                <span class="pulse-dot"></span>
                {{ tel.get('status', 'ONLINE') }}
            </div>
        </div>
        <script>
            let t = 150;
            setInterval(() => {
                t = Math.max(0, t - 1);
                const r = document.getElementById('ring');
                const c = document.getElementById('cd-txt');
                if (r) r.style.strokeDashoffset = 88 - (88 * (t / 150));
                if (c) c.textContent = Math.ceil(t / 10) + 's';
            }, 100);
        </script>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">Net Asset Value (NAV)</div>
            <div class="kpi-val pos-cyan">${{ "%.4f"|format(nav) }}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Account Balance</div>
            <div class="kpi-val">${{ "%.4f"|format(bal) }}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Unrealized P&L</div>
            <div class="kpi-val {{ 'pos-green' if upl >= 0 else 'pos-red' }}">
                {{ "+" if upl >= 0 else "" }}${{ "%.4f"|format(upl) }}
            </div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Gate 5 Firewall (1% Risk)</div>
            <div class="kpi-val">${{ "%.2f"|format(risk) }}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Open Positions</div>
            <div class="kpi-val">{{ trades|length }} Active</div>
        </div>
    </div>

    <div class="section-title">🏆 3-BOT $50 TOURNAMENT ARENA (1% FIREWALL PER SUB-ACCOUNT)</div>
    <div class="pair-grid" style="margin-bottom: 22px;">
        {% for bkey, b in tel.get('tournament', {}).items() %}
        {% set b_ret = b.get('net_return_pct', 0)|float %}
        <div class="pair-card" style="border-top: 3px solid {{ 'var(--green)' if b_ret > 0 else ('var(--red)' if b_ret < 0 else 'var(--cyan)') }};">
            <div class="pair-top">
                <div>
                    <div class="pair-name" style="color:var(--cyan); font-size:1.05rem;">{{ b.get('label') }}</div>
                    <div style="font-size:0.72rem; color:var(--muted); margin-top:2px;">ID: {{ b.get('account_id') }} &bull; {{ b.get('desc') }}</div>
                </div>
                <div style="text-align:right;">
                    <div class="pair-price">${{ "%.2f"|format(b.get('nav', 50.0)|float) }}</div>
                    <div style="font-size:0.75rem;" class="{{ 'pos-green' if b_ret >= 0 else 'pos-red' }}">{{ "%+.2f"|format(b_ret) }}%</div>
                </div>
            </div>
            <div class="ind-row">
                <div class="ind-box"><span>START BAL</span><strong>$50.00</strong></div>
                <div class="ind-box"><span>RECORD</span><strong>{{ b.get('wins', 0) }}W - {{ b.get('losses', 0) }}L</strong></div>
                <div class="ind-box"><span>1% FIREWALL</span><strong>${{ "%.2f"|format(b.get('risk_usd', 0.50)|float) }}</strong></div>
                <div class="ind-box"><span>GEOMETRY</span><strong>{{ b.get('sl_mult') }}x / 1:{{ b.get('rr_ratio') }}</strong></div>
            </div>
            <div style="font-size:0.76rem; color:var(--muted); display:flex; justify-content:space-between;">
                <span>Pairs: <strong style="color:var(--text);">{{ b.get('pairs_watched', [])|join(', ') }}</strong></span>
                <span>Gates Aligned: <strong style="color:var(--amber);">{{ b.get('max_gates_passed', 0) }} / 4</strong></span>
                <span>Open Trades: <strong style="color:var(--green);">{{ b.get('open_trades', [])|length }}</strong></span>
            </div>
        </div>
        {% endfor %}
    </div>

    <div class="section-title">ACTIVE SERVER-SIDE POSITIONS ({{ trades|length }})</div>
    <div class="trades-bar">
        {% if trades %}
            {% for t in trades %}
                {% set units = t.get('units', '0')|int %}
                {% set pl = t.get('pl', '0')|float %}
                <div class="trade-pill {{ 'short' if units < 0 else '' }}">
                    <div>
                        <div style="font-weight:bold; font-size:0.95rem;">
                            {{ t.get('pair') }}
                            <span style="color:{{ 'var(--green)' if units > 0 else 'var(--red)' }};">
                                {{ 'LONG' if units > 0 else 'SHORT' }} ({{ units }}u)
                            </span>
                        </div>
                        <div style="font-size:0.75rem; color:var(--muted); margin-top:3px;">
                            Entry: {{ t.get('price') }} | Trade ID: #{{ t.get('id') }}
                        </div>
                    </div>
                    <div style="font-size:1.1rem; font-weight:bold;" class="{{ 'pos-green' if pl >= 0 else 'pos-red' }}">
                        {{ "+" if pl >= 0 else "" }}${{ "%.4f"|format(pl) }}
                    </div>
                </div>
            {% endfor %}
        {% else %}
            <div class="trade-pill" style="border-left-color: var(--muted);">
                <div style="color: var(--muted); font-size: 0.82rem;">No open positions — stalking 5-Gate alignments...</div>
            </div>
        {% endif %}
    </div>

    <div class="section-title">5-GATE TELEMETRY MATRIX</div>
    <div class="pair-grid">
        {% for pair_name, p in pairs.items() %}
        <div class="pair-card">
            <div class="pair-top">
                <div>
                    <span class="pair-name">{{ pair_name }}</span>
                    <span class="bias-badge bias-{{ p.get('bias', 'NEUTRAL') }}" style="margin-left:8px;">
                        {{ p.get('bias', 'NEUTRAL') }}
                    </span>
                </div>
                <div class="pair-price">{{ p.get('price', '---') }}</div>
            </div>

            <div class="ind-row">
                <div class="ind-box">
                    <span>SPREAD</span>
                    <strong>{{ "%.1f"|format(p.get('spread_pips', 0)|float) }}p</strong>
                </div>
                <div class="ind-box">
                    <span>14 RSI</span>
                    <strong>{{ "%.1f"|format(p.get('rsi', 0)|float) }}</strong>
                </div>
                <div class="ind-box">
                    <span>ATR (M15)</span>
                    <strong>{{ "%.1f"|format(p.get('atr_pips', 0)|float) }}p</strong>
                </div>
                <div class="ind-box">
                    <span>EMA 9/21/200</span>
                    <strong>
                        {% if 'JPY' in pair_name %}
                            {{ "%.2f"|format(p.get('ema9', 0)|float) }} / {{ "%.2f"|format(p.get('ema200', 0)|float) }}
                        {% else %}
                            {{ "%.4f"|format(p.get('ema9', 0)|float) }} / {{ "%.4f"|format(p.get('ema200', 0)|float) }}
                        {% endif %}
                    </strong>
                </div>
            </div>

            <div class="gates-list">
                <div class="gate-item {{ 'gate-pass' if p.get('g1_pass') else 'gate-wait' }}">
                    <span class="gate-label">GATE 1</span>
                    <span class="gate-msg">{{ p.get('g1_msg', '---') }}</span>
                </div>
                <div class="gate-item {{ 'gate-pass' if p.get('g2_pass') else 'gate-wait' }}">
                    <span class="gate-label">GATE 2</span>
                    <span class="gate-msg">{{ p.get('g2_msg', '---') }}</span>
                </div>
                <div class="gate-item {{ 'gate-pass' if p.get('g3_pass') else 'gate-wait' }}">
                    <span class="gate-label">GATE 3</span>
                    <span class="gate-msg">{{ p.get('g3_msg', '---') }}</span>
                </div>
                <div class="gate-item {{ 'gate-pass' if p.get('g4_pass') else 'gate-wait' }}">
                    <span class="gate-label">GATE 4</span>
                    <span class="gate-msg">{{ p.get('g4_msg', '---') }}</span>
                </div>
                <div class="gate-item {{ 'gate-pass' if 'OPEN' in p.get('g5_msg', '') or 'EXECUTED' in p.get('g5_msg', '') else 'gate-wait' }}">
                    <span class="gate-label">GATE 5</span>
                    <span class="gate-msg">{{ p.get('g5_msg', '---') }}</span>
                </div>
            </div>

            <div class="ai-box">
                <strong>🧠 Gemini Gate Check:</strong> {{ p.get('ai_note', 'Awaiting Gate 1-4 alignment...') }}
            </div>
        </div>
        {% endfor %}
    </div>


    <style>
    .ledger-section { margin: 26px 0 18px; background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 16px; }
    .ledger-hdr { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #21262d; }
    .ledger-title { font-size: 1.08rem; font-weight: 700; color: #58a6ff; }
    .ledger-stats { font-size: 0.84rem; color: #8b949e; margin-top: 3px; }
    .study-btn { cursor: pointer; background: rgba(245, 158, 11, 0.16); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.65); border-radius: 8px; padding: 6px 12px; font-weight: 700; font-size: 0.82rem; }
    .study-btn.active { background: #fbbf24; color: #0d1117; }
    .baseline-banner { background: #0d1117; border-left: 3px solid #58a6ff; padding: 9px 12px; border-radius: 6px; font-size: 0.84rem; color: #c9d1d9; margin-bottom: 10px; }
    .trade-row-card { background: #0d1117; border: 1px solid #21262d; border-radius: 8px; margin-bottom: 8px; overflow: hidden; }
    .trade-row-card summary { list-style: none; cursor: pointer; padding: 11px 13px; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px; font-size: 0.88rem; font-weight: 600; }
    .trade-row-card summary::-webkit-details-marker { display: none; }
    .trade-row-card summary:hover { background: #131922; }
    .t-badge { padding: 2px 7px; border-radius: 5px; font-size: 0.74rem; font-weight: 700; }
    .t-long { background: rgba(63, 185, 80, 0.18); color: #3fb950; border: 1px solid rgba(63, 185, 80, 0.5); }
    .t-short { background: rgba(248, 81, 73, 0.18); color: #f85149; border: 1px solid rgba(248, 81, 73, 0.5); }
    .t-open { background: rgba(88, 166, 255, 0.18); color: #58a6ff; border: 1px solid rgba(88, 166, 255, 0.5); }
    .pl-win { color: #3fb950; font-weight: 700; }
    .pl-loss { color: #f85149; font-weight: 700; }
    .autopsy-body { padding: 12px 14px; border-top: 1px solid #21262d; background: #090d13; font-size: 0.83rem; line-height: 1.5; color: #c9d1d9; }
    .autopsy-step { margin-bottom: 7px; padding-left: 10px; border-left: 2px solid #3fb950; }
    .autopsy-step.g5 { border-left-color: #fbbf24; }
    .autopsy-step.ai { border-left-color: #d2a8ff; }
    .autopsy-exit { margin-top: 10px; padding: 9px 11px; border-radius: 6px; background: #161b22; border-left: 3px solid #58a6ff; }
    </style>

    {% set led = tel.get('ledger', {}) %}
    <div class="ledger-section" id="ledger-root">
        <div class="ledger-hdr">
            <div>
                <div class="ledger-title">📜 $50 Baseline Historical Ledger &amp; 5-Gate Anatomy</div>
                <div class="ledger-stats">
                    Start: <strong>${{ "%.2f"|format(led.get('baseline_usd', 50.0)) }}</strong> &bull;
                    Closed W/L: <strong>{{ led.get('closed_wins', 0) }}W – {{ led.get('closed_losses', 0) }}L</strong> ({{ "%+.2f"|format(led.get('closed_pl', 0.0)) }}) &bull;
                    Open P/L: <strong>{{ "%+.2f"|format(led.get('open_pl', 0.0)) }}</strong> &bull;
                    Live Equity: <strong style="color:#3fb950">${{ "%.2f"|format(led.get('net_equity', tel.get('account', {}).get('nav', 50.0))) }}</strong>
                </div>
            </div>
            <button type="button" class="study-btn" id="study-mode-btn" onclick="toggleStudyMode()">📚 Study Mode: Expand All</button>
        </div>

        <div class="baseline-banner">
            🏁 <strong>BASELINE DEPOSIT ({{ led.get('baseline_mt', 'Nov 08, 2026') }}):</strong> Account reset to <strong>${{ "%.2f"|format(led.get('baseline_usd', 50.0)) }}</strong> &mdash; Gate 5 1% Risk Firewall armed at $0.50 max risk per trade with 2x ATR Stop &amp; 1:3 Take Profit.
        </div>

        {% for tr in led.get('trades', [])|reverse %}
        <details class="trade-row-card" data-tid="{{ tr.trade_id }}">
            <summary>
                <span>
                    <strong>#{{ "%03d"|format(tr.seq) }}</strong> &nbsp;{{ tr.pair }}&nbsp;
                    <span class="t-badge {{ 't-long' if tr.bias == 'LONG' else 't-short' }}">{{ tr.bias }}</span>
                    {% if tr.status == 'OPEN' %}<span class="t-badge t-open">LIVE</span>{% endif %}
                    &nbsp;<span style="color:#8b949e;font-weight:400;">{{ tr.entry_mt }} @ {{ tr.entry_price }} &rarr; {{ tr.exit_price }} ({{ tr.duration }})</span>
                </span>
                <span>
                    <span class="{{ 'pl-win' if tr.pl_usd >= 0 else 'pl-loss' }}">{{ "%+.2f"|format(tr.pl_usd) }} USD ({{ "%+.1f"|format(tr.pips) }}p)</span>
                    &nbsp;&bull;&nbsp; <span style="color:#e6edf3;">Eq: ${{ "%.2f"|format(tr.bal_after) }}</span>
                </span>
            </summary>
            <div class="autopsy-body">
                <div class="autopsy-step"><strong>🟢 GATE 1 (Clock &amp; Spread):</strong> {{ tr.autopsy.g1 }}</div>
                <div class="autopsy-step"><strong>🟢 GATE 2 (200 EMA &amp; 9/21 Trend):</strong> {{ tr.autopsy.g2 }}</div>
                <div class="autopsy-step"><strong>🟢 GATE 3 (21 EMA Value Zone):</strong> {{ tr.autopsy.g3 }}</div>
                <div class="autopsy-step"><strong>🟢 GATE 4 (14 RSI &amp; Candle Trigger):</strong> {{ tr.autopsy.g4 }}</div>
                <div class="autopsy-step g5"><strong>🟡 GATE 5 (1% Risk &amp; Bracket Math):</strong> {{ tr.autopsy.g5 }}</div>
                <div class="autopsy-step ai"><strong>🧠 Gemini Sanity Check:</strong> {{ tr.autopsy.ai }}</div>
                <div class="autopsy-exit"><strong>🏁 EXIT / STATUS AUTOPSY:</strong> {{ tr.exit_exp }}</div>
            </div>
        </details>
        {% else %}
        <div style="color:#8b949e;font-size:0.86rem;padding:8px;">Syncing historical OANDA v20 transactions (refreshes automatically in ~15s)...</div>
        {% endfor %}
    </div>

    <script>
    function applySavedLedgerState() {
      var study = localStorage.getItem("oanda_study_mode") === "1";
      var openIds = JSON.parse(localStorage.getItem("oanda_open_tids") || "[]");
      var btn = document.getElementById("study-mode-btn");
      if (btn) {
        btn.classList.toggle("active", study);
        btn.textContent = study ? "📚 Study Mode: ON (Collapse All)" : "📚 Study Mode: Expand All";
      }
      document.querySelectorAll(".trade-row-card").forEach(function(el) {
        var tid = el.getAttribute("data-tid");
        el.open = study || openIds.indexOf(tid) !== -1;
        el.addEventListener("toggle", function() {
          if (localStorage.getItem("oanda_study_mode") === "1") return;
          var cur = JSON.parse(localStorage.getItem("oanda_open_tids") || "[]");
          if (el.open && cur.indexOf(tid) === -1) cur.push(tid);
          if (!el.open) cur = cur.filter(function(x) { return x !== tid; });
          localStorage.setItem("oanda_open_tids", JSON.stringify(cur));
        });
      });
    }
    function toggleStudyMode() {
      var next = localStorage.getItem("oanda_study_mode") === "1" ? "0" : "1";
      localStorage.setItem("oanda_study_mode", next);
      if (next === "0") localStorage.setItem("oanda_open_tids", "[]");
      applySavedLedgerState();
    }
    applySavedLedgerState();
    </script>

    <details>
        <summary>📂 View Raw Telemetry JSON (/state)</summary>
        <pre>{{ raw_json }}</pre>
    </details>
<style>
.amber-model-pill {
  display: inline-block;
  padding: 1px 8px;
  margin-right: 6px;
  border-radius: 999px;
  font-size: 0.76em;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: #fbbf24;
  background: rgba(245, 158, 11, 0.18);
  border: 1px solid rgba(245, 158, 11, 0.65);
  vertical-align: middle;
}
</style>
<script>
(function() {
  var rx = new RegExp(String.fromCharCode(91) + "([0-9.]+-flash[a-z0-9-]*)" + String.fromCharCode(93), "gi");
  function applyAmberBadges(root) {
    if (!root) return;
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
    var hits = [], n;
    while ((n = w.nextNode())) {
      if (n.parentNode && (!n.parentNode.classList || !n.parentNode.classList.contains("amber-model-pill"))) {
        rx.lastIndex = 0;
        if (rx.test(n.nodeValue)) hits.push(n);
      }
    }
    for (var i = 0; i < hits.length; i++) {
      var t = hits[i], parts = t.nodeValue.split(rx);
      var frag = document.createDocumentFragment();
      for (var j = 0; j < parts.length; j++) {
        if (j % 2 === 1) {
          var s = document.createElement("span");
          s.className = "amber-model-pill";
          s.textContent = parts[j];
          frag.appendChild(s);
        } else if (parts[j]) {
          frag.appendChild(document.createTextNode(parts[j]));
        }
      }
      if (t.parentNode) t.parentNode.replaceChild(frag, t);
    }
  }
  applyAmberBadges(document.body);
  new MutationObserver(function() { applyAmberBadges(document.body); }).observe(
    document.body, { childList: true, subtree: true, characterData: true }
  );
})();
</script>
</body>
</html>
"""

@oanda_bp.route("/")
def dashboard():
    tel = load_bot_state()
    raw_json = json.dumps({"bot_thread": bot_status, "telemetry": tel}, indent=2)
    return render_template_string(DASHBOARD_HTML, tel=tel, bot=bot_status, raw_json=raw_json)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
