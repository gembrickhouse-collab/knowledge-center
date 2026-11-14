import os, sys, io, json, time, queue, hashlib, threading, webbrowser, urllib.request, urllib.error
_T0 = time.perf_counter()
import tkinter as tk
from tkinter import simpledialog
from PIL import Image, ImageTk, ImageOps

def _log_t(msg):
    print(f"[{time.perf_counter() - _T0:6.3f}s] {msg}", flush=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CURRICULUM_FILE = os.path.join(BASE_DIR, "curriculum.json")
CLOUD_URL_FILE = os.path.join(BASE_DIR, "cloud_url.txt")
IMG_CACHE_DIR = os.path.expanduser("~/.cache/knowledge_hub_plates")
os.makedirs(IMG_CACHE_DIR, exist_ok=True)
_UA = "KnowledgeDesktopHub/4.4 (Ubuntu; educational)"

_MEM_PIL_CACHE = {}
_MEM_TK_CACHE = {}
_FAILED_URLS = set()
PAGE_SIZE = 5

_ASCII_MAP = str.maketrans({
    "—": "--", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"',
    "•": "|", "…": "...", "é": "e", "è": "e", "ê": "e", "ö": "o", "ü": "u"
})

def _fast_ascii(s):
    if not s:
        return ""
    return str(s).translate(_ASCII_MAP).encode("ascii", "ignore").decode("ascii")


def get_cloud_url():
    if os.path.exists(CLOUD_URL_FILE):
        u = open(CLOUD_URL_FILE).read().strip().rstrip("/")
        if u:
            return u
    return "https://consciousness-irreverser-lab.onrender.com"


def _normalize_pil_image(raw_im):
    raw_im = ImageOps.exif_transpose(raw_im)
    if raw_im.mode in ("RGBA", "LA") or (raw_im.mode == "P" and "transparency" in raw_im.info):
        rgba = raw_im.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (38, 46, 58, 255))
        bg.alpha_composite(rgba)
        return bg.convert("RGB")
    return raw_im.convert("RGB")


def fetch_cached_pil(url, max_size):
    if not url or url in _FAILED_URLS:
        return None
    cache_key = (url, max_size)
    if cache_key in _MEM_PIL_CACHE:
        return _MEM_PIL_CACHE[cache_key]
    h = hashlib.sha256(url.encode()).hexdigest()[:24]
    thumb_path = os.path.join(IMG_CACHE_DIR, f"{h}_{max_size[0]}x{max_size[1]}.jpg")
    full_path = os.path.join(IMG_CACHE_DIR, f"{h}_v31.jpg")
    try:
        if os.path.exists(thumb_path):
            im = Image.open(thumb_path).convert("RGB")
            _MEM_PIL_CACHE[cache_key] = im
            return im
        if not os.path.exists(full_path):
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            raw = urllib.request.urlopen(req, timeout=3.5).read()
            im = _normalize_pil_image(Image.open(io.BytesIO(raw)))
            im.thumbnail((900, 900), Image.Resampling.BILINEAR)
            im.save(full_path, "JPEG", quality=85)
        else:
            im = Image.open(full_path).convert("RGB")
        thumb = im.copy()
        thumb.thumbnail(max_size, Image.Resampling.BILINEAR)
        thumb.save(thumb_path, "JPEG", quality=85)
        _MEM_PIL_CACHE[cache_key] = thumb
        return thumb
    except Exception:
        _FAILED_URLS.add(url)
        return None


_BLANK_TK = None
_BLANK_GAL_TK = None


