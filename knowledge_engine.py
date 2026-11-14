import os, re, json, time, base64, threading, urllib.request, urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

CURRICULUM_FILE = os.path.join(os.path.dirname(__file__), "curriculum.json")
MT_ZONE = ZoneInfo("America/Denver")
EPOCH_ZERO_TS = 1794623880  # 2026-11-13T19:38:00-07:00 (Epoch Zero)
_LOCK = threading.Lock()
_UA = "KnowledgeMatrixHub/2.0 (https://knowledge-center-dsog.onrender.com; educational)"

MODELS_CASCADE = [
    ("gemini-3.5-flash-lite", "3.5-FLASH-LITE"),
    ("gemini-3-flash-preview", "3-FLASH"),
    ("gemini-2.5-flash", "2.5-FLASH"),
    ("gemini-3.8-flash", "3.8-FLASH"),
]


_DROP_LOCK = threading.Lock()


def sync_curriculum_from_github():
    """Pull newest curriculum.json from GitHub on container boot so deploys never clobber cloud drops/stars."""
    tok = os.getenv("GITHUB_TOKEN", "").strip()
    repo = os.getenv("GITHUB_REPO", "").strip()
    if not tok or not repo:
        return False
    url = f"https://api.github.com/repos/{repo}/contents/curriculum.json"
    hdrs = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "User-Agent": _UA}
    try:
        req = urllib.request.Request(url, headers=hdrs)
        cur = json.loads(urllib.request.urlopen(req, timeout=12).read().decode())
        b64 = cur.get("content", "")
        if b64:
            raw = base64.b64decode(b64).decode("utf-8")
            cloud_data = json.loads(raw)
            local_data = load_curriculum()
            c_tot = sum(len(v.get("lessons", [])) for v in cloud_data.get("tracks", {}).values())
            l_tot = sum(len(v.get("lessons", [])) for v in local_data.get("tracks", {}).values())
            # Merge stamps by seq + note so neither GitHub nor container ever drops a stamp
            merged_stamps = {int(s.get("seq", 0)): s for s in local_data.get("stamps", [])}
            for s in cloud_data.get("stamps", []):
                merged_stamps[int(s.get("seq", 0))] = s
            base = cloud_data if c_tot >= l_tot else local_data
            base["stamps"] = [merged_stamps[k] for k in sorted(merged_stamps.keys())]
            base["epoch_zero"] = 1794623880
            with _LOCK:
                with open(CURRICULUM_FILE, "w") as f:
                    json.dump(base, f, indent=2)
            return True
    except Exception as e:
        print(f"[GitHub Boot Pull Warn] {e}", flush=True)
    return False


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


def _parse_lenient_json(raw_txt):
    """Parses Gemini JSON reliably even if the model puts raw newlines or markdown fences inside long monograph strings."""
    t = raw_txt.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    try:
        return json.loads(t, strict=False)
    except Exception:
        # Extract first {...} block and parse with strict=False (allows literal newlines/tabs inside strings!)
        m = re.search(r"\{.*\}", t, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0), strict=False)
            except Exception:
                cleaned = re.sub(r"\r?\n", r"\\n", m.group(0))
                return json.loads(cleaned, strict=False)
        raise


def call_gemini_json(prompt, expect_json=True):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set on server.")
    last_err = None
    for model_id, badge in MODELS_CASCADE:
        try:
            u = "https://generativelanguage.googleapis.com/v1beta/models/" + model_id + ":generateContent?key=" + key
            cfg = {"temperature": 0.65}
            if expect_json:
                cfg["responseMimeType"] = "application/json"
            body = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": cfg,
            }).encode()
            req = urllib.request.Request(u, data=body, headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST")
            resp = json.loads(urllib.request.urlopen(req, timeout=35).read().decode())
            txt = resp["candidates"][0]["content"]["parts"][0]["text"].strip()
            if expect_json:
                return _parse_lenient_json(txt), badge
            return txt, badge
        except Exception as e:
            last_err = f"{model_id}: {e}"
            continue
    raise RuntimeError(f"Gemini cascade exhausted ({last_err})")



def _http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode())


