import os, json, time, base64, threading, urllib.request, urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

CURRICULUM_FILE = os.path.join(os.path.dirname(__file__), "curriculum.json")
MT_ZONE = ZoneInfo("America/Denver")
_LOCK = threading.Lock()
_UA = "KnowledgeMatrixHub/2.0 (https://knowledge-center-dsog.onrender.com; educational)"

MODELS_CASCADE = [
    ("gemini-3.8-flash", "3.8-FLASH"),
    ("gemini-3.6-flash", "3.6-FLASH"),
    ("gemini-3.5-flash-lite", "3.5-FLASH-LITE"),
]


def load_curriculum():
    with open(CURRICULUM_FILE, "r") as f:
        return json.load(f)


def save_curriculum(data, commit_msg=None):
    with _LOCK:
        with open(CURRICULUM_FILE, "w") as f:
            json.dump(data, f, indent=2)
        if commit_msg:
            threading.Thread(target=_commit_to_github, args=(commit_msg,), daemon=True).start()


def _commit_to_github(commit_msg):
    tok = os.getenv("GITHUB_TOKEN", "").strip()
    repo = os.getenv("GITHUB_REPO", "").strip()
    if not tok or not repo:
        return False
    url = f"https://api.github.com/repos/{repo}/contents/curriculum.json"
    hdrs = {
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
        "User-Agent": _UA,
    }
    try:
        req = urllib.request.Request(url, headers=hdrs)
        cur = json.loads(urllib.request.urlopen(req, timeout=12).read().decode())
        sha = cur.get("sha")
        with open(CURRICULUM_FILE, "rb") as f:
            raw_b64 = base64.b64encode(f.read()).decode()
        payload = json.dumps({"message": commit_msg, "content": raw_b64, "sha": sha}).encode()
        put_req = urllib.request.Request(url, data=payload, headers={**hdrs, "Content-Type": "application/json"}, method="PUT")
        urllib.request.urlopen(put_req, timeout=15).read()
        return True
    except Exception as e:
        print(f"[GitHub Sync Warn] {e}")
        return False


def call_gemini_json(prompt, expect_json=True):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set on server.")
    last_err = None
    for model_id, badge in MODELS_CASCADE:
        try:
            u = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={key}"
            cfg = {}
            if expect_json:
                cfg["responseMimeType"] = "application/json"
            body = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}).encode()
            req = urllib.request.Request(u, data=body, headers={"Content-Type": "application/json"}, method="POST")
            resp = json.loads(urllib.request.urlopen(req, timeout=75).read().decode())
            txt = resp["candidates"][0]["content"]["parts"][0]["text"].strip()
            if expect_json:
                if txt.startswith("```"):
                    txt = txt.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                return json.loads(txt), badge
            return txt, badge
        except Exception as e:
            print(f'[Gemini Try {model_id}] {e}', flush=True)
            last_err = f'{model_id}: {e}'
            time.sleep(2)
            continue
    raise RuntimeError(f"Gemini cascade exhausted: {last_err}")


def _http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode())