class KnowledgeDesktopHub(tk.Tk):
    def __init__(self):
        global _BLANK_TK, _BLANK_GAL_TK
        _log_t("Entering tk.Tk.__init__")
        super().__init__(className="knowledge-hub")
        self.title("EPOCH ZERO // Consciousness Irreverser Lab (Pure-Canvas Engine)")
        self.geometry("960x760")
        self.minsize(480, 440)
        self.configure(bg="#0d1117")
        self.protocol("WM_DELETE_WINDOW", self._instant_quit)

        _BLANK_TK = ImageTk.PhotoImage(Image.new("RGB", (240, 170), (28, 35, 45)))
        _BLANK_GAL_TK = ImageTk.PhotoImage(Image.new("RGB", (190, 126), (28, 35, 45)))

        self.cur_track = "art"
        self.page_idx = {"art": 0, "universe": 0, "favorites": 0}
        self.data = {"tracks": {"art": {"lessons": []}, "universe": {"lessons": []}}, "favorites": []}
        self.capacity = {}
        self.open_dd = set()
        self.open_gal = set()
        self.closed_qa = set()
        self._busy_btns = {}  # (track, seq, kind) -> status text
        self._img_queue = queue.LifoQueue()
        self._last_cw = 920
        self._resize_timer = None
        self._closing = False
        self.sched_status = "ONLINE | 08:30 MT Auto-Drop Armed (Art + Universe + Matrix)"
        self.search_query = ""

        # SINGLE Canvas for the entire application (Header + Tabs + Cards + Drawers = ZERO nested X11 sub-windows!)
        wrap = tk.Frame(self, bg="#0d1117")
        wrap.pack(fill="both", expand=True)
        self.cv = tk.Canvas(wrap, bg="#0d1117", highlightthickness=0, bd=0)
        self.sb = tk.Scrollbar(wrap, orient="vertical", command=self.cv.yview, bg="#161b22", troughcolor="#0d1117", activebackground="#30363d", highlightthickness=0, bd=0)
        self.cv.configure(yscrollcommand=self.sb.set)
        self.cv.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")

        self.bind_all("<Button-4>", lambda e: self.cv.yview_scroll(-1, "units"))
        self.bind_all("<Button-5>", lambda e: self.cv.yview_scroll(1, "units"))
        self.cv.bind("<Configure>", self._on_canvas_configure)

        self._load_local()
        self.render_scene()
        self.update()
        _log_t(f"PURE CANVAS LIVE ON MONITOR IN {time.perf_counter() - _T0:.3f}s!")

        for _ in range(3):
            threading.Thread(target=self._image_worker_loop, daemon=True).start()
        self.after(2500, lambda: threading.Thread(target=self._cloud_sync_loop, daemon=True).start())
        self._tick_epoch_clock()

    def _instant_quit(self):
        self._closing = True
        try:
            self.withdraw()
        except Exception:
            pass
        os._exit(0)

    def _on_canvas_configure(self, event):
        if event.width < 120 or abs(event.width - self._last_cw) < 6:
            return
        self._last_cw = event.width
        if self._resize_timer:
            self.after_cancel(self._resize_timer)
        self._resize_timer = self.after(25, self.render_scene)

    def _draw_pill_btn(self, x, y, text, bg, fg, tag, border=None, pad_x=10, pad_y=5, font_sz=8):
        t_id = self.cv.create_text(x + pad_x, y + pad_y, text=text, fill=fg, font=("DejaVu Sans Mono", font_sz, "bold"), anchor="nw", tags=(tag,))
        bb = self.cv.bbox(t_id) or (x, y, x + 60, y + 20)
        w = (bb[2] - bb[0]) + pad_x * 2
        h = (bb[3] - bb[1]) + pad_y * 2
        r_id = self.cv.create_rectangle(x, y, x + w, y + h, fill=bg, outline=border or bg, width=1, tags=(tag,))
        self.cv.tag_lower(r_id, t_id)
        return x + w, y + h

    def _get_cached_tk_img(self, url, size=(240, 170)):
        if not url:
            return _BLANK_TK if size == (240, 170) else _BLANK_GAL_TK
        ck = (url, size)
        if ck in _MEM_TK_CACHE:
            return _MEM_TK_CACHE[ck]
        if ck in _MEM_PIL_CACHE:
            ph = ImageTk.PhotoImage(_MEM_PIL_CACHE[ck])
            _MEM_TK_CACHE[ck] = ph
            return ph
        h = hashlib.sha256(url.encode()).hexdigest()[:24]
        thumb_path = os.path.join(IMG_CACHE_DIR, f"{h}_{size[0]}x{size[1]}.jpg")
        if os.path.exists(thumb_path):
            try:
                im = Image.open(thumb_path).convert("RGB")
                _MEM_PIL_CACHE[ck] = im
                ph = ImageTk.PhotoImage(im)
                _MEM_TK_CACHE[ck] = ph
                return ph
            except Exception:
                pass
        self._img_queue.put((url, size))
        return _BLANK_TK if size == (240, 170) else _BLANK_GAL_TK

    def _image_worker_loop(self):
        while not self._closing:
            try:
                url, size = self._img_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if self._closing:
                continue
            im = fetch_cached_pil(url, size)
            if im and not self._closing:
                self.after(0, self.render_scene)

    def _load_local(self):
        if os.path.exists(CURRICULUM_FILE):
            try:
                self.data = json.load(open(CURRICULUM_FILE))
                self.data.setdefault("favorites", [])
            except Exception:
                pass

    def _save_local(self):
        try:
            with open(CURRICULUM_FILE, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def _is_starred(self, url):
        return any(f.get("url") == url for f in (self.data.get("favorites") or []))

    def _norm_lesson(self, les):
        if not isinstance(les, dict):
            return {"seq": 0, "title": "Untitled", "core": "", "maker": "", "tags": []}
        raw_seq = les.get("seq", 0)
        try:
            les["seq"] = int(str(raw_seq).strip().lstrip("#") or 0)
        except Exception:
            les["seq"] = 0
        raw_tags = les.get("tags")
        if isinstance(raw_tags, str):
            les["tags"] = [t.strip().lstrip("#") for t in raw_tags.split(",") if t.strip()]
        elif isinstance(raw_tags, list):
            les["tags"] = [str(t).strip().lstrip("#") for t in raw_tags if t]
        else:
            les["tags"] = []
        les["title"] = str(les.get("title") or les.get("topic") or f"Lesson #{les['seq']:03d}")
        les["core"] = str(les.get("core") or les.get("summary") or les.get("body") or "")
        les["maker"] = str(les.get("maker") or les.get("lens") or les.get("synthesis") or les.get("application") or "Structural time-symmetry & physical endurance synthesis.")
        return les

    def _get_lesson_obj(self, track, seq):
        for item in self.data.get("tracks", {}).get(track, {}).get("lessons", []):
            if int(item.get("seq", 0)) == int(seq):
                return item
        return None

    def switch_track(self, t):
        self.cur_track = t
        self.cv.yview_moveto(0.0)
        self.render_scene()

    def _step_page(self, delta):
        self.page_idx[self.cur_track] = max(0, self.page_idx.get(self.cur_track, 0) + delta)
        self.cv.yview_moveto(0.0)
        self.render_scene()

    def _prompt_search(self):
        q = simpledialog.askstring("Filter Archive", "Enter keyword, artist, physicist, or #tag (leave blank to clear):", initialvalue=self.search_query, parent=self)
        if q is not None:
            self.search_query = q.strip()
            self.page_idx[self.cur_track] = 0
            self.cv.yview_moveto(0.0)
            self.render_scene()

    def _prompt_ask_gemini(self, track, seq, title):
        q = simpledialog.askstring("Ask Gemini", f"Ask Gemini a question about #{seq:03d} ({title[:35]}):", parent=self)
        if q and q.strip():
            self._call_cloud_action("/api/ask", {"track": track, "seq": seq, "question": q.strip()}, (track, seq, "ask"), "... Asking...")

    def _prompt_more_plates(self, track, seq):
        q = simpledialog.askstring("Curate 5 More Plates", "Optional custom search angle (or leave blank for automatic):", parent=self)
        if q is not None:
            self.open_gal.add((track, seq))
            self._call_cloud_action("/api/gallery", {"track": track, "seq": seq, "append": True, "query": q.strip()}, (track, seq, "more_gal"), "... Routing...")

    def render_scene(self):
        if self._closing:
            return
        cw = self.cv.winfo_width()
        if cw < 120:
            cw = self._last_cw
        self._last_cw = cw
        self.cv.delete("all")

        # 1. Top Header Banner
        self.cv.create_rectangle(0, 0, cw, 82, fill="#090d13", outline="#090d13")
        self.cv.create_text(cw // 2, 14, text="[EPOCH ZERO] CONSCIOUSNESS IRREVERSER // VISUAL MONOGRAPH ARCHIVE", fill="#fbbf24", font=("DejaVu Sans Mono", 11, "bold"), anchor="n")
        self.cv.create_text(cw // 2, 36, text=_fast_ascii(self.sched_status), fill="#8b949e", font=("DejaVu Sans Mono", 8), anchor="n")

        c = self.capacity
        ep_hrs = max(0.0, (time.time() - 1794623880) / 3600.0)
        ep_str = f"{int(ep_hrs):06,d}.{int((ep_hrs - int(ep_hrs))*10000):04d} HRS"
        if c:
            r_hrs = c.get("runway_hours") or int(round(float(c.get("runway_years", 18.8)) * 8766))
            cap_txt = f"EPOCH ZERO: {ep_str}  |  Vault: {c.get('json_kb', 0)} KB ({c.get('gh_pct', 0)}%)  |  Auto-Drop Runway: {r_hrs:,} HRS"
        else:
            cap_txt = f"EPOCH ZERO: {ep_str}  |  Vault: Synced Locally  |  Auto-Drop Runway: 165,000 HRS"
        self.cv.create_rectangle(16, 54, cw - 16, 76, fill="#111822", outline="#238636", width=1)
        self.cv.create_text(cw // 2, 65, text=cap_txt, fill="#3fb950", font=("DejaVu Sans Mono", 8, "bold"), anchor="center", tags=("top_cap_bar",))

        # 2. Navigation Bar
        y = 92
        a_n = len(self.data.get("tracks", {}).get("art", {}).get("lessons", []))
        u_n = len(self.data.get("tracks", {}).get("universe", {}).get("lessons", []))
        f_n = len(self.data.get("favorites") or [])

        x_cur = 16
        s_n = len(self.data.get("stamps") or [])
        x_cur, _ = self._draw_pill_btn(x_cur, y, f"FOUNDATIONS ({s_n})", "#d2a8ff" if self.cur_track == "foundations" else "#21262d", "#090d13" if self.cur_track == "foundations" else "#d2a8ff", "nav_fnd")
        self.cv.tag_bind("nav_fnd", "<Button-1>", lambda e: self.switch_track("foundations"))
        x_cur += 8
        x_cur, _ = self._draw_pill_btn(x_cur, y, f"ART ENDURANCE ({a_n})", "#fbbf24" if self.cur_track == "art" else "#21262d", "#090d13" if self.cur_track == "art" else "#c9d1d9", "nav_art")
        self.cv.tag_bind("nav_art", "<Button-1>", lambda e: self.switch_track("art"))

        x_cur, _ = self._draw_pill_btn(x_cur + 8, y, f"PHYSICS OF TIME ({u_n})", "#58a6ff" if self.cur_track == "universe" else "#21262d", "#090d13" if self.cur_track == "universe" else "#c9d1d9", "nav_uni")
        self.cv.tag_bind("nav_uni", "<Button-1>", lambda e: self.switch_track("universe"))

        x_cur, _ = self._draw_pill_btn(x_cur + 8, y, f"* FAVORITES ({f_n})", "#fbbf24" if self.cur_track == "favorites" else "#21262d", "#090d13" if self.cur_track == "favorites" else "#fbbf24", "nav_fav")
        self.cv.tag_bind("nav_fav", "<Button-1>", lambda e: self.switch_track("favorites"))

        filt_txt = f"Filter: '{self.search_query}' [x]" if self.search_query else "Filter / Search..."
        x_cur, _ = self._draw_pill_btn(x_cur + 10, y, filt_txt, "#161b22", "#fbbf24" if self.search_query else "#8b949e", "nav_search", border="#30363d")
        self.cv.tag_bind("nav_search", "<Button-1>", lambda e: (setattr(self, "search_query", ""), self.render_scene()) if self.search_query else self._prompt_search())

        # Right-hand Matrix & Sync Drop buttons
        sync_lbl = self._busy_btns.get(("global", 0, "sync"), "Sync Drop")
        _, _ = self._draw_pill_btn(cw - 102, y, sync_lbl, "#192b20", "#3fb950", "nav_sync", border="#238636")
        self.cv.tag_bind("nav_sync", "<Button-1>", lambda e: self._manual_sync_drop())

        _, _ = self._draw_pill_btn(cw - 196, y, "Matrix ->", "#21262d", "#58a6ff", "nav_matrix")
        self.cv.tag_bind("nav_matrix", "<Button-1>", lambda e: webbrowser.open(get_cloud_url() + "/matrix"))

        y += 34

        # 2.5 Foundations (Epoch Zero) View
        if self.cur_track == "foundations":
            y = self._draw_foundations_on_canvas(y, cw)
            self.cv.configure(scrollregion=(0, 0, cw, max(760, y + 20)))
            return

        # 3. Favorites View
        if self.cur_track == "favorites":
            self.cv.create_rectangle(16, y, cw - 16, y + 28, fill="#111822", outline="#30363d")
            self.cv.create_text(cw // 2, y + 14, text=f"* KEY'S FAVORITES VAULT ({f_n} Pinned Plates)", fill="#fbbf24", font=("DejaVu Sans Mono", 8, "bold"), anchor="center")
            y += 38
            favs = self.data.get("favorites") or []
            if not favs:
                self.cv.create_rectangle(16, y, cw - 16, y + 80, fill="#161b22", outline="#30363d")
                self.cv.create_text(cw // 2, y + 28, text="* Key's Favorites Vault is empty right now.", fill="#f0f6fc", font=("DejaVu Sans Mono", 10, "bold"))
                self.cv.create_text(cw // 2, y + 54, text="Click [+Fav Plate] on any card or gallery plate to pin it permanently to GitHub.", fill="#8b949e", font=("DejaVu Sans Mono", 8))
                y += 100
            else:
                for idx_f, f in enumerate(favs):
                    f_url = f.get("url", "")
                    f_cap = _fast_ascii(f.get("caption", "Visual Plate"))
                    f_tr = str(f.get("track", "art"))
                    f_sq = int(f.get("seq", 1))
                    self.cv.create_rectangle(16, y, cw - 16, y + 160, fill="#161b22", outline="#fbbf24")
                    ph = self._get_cached_tk_img(f_url, (240, 170))
                    im_tag = f"fav_im_{idx_f}"
                    self.cv.create_image(28, y + 10, image=ph, anchor="nw", tags=(im_tag,))
                    self.cv.tag_bind(im_tag, "<Button-1>", lambda e, u=f_url, c=f_cap: self._open_lightbox(u, c))
                    tx = 284
                    self.cv.create_text(tx, y + 16, text=_fast_ascii(f"{f_tr.upper()} #{f_sq:03d}  |  {f.get('source','Archive')}  |  Saved {f.get('saved_at','')}"), fill="#8b949e", font=("DejaVu Sans Mono", 8, "bold"), anchor="nw")
                    self.cv.create_text(tx, y + 40, text=f_cap, fill="#f0f6fc", font=("DejaVu Sans Mono", 10, "bold"), anchor="nw", width=max(180, cw - tx - 30))
                    if f.get("study_note"):
                        self.cv.create_text(tx, y + 68, text=_fast_ascii(f.get("study_note", "")), fill="#fbbf24", font=("DejaVu Sans Mono", 8), anchor="nw", width=max(180, cw - tx - 30))
                    bx, _ = self._draw_pill_btn(tx, y + 118, f"Open {f_tr.upper()} (#{f_sq:03d}) ->", "#21262d", "#fbbf24", f"fav_jmp_{idx_f}")
                    self.cv.tag_bind(f"fav_jmp_{idx_f}", "<Button-1>", lambda e, tr=f_tr, sq=f_sq: self._jump_to_lesson(tr, sq))
                    self._draw_pill_btn(bx + 10, y + 118, "[*] Unstar", "#2d2208", "#fbbf24", f"fav_uns_{idx_f}")
                    self.cv.tag_bind(f"fav_uns_{idx_f}", "<Button-1>", lambda e, tr=f_tr, sq=f_sq, u=f_url: self._toggle_star(tr, sq, u))
                    y += 172
            self.cv.configure(scrollregion=(0, 0, cw, max(760, y + 20)))
            return

        # 4. Filter & Paginate Active Track
        q = self.search_query.lower()
        raw_list = self.data.get("tracks", {}).get(self.cur_track, {}).get("lessons", [])
        all_lessons = [self._norm_lesson(x) for x in reversed(raw_list) if isinstance(x, dict)]
        filtered = [
            les for les in all_lessons
            if not q or q in f"#{les.get('seq',0):03d} {les.get('title','')} {les.get('core','')} {' '.join(les.get('tags',[]))}".lower()
        ]
        total = len(filtered)
        max_page = max(0, (total - 1) // PAGE_SIZE)
        cur_p = min(self.page_idx.get(self.cur_track, 0), max_page)
        self.page_idx[self.cur_track] = cur_p

        start_i = cur_p * PAGE_SIZE
        end_i = min(total, start_i + PAGE_SIZE)
        page_slice = filtered[start_i:end_i]
        has_prev = (cur_p > 0)
        has_next = (end_i < total)

        # Top Pagination Bar
        self.cv.create_rectangle(16, y, cw - 16, y + 28, fill="#111822", outline="#30363d")
        t_label = "ART ENDURANCE" if self.cur_track == "art" else "PHYSICS OF TIME"
        if total > 0:
            meta_p = f"{t_label}  |  Showing #{page_slice[0]['seq']:03d}-#{page_slice[-1]['seq']:03d} of {total}  (Page {cur_p + 1}/{max_page + 1})"
        else:
            meta_p = f"{t_label}  |  0 matching lessons"
        self.cv.create_text(cw // 2, y + 14, text=meta_p, fill="#e6edf3", font=("DejaVu Sans Mono", 8, "bold"), anchor="center")

        if has_prev:
            self._draw_pill_btn(22, y + 3, "<< Newer 5", "#21262d", "#58a6ff", "pg_prev_top", pad_x=8, pad_y=3)
            self.cv.tag_bind("pg_prev_top", "<Button-1>", lambda e: self._step_page(-1))
        if has_next:
            self._draw_pill_btn(cw - 108, y + 3, "Older 5 >>", "#21262d", "#58a6ff", "pg_next_top", pad_x=8, pad_y=3)
            self.cv.tag_bind("pg_next_top", "<Button-1>", lambda e: self._step_page(1))
        y += 38

        # 5. Draw Each of the 5 Cards Directly on self.cv!
        is_wide = (cw >= 820)
        for les in page_slice:
            y = self._draw_card_on_canvas(les, self.cur_track, y, cw, is_wide) + 12

        # Bottom Pagination Bar
        if total > PAGE_SIZE:
            self.cv.create_rectangle(16, y, cw - 16, y + 34, fill="#111822", outline="#30363d")
            self.cv.create_text(cw // 2, y + 17, text=f"Page {cur_p + 1} of {max_page + 1}", fill="#8b949e", font=("DejaVu Sans Mono", 8, "bold"), anchor="center")
            if has_prev:
                self._draw_pill_btn(24, y + 5, "<< Newer 5 Lessons", "#21262d", "#fbbf24", "pg_prev_bot", pad_x=10, pad_y=4)
                self.cv.tag_bind("pg_prev_bot", "<Button-1>", lambda e: self._step_page(-1))
            if has_next:
                self._draw_pill_btn(cw - 165, y + 5, "Older 5 Lessons >>", "#21262d", "#fbbf24", "pg_next_bot", pad_x=10, pad_y=4)
                self.cv.tag_bind("pg_next_bot", "<Button-1>", lambda e: self._step_page(1))
            y += 48

        self.cv.configure(scrollregion=(0, 0, cw, max(760, y + 20)))

    def _draw_card_on_canvas(self, les, track_key, y_top, cw, is_wide):
        seq = les["seq"]
        key = (track_key, seq)
        card_bg_id = self.cv.create_rectangle(16, y_top, cw - 16, y_top + 200, fill="#161b22", outline="#30363d", width=1)

        img_w, img_h = 240, 170
        left_x = 28
        text_w = max(180, (cw - img_w - 68) if is_wide else (cw - 56))
        y = y_top + 12

        tags_str = "  ".join(f"#{t}" for t in (les.get("tags") or []))
        meta_txt = _fast_ascii(f"#{seq:03d} | {les.get('date','')}  [{str(les.get('model','ARCHIVE')).upper()}]  {tags_str}".strip())
        m_id = self.cv.create_text(left_x, y, text=meta_txt, fill="#58a6ff", font=("DejaVu Sans Mono", 8, "bold"), anchor="nw", width=text_w)
        y = (self.cv.bbox(m_id) or (0, 0, 0, y + 16))[3] + 6

        t_id = self.cv.create_text(left_x, y, text=_fast_ascii(les.get("title", "")), fill="#f0f6fc", font=("DejaVu Sans Mono", 11, "bold"), anchor="nw", width=text_w)
        y = (self.cv.bbox(t_id) or (0, 0, 0, y + 22))[3] + 6

        c_id = self.cv.create_text(left_x, y, text=_fast_ascii(les.get("core", "")), fill="#c9d1d9", font=("DejaVu Sans Mono", 9), anchor="nw", width=text_w)
        y = (self.cv.bbox(c_id) or (0, 0, 0, y + 40))[3] + 10

        lens_prefix = ">> Temporal & Studio Lens: " if track_key == "universe" else ">> Studio Craft Lens: "
        mk_id = self.cv.create_text(left_x + 10, y + 8, text=_fast_ascii(lens_prefix + les.get("maker", "")), fill="#fbbf24", font=("DejaVu Sans Mono", 8), anchor="nw", width=max(150, text_w - 20))
        mk_bb = self.cv.bbox(mk_id) or (left_x, y, left_x + text_w, y + 36)
        box_id = self.cv.create_rectangle(left_x, y, left_x + text_w, mk_bb[3] + 8, fill="#0f141b", outline="#fbbf24", width=1)
        self.cv.tag_lower(box_id, mk_id)
        y = mk_bb[3] + 14

        # Lead Plate Image
        img_url = les.get("image_url", "")
        img_x = (cw - img_w - 28) if is_wide else left_x
        img_y = (y_top + 12) if is_wide else y
        self.cv.create_rectangle(img_x - 1, img_y - 1, img_x + img_w + 1, img_y + img_h + 22, fill="#090d13", outline="#30363d", width=1)
        ph = self._get_cached_tk_img(img_url, (240, 170))
        p_tag = f"lead_img_{track_key}_{seq}"
        self.cv.create_image(img_x, img_y, image=ph, anchor="nw", tags=(p_tag,))
        cap_txt = _fast_ascii((les.get("image_caption") or les.get("title", ""))[:27]) + " [Zoom]"
        self.cv.create_text(img_x + 6, img_y + img_h + 4, text=cap_txt, fill="#8b949e", font=("DejaVu Sans Mono", 7, "bold"), anchor="nw", tags=(p_tag,))
        if img_url:
            self.cv.tag_bind(p_tag, "<Button-1>", lambda e, u=img_url, c=_fast_ascii(les.get("image_caption") or les.get("title", "")): self._open_lightbox(u, c))

        y = max(y, (img_y + img_h + 30))

        # Action Buttons Row (Pure Canvas Pills!)
        has_dd = bool(les.get("deep_dive") and len(les["deep_dive"]) > 40)
        ch_count = (les.get("deep_dive") or "").count("=== DEEPER DIVE CHAPTER") + (1 if has_dd else 0)
        dd_wait = self._busy_btns.get((track_key, seq, "dd"))
        if dd_wait:
            dd_txt, dd_bg, dd_fg = dd_wait, "#1f2937", "#fbbf24"
        elif key in self.open_dd and has_dd:
            dd_txt, dd_bg, dd_fg = (f"Minimize Deep Dive ({ch_count} Ch)" if ch_count > 1 else "Minimize Deep Dive"), "#1f2937", "#fbbf24"
        else:
            dd_txt = (f"Read Deep Dive ({ch_count} Ch)" if ch_count > 1 else "Read Deep Dive") if has_dd else "Generate Deep Dive"
            dd_bg, dd_fg = "#21262d", "#58a6ff"

        bx = left_x
        dd_tag = f"btn_dd_{track_key}_{seq}"
        bx, _ = self._draw_pill_btn(bx, y, dd_txt, dd_bg, dd_fg, dd_tag)
        self.cv.tag_bind(dd_tag, "<Button-1>", lambda e, t=track_key, s=seq, r=has_dd: self._on_dd_click(t, s, r))

        gal_list = les.get("gallery") or []
        has_gal = len(gal_list) >= 1
        gal_wait = self._busy_btns.get((track_key, seq, "gal"))
        if gal_wait:
            gal_txt = gal_wait
        elif key in self.open_gal and has_gal:
            gal_txt = f"Hide Plates ({len(gal_list)})"
        else:
            gal_txt = f"Plates ({len(gal_list)})" if has_gal else "Curate Plates"
        gal_tag = f"btn_gal_{track_key}_{seq}"
        bx, _ = self._draw_pill_btn(bx + 8, y, gal_txt, "#21262d", "#3fb950", gal_tag)
        self.cv.tag_bind(gal_tag, "<Button-1>", lambda e, t=track_key, s=seq, r=has_gal: self._on_gal_click(t, s, r))

        if img_url:
            starred = self._is_starred(img_url)
            fav_tag = f"btn_fav_{track_key}_{seq}"
            bx, _ = self._draw_pill_btn(bx + 8, y, "[*Fav Plate]" if starred else "[+Fav Plate]", "#21262d", "#fbbf24" if starred else "#8b949e", fav_tag)
            self.cv.tag_bind(fav_tag, "<Button-1>", lambda e, t=track_key, s=seq, u=img_url, cp=les.get("image_caption") or les.get("title", ""): self._toggle_star(t, s, u, cp, "", "Lead Plate"))

        ask_wait = self._busy_btns.get((track_key, seq, "ask"), "Ask Gemini...")
        ask_tag = f"btn_ask_{track_key}_{seq}"
        _, btn_bot = self._draw_pill_btn(bx + 8, y, ask_wait, "#251736", "#d2a8ff", ask_tag)
        self.cv.tag_bind(ask_tag, "<Button-1>", lambda e, t=track_key, s=seq, ti=les.get("title", ""): self._prompt_ask_gemini(t, s, ti))

        y = btn_bot + 10

        # Expandable Deep Dive Drawer (drawn directly on Canvas!)
        if key in self.open_dd and has_dd:
            dd_top = y
            self.cv.create_rectangle(left_x, y, cw - 28, y + 30, fill="#111822", outline="#30363d")
            self.cv.create_text(left_x + 10, y + 15, text=f"DEEP DIVE MONOGRAPH  |  {ch_count} CHAPTER(S) ARCHIVED", fill="#58a6ff", font=("DejaVu Sans Mono", 8, "bold"), anchor="w")

            min_tag = f"dd_min_{track_key}_{seq}"
            self._draw_pill_btn(cw - 178, y + 4, "Minimize Deep Dive", "#21262d", "#fbbf24", min_tag, pad_x=8, pad_y=3)
            self.cv.tag_bind(min_tag, "<Button-1>", lambda e, k=key: (self.open_dd.discard(k), self.render_scene()))

            dp_wait = self._busy_btns.get((track_key, seq, "deeper"), f"+ Deeper Dive (Ch.{ch_count + 1})")
            dp_tag = f"dd_more_{track_key}_{seq}"
            self._draw_pill_btn(cw - 355, y + 4, dp_wait, "#251736", "#d2a8ff", dp_tag, pad_x=8, pad_y=3)
            self.cv.tag_bind(dp_tag, "<Button-1>", lambda e, t=track_key, s=seq: self._call_cloud_action("/api/deep_dive", {"track": t, "seq": s, "append": True}, (t, s, "deeper"), "... Diving Deeper..."))

            y += 38
            dd_txt_id = self.cv.create_text(left_x + 12, y, text=_fast_ascii(les["deep_dive"]), fill="#d0d7de", font=("DejaVu Sans Mono", 9), anchor="nw", width=max(200, cw - 80))
            dd_bb = self.cv.bbox(dd_txt_id) or (left_x, y, cw - 28, y + 100)
            y = dd_bb[3] + 12
            min_bot_tag = f"dd_min_b_{track_key}_{seq}"
            _, y_end_btn = self._draw_pill_btn(cw - 182, y, "Minimize Deep Dive", "#21262d", "#fbbf24", min_bot_tag, pad_x=8, pad_y=3)
            self.cv.tag_bind(min_bot_tag, "<Button-1>", lambda e, k=key: (self.open_dd.discard(k), self.render_scene()))
            y = y_end_btn + 8
            dd_box = self.cv.create_rectangle(left_x, dd_top, cw - 28, y, fill="#090d13", outline="#30363d")
            self.cv.tag_lower(dd_box, dd_txt_id)
            y += 10

        # Expandable Gallery Plates Drawer (drawn directly on Canvas!)
        if key in self.open_gal and has_gal:
            gal_cols = max(1, min(4, (cw - 64) // 204))
            gx0 = left_x + 8
            gy = y + 8
            for idx_g, g_item in enumerate(gal_list):
                r_i, c_i = divmod(idx_g, gal_cols)
                cx = gx0 + c_i * 204
                cy = gy + r_i * 168
                gu = g_item.get("url", "")
                gc = _fast_ascii(f"{g_item.get('caption', '')} -- {g_item.get('study_note', '')}".strip(" -"))
                gs = _fast_ascii(g_item.get("source", "Archive"))[:16]
                g_star = self._is_starred(gu)

                self.cv.create_rectangle(cx, cy, cx + 194, cy + 160, fill="#161b22", outline="#30363d")
                del_tag = f"gdel_{track_key}_{seq}_{idx_g}"
                self.cv.create_text(cx + 8, cy + 3, text="x", fill="#f85149", font=("DejaVu Sans Mono", 8, "bold"), anchor="nw", tags=(del_tag,))
                self.cv.tag_bind(del_tag, "<Button-1>", lambda e, t=track_key, s=seq, u=gu: self._delete_plate(t, s, u))

                self.cv.create_text(cx + 24, cy + 4, text=gs, fill="#58a6ff", font=("DejaVu Sans Mono", 6), anchor="nw")
                st_tag = f"gstar_{track_key}_{seq}_{idx_g}"
                self.cv.create_text(cx + 166, cy + 3, text="[*]" if g_star else "[+]", fill="#fbbf24" if g_star else "#8b949e", font=("DejaVu Sans Mono", 8, "bold"), anchor="nw", tags=(st_tag,))
                self.cv.tag_bind(st_tag, "<Button-1>", lambda e, t=track_key, s=seq, u=gu, cp=g_item.get("caption", ""), sn=g_item.get("study_note", ""), sr=gs: self._toggle_star(t, s, u, cp, sn, sr))

                g_ph = self._get_cached_tk_img(gu, (190, 126))
                gim_tag = f"gim_{track_key}_{seq}_{idx_g}"
                self.cv.create_image(cx + 2, cy + 18, image=g_ph, anchor="nw", tags=(gim_tag,))
                self.cv.create_text(cx + 6, cy + 145, text=_fast_ascii((g_item.get("caption") or "Plate")[:24]), fill="#c9d1d9", font=("DejaVu Sans Mono", 7), anchor="nw", tags=(gim_tag,))
                self.cv.tag_bind(gim_tag, "<Button-1>", lambda e, u=gu, c=gc: self._open_lightbox(u, c))

            rows_n = (len(gal_list) + gal_cols - 1) // gal_cols
            y = gy + rows_n * 168 + 4
            more_wait = self._busy_btns.get((track_key, seq, "more_gal"), "+ Curate 5 More Plates")
            more_tag = f"gmore_{track_key}_{seq}"
            _, y_mb = self._draw_pill_btn(left_x + 8, y, more_wait, "#1f2937", "#fbbf24", more_tag)
            self.cv.tag_bind(more_tag, "<Button-1>", lambda e, t=track_key, s=seq: self._prompt_more_plates(t, s))
            y = y_mb + 10

        # Saved Q&A Drawer
        qa_list = les.get("qa_log") or []
        if qa_list:
            is_min = (key in self.closed_qa)
            q_tag = f"qatog_{track_key}_{seq}"
            _, y_qb = self._draw_pill_btn(left_x, y, f"Show Saved Q&A ({len(qa_list)}) [v]" if is_min else f"Minimize Q&A ({len(qa_list)}) [^]", "#251736", "#d2a8ff", q_tag, pad_x=8, pad_y=3)
            self.cv.tag_bind(q_tag, "<Button-1>", lambda e, k=key: (self.closed_qa.remove(k) if k in self.closed_qa else self.closed_qa.add(k), self.render_scene()))
            y = y_qb + 6
            if not is_min:
                for qa in qa_list:
                    q_top = y
                    q_h = self.cv.create_text(left_x + 10, y + 6, text=_fast_ascii(f"Q: {qa.get('q','')}  [{qa.get('model','GEMINI')} | {qa.get('ts','')}]"), fill="#d2a8ff", font=("DejaVu Sans Mono", 8, "bold"), anchor="nw", width=max(180, cw - 80))
                    y = (self.cv.bbox(q_h) or (0, 0, 0, y + 18))[3] + 4
                    q_a = self.cv.create_text(left_x + 10, y, text=_fast_ascii(qa.get("a", "")), fill="#e6edf3", font=("DejaVu Sans Mono", 9), anchor="nw", width=max(180, cw - 80))
                    y = (self.cv.bbox(q_a) or (0, 0, 0, y + 24))[3] + 8
                    q_rect = self.cv.create_rectangle(left_x, q_top, cw - 28, y, fill="#0c131d", outline="#6e40c9")
                    self.cv.tag_lower(q_rect, q_h)
                    y += 6

        self.cv.coords(card_bg_id, 16, y_top, cw - 16, y + 6)
        return y + 6

    def _on_dd_click(self, track, seq, ready):
        key = (track, seq)
        if ready:
            if key in self.open_dd:
                self.open_dd.remove(key)
            else:
                self.open_dd.add(key)
            self.render_scene()
        else:
            self.open_dd.add(key)
            self._call_cloud_action("/api/deep_dive", {"track": track, "seq": seq}, (track, seq, "dd"), "... Writing...")

    def _on_gal_click(self, track, seq, ready):
        key = (track, seq)
        if ready:
            if key in self.open_gal:
                self.open_gal.remove(key)
            else:
                self.open_gal.add(key)
            self.render_scene()
        else:
            self.open_gal.add(key)
            self._call_cloud_action("/api/gallery", {"track": track, "seq": seq}, (track, seq, "gal"), "... Curating...")

    def _call_cloud_action(self, endpoint, payload, busy_key, wait_txt):
        if busy_key in self._busy_btns:
            return
        self._busy_btns[busy_key] = wait_txt
        self.render_scene()

        def _worker():
            for attempt in range(2):
                try:
                    u = get_cloud_url() + endpoint
                    req = urllib.request.Request(u, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST")
                    j = json.loads(urllib.request.urlopen(req, timeout=95).read().decode())
                    if j.get("ok") and j.get("lesson"):
                        arr = self.data["tracks"][payload["track"]]["lessons"]
                        for idx, item in enumerate(arr):
                            if int(item["seq"]) == int(payload["seq"]):
                                arr[idx] = j["lesson"]
                                break
                        if j.get("capacity"):
                            self.capacity = j["capacity"]
                        self._save_local()
                        self._busy_btns.pop(busy_key, None)
                        self.after(0, self.render_scene)
                        return
                except Exception:
                    pass
                if attempt == 0:
                    self._busy_btns[busy_key] = "... Retrying..."
                    self.after(0, self.render_scene)
                    time.sleep(2)
            self._busy_btns[busy_key] = "[!] Tap to Retry"
            self.after(0, self.render_scene)
            time.sleep(2.5)
            self._busy_btns.pop(busy_key, None)
            self.after(0, self.render_scene)
        threading.Thread(target=_worker, daemon=True).start()

    def _cloud_sync_loop(self):
        while not self._closing:
            try:
                u = get_cloud_url() + "/state"
                req = urllib.request.Request(u, headers={"User-Agent": _UA})
                j = json.loads(urllib.request.urlopen(req, timeout=22).read().decode())
                if j.get("curriculum") and not self._closing:
                    self.data = j["curriculum"]
                    self.data.setdefault("favorites", [])
                    if j.get("capacity"):
                        self.capacity = j["capacity"]
                    self._save_local()
                    st = j.get("scheduler", {}).get("status", "ONLINE")
                    lc = j.get("scheduler", {}).get("last_check", "--")
                    self.sched_status = f"{st}  |  Last Check: {lc}"
                    self.after(0, self.render_scene)
            except Exception:
                pass
            time.sleep(35)

    def _manual_sync_drop(self):
        bkey = ("global", 0, "sync")
        if bkey in self._busy_btns:
            return
        self._busy_btns[bkey] = "... Dropping..."
        self.render_scene()

        def _worker():
            try:
                u = get_cloud_url() + "/api/sync_drop"
                req = urllib.request.Request(u, data=json.dumps({"force": True}).encode(), headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST")
                j = json.loads(urllib.request.urlopen(req, timeout=140).read().decode())
                if j.get("ok"):
                    if j.get("curriculum"):
                        self.data = j["curriculum"]
                        self.data.setdefault("favorites", [])
                        self._save_local()
                    if j.get("capacity"):
                        self.capacity = j["capacity"]
                    added = (j.get("result") or {}).get("changed") or []
                    self._busy_btns[bkey] = f"[OK] +{len(added)}!" if added else "[OK] Synced"
                else:
                    self._busy_btns[bkey] = "[!] Retry"
            except Exception:
                self._busy_btns[bkey] = "[!] Wake & Retry"
            self.after(0, self.render_scene)
            time.sleep(3)
            self._busy_btns.pop(bkey, None)
            self.after(0, self.render_scene)
        threading.Thread(target=_worker, daemon=True).start()

    def _toggle_star(self, track, seq, url, caption="", study_note="", source=""):
        favs = self.data.setdefault("favorites", [])
        if any(f.get("url") == url for f in favs):
            self.data["favorites"] = [f for f in favs if f.get("url") != url]
        else:
            favs.insert(0, {"track": track, "seq": seq, "url": url, "caption": caption, "study_note": study_note, "source": source, "saved_at": time.strftime("%Y-%m-%d")})
        self.render_scene()

        def _worker():
            try:
                u = get_cloud_url() + "/api/favorite"
                payload = {"track": track, "seq": seq, "url": url, "caption": caption, "study_note": study_note, "source": source}
                req = urllib.request.Request(u, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST")
                j = json.loads(urllib.request.urlopen(req, timeout=25).read().decode())
                if j.get("ok"):
                    self.data["favorites"] = j.get("favorites", [])
                    if j.get("capacity"):
                        self.capacity = j["capacity"]
                    self._save_local()
                    self.after(0, self.render_scene)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _delete_plate(self, track, seq, url):
        les = self._get_lesson_obj(track, seq)
        if les and les.get("gallery"):
            les["gallery"] = [g for g in les["gallery"] if g.get("url") != url]
        self.render_scene()

        def _worker():
            try:
                u = get_cloud_url() + "/api/delete_plate"
                req = urllib.request.Request(u, data=json.dumps({"track": track, "seq": seq, "url": url}).encode(), headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST")
                j = json.loads(urllib.request.urlopen(req, timeout=25).read().decode())
                if j.get("ok"):
                    arr = self.data["tracks"][track]["lessons"]
                    for idx, item in enumerate(arr):
                        if int(item["seq"]) == int(seq) and j.get("lesson"):
                            arr[idx] = j["lesson"]
                            break
                    self.data["favorites"] = j.get("favorites", [])
                    if j.get("capacity"):
                        self.capacity = j["capacity"]
                    self._save_local()
                    self.after(0, self.render_scene)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _jump_to_lesson(self, track, seq):
        self.search_query = ""
        raw_list = self.data.get("tracks", {}).get(track, {}).get("lessons", [])
        all_seq = [int(x.get("seq", 0)) for x in reversed(raw_list) if isinstance(x, dict)]
        if int(seq) in all_seq:
            self.page_idx[track] = all_seq.index(int(seq)) // PAGE_SIZE
        else:
            self.page_idx[track] = 0
        self.switch_track(track)


    def _fmt_epoch_hrs(self, hrs):
        hrs = max(0.0, float(hrs))
        whole = int(hrs)
        dec = int((hrs - whole) * 10000)
        return f"{whole:06,d}.{dec:04d}"

    def _tick_epoch_clock(self):
        if self._closing:
            return
        try:
            ep_hrs = max(0.0, (time.time() - 1794623880) / 3600.0)
            ep_str = self._fmt_epoch_hrs(ep_hrs) + " HRS"
            if self.cur_track == "foundations":
                self.cv.itemconfigure("live_monolith_txt", text=ep_str)
                stamps = self.data.get("stamps") or []
                if stamps:
                    last = stamps[-1]
                    since = max(0.0, ep_hrs - float(last.get("epoch_hrs", 0.0)))
                    sub = _fast_ascii(f"LAST MARK: #{int(last.get('seq',1)):03d} @ {self._fmt_epoch_hrs(last.get('epoch_hrs',0))} HRS ('{last.get('note','')}')  |  +{self._fmt_epoch_hrs(since)} HRS ADJACENT")
                    self.cv.itemconfigure("live_lap_txt", text=sub)
            c = self.capacity
            if c:
                r_hrs = c.get("runway_hours") or int(round(float(c.get("runway_years", 18.8)) * 8766))
                cap_txt = f"EPOCH ZERO: {ep_str}  |  Vault: {c.get('json_kb', 0)} KB ({c.get('gh_pct', 0)}%)  |  Auto-Drop Runway: {r_hrs:,} HRS"
            else:
                cap_txt = f"EPOCH ZERO: {ep_str}  |  Vault: Synced Locally  |  Auto-Drop Runway: 165,000 HRS"
            self.cv.itemconfigure("top_cap_bar", text=cap_txt)
        except Exception:
            pass
        self.after(200, self._tick_epoch_clock)

    def _prompt_epoch_stamp(self):
        note = simpledialog.askstring("Epoch Zero Lap Stamp", "Enter anchor note for this exact hour (e.g., 'Legion p.48', 'The Upside cross windows'):", parent=self)
        if note is None:
            return
        note_clean = note.strip() or "Session Lock-In"
        stamps = self.data.setdefault("stamps", [])
        now_ts = time.time()
        ep_hrs = round(max(0.0, (now_ts - 1794623880) / 3600.0), 4)
        prev_hrs = float(stamps[-1].get("epoch_hrs", 0.0)) if stamps else 0.0
        delta_hrs = round(max(0.0, ep_hrs - prev_hrs), 4)
        next_seq = max((int(s.get("seq", 0)) for s in stamps), default=0) + 1
        entry = {"seq": next_seq, "ts": int(now_ts), "epoch_hrs": ep_hrs, "delta_hrs": delta_hrs, "note": note_clean}
        stamps.append(entry)
        self._save_local()
        self.render_scene()

        def _sync_stamp():
            try:
                u = get_cloud_url() + "/api/stamp"
                req = urllib.request.Request(u, data=json.dumps({"note": note_clean}).encode(), headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST")
                j = json.loads(urllib.request.urlopen(req, timeout=25).read().decode())
                if j.get("ok") and j.get("stamps"):
                    self.data["stamps"] = j["stamps"]
                    if j.get("capacity"):
                        self.capacity = j["capacity"]
                    self._save_local()
                    self.after(0, self.render_scene)
            except Exception:
                pass
        threading.Thread(target=_sync_stamp, daemon=True).start()

    def _draw_foundations_on_canvas(self, y, cw):
        ep_hrs = max(0.0, (time.time() - 1794623880) / 3600.0)
        stamps = list(reversed(self.data.get("stamps") or []))
        last = stamps[0] if stamps else {"seq": 1, "epoch_hrs": 0.3333, "note": "Consciousness Irreverser"}
        since = max(0.0, ep_hrs - float(last.get("epoch_hrs", 0.0)))

        # Monolith Box
        self.cv.create_rectangle(16, y, cw - 16, y + 168, fill="#090d13", outline="#fbbf24", width=2)
        self.cv.create_text(cw // 2, y + 14, text="EPOCH ZERO MONOLITH // GENESIS: 2026-11-13T19:38:00-07:00 (PROPER TIME)", fill="#8b949e", font=("DejaVu Sans Mono", 8, "bold"), anchor="n")
        self.cv.create_text(cw // 2, y + 38, text=self._fmt_epoch_hrs(ep_hrs) + " HRS", fill="#fbbf24", font=("DejaVu Sans Mono", 22, "bold"), anchor="n", tags=("live_monolith_txt",))
        sub_txt = _fast_ascii(f"LAST MARK: #{int(last.get('seq',1)):03d} @ {self._fmt_epoch_hrs(last.get('epoch_hrs',0))} HRS ('{last.get('note','')}')  |  +{self._fmt_epoch_hrs(since)} HRS ADJACENT")
        self.cv.create_text(cw // 2, y + 82, text=sub_txt, fill="#3fb950", font=("DejaVu Sans Mono", 8, "bold"), anchor="n", tags=("live_lap_txt",))
        self.cv.create_text(cw // 2, y + 104, text="No days. No repeating calendars. Watch the fourth decimal crawl during deep study vs. leap during flow.", fill="#c9d1d9", font=("DejaVu Sans Mono", 8), anchor="n")
        _, _ = self._draw_pill_btn(cw // 2 - 115, y + 128, "+ LAP STAMP CURRENT HOUR", "#fbbf24", "#090d13", "btn_stamp_now", pad_x=14, pad_y=6, font_sz=9)
        self.cv.tag_bind("btn_stamp_now", "<Button-1>", lambda e: self._prompt_epoch_stamp())
        y += 182

        # Stamp Ledger Box
        led_top = y
        y += 12
        self.cv.create_text(28, y, text=f"THE IRREVERSER STAMP LEDGER ({len(stamps)} MARKS ANCHORED)", fill="#fbbf24", font=("DejaVu Sans Mono", 10, "bold"), anchor="nw")
        y += 24
        for s in stamps[:12]:
            row_txt = _fast_ascii(f"STAMP #{int(s.get('seq',1)):03d}  |  {self._fmt_epoch_hrs(s.get('epoch_hrs',0))} HRS  (Delta +{self._fmt_epoch_hrs(s.get('delta_hrs',0))} HRS)  -->  "{s.get('note','')}"")
            self.cv.create_rectangle(28, y, cw - 28, y + 26, fill="#090d13", outline="#30363d")
            self.cv.create_text(38, y + 6, text=row_txt, fill="#e6edf3", font=("DejaVu Sans Mono", 8, "bold"), anchor="nw")
            y += 30
        led_bg = self.cv.create_rectangle(16, led_top, cw - 16, y + 8, fill="#161b22", outline="#30363d")
        self.cv.tag_lower(led_bg)
        y += 20

        # 3 Foundational Modules
        cards = [
            ("FOUNDATION 01 // WHEELER'S COSMIC DELAYED-CHOICE PHOTON (50M LIGHT-YEARS)", "#58a6ff",
             "A photon from a quasar 50 million light-years away bends around a lensing galaxy. Did it travel around one side as a particle or both sides at once as a wave? Quantum mechanics proves that choice is locked in TONIGHT by how you observe it on Earth. How you focus your mind in this exact hour retroactively defines the trajectory of your entire past."),
            ("FOUNDATION 02 // BE A THINKER: HIVE-MIND (THE CIRCLE) VS. SOVEREIGN DETECTIVE (LEGION)", "#d2a8ff",
             "Mae Holland and Eamon Bailey broadcast and smooth out every experience for external validation. Lt. Kinderman and Damien Karras wrestle with heavy truths in inner silence: Kinderman tests the frying pan to feel real fire behind newspaper ink, lets his subconscious incubate clues, and knows the brain is just the pocket while the mind is the hand inside it."),
            ("FOUNDATION 03 // ENDURANCE ART: TEHCHING HSIEH, ROMAN OPALKA & THE UPSIDE", "#3fb950",
             "Hsieh punched a timeclock 8,760 times on the hour for a year. Opalka painted numbers from 1 toward infinity for decades. Pouring 50 hours of cutting cross windows, layering flannel/Climalite/denim, and hand-stitching raw edges into THE UPSIDE compresses lived spacetime into matter--allowing the viewer to quantum-jump across your hours.")
        ]
        for title, col, body in cards:
            ctop = y
            y += 12
            self.cv.create_text(28, y, text=title, fill=col, font=("DejaVu Sans Mono", 10, "bold"), anchor="nw", width=cw - 56)
            y += 24
            tid = self.cv.create_text(28, y, text=body, fill="#c9d1d9", font=("DejaVu Sans Mono", 9), anchor="nw", width=cw - 56)
            bb = self.cv.bbox(tid) or (28, y, cw - 28, y + 60)
            y = bb[3] + 12
            cbg = self.cv.create_rectangle(16, ctop, cw - 16, y, fill="#161b22", outline=col, width=1)
            self.cv.tag_lower(cbg)
            y += 12
        return y

    def _open_lightbox(self, url, caption):
        if not url:
            return
        top = tk.Toplevel(self)
        top.title("Visual Plate Lightbox // Full Resolution")
        top.geometry("900x680")
        top.configure(bg="#090d13")
        l_cv = tk.Canvas(top, bg="#090d13", highlightthickness=0)
        l_cv.pack(fill="both", expand=True)
        l_cv.create_text(450, 300, text="... Loading high-resolution archival plate...", fill="#fbbf24", font=("DejaVu Sans Mono", 10), tags=("wait",))
        l_cv.create_text(450, 640, text=caption, fill="#e6edf3", font=("DejaVu Sans Mono", 9), width=840)

        def _load():
            im = fetch_cached_pil(url, (860, 580))
            if im:
                def _paint():
                    if top.winfo_exists():
                        ph = ImageTk.PhotoImage(im)
                        top._ph = ph
                        l_cv.delete("wait")
                        l_cv.create_image(450, 300, image=ph, anchor="center")
                self.after(0, _paint)
        threading.Thread(target=_load, daemon=True).start()


if __name__ == "__main__":
    KnowledgeDesktopHub().mainloop()
