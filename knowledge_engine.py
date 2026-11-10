import os
import sys
import json
import time
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

MT_TZ = ZoneInfo("America/Denver")
DATA_FILE = os.path.join(os.path.dirname(__file__), "curriculum.json")
FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]


def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data_and_sync_github(data, commit_msg):
    raw = json.dumps(data, indent=2)
    with open(DATA_FILE, "w") as f:
        f.write(raw)

    gh_token = os.getenv("GITHUB_TOKEN", "").strip()
    gh_repo = os.getenv("GITHUB_REPO", "").strip()  # e.g. gembrickhouse-collab/knowledge-center
    if gh_token and gh_repo:
        try:
            api_url = f"https://api.github.com/repos/{gh_repo}/contents/curriculum.json"
            hdrs = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"}
            r_get = requests.get(api_url, headers=hdrs, timeout=12)
            sha = r_get.json().get("sha") if r_get.status_code == 200 else None
            payload = {
                "message": commit_msg,
                "content": base64.b64encode(raw.encode("utf-8")).decode("ascii"),
            }
            if sha:
                payload["sha"] = sha
            r_put = requests.put(api_url, headers=hdrs, json=payload, timeout=15)
            r_put.raise_for_status()
            print(f"✅ Persisted to GitHub ({gh_repo}): {commit_msg}")
        except Exception as e:
            print(f"⚠️ Saved locally, GitHub sync skipped/failed: {e}")


def generate_next_lesson(track_key, track_obj):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    from google import genai

    client = genai.Client(api_key=api_key)
    past_titles = [f"#{x['seq']}: {x['title']}" for x in track_obj.get("lessons", [])]
    next_seq = len(past_titles) + 1
    today_str = datetime.now(MT_TZ).strftime("%Y-%m-%d")

    prompt = (
        f"Generate Lesson #{next_seq} for the daily track '{track_obj['title']}' ({track_obj['description']}).\n"
        f"Already covered (DO NOT repeat these specific topics/artists):\n" + "\n".join(past_titles) + "\n\n"
        "Return ONLY valid JSON with keys: "
        '{"title": "Topic/Artist — Subtitle", "tags": ["tag1", "tag2", "tag3"], '
        '"core": "2-3 rich, concrete sentences explaining the historical/scientific mechanics with zero fluff.", '
        '"maker": "1-2 sharp sentences connecting the concept directly to wearable fine-art textile reconstruction, geometric non-text symbolism, or disciplined systems craftsmanship."}'
    )

    last_err = None
    for m in FALLBACK_MODELS:
        try:
            resp = client.models.generate_content(model=m, contents=prompt)
            txt = resp.text.strip()
            if "```" in txt:
                txt = txt.split("```")[1]
                if txt.startswith("json"):
                    txt = txt[4:]
            parsed = json.loads(txt.strip())
            return {
                "seq": next_seq,
                "date": today_str,
                "model": m.replace("gemini-", ""),
                "title": parsed["title"],
                "tags": parsed.get("tags", [track_key])[:3],
                "core": parsed["core"],
                "maker": parsed["maker"],
            }
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"All Gemini models failed: {last_err}")


def check_and_run_daily_drop(force=False):
    now_mt = datetime.now(MT_TZ)
    today_str = now_mt.strftime("%Y-%m-%d")
    past_830 = (now_mt.hour > 8) or (now_mt.hour == 8 and now_mt.minute >= 30)
    if not force and not past_830:
        return False

    data = load_data()
    added = []
    for t_key, t_obj in data.get("tracks", {}).items():
        lessons = t_obj.setdefault("lessons", [])
        if not force and any(x.get("date") == today_str for x in lessons):
            continue
        new_item = generate_next_lesson(t_key, t_obj)
        lessons.append(new_item)
        added.append(f"{t_key}#{new_item['seq']}")

    if added:
        save_data_and_sync_github(data, f"8:30 AM MT Auto-Drop: {', '.join(added)}")
        return True
    return False


if __name__ == "__main__":
    # Manual CLI usage:
    #   python3 knowledge_engine.py drop
    #   python3 knowledge_engine.py add art "Title" "Core lesson..." "Maker connection..."
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "drop":
        check_and_run_daily_drop(force=True)
        print("✅ Forced fresh lesson drop across all tracks!")
    elif cmd == "add" and len(sys.argv) >= 6:
        tk_k, title, core, maker = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
        d = load_data()
        lessons = d["tracks"][tk_k]["lessons"]
        seq = len(lessons) + 1
        lessons.append({
            "seq": seq,
            "date": datetime.now(MT_TZ).strftime("%Y-%m-%d"),
            "model": "CURATED",
            "title": title,
            "tags": ["curated"],
            "core": core,
            "maker": maker,
        })
        save_data_and_sync_github(d, f"Add curated {tk_k} lesson #{seq}: {title}")
        print(f"✅ Added {tk_k} #{seq:03d}!")
    else:
        d = load_data()
        for k, v in d["tracks"].items():
            print(f"{v['icon']} {k}: {len(v['lessons'])} lessons ({v['title']})")
