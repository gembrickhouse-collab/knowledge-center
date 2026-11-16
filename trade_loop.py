import os
import time
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import pandas as pd
import ledger_engine
import numpy as np
from dotenv import load_dotenv
from google import genai

GEMINI_FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]

class _TaggedGeminiResponse:
    def __init__(self, resp, model_name):
        self._resp = resp
        self.model_tag = model_name.replace("gemini-", "")

    @property
    def text(self):
        raw = (getattr(self._resp, "text", "") or "").strip()
        return f"[{self.model_tag}] {raw}" if raw else f"[{self.model_tag}]"

    def __getattr__(self, name):
        return getattr(self._resp, name)

def _call_gemini_with_fallback(call_fn):
    last_err = None
    for m in GEMINI_FALLBACK_MODELS:
        try:
            return _TaggedGeminiResponse(call_fn(m), m)
        except Exception as e:
            last_err = e
            err_s = str(e).upper()
            if any(k in err_s for k in ("503", "429", "UNAVAILABLE", "OVERLOADED", "RESOURCE_EXHAUSTED", "404", "NOT_FOUND")):
                continue
            raise
    raise last_err

load_dotenv()

API_KEY = os.getenv("OANDA_API_KEY", "").strip()
OANDA_ENV = os.getenv("OANDA_ENV", "practice").strip().lower()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()

TOURNAMENT_BOTS = {
    "BOT_A_SNIPER": {
        "id": os.getenv("OANDA_ACCOUNT_A", "101-001-40528994-006").strip(),
        "label": "SLOT A // THE SNIPER",
        "desc": "Strict 5-Gate Baseline (USD_JPY Only | 2.0x ATR SL | 1:3.0 R:R | Pure Quant)",
        "pairs": ["USD_JPY"],
        "sl_mult": 2.0,
        "rr_ratio": 3.0,
        "zone_atr": 1.0,
        "clr_atr": 0.50,
        "use_ai": False,
    },
    "BOT_B_SPRINTER": {
        "id": os.getenv("OANDA_ACCOUNT_B", "101-001-40528994-005").strip(),
        "label": "SLOT B // THE SPRINTER",
        "desc": "Fast Ribbon Pullback (All 3 Pairs | 1.5x ATR SL | 1:2.0 R:R | Wider Value Zone)",
        "pairs": ["EUR_USD", "USD_JPY", "GBP_USD"],
        "sl_mult": 1.5,
        "rr_ratio": 2.0,
        "zone_atr": 1.4,
        "clr_atr": 0.35,
        "use_ai": False,
    },
    "BOT_C_SENTINEL": {
        "id": os.getenv("OANDA_ACCOUNT_C", "101-001-40528994-004").strip(),
        "label": "SLOT C // MACRO SENTINEL",
        "desc": "Gemini Flash AI + Multi-Pair Runner (All 3 Pairs | 2.0x ATR SL | 1:3.5 R:R)",
        "pairs": ["EUR_USD", "USD_JPY", "GBP_USD"],
        "sl_mult": 2.0,
        "rr_ratio": 3.5,
        "zone_atr": 1.2,
        "clr_atr": 0.50,
        "use_ai": True,
    },
}

ACCOUNT_ID = TOURNAMENT_BOTS["BOT_C_SENTINEL"]["id"]

BASE_URL = (
    "https://api-fxtrade.oanda.com/v3"
    if OANDA_ENV == "live"
    else "https://api-fxpractice.oanda.com/v3"
)
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

PAIRS = ["EUR_USD", "USD_JPY", "GBP_USD"]
GRANULARITY = "M15"
RISK_PCT = 0.01  # Gate 5: 1% Risk Firewall ($0.50 per $50 sub-account)
STATE_FILE = os.path.join(os.path.dirname(__file__), "bot_state.json")

ai_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY and "PASTE" not in GEMINI_KEY else None


def get_mt_time():
    return datetime.now(ZoneInfo("America/Denver"))


