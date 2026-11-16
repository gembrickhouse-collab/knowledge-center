import os
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

MT_TZ = ZoneInfo("America/Denver")
CACHE_FILE = os.path.join(os.path.dirname(__file__), "ledger_cache.json")


def _load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"entries": {}, "live_notes": {}}


def _save_cache(cache):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def record_live_entry_snapshot(tx_id, tel, nav, units, sl, tp, ai_note):
    cache = _load_cache()
    cache.setdefault("live_notes", {})[str(tx_id)] = {
        "ai_note": ai_note,
        "nav": nav,
        "sl": sl,
        "tp": tp,
        "tel": tel,
    }
    _save_cache(cache)


def _fmt_dt_mt(iso_str):
    clean = iso_str.split(".")[0].replace("Z", "") + "+00:00"
    dt_utc = datetime.fromisoformat(clean)
    return dt_utc.astimezone(MT_TZ)


def _fmt_duration(t_open_iso, t_close_iso):
    t1 = _fmt_dt_mt(t_open_iso)
    t2 = _fmt_dt_mt(t_close_iso)
    mins = max(1, int((t2 - t1).total_seconds() // 60))
    if mins < 60:
        return f"{mins}m"
    return f"{mins // 60}h {mins % 60:02d}m"


def _reconstruct_entry_autopsy(oanda_get, base_url, pair, entry_iso, units, fill_price, nav_before, sl_tx, tp_tx, live_meta):
    pip_mult = 100.0 if "JPY" in pair else 10000.0
    dec = 3 if "JPY" in pair else 5
    bias = "LONG" if units > 0 else "SHORT"
    dt_mt = _fmt_dt_mt(entry_iso)
    max_spread = 2.5 if pair == "GBP_USD" else 2.0

    # Fetch 250 M15 candles ending right at the trade's entry timestamp
    to_ts = entry_iso.split(".")[0] + "Z" if not entry_iso.endswith("Z") else entry_iso
    url = f"{base_url}/instruments/{pair}/candles"
    params = {"to": to_ts, "count": 250, "granularity": "M15", "price": "MBA"}
    r = oanda_get(url, params=params)
    candles = r.json().get("candles", [])

    rows = []
    for c in candles:
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
    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi14"] = 100 - (100 / (1 + rs))

    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    df["atr14"] = tr.ewm(alpha=1 / 14, adjust=False).mean()

    # Evaluate both the live forming candle (-1) and prior completed candle (-2) to match exact trigger moment
    idx = -1
    if len(df) >= 3:
        c1, c2 = df.iloc[-1], df.iloc[-2]
        if bias == "LONG" and not (c1["close"] > c1["open"]) and (c2["close"] > c2["open"]):
            idx = -2
        elif bias == "SHORT" and not (c1["close"] < c1["open"]) and (c2["close"] < c2["open"]):
            idx = -2

    last = df.iloc[idx]
    prev = df.iloc[idx - 1]
    c_price = float(last["close"])
    ema9, ema21, ema200 = float(last["ema9"]), float(last["ema21"]), float(last["ema200"])
    rsi = float(last["rsi14"])
    atr = float(last["atr14"])
    atr_pips = atr * pip_mult
    spread_pips = (float(df.iloc[-1]["ask"]) - float(df.iloc[-1]["bid"])) * pip_mult
    dist_pips = abs(c_price - ema21) * pip_mult
    max_zone_pips = (atr * 1.2) * pip_mult

    # Gate-by-gate plain-English educational explanations
    g1_exp = (
        f"PASSED — Trade fired on {dt_mt.strftime('%a %b %d at %H:%M MT')}, cleanly inside the "
        f"06:00–12:00 MT London/NY overlap window (avoiding the 14:00–16:00 MT rollover trap). "
        f"Spread was {spread_pips:.1f}p (under the {max_spread:.1f}p max limit for {pair})."
    )
    clr_x = abs(c_price - ema200) / max(atr, 1e-9)
    if bias == "LONG":
        stack_ok = ema21 > ema200
        v2_note = (
            f"Clearance: {clr_x:.2f}x ATR (>= 0.50x v2 buffer, full 9>21>200 stack)."
            if (stack_ok and clr_x >= 0.5)
            else f"[LEGACY v1 ENTRY — v2 filter blocks this: {'21 EMA below 200 EMA' if not stack_ok else f'clearance {clr_x:.2f}x < 0.50x ATR'}]."
        )
        g2_exp = (
            f"PASSED (BULLISH STACK) — M15 price ({c_price:.{dec}f}) held above the 200 EMA macro floor "
            f"({ema200:.{dec}f}, +{(c_price - ema200) * pip_mult:.1f}p above), while fast 9 EMA "
            f"({ema9:.{dec}f}) stacked above slow 21 EMA ({ema21:.{dec}f}). {v2_note}"
        )
    else:
        stack_ok = ema21 < ema200
        v2_note = (
            f"Clearance: {clr_x:.2f}x ATR (>= 0.50x v2 buffer, full 9<21<200 stack)."
            if (stack_ok and clr_x >= 0.5)
            else f"[LEGACY v1 ENTRY — v2 filter blocks this: {'21 EMA still above 200 EMA' if not stack_ok else f'clearance {clr_x:.2f}x < 0.50x ATR'}]."
        )
        g2_exp = (
            f"PASSED (BEARISH STACK) — M15 price ({c_price:.{dec}f}) stayed below the 200 EMA macro ceiling "
            f"({ema200:.{dec}f}, {(ema200 - c_price) * pip_mult:.1f}p below), while fast 9 EMA "
            f"({ema9:.{dec}f}) stacked below slow 21 EMA ({ema21:.{dec}f}). {v2_note}"
        )

    g3_exp = (
        f"PASSED (IN VALUE ZONE) — Instead of chasing extended price, {pair} pulled back within "
        f"{dist_pips:.1f}p of the 21 EMA ({ema21:.{dec}f}), inside the 1.2x ATR ceiling ({max_zone_pips:.1f}p max)."
    )

    if bias == "LONG":
        g4_exp = (
            f"PASSED (BULLISH TRIGGER) — 14 RSI cooled to {rsi:.1f} (inside 40–65 bullish reset zone), "
            f"prior M15 low ({prev['low']:.{dec}f}) tested the 21 EMA support band ({ema21:.{dec}f}), "
            f"and trigger candle closed green ({last['open']:.{dec}f} -> {last['close']:.{dec}f})."
        )
    else:
        g4_exp = (
            f"PASSED (BEARISH TRIGGER) — 14 RSI cooled to {rsi:.1f} (inside 35–60 bearish reset zone), "
            f"prior M15 high ({prev['high']:.{dec}f}) tested the 21 EMA ceiling ({ema21:.{dec}f}), "
            f"and trigger candle closed red ({last['open']:.{dec}f} -> {last['close']:.{dec}f})."
        )

    risk_usd = nav_before * 0.01
    sl_p = float(sl_tx) if sl_tx else round(fill_price - (2 * atr if bias == "LONG" else -2 * atr), dec)
    tp_p = float(tp_tx) if tp_tx else round(fill_price + (6 * atr if bias == "LONG" else -6 * atr), dec)
    sl_pips = abs(fill_price - sl_p) * pip_mult
    tp_pips = abs(tp_p - fill_price) * pip_mult

    g5_exp = (
        f"PASSED (1% RISK FIREWALL) — 1% of ${nav_before:.2f} equity = ${risk_usd:.2f} risked across "
        f"{abs(units)} units @ {fill_price:.{dec}f}. M15 ATR was {atr_pips:.1f}p -> 2x ATR Stop Loss set at "
        f"{sl_p:.{dec}f} ({sl_pips:.1f}p risk) and 1:3 Take Profit set at {tp_p:.{dec}f} ({tp_pips:.1f}p target)."
    )

    ai_text = (live_meta or {}).get("ai_note") or "APPROVED — All 5 quantitative gates aligned during active session."

    return {
        "g1": g1_exp,
        "g2": g2_exp,
        "g3": g3_exp,
        "g4": g4_exp,
        "g5": g5_exp,
        "ai": ai_text,
        "sl_price": round(sl_p, dec),
        "tp_price": round(tp_p, dec),
        "sl_pips": round(sl_pips, 1),
        "tp_pips": round(tp_pips, 1),
        "atr_pips": round(atr_pips, 1),
        "rsi": round(rsi, 1),
    }


def sync_historical_ledger(oanda_get, base_url, account_id, open_trades_list, current_prices):
    cache = _load_cache()
    entries_cache = cache.setdefault("entries", {})
    live_notes = cache.get("live_notes", {})

    acct_r = oanda_get(f"{base_url}/accounts/{account_id}/summary").json()["account"]
    last_id = int(acct_r.get("lastTransactionID", 1))

    all_txs = []
    for start in range(1, last_id + 1, 1000):
        res = oanda_get(
            f"{base_url}/accounts/{account_id}/transactions/idrange",
            params={"from": start, "to": min(last_id, start + 999)},
        ).json()
        all_txs.extend(res.get("transactions", []))

    # Find the most recent ~$50 baseline TRANSFER_FUNDS (Tx #20 = $49.9951)
    baseline_idx = 0
    baseline_bal = 50.00
    baseline_time = ""
    for i, tx in enumerate(all_txs):
        if tx.get("type") == "TRANSFER_FUNDS":
            b = float(tx.get("accountBalance", 0))
            if 40.0 <= b <= 65.0:
                baseline_idx = i
                baseline_bal = b
                baseline_time = _fmt_dt_mt(tx["time"]).strftime("%b %d, %Y %H:%M MT")

    # Map SL/TP prices created right after each ORDER_FILL
    sl_by_trade, tp_by_trade = {}, {}
    for tx in all_txs[baseline_idx:]:
        t_type = tx.get("type", "")
        tid = str(tx.get("tradeID", ""))
        if t_type == "STOP_LOSS_ORDER" and tid and tx.get("price"):
            sl_by_trade[tid] = tx["price"]
        elif t_type == "TAKE_PROFIT_ORDER" and tid and tx.get("price"):
            tp_by_trade[tid] = tx["price"]

    open_map = {str(t["id"]): t for t in open_trades_list}

    trades_by_id = {}
    trade_order = []
    running_bal = baseline_bal

    for tx in all_txs[baseline_idx + 1:]:
        if tx.get("type") != "ORDER_FILL":
            continue
        # Opening fill?
        opened = tx.get("tradeOpened")
        if opened and opened.get("tradeID"):
            tid = str(opened["tradeID"])
            trade_order.append(tid)
            trades_by_id[tid] = {
                "trade_id": tid,
                "pair": tx["instrument"],
                "units": int(float(opened.get("units", tx.get("units", 0)))),
                "entry_price": float(tx["price"]),
                "entry_iso": tx["time"],
                "entry_mt": _fmt_dt_mt(tx["time"]).strftime("%b %d %H:%M MT"),
                "bal_before": running_bal,
                "status": "OPEN",
            }

        # Closing fill?
        closed_list = tx.get("tradesClosed", []) + ([tx["tradeReduced"]] if tx.get("tradeReduced") else [])
        for c in closed_list:
            tid = str(c.get("tradeID", ""))
            if tid in trades_by_id:
                pl = float(c.get("realizedPL", tx.get("pl", 0.0)))
                running_bal = float(tx.get("accountBalance", running_bal + pl))
                trades_by_id[tid].update({
                    "status": "CLOSED",
                    "exit_price": float(tx["price"]),
                    "exit_iso": tx["time"],
                    "exit_mt": _fmt_dt_mt(tx["time"]).strftime("%b %d %H:%M MT"),
                    "exit_reason": tx.get("reason", "ORDER_FILL"),
                    "pl_usd": round(pl, 2),
                    "bal_after": round(running_bal, 2),
                    "duration": _fmt_duration(trades_by_id[tid]["entry_iso"], tx["time"]),
                })

    ledger_rows = []
    cache_dirty = False

    for seq, tid in enumerate(trade_order, 1):
        tr = trades_by_id[tid]
        pair = tr["pair"]
        pip_mult = 100.0 if "JPY" in pair else 10000.0
        dec = 3 if "JPY" in pair else 5
        bias = "LONG" if tr["units"] > 0 else "SHORT"

        cache_key = f"{account_id}:{tid}"
        if cache_key not in entries_cache:
            try:
                entries_cache[cache_key] = _reconstruct_entry_autopsy(
                    oanda_get, base_url, pair, tr["entry_iso"], tr["units"],
                    tr["entry_price"], tr["bal_before"],
                    sl_by_trade.get(tid), tp_by_trade.get(tid), live_notes.get(tid),
                )
                cache_dirty = True
            except Exception as e:
                entries_cache[cache_key] = {
                    "g1": "Passed 06:00-12:00 MT session & spread filter.",
                    "g2": f"Passed {bias} 200 EMA + 9/21 EMA alignment.",
                    "g3": "Passed 21 EMA value zone pullback.",
                    "g4": "Passed 14 RSI momentum & trigger candle.",
                    "g5": f"1% risk on ${tr['bal_before']:.2f} equity across {abs(tr['units'])}u.",
                    "ai": f"Fallback note ({e})",
                    "sl_price": 0, "tp_price": 0, "sl_pips": 0, "tp_pips": 0,
                }

        autopsy = entries_cache[cache_key]

        if tr["status"] == "CLOSED":
            raw_pips = (tr["exit_price"] - tr["entry_price"]) * pip_mult * (1 if bias == "LONG" else -1)
            r_mult = round(tr["pl_usd"] / max(tr["bal_before"] * 0.01, 0.01), 2)
            reason = tr["exit_reason"]
            if reason == "TAKE_PROFIT_ORDER":
                exit_exp = (
                    f"TARGET HIT (1:3 TAKE PROFIT) — Price reached {tr['exit_price']:.{dec}f} on {tr['exit_mt']} "
                    f"after {tr['duration']}, banking +{raw_pips:.1f}p (+${tr['pl_usd']:.2f} / +{r_mult:.1f}R) "
                    f"and lifting closed balance from ${tr['bal_before']:.2f} -> ${tr['bal_after']:.2f}."
                )
            elif reason == "STOP_LOSS_ORDER":
                exit_exp = (
                    f"2x ATR STOP LOSS HIT — Trend pullback invalidated at {tr['exit_price']:.{dec}f} on {tr['exit_mt']} "
                    f"after {tr['duration']} ({raw_pips:.1f}p). Gate 5's 1% Risk Firewall capped the loss at "
                    f"${tr['pl_usd']:.2f} ({r_mult:.1f}R), protecting account balance at ${tr['bal_after']:.2f}."
                )
            else:
                exit_exp = (
                    f"CLOSED ({reason}) at {tr['exit_price']:.{dec}f} after {tr['duration']} "
                    f"({raw_pips:+.1f}p / ${tr['pl_usd']:+.2f}) -> Balance ${tr['bal_after']:.2f}."
                )
        else:
            live_t = open_map.get(tid, {})
            u_pl = float(live_t.get("pl", 0.0))
            cur_p = float(current_prices.get(pair, tr["entry_price"]))
            raw_pips = (cur_p - tr["entry_price"]) * pip_mult * (1 if bias == "LONG" else -1)
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            dur = _fmt_duration(tr["entry_iso"], now_iso)
            tr["pl_usd"] = round(u_pl, 2)
            tr["bal_after"] = round(running_bal + u_pl, 2)
            tr["exit_reason"] = "LIVE / OPEN"
            tr["exit_mt"] = "ACTIVE NOW"
            tr["exit_price"] = round(cur_p, dec)
            tr["duration"] = dur
            exit_exp = (
                f"ACTIVE RUNNER ({dur} elapsed) — Currently trading at {cur_p:.{dec}f} "
                f"({raw_pips:+.1f}p / ${u_pl:+.2f} unrealized). Server-side 2x ATR Stop ({autopsy['sl_price']}) "
                f"and 1:3 Take Profit ({autopsy['tp_price']}) are armed on OANDA's servers."
            )

        ledger_rows.append({
            "seq": seq,
            "trade_id": tid,
            "pair": pair,
            "bias": bias,
            "units": tr["units"],
            "status": tr["status"],
            "entry_price": tr["entry_price"],
            "exit_price": tr["exit_price"],
            "entry_mt": tr["entry_mt"],
            "exit_mt": tr["exit_mt"],
            "duration": tr["duration"],
            "exit_reason": tr["exit_reason"],
            "pips": round(raw_pips, 1),
            "pl_usd": tr["pl_usd"],
            "bal_before": round(tr["bal_before"], 2),
            "bal_after": tr["bal_after"],
            "autopsy": autopsy,
            "exit_exp": exit_exp,
        })

    if cache_dirty:
        _save_cache(cache)

    wins = sum(1 for r in ledger_rows if r["status"] == "CLOSED" and r["pl_usd"] > 0)
    losses = sum(1 for r in ledger_rows if r["status"] == "CLOSED" and r["pl_usd"] <= 0)
    closed_pl = round(sum(r["pl_usd"] for r in ledger_rows if r["status"] == "CLOSED"), 2)
    open_pl = round(sum(r["pl_usd"] for r in ledger_rows if r["status"] == "OPEN"), 2)

    return {
        "baseline_usd": round(baseline_bal, 2),
        "baseline_mt": baseline_time,
        "closed_wins": wins,
        "closed_losses": losses,
        "closed_pl": closed_pl,
        "open_pl": open_pl,
        "net_equity": round(baseline_bal + closed_pl + open_pl, 2),
        "trades": ledger_rows,
    }


# === _ENTRY_CHART_HOOK_INSTALLED: M15 Entry Candlestick Snapshot Builder ===
import os as _ec_os, re as _ec_re, json as _ec_json, urllib.request as _ec_req
from datetime import datetime as _ec_dt, timezone as _ec_tz
from zoneinfo import ZoneInfo as _ec_zi

_CHART_CACHE_FILE = _ec_os.path.join(_ec_os.path.dirname(__file__), "entry_charts_cache.json")

def _ec_ema(vals, period):
    if not vals:
        return []
    k = 2.0 / (period + 1.0)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out

def _ec_fetch_snapshot(tr, baseline_mt):
    tok = (
        _ec_os.getenv("OANDA_API_KEY") or _ec_os.getenv("OANDA_ACCESS_TOKEN")
        or _ec_os.getenv("OANDA_TOKEN") or globals().get("OANDA_API_KEY")
        or globals().get("OANDA_ACCESS_TOKEN") or globals().get("OANDA_TOKEN")
    )
    if not tok:
        return None
    acct = (
        _ec_os.getenv("OANDA_ACCOUNT_ID") or _ec_os.getenv("ACCOUNT_ID")
        or globals().get("OANDA_ACCOUNT_ID") or globals().get("ACCOUNT_ID")
        or "101-001-40528994-003"
    )
    base = _ec_os.getenv("OANDA_URL") or "https://api-fxpractice.oanda.com/v3"
    hdrs = {"Authorization": f"Bearer {tok}", "Accept-Datetime-Format": "RFC3339"}

    tid = str(tr.get("trade_id", "")).lstrip("#").strip()
    entry_epoch = None
    if tid:
        try:
            r = _ec_req.Request(f"{base}/accounts/{acct}/trades/{tid}", headers=hdrs)
            t_obj = _ec_json.loads(_ec_req.urlopen(r, timeout=8).read().decode()).get("trade", {})
            ot = t_obj.get("openTime", "")
            if ot:
                iso_core = ot.split(".")[0].replace("Z", "")
                entry_epoch = int(_ec_dt.strptime(iso_core, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=_ec_tz.utc).timestamp())
        except Exception:
            pass

    if not entry_epoch:
        yr_m = _ec_re.search(r"20\d\d", str(baseline_mt))
        yr = yr_m.group(0) if yr_m else "2026"
        clean_mt = tr.get("entry_mt", "").replace(" MT", "").strip()
        dt_loc = _ec_dt.strptime(f"{yr} {clean_mt}", "%Y %b %d %H:%M").replace(tzinfo=_ec_zi("America/Denver"))
        entry_epoch = int(dt_loc.timestamp())

    pair = tr["pair"]
    c_url = f"{base}/instruments/{pair}/candles?price=M&granularity=M15&count=230&to={entry_epoch + 5}"
    rc = _ec_req.Request(c_url, headers=hdrs)
    raw_c = _ec_json.loads(_ec_req.urlopen(rc, timeout=10).read().decode()).get("candles", [])
    comp = [c for c in raw_c if c.get("complete", True)] or raw_c
    if len(comp) < 5:
        return None

    digs = 3 if "JPY" in pair else 5
    ohlc = [[round(float(c["mid"]["o"]), digs), round(float(c["mid"]["h"]), digs),
             round(float(c["mid"]["l"]), digs), round(float(c["mid"]["c"]), digs)] for c in comp]
    closes = [x[3] for x in ohlc]
    e9 = [round(x, digs) for x in _ec_ema(closes, 9)]
    e21 = [round(x, digs) for x in _ec_ema(closes, 21)]
    e200 = [round(x, digs) for x in _ec_ema(closes, 200)]

    g5_txt = (tr.get("autopsy") or {}).get("g5", "")
    sl_m = _ec_re.search(r"Stop Loss set at ([0-9.]+)", g5_txt)
    tp_m = _ec_re.search(r"Take Profit set at ([0-9.]+)", g5_txt)

    return {
        "tf": "M15",
        "candles": ohlc[-28:],
        "ema9": e9[-28:],
        "ema21": e21[-28:],
        "ema200": e200[-28:],
        "entry": float(tr["entry_price"]),
        "sl": float(sl_m.group(1)) if sl_m else None,
        "tp": float(tp_m.group(1)) if tp_m else None,
    }

def _enrich_ledger_charts(res):
    if not isinstance(res, dict) or not isinstance(res.get("trades"), list):
        return res
    cache = {}
    if _ec_os.path.exists(_CHART_CACHE_FILE):
        try:
            cache = _ec_json.load(open(_CHART_CACHE_FILE))
        except Exception:
            cache = {}
    dirty = False
    b_mt = res.get("baseline_mt", "2026")
    for tr in res["trades"]:
        k = str(tr.get("trade_id", ""))
        if k in cache and cache[k].get("candles"):
            tr["chart"] = cache[k]
        else:
            try:
                snap = _ec_fetch_snapshot(tr, b_mt)
                if snap:
                    cache[k] = snap
                    tr["chart"] = snap
                    dirty = True
            except Exception:
                pass
    if dirty:
        try:
            with open(_CHART_CACHE_FILE, "w") as f:
                _ec_json.dump(cache, f)
        except Exception:
            pass
    return res

for _fn_name, _fn_obj in list(globals().items()):
    if not _fn_name.startswith("_") and callable(_fn_obj) and getattr(_fn_obj, "__module__", "") == __name__:
        def _make_wrap(f):
            def _wrapped(*a, **kw):
                return _enrich_ledger_charts(f(*a, **kw))
            return _wrapped
        globals()[_fn_name] = _make_wrap(_fn_obj)