def resolve_visual_plates(query, count=1, track="art"):
    """Resolves verified HTTPS Wikimedia/Wikipedia or Art Institute plates (zero hallucinated URLs)."""
    plates = []
    seen = set()
    q_clean = query.split("—")[0].split("(")[0].strip() if "—" in query and len(query) > 38 else query.strip()

    # 1) Wikipedia PageImages Search (Primary high-precision match)
    try:
        wq = urllib.parse.quote(q_clean)
        wurl = f"https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch={wq}&gsrlimit={max(4, count*2)}&prop=pageimages|pageterms&piprop=thumbnail&pithumbsize=900&format=json"
        pages = _http_json(wurl).get("query", {}).get("pages", {})
        for p in sorted(pages.values(), key=lambda x: x.get("index", 99)):
            src = (p.get("thumbnail") or {}).get("source", "")
            if src and src not in seen and not src.lower().endswith(".svg"):
                seen.add(src)
                desc = ((p.get("terms") or {}).get("description") or [""])[0]
                cap = f"{p.get('title', q_clean)}" + (f" — {desc}" if desc else "")
                plates.append({"url": src, "caption": cap, "source": "Wikimedia Archive"})
                if len(plates) >= count:
                    return plates
        # Allow SVG diagrams for Universe/Matrix if raster wasn't enough
        for p in sorted(pages.values(), key=lambda x: x.get("index", 99)):
            src = (p.get("thumbnail") or {}).get("source", "")
            if src and src not in seen:
                seen.add(src)
                plates.append({"url": src, "caption": p.get("title", q_clean), "source": "Wikimedia Diagram"})
                if len(plates) >= count:
                    return plates
    except Exception:
        pass

    # 2) Art Institute of Chicago Open Access Fallback (Great for fine art closeups)
    if track == "art" and len(plates) < count:
        try:
            aq = urllib.parse.quote(q_clean)
            aurl = f"https://api.artic.edu/api/v1/artworks/search?q={aq}&fields=id,title,artist_title,image_id,date_display&limit={count+3}"
            adata = _http_json(aurl)
            iiif = (adata.get("config") or {}).get("iiif_url", "https://www.artic.edu/iiif/2")
            for item in adata.get("data", []):
                iid = item.get("image_id")
                if iid:
                    iu = f"{iiif}/{iid}/full/843,/0/default.jpg"
                    if iu not in seen:
                        seen.add(iu)
                        plates.append({
                            "url": iu,
                            "caption": f"{item.get('title', '')} ({item.get('date_display', '')}) — {item.get('artist_title', '')}".strip(" —"),
                            "source": "Art Institute Open Access"
                        })
                        if len(plates) >= count:
                            return plates
        except Exception:
            pass

    # 3) Wikimedia Commons Direct File Search
    if len(plates) < count:
        try:
            cq = urllib.parse.quote(q_clean)
            curl = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrsearch={cq}&gsrlimit={count*3}&prop=imageinfo&iiprop=url&iiurlwidth=900&format=json"
            cpages = _http_json(curl).get("query", {}).get("pages", {})
            for cp in cpages.values():
                ii = (cp.get("imageinfo") or [{}])[0]
                tu = ii.get("thumburl") or ii.get("url", "")
                if tu and tu not in seen and any(ext in tu.lower() for ext in [".jpg", ".jpeg", ".png"]):
                    seen.add(tu)
                    ttl = cp.get("title", "").replace("File:", "").rsplit(".", 1)[0].replace("_", " ")
                    plates.append({"url": tu, "caption": ttl[:95], "source": "Wikimedia Commons"})
                    if len(plates) >= count:
                        return plates
        except Exception:
            pass

    return plates


def find_lesson(data, track_key, seq):
    lessons = data.get("tracks", {}).get(track_key, {}).get("lessons", [])
    for les in lessons:
        if int(les.get("seq", -1)) == int(seq):
            return les
    raise KeyError(f"Lesson #{seq} not found in track '{track_key}'")


def generate_deep_dive_for_lesson(track_key, seq):
    data = load_curriculum()
    les = find_lesson(data, track_key, seq)
    if les.get("deep_dive") and len(les["deep_dive"]) > 200:
        return les

    if track_key == "matrix":
        prompt = f"""You are Keyshawn's lead systems architect teaching him every nut and bolt of his own live codebase (Keith Stoner spaceship-engineer style).
Module: {les['title']}
Summary: {les['core']}
Code Snippet:
{les.get('code_snippet', '')}

Return JSON with keys:
- "deep_dive": A rich 4-paragraph architectural & engineering deep dive (separated by \\n\\n) explaining: (1) Why this subsystem exists in the spaceship, (2) How data flows step-by-step at runtime, (3) Failure modes / security / rate-limit guardrails we built in, and (4) How Keyshawn can modify or extend this module himself.
- "line_decode": Array of 6 to 8 objects [{{"code": "exact line or construct", "meaning": "crystal-clear plain-English explanation of every keyword, symbol, and operation"}}]."""
        res, badge = call_gemini_json(prompt, expect_json=True)
        les["deep_dive"] = res.get("deep_dive", "")
        if res.get("line_decode"):
            les["line_decode"] = res["line_decode"]
        les["deep_dive_model"] = badge
    else:
        lens_hint = "garment architecture, multi-fabric layering (denim, felt, flannel, Climalite), negative-space cross cutouts, and 20+ hour studio endurance" if track_key == "art" else "structural craft, block-universe geometry, entropy, and physical studio intuition"
        prompt = f"""Write an authoritative, riveting 4-paragraph monograph deep dive (separated by \\n\\n) on:
Title: {les['title']}
Core Premise: {les['core']}

Cover:
Paragraph 1: Historical/scientific origin and the exact problem or orthodoxy being shattered.
Paragraph 2: Deep technical or physical mechanics—materials, equations, brushwork, or experimental apparatus in concrete detail.
Paragraph 3: Signature masterwork or landmark experiment unpacked closely.
Paragraph 4: Extended Studio Craft synthesis connecting directly to {lens_hint}.

Return JSON: {{"deep_dive": "paragraph1\\n\\nparagraph2\\n\\nparagraph3\\n\\nparagraph4"}}"""
        res, badge = call_gemini_json(prompt, expect_json=True)
        les["deep_dive"] = res.get("deep_dive", "")
        les["deep_dive_model"] = badge

    save_curriculum(data, f"Cache Deep Dive for {track_key} #{seq:03d} ({les['title'][:36]})")
    return les