def oanda_get(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if r.status_code in (502, 503, 504) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def check_gate_1_clock_and_spread(pair, spread_pips):
    now_mt = get_mt_time()
    weekday = now_mt.weekday()  # Mon=0 ... Sun=6
    hour = now_mt.hour

    if 14 <= hour < 16:
        return False, f"BLOCKED: Rollover Window ({now_mt.strftime('%H:%M MT')})"

    in_window = (weekday in range(0, 5)) and (6 <= hour < 12)
    max_spread = 2.0 if pair != "GBP_USD" else 2.5

    if spread_pips > max_spread:
        return False, f"BLOCKED: Spread {spread_pips:.1f}p > {max_spread}p"
    if not in_window:
        return False, f"STANDBY: Outside 06:00-12:00 MT ({now_mt.strftime('%a %H:%M MT')})"
    return True, f"ACTIVE ({now_mt.strftime('%H:%M MT')}) | Spread {spread_pips:.1f}p"


def fetch_account_summary(account_id=ACCOUNT_ID):
    url = f"{BASE_URL}/accounts/{account_id}/summary"
    r = oanda_get(url)
    return r.json()["account"]


def fetch_open_trades(account_id=ACCOUNT_ID):
    url = f"{BASE_URL}/accounts/{account_id}/openTrades"
    r = oanda_get(url)
    return r.json().get("trades", [])


def fetch_candles_and_spread(pair, count=250):
    url = f"{BASE_URL}/instruments/{pair}/candles"
    params = {"count": count, "granularity": GRANULARITY, "price": "MBA"}
    r = oanda_get(url, params=params)
    candles = r.json()["candles"]

    rows = []
    for c in candles:
        if c["complete"] or c == candles[-1]:
            rows.append({
                "time": c["time"],
                "open": float(c["mid"]["o"]),
                "high": float(c["mid"]["h"]),
                "low": float(c["mid"]["l"]),
                "close": float(c["mid"]["c"]),
                "bid": float(c["bid"]["c"]),
                "ask": float(c["ask"]["c"]),
            })
    df = pd.DataFrame(rows)
    pip_mult = 100.0 if "JPY" in pair else 10000.0
    spread_pips = (df.iloc[-1]["ask"] - df.iloc[-1]["bid"]) * pip_mult
    return df, spread_pips, pip_mult


def compute_indicators(df):
    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi14"] = 100 - (100 / (1 + rs))

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr14"] = tr.ewm(alpha=1/14, adjust=False).mean()
    return df


def evaluate_gates(pair, df, spread_pips, pip_mult, clr_min=0.50, zone_mult=1.2):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = last["close"]
    ema9, ema21, ema200 = last["ema9"], last["ema21"], last["ema200"]
    rsi = last["rsi14"]
    atr = last["atr14"]

    g1_pass, g1_msg = check_gate_1_clock_and_spread(pair, spread_pips)

    dist_ema200 = abs(price - ema200)
    clr_ratio = dist_ema200 / max(atr, 1e-9)
    buf_ok = clr_ratio >= clr_min

    if price > ema200 and ema9 > ema21 and ema21 > ema200:
        bias = "LONG"
        g2_pass = buf_ok
        g2_msg = (
            f"BULLISH 3-STACK (+{clr_ratio:.2f}x ATR)"
            if buf_ok else f"200 EMA DEAD-ZONE ({clr_ratio:.2f}x < {clr_min:.2f}x ATR)"
        )
    elif price < ema200 and ema9 < ema21 and ema21 < ema200:
        bias = "SHORT"
        g2_pass = buf_ok
        g2_msg = (
            f"BEARISH 3-STACK (-{clr_ratio:.2f}x ATR)"
            if buf_ok else f"200 EMA DEAD-ZONE ({clr_ratio:.2f}x < {clr_min:.2f}x ATR)"
        )
    else:
        bias = "NEUTRAL"
        g2_pass = False
        g2_msg = "CHOP / UNSTACKED EMAs (Await 9-21-200 Align)"

    dist_to_ema21 = abs(price - ema21)
    g3_pass = g2_pass and (dist_to_ema21 <= atr * zone_mult)
    g3_msg = "IN VALUE ZONE" if g3_pass else f"EXTENDED ({dist_to_ema21 * pip_mult:.1f}p from EMA21)"

    if bias == "LONG":
        g4_pass = (40 <= rsi <= 65) and (last["close"] > last["open"]) and (prev["low"] <= ema21 * 1.0005)
        g4_msg = f"RSI {rsi:.1f} + Bullish Trigger" if g4_pass else f"WAITING (RSI {rsi:.1f})"
    elif bias == "SHORT":
        g4_pass = (35 <= rsi <= 60) and (last["close"] < last["open"]) and (prev["high"] >= ema21 * 0.9995)
        g4_msg = f"RSI {rsi:.1f} + Bearish Trigger" if g4_pass else f"WAITING (RSI {rsi:.1f})"
    else:
        g4_pass = False
        g4_msg = f"NEUTRAL (RSI {rsi:.1f})"

    return {
        "pair": pair,
        "price": price,
        "spread_pips": round(spread_pips, 2),
        "bias": bias,
        "ema9": ema9,
        "ema21": ema21,
        "ema200": ema200,
        "rsi": round(rsi, 1),
        "atr_pips": round(atr * pip_mult, 1),
        "atr_raw": atr,
        "g1_pass": g1_pass, "g1_msg": g1_msg,
        "g2_pass": g2_pass, "g2_msg": g2_msg,
        "g3_pass": g3_pass, "g3_msg": g3_msg,
        "g4_pass": g4_pass, "g4_msg": g4_msg,
    }


def ask_gemini_sanity_check(telemetry):
    if not ai_client:
        return True, "AI Check Bypassed (No GEMINI_API_KEY configured)"
    prompt = (
        f"5-Gate Forex Bot Sanity Check for {telemetry['pair']} ({telemetry['bias']}):\n"
        f"Price: {telemetry['price']}, EMA9: {telemetry['ema9']:.5f}, EMA21: {telemetry['ema21']:.5f}, "
        f"EMA200: {telemetry['ema200']:.5f}, RSI14: {telemetry['rsi']}, ATR(pips): {telemetry['atr_pips']}, "
        f"Spread: {telemetry['spread_pips']}p.\n"
        "Respond on one short line starting with APPROVE or VETO followed by a 12-word technical reason."
    )
    try:
        resp = _call_gemini_with_fallback(lambda _m: ai_client.models.generate_content(
            model=_m,
            contents=prompt,
        ))
        text = resp.text.strip().replace("\n", " ")
        approved = "APPROVE" in text.upper() and "VETO" not in text.upper()
        return approved, text[:120]
    except Exception as e:
        return True, f"AI Check Fallback (API busy): {str(e)[:60]}"


def place_bracket_order(account_id, bot_key, pair, bias, price, atr_raw, nav, sl_mult=2.0, rr_ratio=3.0):
    stop_dist = sl_mult * atr_raw
    tp_dist = stop_dist * rr_ratio
    risk_dollars = nav * RISK_PCT

    if "JPY" in pair:
        risk_per_unit = stop_dist / price
        decimals = 3
    else:
        risk_per_unit = stop_dist
        decimals = 5

    units = int(max(1, round(risk_dollars / max(risk_per_unit, 1e-6))))
    if bias == "SHORT":
        units = -units
        sl_price = round(price + stop_dist, decimals)
        tp_price = round(price - tp_dist, decimals)
    else:
        sl_price = round(price - stop_dist, decimals)
        tp_price = round(price + tp_dist, decimals)

    payload = {
        "order": {
            "instrument": pair,
            "units": str(units),
            "type": "MARKET",
            "positionFill": "DEFAULT",
            "clientExtensions": {"tag": bot_key.lower(), "comment": f"{bot_key} 1:{rr_ratio}"},
            "tradeClientExtensions": {"tag": bot_key.lower(), "comment": f"{bot_key} 1:{rr_ratio}"},
            "stopLossOnFill": {"price": f"{sl_price:.{decimals}f}"},
            "takeProfitOnFill": {"price": f"{tp_price:.{decimals}f}"},
        }
    }
    url = f"{BASE_URL}/accounts/{account_id}/orders"
    r = requests.post(url, headers=HEADERS, json=payload, timeout=10)
    r.raise_for_status()
    resp_j = r.json()
    fill_tid = resp_j.get("orderFillTransaction", {}).get("tradeOpened", {}).get("tradeID", "")
    return units, sl_price, tp_price, fill_tid


def run_loop():
    print("🛰️ 3-Bot OANDA Tournament Engine Started. Writing live telemetry to bot_state.json...")
    last_ai_notes = {p: "Awaiting Gate 1-4 alignment..." for p in PAIRS}
    cached_ledgers = {}
    last_ledger_ts = 0.0

    while True:
        state = {
            "timestamp": get_mt_time().strftime("%Y-%m-%d %H:%M:%S MT"),
            "account": {},
            "open_trades": [],
            "pairs": {},
            "tournament": {},
            "status": "ONLINE // 3-BOT TOURNAMENT ARMED",
        }
        try:
            # 1. Pull M15 Candles & Compute Indicators once per cycle for all 3 pairs
            market_data = {}
            for pair in PAIRS:
                df, spread_pips, pip_mult = fetch_candles_and_spread(pair)
                df = compute_indicators(df)
                market_data[pair] = (df, spread_pips, pip_mult)

            total_nav = 0.0
            total_bal = 0.0
            total_upl = 0.0
            all_open_trades = []

            # 2. Evaluate & Execute each of the 3 Tournament Bots against its own $50 Sub-Account
            for bot_key, cfg in TOURNAMENT_BOTS.items():
                acc_id = cfg["id"]
                acct = fetch_account_summary(acc_id)
                nav = float(acct.get("NAV", acct.get("balance", 50.0)))
                bal = float(acct.get("balance", 50.0))
                upl = float(acct.get("unrealizedPL", 0.0))
                total_nav += nav
                total_bal += bal
                total_upl += upl

                raw_trades = fetch_open_trades(acc_id)
                open_pairs = {t["instrument"] for t in raw_trades}
                bot_trades = []
                for t in raw_trades:
                    tr_obj = {
                        "id": t["id"],
                        "bot": bot_key,
                        "bot_label": cfg["label"],
                        "account_id": acc_id,
                        "pair": t["instrument"],
                        "units": t["currentUnits"],
                        "price": t["price"],
                        "pl": t["unrealizedPL"],
                    }
                    bot_trades.append(tr_obj)
                    all_open_trades.append(tr_obj)

                bot_pairs_tel = {}
                gates_ready_count = 0

                for pair in cfg["pairs"]:
                    df, spread_pips, pip_mult = market_data[pair]
                    tel = evaluate_gates(
                        pair, df, spread_pips, pip_mult,
                        clr_min=cfg["clr_atr"], zone_mult=cfg["zone_atr"]
                    )
                    passed_cnt = sum(1 for k in ("g1_pass", "g2_pass", "g3_pass", "g4_pass") if tel[k])
                    gates_ready_count = max(gates_ready_count, passed_cnt)

                    all_gates_ready = (passed_cnt == 4)
                    if pair in open_pairs:
                        tel["g5_msg"] = f"POSITION OPEN ({bot_key} Server SL/TP Active)"
                    elif all_gates_ready:
                        if cfg["use_ai"]:
                            approved, ai_note = ask_gemini_sanity_check(tel)
                            last_ai_notes[pair] = ai_note
                        else:
                            approved = True
                            ai_note = f"QUANT AUTO-APPROVE ({cfg['label']})"

                        if approved:
                            units, sl, tp, fill_tid = place_bracket_order(
                                acc_id, bot_key, pair, tel["bias"], tel["price"],
                                tel["atr_raw"], nav, sl_mult=cfg["sl_mult"], rr_ratio=cfg["rr_ratio"]
                            )
                            if fill_tid:
                                ledger_engine.record_live_entry_snapshot(
                                    fill_tid, tel, nav, units, sl, tp, ai_note
                                )
                            tel["g5_msg"] = f"EXECUTED {units}u | SL {sl} | TP {tp}"
                        else:
                            tel["g5_msg"] = "AI VETOED ENTRY"
                    else:
                        tel["g5_msg"] = (
                            f"ARMED (1% = ${nav * RISK_PCT:.2f} | "
                            f"{cfg['sl_mult']}xATR SL / 1:{cfg['rr_ratio']} TP)"
                        )

                    tel["ai_note"] = last_ai_notes[pair] if cfg["use_ai"] else f"Pure Quant Mode ({cfg['sl_mult']}x ATR / 1:{cfg['rr_ratio']} R:R)"
                    bot_pairs_tel[pair] = tel
                    if bot_key == "BOT_C_SENTINEL":
                        state["pairs"][pair] = tel

                state["tournament"][bot_key] = {
                    "bot_key": bot_key,
                    "label": cfg["label"],
                    "desc": cfg["desc"],
                    "account_id": acc_id,
                    "nav": round(nav, 4),
                    "balance": round(bal, 4),
                    "unrealized_pl": round(upl, 4),
                    "net_return_pct": round(((nav - 50.0) / 50.0) * 100.0, 2),
                    "risk_usd": round(nav * RISK_PCT, 2),
                    "sl_mult": cfg["sl_mult"],
                    "rr_ratio": cfg["rr_ratio"],
                    "pairs_watched": cfg["pairs"],
                    "max_gates_passed": gates_ready_count,
                    "open_trades": bot_trades,
                    "pairs": bot_pairs_tel,
                }

            # Populate top-level summary across the 3-Bot Fleet ($150.00 Combined)
            state["account"] = {
                "id": "3-BOT FLEET (-006 / -005 / -004)",
                "balance": round(total_bal, 4),
                "nav": round(total_nav, 4),
                "unrealized_pl": round(total_upl, 4),
                "margin_used": 0.0,
                "risk_1pct": round((total_nav / 3.0) * RISK_PCT, 2),
            }
            state["open_trades"] = all_open_trades

            # 3. Sync Historical Ledgers every 60s across all 3 accounts
            if (time.time() - last_ledger_ts > 60) or not cached_ledgers:
                cur_prices = {k: v["price"] for k, v in state["pairs"].items()}
                combined_trades = []
                wins_tot, loss_tot, cpl_tot, opl_tot = 0, 0, 0.0, 0.0
                for bot_key, cfg in TOURNAMENT_BOTS.items():
                    acc_id = cfg["id"]
                    b_open = state["tournament"][bot_key]["open_trades"]
                    led = ledger_engine.sync_historical_ledger(
                        oanda_get, BASE_URL, acc_id, b_open, cur_prices
                    )
                    cached_ledgers[bot_key] = led
                    wins_tot += led.get("closed_wins", 0)
                    loss_tot += led.get("closed_losses", 0)
                    cpl_tot += led.get("closed_pl", 0.0)
                    opl_tot += led.get("open_pl", 0.0)
                    for tr in led.get("trades", []):
                        tr_copy = dict(tr)
                        tr_copy["bot_key"] = bot_key
                        tr_copy["bot_label"] = cfg["label"]
                        combined_trades.append(tr_copy)

                state["ledger"] = {
                    "baseline_usd": 150.00,
                    "baseline_mt": "Nov 15, 2026 (3x $50 Tournament)",
                    "closed_wins": wins_tot,
                    "closed_losses": loss_tot,
                    "closed_pl": round(cpl_tot, 2),
                    "open_pl": round(opl_tot, 2),
                    "net_equity": round(total_nav, 2),
                    "trades": combined_trades,
                }
                last_ledger_ts = time.time()
            else:
                for bot_key, led in cached_ledgers.items():
                    if bot_key in state["tournament"]:
                        state["tournament"][bot_key]["wins"] = led.get("closed_wins", 0)
                        state["tournament"][bot_key]["losses"] = led.get("closed_losses", 0)

            for bot_key, led in cached_ledgers.items():
                if bot_key in state["tournament"]:
                    state["tournament"][bot_key]["wins"] = led.get("closed_wins", 0)
                    state["tournament"][bot_key]["losses"] = led.get("closed_losses", 0)

        except Exception as e:
            state["status"] = f"ERROR: {str(e)}"
            print(f"[{state['timestamp']}] {state['status']}", flush=True)

        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=lambda x: bool(x) if hasattr(x, "item") and isinstance(x.item(), bool) else (float(x) if hasattr(x, "item") else str(x)))

        time.sleep(15)


if __name__ == "__main__":
    run_loop()