def resolve_visual_plates(query, count=1, track="art", exclude_urls=None):
    """Intent-aware 6-source visual resolver: routes album/book/cover queries to iTunes, Open Library & Wiki REST before generic keyword search."""
    plates = []
    seen = set(exclude_urls or [])
    q_raw = (query or "").strip()
    if not q_raw:
        return plates
    q_clean = q_raw.split("—")[0].split("(")[0].strip() if "—" in q_raw and len(q_raw) > 38 else q_raw
    q_low = q_clean.lower()

    album_intent = any(w in q_low for w in ("album", "vinyl", "lp", "single", "soundtrack", "sleeve", "discography", "record", "huncho", "music")) or ("cover" in q_low and "book" not in q_low)
    book_intent = any(w in q_low for w in ("book", "novel", "edition", "monograph", "jacket", "illustrated", "gonzo", "fear and loathing", "animal farm", "treasure island"))

    # Strip meta-words like 'album cover' or 'book cover' when querying strict catalog APIs (iTunes / Open Library)
    q_catalog = re.sub(r"\b(album\s+cover|book\s+cover|cover\s+art|album\s+art|sleeve\s+art|cover|album|artwork)\b", " ", q_clean, flags=re.I)
    q_catalog = " ".join(q_catalog.split()).strip() or q_clean

    def run_itunes():
        try:
            iq = urllib.parse.quote(q_catalog)
            for entity in ("album", "musicTrack"):
                iurl = f"https://itunes.apple.com/search?term={iq}&entity={entity}&limit={max(8, count*3)}"
                for item in _http_json(iurl).get("results", []):
                    art100 = item.get("artworkUrl100", "")
                    if art100:
                        hi = art100.replace("100x100bb", "1000x1000bb").replace("100x100", "1000x1000")
                        if hi not in seen:
                            seen.add(hi)
                            cname = item.get("collectionName") or item.get("trackName") or q_catalog
                            aname = item.get("artistName", "")
                            plates.append({
                                "url": hi,
                                "caption": f"{cname} — {aname}".strip(" —")[:100],
                                "source": "iTunes 1000px Sleeve Archive"
                            })
                            if len(plates) >= count:
                                return
        except Exception:
            pass

    def run_openlibrary():
        try:
            oq = urllib.parse.quote(q_catalog)
            ourl = f"https://openlibrary.org/search.json?q={oq}&limit={max(8, count*3)}"
            for doc in _http_json(ourl).get("docs", []):
                cid = doc.get("cover_i")
                if cid:
                    ou = f"https://covers.openlibrary.org/b/id/{cid}-L.jpg"
                    if ou not in seen:
                        seen.add(ou)
                        auth = ", ".join((doc.get("author_name") or [])[:2])
                        yr = doc.get("first_publish_year", "")
                        cap = f"{doc.get('title', q_catalog)}" + (f" ({yr})" if yr else "") + (f" — {auth}" if auth else "")
                        plates.append({"url": ou, "caption": cap[:100], "source": "Open Library Monographs"})
                        if len(plates) >= count:
                            return
        except Exception:
            pass

    def run_wiki_rest_lead():
        # Search top 3 exact Wikipedia titles, then hit REST /page/summary/ which DOES expose fair-use album/book cover lead images
        try:
            sq = urllib.parse.quote(q_catalog)
            s_hits = _http_json(f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={sq}&srlimit=3&format=json").get("query", {}).get("search", [])
            titles = [h.get("title", "") for h in s_hits if h.get("title")] or [q_catalog]
            for ttl in titles:
                slug = urllib.parse.quote(ttl.replace(" ", "_"))
                sdata = _http_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}")
                orig = (sdata.get("originalimage") or {}).get("source") or (sdata.get("thumbnail") or {}).get("source", "")
                if orig and orig not in seen and not orig.lower().endswith(".svg"):
                    seen.add(orig)
                    desc = sdata.get("description", "")
                    cap = f"{sdata.get('title', ttl)}" + (f" — {desc}" if desc else "")
                    plates.append({"url": orig, "caption": cap[:100], "source": "Wikipedia Lead Plate"})
                    if len(plates) >= count:
                        return
        except Exception:
            pass

    def run_wiki_pageimages():
        try:
            wq = urllib.parse.quote(q_clean)
            wurl = f"https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch={wq}&gsrlimit={max(8, count*3)}&prop=pageimages|pageterms&piprop=thumbnail&pithumbsize=960&format=json"
            pages = _http_json(wurl).get("query", {}).get("pages", {})
            for p in sorted(pages.values(), key=lambda x: x.get("index", 99)):
                src = (p.get("thumbnail") or {}).get("source", "")
                if src and src not in seen and not src.lower().endswith(".svg"):
                    seen.add(src)
                    desc = ((p.get("terms") or {}).get("description") or [""])[0]
                    cap = f"{p.get('title', q_clean)}" + (f" — {desc}" if desc else "")
                    plates.append({"url": src, "caption": cap, "source": "Wikipedia Archive"})
                    if len(plates) >= count:
                        return
        except Exception:
            pass

    def run_artic():
        if track != "art" or album_intent:
            return
        try:
            aq = urllib.parse.quote(q_clean)
            aurl = f"https://api.artic.edu/api/v1/artworks/search?q={aq}&fields=id,title,artist_title,image_id,date_display&limit={max(8, count*3)}"
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
                            return
        except Exception:
            pass

    def run_commons():
        try:
            cq = urllib.parse.quote(q_clean)
            curl = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrsearch={cq}&gsrlimit={max(12, count*4)}&prop=imageinfo&iiprop=url&iiurlwidth=960&format=json"
            cpages = _http_json(curl).get("query", {}).get("pages", {})
            for cp in cpages.values():
                ii = (cp.get("imageinfo") or [{}])[0]
                tu = ii.get("thumburl") or ii.get("url", "")
                if tu and tu not in seen and any(ext in tu.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    seen.add(tu)
                    ttl = cp.get("title", "").replace("File:", "").rsplit(".", 1)[0].replace("_", " ")
                    plates.append({"url": tu, "caption": ttl[:95], "source": "Wikimedia Commons"})
                    if len(plates) >= count:
                        return
        except Exception:
            pass

    # Dynamic pipeline routing based on query intent
    if album_intent:
        pipeline = [run_itunes, run_wiki_rest_lead, run_commons, run_wiki_pageimages, run_openlibrary]
    elif book_intent:
        pipeline = [run_openlibrary, run_wiki_rest_lead, run_commons, run_wiki_pageimages, run_artic, run_itunes]
    else:
        pipeline = [run_wiki_rest_lead, run_wiki_pageimages, run_artic, run_commons, run_openlibrary, run_itunes]

    for stage in pipeline:
        if len(plates) < count:
            stage()

    return plates

def find_lesson(data, track_key, seq):
    lessons = data.get("tracks", {}).get(track_key, {}).get("lessons", [])
    for les in lessons:
        if int(les.get("seq", -1)) == int(seq):
            return les
    raise KeyError(f"Lesson #{seq} not found in track '{track_key}'")


def generate_deep_dive_for_lesson(track_key, seq, append=False):
    data = load_curriculum()
    les = find_lesson(data, track_key, seq)
    if not les:
        raise ValueError(f"Lesson {track_key} #{seq} not found")

    existing_dd = (les.get("deep_dive") or "").strip()
    if append and existing_dd:
        chapter_num = existing_dd.count("=== DEEPER DIVE CHAPTER") + 2
        prompt = f"""Write Deeper Dive Chapter {chapter_num} for lesson: "{les.get('title')}" ({track_key} track).
Core summary: {les.get('core')}
Studio craft lens: {les.get('maker')}

Already covered in previous chapters (DO NOT repeat these exact points; go one layer deeper into concrete material physics, archival history, rare technical mechanics, or radical studio execution):
{existing_dd[-1800:]}

Format strictly as:
TITLE: <Short punchy subtitle for Chapter {chapter_num}>
<3-4 rich, forensic paragraphs separated by blank lines. Write plain text only, no JSON, no markdown code fences.>"""
        raw_txt, badge = call_gemini_json(prompt, expect_json=False)
        lines = [ln.strip() for ln in raw_txt.strip().splitlines() if ln.strip()]
        ch_title = f"Level {chapter_num} Synthesis"
        body_start = 0
        if lines and lines[0].upper().startswith("TITLE:"):
            ch_title = lines[0][6:].strip().strip('"').strip("*")
            body_start = 1
        new_body = "\n\n".join(lines[body_start:]) if body_start < len(lines) else raw_txt.strip()
        les["deep_dive"] = f"{existing_dd}\n\n=== DEEPER DIVE CHAPTER {chapter_num}: {ch_title.upper()} [{badge}] ===\n\n{new_body}"
        les["model"] = badge
        save_curriculum(data, f"Deeper Dive Ch.{chapter_num}: {track_key} #{seq:03d}")
        return les

    prompt = f"""Write an exhaustive, vivid 4-paragraph Deep Dive Monograph for lesson: "{les.get('title')}" ({track_key} track).
Core context: {les.get('core')}
Studio Craft connection: {les.get('maker')}

Write 4 rich paragraphs separated by blank lines covering:
1. Origin & historical/scientific context
2. Exact physical, material, or mathematical mechanics
3. Landmark masterwork or experiment
4. Hands-on Studio Craft synthesis

Write plain text paragraphs only (no JSON, no markdown headings)."""
    raw_txt, badge = call_gemini_json(prompt, expect_json=False)
    les["deep_dive"] = raw_txt.strip()
    les["model"] = badge
    save_curriculum(data, f"Deep Dive: {track_key} #{seq:03d}")
    return les


def generate_gallery_for_lesson(track_key, seq, append=False, custom_query=""):
    data = load_curriculum()
    les = find_lesson(data, track_key, seq)
    existing = list(les.get("gallery") or [])
    custom_q = (custom_query or "").strip()

    if not append and not custom_q and len(existing) >= 3:
        return les

    seen = {les.get("image_url", "")} | {p.get("url", "") for p in existing if p.get("url")}
    existing_caps = [p.get("caption", "")[:45] for p in existing[-12:]]
    new_plates = []

    # Direct fast-path + Gemini query expansion when custom_query is given or infinite "Curate 5 More" is clicked
    if custom_q:
        direct = resolve_visual_plates(custom_q, count=3, track=track_key, exclude_urls=seen)
        for p in direct:
            if p["url"] not in seen:
                seen.add(p["url"])
                p["study_note"] = f"Custom target: {custom_q}"
                new_plates.append(p)

    focus_line = f"CRITICAL: Every query MUST directly retrieve '{custom_q}' (use exact album/book/work titles, e.g. 'Huncho Jack, Jack Huncho' or 'Fear and Loathing in Las Vegas', NEVER generic artist portrait pages)." if custom_q else f"Avoid already-shown plates: {existing_caps}. Dig into fresh masterworks, closeups, editions, sketches, or apparatus."
    prompt = f"""Give me 6 specific search queries across Wikipedia, Art Institute, Wikimedia Commons, Open Library, or iTunes to pull real visual plates for:
Track: {track_key}
Lesson Title: {les['title']}
Summary: {les['core']}
Directive: {focus_line}
Return JSON: {{"queries": [{{"q": "exact search term (artist + specific work, book title, or specific physics diagram)", "note": "1-sentence guide on what structural detail to look for"}}]}}"""

    try:
        res, _ = call_gemini_json(prompt, expect_json=True)
        for item in res.get("queries", [])[:7]:
            if len(new_plates) >= 5:
                break
            found = resolve_visual_plates(item.get("q", ""), count=2, track=track_key, exclude_urls=seen)
            for p in found:
                if p["url"] not in seen:
                    seen.add(p["url"])
                    p["study_note"] = item.get("note", "") or (f"Target: {custom_q}" if custom_q else "")
                    new_plates.append(p)
                    break
    except Exception:
        pass

    if len(new_plates) < 5:
        fallback_q = custom_q if custom_q else les["title"].split("—")[0].strip()
        extra = resolve_visual_plates(fallback_q, count=8, track=track_key, exclude_urls=seen)
        for p in extra:
            if p["url"] not in seen:
                seen.add(p["url"])
                if custom_q and not p.get("study_note"):
                    p["study_note"] = f"Target: {custom_q}"
                new_plates.append(p)
                if len(new_plates) >= 5:
                    break

    if append or custom_q or existing:
        les["gallery"] = existing + new_plates[:5]
    else:
        les["gallery"] = new_plates[:5]

    action_lbl = f"Curate +{len(new_plates[:5])} Plates" + (f" [{custom_q[:24]}]" if custom_q else "")
    save_curriculum(data, f"{action_lbl} for {track_key} #{seq:03d}")
    return les


def delete_gallery_plate(track_key, seq, url):
    url_clean = (url or "").strip()
    if not url_clean:
        raise ValueError("Missing plate URL")
    data = load_curriculum()
    les = find_lesson(data, track_key, int(seq))
    les["gallery"] = [g for g in (les.get("gallery") or []) if (g.get("url") or "").strip() != url_clean]
    data["favorites"] = [f for f in data.setdefault("favorites", []) if (f.get("url") or "").strip() != url_clean]
    save_curriculum(data, f"Prune gallery plate from {track_key} #{int(seq):03d}")
    return {"lesson": les, "favorites": data["favorites"]}


def toggle_favorite_plate(track_key, seq, url, caption="", study_note="", source=""):
    url_clean = (url or "").strip()
    if not url_clean:
        raise ValueError("Missing plate URL")
    data = load_curriculum()
    favs = data.setdefault("favorites", [])
    for idx, f_item in enumerate(favs):
        if f_item.get("url") == url_clean:
            favs.pop(idx)
            save_curriculum(data, f"Unstar plate from {track_key} #{int(seq):03d}")
            return {"favorited": False, "favorites": favs}

    les_title = ""
    try:
        les_title = find_lesson(data, track_key, int(seq)).get("title", "")
    except Exception:
        pass

    entry = {
        "url": url_clean,
        "caption": (caption or les_title or "Visual Plate")[:160],
        "study_note": (study_note or "")[:200],
        "source": (source or "Archive")[:60],
        "track": track_key,
        "seq": int(seq),
        "lesson_title": les_title,
        "saved_at": datetime.now(MT_ZONE).strftime("%Y-%m-%d %H:%M MT"),
    }
    favs.insert(0, entry)
    save_curriculum(data, f"Star plate to Key's Favorites ({track_key} #{int(seq):03d})")
    return {"favorited": True, "favorites": favs}


def get_capacity_telemetry(data=None):
    try:
        raw_bytes = os.path.getsize(CURRICULUM_FILE)
    except Exception:
        raw_bytes = len(json.dumps(data or {}).encode("utf-8"))

    # GitHub Contents API blob limit via base64 PUT is 100 MB (~75 MB raw JSON safe ceiling)
    gh_limit_mb = 75.0
    used_mb = raw_bytes / (1024 * 1024)
    gh_pct = round((used_mb / gh_limit_mb) * 100, 2)

    ram_mb = 0.0
    try:
        with open("/proc/self/status", "r") as sf:
            for line in sf:
                if line.startswith("VmRSS:"):
                    ram_mb = int(line.split()[1]) / 1024.0
                    break
    except Exception:
        pass

    d = data if isinstance(data, dict) else load_curriculum()
    tracks = d.get("tracks", {})
    total_lessons = sum(len(tracks.get(t, {}).get("lessons", [])) for t in ("art", "universe", "matrix"))
    avg_bytes = max(3800, raw_bytes / max(1, total_lessons))
    daily_bytes = avg_bytes * 3.0
    remaining_bytes = max(0, (gh_limit_mb * 1024 * 1024) - raw_bytes)
    runway_years = round((remaining_bytes / daily_bytes) / 365.25, 1)
    runway_hours = int(round((remaining_bytes / daily_bytes) * 24))

    return {
        "runway_hours": runway_hours,
        "epoch_zero": EPOCH_ZERO_TS,
        "json_kb": round(raw_bytes / 1024.0, 1),
        "json_mb": round(used_mb, 2),
        "gh_limit_mb": gh_limit_mb,
        "gh_pct": gh_pct,
        "ram_mb": round(ram_mb, 1),
        "ram_limit_mb": 512,
        "ram_pct": round((ram_mb / 512.0) * 100, 1) if ram_mb else 0.0,
        "total_lessons": total_lessons,
        "favorites_count": len(d.get("favorites", [])),
        "runway_years": runway_years,
    }

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


def check_and_run_daily_drop(force=False):
    if not _DROP_LOCK.acquire(blocking=False):
        return {"ran": False, "changed": [], "reason": "already_running"}
    try:
        now_mt = datetime.now(MT_ZONE)
        if not force and (now_mt.hour, now_mt.minute) < (8, 30):
            return {"ran": False, "changed": [], "reason": "before_0830_mt"}
        today_str = now_mt.strftime("%Y-%m-%d")
        data = load_curriculum()
        changed = []
        errors = {}
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
                save_curriculum(data, f"Daily Drop ({today_str}): {tag}")
                time.sleep(2)
            except Exception as e:
                errors[t_key] = str(e)
                print(f"[Auto-Drop Error {t_key}] {e}", flush=True)
        return {"ran": bool(changed), "changed": changed, "errors": errors, "date": today_str}
    finally:
        _DROP_LOCK.release()


def add_epoch_stamp(note=""):
    note_clean = (note or "").strip()[:140] or "Unlabeled Session Mark"
    data = load_curriculum()
    stamps = data.setdefault("stamps", [])
    now_ts = time.time()
    epoch_hrs = round(max(0.0, (now_ts - EPOCH_ZERO_TS) / 3600.0), 4)
    prev_hrs = stamps[-1]["epoch_hrs"] if stamps else 0.0
    delta_hrs = round(max(0.0, epoch_hrs - prev_hrs), 4)
    next_seq = max((int(s.get("seq", 0)) for s in stamps), default=0) + 1
    entry = {
        "seq": next_seq,
        "ts": int(now_ts),
        "epoch_hrs": epoch_hrs,
        "delta_hrs": delta_hrs,
        "note": note_clean,
    }
    stamps.append(entry)
    save_curriculum(data, f"Epoch Zero Stamp #{next_seq:03d} ({epoch_hrs:011.4f} HRS): {note_clean[:40]}")
    return {"stamp": entry, "stamps": stamps}


def _get_recent_curriculum_context(data):
    tracks = data.get("tracks", {})
    summary = []
    for t_key, label in (("art", "Art Endurance"), ("universe", "Physics of Time"), ("matrix", "Matrix")):
        lessons = tracks.get(t_key, {}).get("lessons", [])
        if lessons:
            latest = lessons[-1]
            summary.append(f"{label} #{int(latest.get('seq', 0)):03d}: {latest.get('title', '')} — {(latest.get('core') or '')[:140]}...")
    return summary

POEM_THEMES = ["time", "eternity", "dream", "shadow", "star", "night", "infinite", "silence", "flame", "clock", "soul", "light", "sleep", "memory", "void"]

def curate_poem_desk(force_new=False):
    data = load_curriculum()
    if not force_new and data.get("current_poem"):
        return data["current_poem"]

    favs = data.get("favorites", [])
    starred_poems = [f for f in favs if str(f.get("url", "")).startswith("poem://")]
    fav_authors = list({f.get("source", "") for f in starred_poems if f.get("source")})
    stamps = data.get("stamps", [])
    last_stamp = stamps[-1].get("note", "Epoch Zero") if stamps else "Epoch Zero"

    candidates = []
    import random
    search_terms = random.sample(POEM_THEMES, min(3, len(POEM_THEMES)))
    for term in search_terms:
        try:
            url = f"https://poetrydb.org/title,lines/{urllib.parse.quote(term)};14/author,title,lines,linecount.json"
            res = _http_json(url)
            if isinstance(res, list):
                for p in res:
                    lines = p.get("lines", [])
                    if len(lines) >= 4:
                        candidates.append({
                            "author": p.get("author", "Unknown"),
                            "title": p.get("title", "Untitled"),
                            "lines": lines[:16],
                            "full_lines": lines[:140],
                            "linecount": len(lines)
                        })
        except Exception:
            pass

    if not candidates:
        try:
            res = _http_json("https://poetrydb.org/random/6/author,title,lines,linecount.json")
            if isinstance(res, list):
                for p in res:
                    lines = p.get("lines", [])
                    if lines:
                        candidates.append({
                            "author": p.get("author", "Archival Poet"),
                            "title": p.get("title", "Fragment"),
                            "lines": lines[:16],
                            "full_lines": lines[:140],
                            "linecount": len(lines)
                        })
        except Exception:
            pass

    chosen = candidates[0] if candidates else {
        "author": "Robert Louis Stevenson",
        "title": "Death, to the Dead for Evermore",
        "lines": ["DEATH, to the dead for evermore", "A King, a God, the last, the best of friends -"],
        "full_lines": ["DEATH, to the dead for evermore", "A King, a God, the last, the best of friends -"],
        "linecount": 2
    }
    curator_note = f"Matched to Stamp '{last_stamp}' across the 1,000-author corpus."
    written_when = "Historical Era (Archival Corpus)"
    written_where = "Literary Spacetime Coordinate"

    if os.getenv("GEMINI_API_KEY", "").strip():
        try:
            pool = random.sample(candidates, min(6, len(candidates))) if len(candidates) > 1 else [chosen]
            prompt = {
                "task": "Select the single poem index (0 to N-1) that best resonates with the user's latest Epoch Zero stamp note and starred poet taste, and provide the historical date/year and geographical location where the author wrote it.",
                "latest_stamp_note": last_stamp,
                "active_curriculum_lessons": _get_recent_curriculum_context(data),
                "starred_poets": fav_authors[:8],
                "candidates": [{"idx": i, "author": c["author"], "title": c["title"], "preview": " / ".join(c["lines"][:4])} for i, c in enumerate(pool)],
                "return_json": {
                    "idx": 0,
                    "written_when": "Exact year or historical decade written/published (e.g. 'c. 1891 (Late Victorian Era)')",
                    "written_where": "City/Country or estate where the poet lived when writing this (e.g. 'Vailima, Samoa / Edinburgh, Scotland')",
                    "curator_note": "1-2 sentence synthesis linking this poem to the user's latest stamp note and consciousness/time."
                }
            }
            g_res = call_gemini_json(json.dumps(prompt), expect_json=True)
            if isinstance(g_res, dict):
                idx = int(g_res.get("idx", 0))
                if 0 <= idx < len(pool):
                    chosen = pool[idx]
                if g_res.get("curator_note"):
                    curator_note = str(g_res["curator_note"])[:280]
                if g_res.get("written_when"):
                    written_when = str(g_res["written_when"])[:90]
                if g_res.get("written_where"):
                    written_where = str(g_res["written_where"])[:90]
        except Exception:
            pass

    poem_uri = f"poem://{chosen['author']}/{chosen['title']}"
    entry = {
        "uri": poem_uri,
        "author": chosen["author"],
        "title": chosen["title"],
        "lines": chosen["lines"],
        "full_lines": chosen.get("full_lines") or chosen["lines"],
        "total_lines": chosen.get("linecount") or len(chosen["lines"]),
        "written_when": written_when,
        "written_where": written_where,
        "curator_note": curator_note,
        "deep_dive": "",
        "curated_at": datetime.now(MT_ZONE).strftime("%Y-%m-%d %H:%M MT")
    }
    data["current_poem"] = entry
    save_curriculum(data, f"Poem Desk Curated: {chosen['title']} ({chosen['author']})")
    return entry


def generate_poem_deep_dive():
    data = load_curriculum()
    p = data.get("current_poem")
    if not p:
        p = curate_poem_desk(force_new=False)
    existing_dd = (p.get("deep_dive") or "").strip()
    chap_num = 1 if not existing_dd else (existing_dd.count("=== POEM DEEP DIVE CHAPTER") + 2)
    stamps = data.get("stamps", [])
    last_stamp = stamps[-1].get("note", "Epoch Zero") if stamps else "Epoch Zero"

    prompt = (
        f"You are the Epoch Zero Literary & Temporal Architect. Write CHAPTER {chap_num} of an unlimited Deep Dive "
        f"into the poem '{p.get('title')}' by {p.get('author')}.\n"
        f"Poem Lines:\n" + "\n".join((p.get("full_lines") or p.get("lines") or [])[:45]) + "\n\n"
        f"Latest User Epoch Zero Stamp: '{last_stamp}'.\n"
        f"Active Art & Physics of Time Curriculum Lessons to collide with this poem:\n" + "\n".join(_get_recent_curriculum_context(data)) + "\n\n"
        f"Previous Chapters Already Written (DO NOT REPEAT, go deeper into new stanzas, biography, historical location/date, and philosophical subtext):\n{existing_dd[-1800:] if existing_dd else 'None yet.'}\n\n"
        "Return STRICT JSON with keys: "
        "{\"written_when\": \"Exact year/date written\", \"written_where\": \"Exact city/place written\", \"chapter_title\": \"Title of this chapter\", \"analysis\": \"3-4 rich paragraphs analyzing the historical spacetime coordinates of the poet, line-by-line hidden meaning, and direct collision with the user's active Art Endurance & Physics of Time lessons, latest Epoch Zero stamp, and Sovereign Detective consciousness.\"}"
    )
    res = call_gemini_json(prompt, expect_json=True)
    if isinstance(res, dict):
        if res.get("written_when") and ("Historical Era" in p.get("written_when", "") or not p.get("written_when")):
            p["written_when"] = str(res["written_when"])[:90]
        if res.get("written_where") and ("Literary Spacetime" in p.get("written_where", "") or not p.get("written_where")):
            p["written_where"] = str(res["written_where"])[:90]
        c_title = str(res.get("chapter_title") or f"The Poet's Reference Frame & Hidden Symbols")
        body = str(res.get("analysis") or "").strip()
    else:
        c_title = f"Biographical & Line-by-Line Exegesis"
        body = str(res or "Deep analysis unavailable—check GEMINI_API_KEY.")

    header = f"=== POEM DEEP DIVE CHAPTER {chap_num}: {c_title.upper()} ==="
    if existing_dd:
        p["deep_dive"] = existing_dd + "\n\n" + header + "\n" + body
    else:
        p["deep_dive"] = header + "\n" + body

    data["current_poem"] = p
    save_curriculum(data, f"Poem Deep Dive Ch.{chap_num}: {p.get('title')} ({p.get('author')})")
    return p