def generate_gallery_for_lesson(track_key, seq):
    data = load_curriculum()
    les = find_lesson(data, track_key, seq)
    if les.get("gallery") and len(les["gallery"]) >= 3:
        return les

    prompt = f"""Give me 5 specific Wikipedia/Wikimedia/Museum search queries to pull real archival photos or diagrams for:
Track: {track_key}
Title: {les['title']}
Summary: {les['core']}
Return JSON: {{"queries": [{{"q": "exact search term (artist + specific work, or specific physics diagram)", "note": "1-sentence guide on what structural detail to look for"}}]}}"""
    plates = []
    seen = {les.get("image_url", "")}
    try:
        res, _ = call_gemini_json(prompt, expect_json=True)
        for item in res.get("queries", [])[:6]:
            found = resolve_visual_plates(item.get("q", ""), count=2, track=track_key)
            for p in found:
                if p["url"] not in seen:
                    seen.add(p["url"])
                    p["study_note"] = item.get("note", "")
                    plates.append(p)
                    break
            if len(plates) >= 5:
                break
    except Exception:
        pass

    if len(plates) < 3:
        extra = resolve_visual_plates(les["title"].split("—")[0].strip(), count=5, track=track_key)
        for p in extra:
            if p["url"] not in seen:
                seen.add(p["url"])
                plates.append(p)

    les["gallery"] = plates[:6]
    save_curriculum(data, f"Cache Gallery Plates for {track_key} #{seq:03d}")
    return les


def ask_architect_on_lesson(track_key, seq, question):
    data = load_curriculum()
    les = find_lesson(data, track_key, seq)
    q_clean = (question or "").strip()
    if not q_clean:
        raise ValueError("Empty question")

    ctx_extra = f"\nCode Snippet:\n{les.get('code_snippet', '')}" if track_key == "matrix" else ""
    prompt = f"""You are Keyshawn's direct AI collaborator answering a sharp follow-up question inside his {track_key.upper()} Command Center.
Lesson #{seq:03d}: {les['title']}
Core: {les['core']}
Deep Dive Context: {les.get('deep_dive', '')[:1200]}{ctx_extra}

Keyshawn's Question: {q_clean}

Answer directly, concretely, and insightfully in 2 to 4 tight paragraphs (no fluff intro). Return JSON: {{"answer": "your response"}}"""
    res, badge = call_gemini_json(prompt, expect_json=True)
    qa_entry = {
        "ts": datetime.now(MT_ZONE).strftime("%Y-%m-%d %H:%M MT"),
        "model": badge,
        "q": q_clean,
        "a": res.get("answer", ""),
    }
    les.setdefault("qa_log", []).append(qa_entry)
    save_curriculum(data, f"Save Q&A on {track_key} #{seq:03d}")
    return les


def _generate_next_lesson(track_key, existing_lessons, today_str):
    next_seq = max([l.get("seq", 0) for l in existing_lessons], default=0) + 1
    prev_titles = [l.get("title", "") for l in existing_lessons[-35:]]

    if track_key == "art":
        prompt = f"""Generate Art Endurance & Structural Craft Lesson #{next_seq:03d} for wearable fine artist Keyshawn Bannister.
Avoid repeating these already-covered subjects: {prev_titles}.
Pick a monumental painter, sculptor, avant-garde couturier, textile radical, or endurance artist.
Return JSON:
{{
  "title": "Artist Name — Specific Masterwork or Structural Method",
  "tags": ["tag1", "tag2", "tag3"],
  "wiki_query": "Exact Wikipedia search query for iconic artwork photo",
  "core": "2-3 vivid sentences on their physical process, endurance, and structural rigor.",
  "maker": "1-2 concrete sentences connecting this directly to multi-layered denim/felt/flannel/Climalite garment architecture and hand/zig-zag stitching.",
  "deep_dive": "4 rich paragraphs separated by \\n\\n covering origin, physical material technique, landmark work, and studio craft synthesis."
}}"""
    elif track_key == "universe":
        prompt = f"""Generate Physics of Time, Entropy & Block Universe Lesson #{next_seq:03d}.
Avoid repeating: {prev_titles}.
Return JSON:
{{
  "title": "Concept or Physicist — Specific Physical Mechanism",
  "tags": ["physics-tag1", "tag2", "tag3"],
  "wiki_query": "Exact Wikipedia search query for physics diagram or astronomical plate",
  "core": "2-3 crisp sentences unpacking the exact physical mechanism and math intuition.",
  "maker": "1-2 sentences translating this physical law into material permanence, studio craft, or creative focus.",
  "deep_dive": "4 rich paragraphs separated by \\n\\n covering historical paradox, physical mechanics/equations, experimental proof, and philosophical/studio synthesis."
}}"""
    else:
        prompt = f"""Generate Matrix Systems Engineering Lesson #{next_seq:03d} teaching Keyshawn how his Linux, Python, Tkinter, Flask, OANDA v20 API, Git, and Gemini stack works under the hood.
Avoid repeating: {prev_titles}.
Return JSON:
{{
  "title": "Subsystem Name — Specific Code Mechanism",
  "tags": ["python", "architecture", "systems"],
  "diagram_type": "pipeline",
  "file_ref": "stack_anatomy.py",
  "core": "2-3 clear sentences explaining what this engineering pattern does in his live command centers.",
  "maker": "1-2 sentences comparing code modularity/fault-tolerance to structural seam construction.",
  "code_snippet": "10-16 lines of realistic Python/Bash demonstrating the exact mechanism from his stack",
  "line_decode": [
    {{"code": "line 1", "meaning": "plain-English breakdown"}},
    {{"code": "line 2", "meaning": "plain-English breakdown"}},
    {{"code": "line 3", "meaning": "plain-English breakdown"}},
    {{"code": "line 4", "meaning": "plain-English breakdown"}}
  ],
  "deep_dive": "4 clear paragraphs separated by \\n\\n explaining why it exists, runtime execution flow, edge-case guardrails, and how to hack/extend it."
}}"""

    res, badge = call_gemini_json(prompt, expect_json=True)
    plates = resolve_visual_plates(res.get("wiki_query") or res["title"], count=4, track=track_key)
    primary = plates[0] if plates else {}
    entry = {
        "seq": next_seq,
        "date": today_str,
        "model": badge,
        "title": res["title"],
        "tags": res.get("tags", []),
        "core": res["core"],
        "maker": res["maker"],
        "deep_dive": res.get("deep_dive", ""),
        "image_url": primary.get("url", ""),
        "image_caption": primary.get("caption", ""),
        "gallery": plates[1:5] if len(plates) > 1 else plates,
    }
    if track_key == "matrix":
        entry["diagram_type"] = res.get("diagram_type", "pipeline")
        entry["file_ref"] = res.get("file_ref", "architecture.py")
        entry["code_snippet"] = res.get("code_snippet", "")
        entry["line_decode"] = res.get("line_decode", [])
    return entry


def check_and_run_daily_drop():
    now_mt = datetime.now(MT_ZONE)
    if (now_mt.hour, now_mt.minute) < (8, 30):
        return False
    today_str = now_mt.strftime("%Y-%m-%d")
    data = load_curriculum()
    changed = []
    for t_key in ("art", "universe", "matrix"):
        track = data.get("tracks", {}).get(t_key)
        if not track:
            continue
        lessons = track.get("lessons", [])
        if any(l.get("date") == today_str for l in lessons):
            continue
        try:
            new_l = _generate_next_lesson(t_key, lessons, today_str)
                lessons.append(new_l)
                tag = f"{t_key} #{new_l['seq']:03d}"
                changed.append(tag)
                save_curriculum(data, f"08:30 MT Auto-Drop: {tag}")
                time.sleep(4)
            except Exception as e:
                print(f"[Auto-Drop Error {t_key}] {e}", flush=True)
    if changed:
        return True
    return False
