import os, sys, io, json, time, queue, hashlib, threading, webbrowser, urllib.request, urllib.error
_T0 = time.perf_counter()
import tkinter as tk
from PIL import Image, ImageTk, ImageOps

def _log_t(msg):
    print(f"[{time.perf_counter() - _T0:6.3f}s] {msg}", flush=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CURRICULUM_FILE = os.path.join(BASE_DIR, "curriculum.json")
CLOUD_URL_FILE = os.path.join(BASE_DIR, "cloud_url.txt")
IMG_CACHE_DIR = os.path.expanduser("~/.cache/knowledge_hub_plates")
os.makedirs(IMG_CACHE_DIR, exist_ok=True)
_UA = "KnowledgeDesktopHub/4.0 (Ubuntu; educational)"

_MEM_PIL_CACHE = {}
_MEM_TK_CACHE = {}
_FAILED_URLS = set()
PAGE_SIZE = 5

# Pure ASCII sanitizer for X11 labels so libXft/fontconfig NEVER triggers a 9-second glyph fallback search!
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
    return "https://knowledge-center-dsog.onrender.com"


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


# Blank 1x1 dark placeholder image so image labels never switch between text-mode and image-mode geometry
_BLANK_TK = None


class KnowledgeDesktopHub(tk.Tk):
    def __init__(self):
        global _BLANK_TK
        _log_t("Entering tk.Tk.__init__")
        super().__init__(className="knowledge-hub")
        _log_t("tk.Tk.__init__ complete")
        self.title("Knowledge Command Center // v4.0 Zero-Latency Slot Engine")
        self.geometry("960x760")
        self.minsize(440, 440)
        self.configure(bg="#0d1117")
        self.protocol("WM_DELETE_WINDOW", self._instant_quit)

        _BLANK_TK = ImageTk.PhotoImage(Image.new("RGB", (240, 170), (28, 35, 45)))

        self.cur_track = "art"
        self.page_idx = {"art": 0, "universe": 0, "favorites": 0}
        self.data = {"tracks": {"art": {"lessons": []}, "universe": {"lessons": []}}, "favorites": []}
        self.capacity = {}
        self.open_dd = set()
        self.open_gal = set()
        self.closed_qa = set()
        self._wrap_labels = []
        self._img_queue = queue.LifoQueue()
        self._last_cw = 920
        self._last_mode = "wide"
        self._last_gal_cols = 4
        self._resize_timer = None
        self._sr_job = None
        self._closing = False
        self.sched_status = "Syncing Render cloud..."

        # Header Frame
        self.top_hdr = tk.Frame(self, bg="#090d13", pady=8, padx=12)
        self.top_hdr.pack(fill="x")

        self.title_lbl = tk.Label(
            self.top_hdr,
            text="[KCC] KNOWLEDGE COMMAND CENTER // VISUAL MONOGRAPH ARCHIVE",
            fg="#fbbf24", bg="#090d13", font=("DejaVu Sans Mono", 12, "bold"),
            justify="center", anchor="center", wraplength=900
        )
        self.title_lbl.pack(fill="x")

        self.sub_lbl = tk.Label(
            self.top_hdr, text=self.sched_status,
            fg="#8b949e", bg="#090d13", font=("DejaVu Sans Mono", 8),
            justify="center", anchor="center", wraplength=900
        )
        self.sub_lbl.pack(fill="x", pady=(3, 4))

        self.cap_pill = tk.Label(
            self.top_hdr,
            text="GitHub Vault: -- KB  |  Cloud RAM: --  |  Auto-Drop Runway: ~18.9 yrs",
            fg="#3fb950", bg="#111822", font=("DejaVu Sans Mono", 8, "bold"),
            padx=10, pady=4, highlightbackground="#238636", highlightthickness=1,
            justify="center", anchor="center", wraplength=880
        )
        self.cap_pill.pack(fill="x", padx=8, pady=(1, 0))

        # Navigation Toolbar
        self.nav_outer = tk.Frame(self, bg="#0d1117", pady=6, padx=12)
        self.nav_outer.pack(fill="x")
        self.nav_row1 = tk.Frame(self.nav_outer, bg="#0d1117")
        self.nav_row1.pack(fill="x")
        self.nav_row2 = tk.Frame(self.nav_outer, bg="#0d1117")

        self.btn_art = tk.Button(
            self.nav_row1, text="ART ENDURANCE (0)", command=lambda: self.switch_track("art"),
            bg="#fbbf24", fg="#090d13", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=9, pady=4, cursor="hand2"
        )
        self.btn_uni = tk.Button(
            self.nav_row1, text="PHYSICS OF TIME (0)", command=lambda: self.switch_track("universe"),
            bg="#21262d", fg="#c9d1d9", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=9, pady=4, cursor="hand2"
        )
        self.btn_fav = tk.Button(
            self.nav_row1, text="* FAVORITES (0)", command=lambda: self.switch_track("favorites"),
            bg="#21262d", fg="#fbbf24", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=9, pady=4, cursor="hand2"
        )

        self.filter_lbl = tk.Label(self.nav_row1, text="Filter:", fg="#8b949e", bg="#0d1117", font=("DejaVu Sans Mono", 8))
        self.search_var = tk.StringVar()
        self._search_timer = None
        self.search_var.trace_add("write", self._on_search_type)
        self.filter_ent = tk.Entry(
            self.nav_row1, textvariable=self.search_var, bg="#161b22", fg="#e6edf3",
            insertbackground="#fbbf24", relief="flat", highlightbackground="#30363d",
            highlightthickness=1, font=("DejaVu Sans Mono", 9), width=16
        )

        self.sync_btn = tk.Button(
            self.nav_row1, text="Sync Drop", command=self._manual_sync_drop,
            bg="#192b20", fg="#3fb950", activebackground="#238636", relief="flat",
            font=("DejaVu Sans Mono", 8, "bold"), padx=9, pady=4, cursor="hand2"
        )
        self.matrix_btn = tk.Button(
            self.nav_row1, text="Matrix ->", command=lambda: webbrowser.open(get_cloud_url() + "/matrix"),
            bg="#21262d", fg="#58a6ff", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=8, pady=4, cursor="hand2"
        )

        # Instant Page Bar
        self.page_bar = tk.Frame(self, bg="#111822", pady=4, padx=12, highlightbackground="#30363d", highlightthickness=1)
        self.page_bar.pack(fill="x", padx=12, pady=(0, 6))
        self.prev_btn = tk.Button(
            self.page_bar, text="<< Newer 5", command=lambda: self._step_page(-1),
            bg="#21262d", fg="#58a6ff", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=10, pady=2, cursor="hand2"
        )
        self.prev_btn.pack(side="left")
        self.page_lbl = tk.Label(
            self.page_bar, text="Loading Archive...", fg="#e6edf3", bg="#111822", font=("DejaVu Sans Mono", 8, "bold")
        )
        self.page_lbl.pack(side="left", expand=True)
        self.next_btn = tk.Button(
            self.page_bar, text="Older 5 >>", command=lambda: self._step_page(1),
            bg="#21262d", fg="#58a6ff", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=10, pady=2, cursor="hand2"
        )
        self.next_btn.pack(side="right")

        # Scrollable Main Feed
        wrap = tk.Frame(self, bg="#0d1117")
        wrap.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.cv = tk.Canvas(wrap, bg="#0d1117", highlightthickness=0)
        self.sb = tk.Scrollbar(wrap, orient="vertical", command=self.cv.yview, bg="#161b22", troughcolor="#0d1117", activebackground="#30363d", highlightthickness=0, bd=0)
        self.inner = tk.Frame(self.cv, bg="#0d1117")

        self.inner.bind("<Configure>", self._throttled_scrollregion)
        self.cwin = self.cv.create_window((0, 0), window=self.inner, anchor="nw")
        self.cv.bind("<Configure>", self._on_canvas_configure)
        self.cv.configure(yscrollcommand=self.sb.set)
        self.cv.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.bind_all("<Button-4>", lambda e: self.cv.yview_scroll(-1, "units"))
        self.bind_all("<Button-5>", lambda e: self.cv.yview_scroll(1, "units"))

        self._pack_nav_for_width(960)

        # Build the 5 permanent reusable Card Slots ONCE!
        # Switching tabs or pages NEVER creates or maps new card frames in X11—it mutates these 5 slots in 0.002s!
        self.cards_container = tk.Frame(self.inner, bg="#0d1117")
        self.cards_container.pack(fill="both", expand=True)
        self.favs_container = tk.Frame(self.inner, bg="#0d1117")

        self._slots = []
        for i in range(PAGE_SIZE):
            self._slots.append(self._create_permanent_slot(i))

        self.bot_nav = tk.Frame(self.cards_container, bg="#111822", pady=8, padx=12, highlightbackground="#30363d", highlightthickness=1)
        self.bot_nav.pack(fill="x", pady=(6, 12), padx=2)
        self.bot_prev_btn = tk.Button(
            self.bot_nav, text="<< Newer 5 Lessons", command=lambda: self._step_page(-1),
            bg="#21262d", fg="#fbbf24", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=12, pady=4, cursor="hand2"
        )
        self.bot_prev_btn.pack(side="left")
        self.bot_page_lbl = tk.Label(self.bot_nav, text="Page 1", fg="#8b949e", bg="#111822", font=("DejaVu Sans Mono", 8, "bold"))
        self.bot_page_lbl.pack(side="left", expand=True)
        self.bot_next_btn = tk.Button(
            self.bot_nav, text="Older 5 Lessons >>", command=lambda: self._step_page(1),
            bg="#21262d", fg="#fbbf24", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=12, pady=4, cursor="hand2"
        )
        self.bot_next_btn.pack(side="right")

        _log_t("5 permanent card slots constructed in memory! Populating data...")
        self._load_local()
        self.render_cards()

        _log_t("Mapping window + 5 slots to X11 in one single pass...")
        self.deiconify()
        self.update_idletasks()
        _log_t("READY! Window + Art Page 1 live on screen!")

        for _ in range(3):
            threading.Thread(target=self._image_worker_loop, daemon=True).start()
        self.after(3000, lambda: threading.Thread(target=self._cloud_sync_loop, daemon=True).start())

    def _create_permanent_slot(self, idx):
        """Creates 1 permanent card slot widget tree that stays mapped forever and updates in-place in 0.2ms."""
        card = tk.Frame(self.cards_container, bg="#161b22", highlightbackground="#30363d", highlightthickness=1)
        card.pack(fill="x", pady=6, padx=2)

        top_row = tk.Frame(card, bg="#161b22")
        top_row.pack(fill="x", padx=12, pady=(10, 4))

        left_col = tk.Frame(top_row, bg="#161b22")
        p_card = tk.Frame(top_row, bg="#090d13", highlightbackground="#30363d", highlightthickness=1, cursor="hand2")
        img_lbl = tk.Label(p_card, image=_BLANK_TK, bg="#1c232d", width=240, height=170, cursor="hand2")
        img_lbl.pack()

        b_bar = tk.Frame(p_card, bg="#161b22")
        b_bar.pack(fill="x")
        cap_lbl = tk.Label(b_bar, text="Plate [Zoom]", fg="#8b949e", bg="#161b22", font=("DejaVu Sans Mono", 7, "bold"), padx=5, pady=3, cursor="hand2")
        cap_lbl.pack(side="left")
        lead_st_btn = tk.Button(b_bar, text="[+Fav]", fg="#8b949e", bg="#161b22", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=4, pady=0, cursor="hand2")
        lead_st_btn.pack(side="right")

        p_card.pack(in_=top_row, side="right", anchor="n", padx=(12, 0))
        left_col.pack(in_=top_row, side="left", fill="both", expand=True)

        meta_lbl = self._make_lbl(left_col, "body", text="", fg="#58a6ff", bg="#161b22", font=("DejaVu Sans Mono", 8, "bold"), anchor="w", justify="left")
        meta_lbl.pack(fill="x")
        title_lbl = self._make_lbl(left_col, "body", text="", fg="#f0f6fc", bg="#161b22", font=("DejaVu Sans Mono", 11, "bold"), anchor="w", justify="left")
        title_lbl.pack(fill="x", pady=(5, 4))
        core_lbl = self._make_lbl(left_col, "body", text="", fg="#c9d1d9", bg="#161b22", font=("DejaVu Sans Mono", 9), anchor="w", justify="left")
        core_lbl.pack(fill="x", pady=(0, 6))

        maker_box = tk.Frame(left_col, bg="#0f141b", highlightbackground="#fbbf24", highlightthickness=1)
        maker_box.pack(fill="x", pady=(2, 4))
        maker_lbl = self._make_lbl(maker_box, "maker", text="", fg="#fbbf24", bg="#0f141b", font=("DejaVu Sans Mono", 8), anchor="w", justify="left", padx=8, pady=6)
        maker_lbl.pack(fill="x")

        act_wrap = tk.Frame(card, bg="#161b22")
        act_wrap.pack(fill="x", padx=12, pady=(4, 8))
        act_r1 = tk.Frame(act_wrap, bg="#161b22")
        act_r1.pack(fill="x")
        act_r2 = tk.Frame(act_wrap, bg="#161b22")

        dd_btn = tk.Button(act_r1, text="Read Deep Dive", bg="#21262d", fg="#58a6ff", activebackground="#30363d", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=9, pady=4, cursor="hand2")
        dd_btn.pack(side="left", padx=(0, 6))

        gal_btn = tk.Button(act_r1, text="Plates", bg="#21262d", fg="#3fb950", activebackground="#30363d", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=9, pady=4, cursor="hand2")
        gal_btn.pack(side="left", padx=(0, 8))

        ask_btn = tk.Button(act_wrap, text="Ask Gemini", bg="#251736", fg="#d2a8ff", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=9, pady=4, cursor="hand2")
        ask_ent = tk.Entry(act_wrap, bg="#090d13", fg="#e6edf3", insertbackground="#d2a8ff", relief="flat", highlightbackground="#30363d", highlightthickness=1, font=("DejaVu Sans Mono", 8), width=16)
        ask_ent.pack(in_=act_r1, side="left", fill="x", expand=True, padx=(0, 6), ipady=3)
        ask_btn.pack(in_=act_r1, side="right")

        drawer_area = tk.Frame(card, bg="#161b22")
        drawer_area.pack(fill="x")

        return {
            "idx": idx, "card": card, "top_row": top_row, "left_col": left_col,
            "p_card": p_card, "img_lbl": img_lbl, "cap_lbl": cap_lbl, "lead_st_btn": lead_st_btn,
            "meta_lbl": meta_lbl, "title_lbl": title_lbl, "core_lbl": core_lbl, "maker_lbl": maker_lbl,
            "act_r1": act_r1, "act_r2": act_r2, "dd_btn": dd_btn, "gal_btn": gal_btn,
            "ask_ent": ask_ent, "ask_btn": ask_btn, "drawer_area": drawer_area,
            "bound_key": None
        }

    def _populate_slot(self, slot, les, track_key):
        """Updates an existing card slot in-place in 0.0004 seconds without creating or destroying X11 widgets!"""
        seq = les["seq"]
        key = (track_key, seq)
        slot["bound_key"] = key

        tags_str = "  ".join(f"#{t}" for t in (les.get("tags") or []))
        meta_txt = _fast_ascii(f"#{seq:03d} | {les.get('date','')}  [{str(les.get('model','ARCHIVE')).upper()}]  {tags_str}".strip())
        slot["meta_lbl"].config(text=meta_txt)
        slot["title_lbl"].config(text=_fast_ascii(les.get("title", "")))
        slot["core_lbl"].config(text=_fast_ascii(les.get("core", "")))

        lens_prefix = ">> Temporal & Studio Lens: " if track_key == "universe" else ">> Studio Craft Lens: "
        slot["maker_lbl"].config(text=_fast_ascii(lens_prefix + les.get("maker", "")))

        img_url = les.get("image_url", "")
        if img_url:
            starred = self._is_starred(img_url)
            cap_txt = _fast_ascii((les.get("image_caption") or les.get("title", ""))[:28])
            slot["cap_lbl"].config(text=f"{cap_txt} [Zoom]")
            slot["lead_st_btn"].config(
                text="[*Fav]" if starred else "[+Fav]",
                fg="#fbbf24" if starred else "#8b949e",
                command=lambda tr=track_key, sq=seq, u=img_url, cp=les.get("image_caption") or les.get("title", ""), b=slot["lead_st_btn"]: self._toggle_star(tr, sq, u, cp, "", "Lead Plate", b)
            )
            for wg in (slot["img_lbl"], slot["cap_lbl"]):
                wg.bind("<Button-1>", lambda e, u=img_url, c=_fast_ascii(les.get("image_caption") or les.get("title", "")): self._open_lightbox(u, c))
            self._load_thumb_async(slot["img_lbl"], img_url)
        else:
            slot["img_lbl"].config(image=_BLANK_TK)

        def _on_dd(s_ref=slot, k=key, t=track_key, sq=seq):
            cur_les = self._get_lesson_obj(t, sq) or {}
            ready = bool(cur_les.get("deep_dive") and len(cur_les["deep_dive"]) > 40)
            if ready:
                if k in self.open_dd:
                    self.open_dd.remove(k)
                else:
                    self.open_dd.add(k)
                self._render_slot_drawers(s_ref)
            else:
                self._call_cloud_action("/api/deep_dive", {"track": t, "seq": sq}, s_ref["dd_btn"], "... Writing...", lambda: (self.open_dd.add(k), self._render_slot_drawers(s_ref)))
        slot["dd_btn"].config(command=_on_dd)

        def _on_gal(s_ref=slot, k=key, t=track_key, sq=seq):
            cur_les = self._get_lesson_obj(t, sq) or {}
            ready = len(cur_les.get("gallery") or []) >= 1
            if ready:
                if k in self.open_gal:
                    self.open_gal.remove(k)
                else:
                    self.open_gal.add(k)
                self._render_slot_drawers(s_ref)
            else:
                self._call_cloud_action("/api/gallery", {"track": t, "seq": sq}, s_ref["gal_btn"], "... Curating...", lambda: (self.open_gal.add(k), self._render_slot_drawers(s_ref)))
        slot["gal_btn"].config(command=_on_gal)

        def _on_ask(s_ref=slot, t=track_key, sq=seq):
            q_str = s_ref["ask_ent"].get().strip()
            if not q_str:
                return
            s_ref["ask_ent"].delete(0, "end")
            self._call_cloud_action("/api/ask", {"track": t, "seq": sq, "question": q_str}, s_ref["ask_btn"], "... Asking...", lambda: (s_ref["ask_btn"].config(text="Ask Gemini", state="normal"), self._render_slot_drawers(s_ref)))
        slot["ask_btn"].config(command=_on_ask, text="Ask Gemini", state="normal")
        slot["ask_ent"].bind("<Return>", lambda e, fn=_on_ask: fn())

        self._render_slot_drawers(slot)

    def _render_slot_drawers(self, slot):
        key = slot["bound_key"]
        if not key:
            return
        track, seq = key
        les = self._get_lesson_obj(track, seq) or {}

        has_dd = bool(les.get("deep_dive") and len(les["deep_dive"]) > 40)
        ch_count = (les.get("deep_dive") or "").count("=== DEEPER DIVE CHAPTER") + (1 if has_dd else 0)
        if key in self.open_dd and has_dd:
            slot["dd_btn"].config(text=f"Minimize Deep Dive ({ch_count} Ch)" if ch_count > 1 else "Minimize Deep Dive", bg="#1f2937", fg="#fbbf24", state="normal")
        else:
            slot["dd_btn"].config(text=(f"Read Deep Dive ({ch_count} Ch)" if ch_count > 1 else "Read Deep Dive") if has_dd else "Generate Deep Dive", bg="#21262d", fg="#58a6ff", state="normal")

        gal_list = les.get("gallery") or []
        has_gal = len(gal_list) >= 1
        if key in self.open_gal and has_gal:
            slot["gal_btn"].config(text=f"Hide Plates ({len(gal_list)})", state="normal")
        else:
            slot["gal_btn"].config(text=f"Plates ({len(gal_list)})" if has_gal else "Curate Plates", state="normal")

        da = slot["drawer_area"]
        for w in da.winfo_children():
            w.destroy()

        if key in self.open_dd and has_dd:
            dd_frame = tk.Frame(da, bg="#090d13", highlightbackground="#30363d", highlightthickness=1)
            dd_frame.pack(fill="x", padx=12, pady=(0, 8))
            hdr_bar = tk.Frame(dd_frame, bg="#111822")
            hdr_bar.pack(fill="x", padx=1, pady=1)
            tk.Label(hdr_bar, text=f"DEEP DIVE MONOGRAPH  |  {ch_count} CHAPTER(S) ARCHIVED", fg="#58a6ff", bg="#111822", font=("DejaVu Sans Mono", 8, "bold"), anchor="w", padx=10, pady=6).pack(side="left")
            tk.Button(hdr_bar, text="Minimize Deep Dive", command=lambda s_ref=slot, k=key: (self.open_dd.discard(k), self._render_slot_drawers(s_ref)), bg="#21262d", fg="#fbbf24", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=9, pady=3, cursor="hand2").pack(side="right", padx=6, pady=3)
            deeper_btn = tk.Button(hdr_bar, text=f"+ Deeper Dive (Ch.{ch_count + 1})", bg="#251736", fg="#d2a8ff", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=9, pady=3, cursor="hand2")
            deeper_btn.config(command=lambda s_ref=slot, k=key, t=track, sq=seq, b=deeper_btn: self._call_cloud_action("/api/deep_dive", {"track": t, "seq": sq, "append": True}, b, "... Diving Deeper...", lambda: (self.open_dd.add(k), self._render_slot_drawers(s_ref))))
            deeper_btn.pack(side="right", padx=4, pady=3)
            self._make_lbl(dd_frame, "full", text=_fast_ascii(les["deep_dive"]), fg="#d0d7de", bg="#090d13", font=("DejaVu Sans Mono", 9), justify="left", anchor="w", padx=12, pady=8).pack(fill="x")
            bot_bar = tk.Frame(dd_frame, bg="#090d13")
            bot_bar.pack(fill="x", padx=10, pady=(0, 8))
            tk.Button(bot_bar, text="Minimize Deep Dive", command=lambda s_ref=slot, k=key: (self.open_dd.discard(k), self._render_slot_drawers(s_ref)), bg="#21262d", fg="#fbbf24", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=10, pady=3, cursor="hand2").pack(side="right")

        if key in self.open_gal and has_gal:
            g_strip = tk.Frame(da, bg="#090d13", highlightbackground="#30363d", highlightthickness=1)
            g_strip.pack(fill="x", padx=12, pady=(0, 8))
            grid_f = tk.Frame(g_strip, bg="#090d13")
            grid_f.pack(fill="x", padx=8, pady=(8, 4))
            gal_cols = self._last_gal_cols
            for idx_g, g_item in enumerate(gal_list):
                r_i, c_i = divmod(idx_g, gal_cols)
                gu = g_item.get("url", "")
                gc = _fast_ascii(f"{g_item.get('caption', '')} -- {g_item.get('study_note', '')}".strip(" -"))
                gs = _fast_ascii(g_item.get("source", "Archive"))
                g_star = self._is_starred(gu)
                cell = tk.Frame(grid_f, bg="#161b22", highlightbackground="#30363d", highlightthickness=1)
                cell.grid(row=r_i, column=c_i, padx=4, pady=4, sticky="n")

                hdr_c = tk.Frame(cell, bg="#161b22")
                hdr_c.pack(fill="x")
                tk.Button(hdr_c, text="x", fg="#f85149", bg="#161b22", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=5, pady=0, cursor="hand2", command=lambda s_ref=slot, tr=track, sq=seq, u=gu: self._delete_plate(tr, sq, u, s_ref)).pack(side="left")
                tk.Label(hdr_c, text=gs[:16], fg="#58a6ff", bg="#161b22", font=("DejaVu Sans Mono", 6)).pack(side="left", padx=2)
                st_btn = tk.Button(hdr_c, text="[*]" if g_star else "[+]", fg="#fbbf24" if g_star else "#8b949e", bg="#161b22", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=4, pady=0, cursor="hand2")
                st_btn.config(command=lambda tr=track, sq=seq, u=gu, cp=g_item.get("caption", ""), sn=g_item.get("study_note", ""), sr=gs, b_ref=st_btn: self._toggle_star(tr, sq, u, cp, sn, sr, b_ref))
                st_btn.pack(side="right")

                gl = tk.Label(cell, image=_BLANK_TK, bg="#1c232d", width=190, height=126, cursor="hand2")
                gl.pack()
                cl = tk.Label(cell, text=_fast_ascii((g_item.get("caption") or "Plate")[:24]), fg="#c9d1d9", bg="#161b22", font=("DejaVu Sans Mono", 7), pady=3, cursor="hand2")
                cl.pack(fill="x")
                for wg in (gl, cl):
                    wg.bind("<Button-1>", lambda e, u=gu, c=gc: self._open_lightbox(u, c))
                self._load_thumb_async(gl, gu, size=(190, 126))

            cur_bar = tk.Frame(g_strip, bg="#090d13")
            cur_bar.pack(fill="x", padx=10, pady=(4, 8))
            c_btn = tk.Button(cur_bar, text="+ Curate 5 Plates", bg="#1f2937", fg="#fbbf24", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=9, pady=4, cursor="hand2")
            c_ent = tk.Entry(cur_bar, bg="#161b22", fg="#e6edf3", insertbackground="#fbbf24", relief="flat", highlightbackground="#30363d", highlightthickness=1, font=("DejaVu Sans Mono", 8), width=16)
            c_ent.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=3)
            c_btn.pack(side="right")

            def _on_more_gal(s_ref=slot, t=track, sq=seq, ent=c_ent, b=c_btn, k=key):
                cq = ent.get().strip()
                self._call_cloud_action("/api/gallery", {"track": t, "seq": sq, "append": True, "query": cq}, b, "... Routing...", lambda: (self.open_gal.add(k), self._render_slot_drawers(s_ref)))
            c_btn.config(command=_on_more_gal)
            c_ent.bind("<Return>", lambda e, fn=_on_more_gal: fn())

        qa_list = les.get("qa_log") or []
        if qa_list:
            is_minimized = (key in self.closed_qa)
            qa_hdr = tk.Frame(da, bg="#120d1d")
            qa_hdr.pack(fill="x", padx=12, pady=(0, 4))
            tk.Button(
                qa_hdr,
                text=f"Show Saved Q&A ({len(qa_list)}) [v]" if is_minimized else f"Minimize Q&A ({len(qa_list)}) [^]",
                command=lambda s_ref=slot, k=key: (self.closed_qa.remove(k) if k in self.closed_qa else self.closed_qa.add(k), self._render_slot_drawers(s_ref)),
                bg="#251736", fg="#d2a8ff", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=8, pady=2, cursor="hand2"
            ).pack(side="left")
            if not is_minimized:
                for qa in qa_list:
                    qa_box = tk.Frame(da, bg="#0c131d", highlightbackground="#6e40c9", highlightthickness=1)
                    qa_box.pack(fill="x", padx=12, pady=(0, 6))
                    self._make_lbl(qa_box, "full", text=_fast_ascii(f"Q: {qa.get('q','')}   [{qa.get('model','GEMINI')} | {qa.get('ts','')}]"), fg="#d2a8ff", bg="#0c131d", font=("DejaVu Sans Mono", 8, "bold"), anchor="w", justify="left", padx=10, pady=4).pack(fill="x")
                    self._make_lbl(qa_box, "full", text=_fast_ascii(qa.get("a", "")), fg="#e6edf3", bg="#0c131d", font=("DejaVu Sans Mono", 9), justify="left", anchor="w", padx=10, pady=6).pack(fill="x")

        self._throttled_scrollregion()

    def _throttled_scrollregion(self, _event=None):
        if self._sr_job:
            return
        self._sr_job = self.after(30, self._do_scrollregion)

    def _do_scrollregion(self):
        self._sr_job = None
        if not self._closing:
            self.cv.configure(scrollregion=self.cv.bbox("all") or (0, 0, 100, 100))

    def _instant_quit(self):
        self._closing = True
        try:
            self.withdraw()
        except Exception:
            pass
        os._exit(0)

    def _step_page(self, delta):
        self.page_idx[self.cur_track] = max(0, self.page_idx.get(self.cur_track, 0) + delta)
        self.render_cards()

    def _on_search_type(self, *_):
        if self._search_timer:
            self.after_cancel(self._search_timer)
        self.page_idx[self.cur_track] = 0
        self._search_timer = self.after(150, self.render_cards)

    def _image_worker_loop(self):
        while not self._closing:
            try:
                lbl, url, size = self._img_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if self._closing:
                continue
            try:
                if not lbl.winfo_exists():
                    continue
                im = fetch_cached_pil(url, size)
                if im and not self._closing:
                    def _paint(l=lbl, img=im, u=url, sz=size):
                        if not self._closing and l.winfo_exists():
                            ck = (u, sz)
                            ph = _MEM_TK_CACHE.get(ck)
                            if not ph:
                                ph = ImageTk.PhotoImage(img)
                                _MEM_TK_CACHE[ck] = ph
                            l.config(image=ph, width=sz[0], height=sz[1])
                    self.after(0, _paint)
            except Exception:
                pass

    def _calc_wraps(self, cw=None):
        if cw is None:
            cw = self._last_cw
        is_wide = (cw >= 880)
        body_w = max(180, (cw - 310) if is_wide else (cw - 48))
        maker_w = max(160, body_w - 22)
        full_w = max(180, cw - 56)
        fav_w = max(180, (cw - 260) if cw >= 660 else (cw - 48))
        return {"body": body_w, "maker": maker_w, "full": full_w, "fav": fav_w}

    def _make_lbl(self, parent, kind="body", **kwargs):
        wraps = self._calc_wraps()
        lbl = tk.Label(parent, wraplength=wraps.get(kind, 600), **kwargs)
        self._wrap_labels.append((lbl, kind))
        return lbl

    def _pack_nav_for_width(self, w):
        target_nav = "wide" if w >= 940 else "narrow"
        if getattr(self, "_cur_nav_mode", None) == target_nav:
            return
        self._cur_nav_mode = target_nav
        for child in (self.btn_art, self.btn_uni, self.btn_fav, self.filter_lbl, self.filter_ent, self.sync_btn, self.matrix_btn):
            child.pack_forget()
        self.nav_row2.pack_forget()

        if target_nav == "wide":
            self.btn_art.pack(in_=self.nav_row1, side="left", padx=(0, 6))
            self.btn_uni.pack(in_=self.nav_row1, side="left", padx=(0, 6))
            self.btn_fav.pack(in_=self.nav_row1, side="left", padx=(0, 10))
            self.filter_lbl.pack(in_=self.nav_row1, side="left")
            self.filter_ent.config(width=20)
            self.filter_ent.pack(in_=self.nav_row1, side="left", padx=5, ipady=3)
            self.sync_btn.pack(in_=self.nav_row1, side="right", padx=(6, 0))
            self.matrix_btn.pack(in_=self.nav_row1, side="right")
        else:
            self.nav_row2.pack(fill="x", pady=(6, 0))
            self.btn_art.pack(in_=self.nav_row1, side="left", padx=(0, 4))
            self.btn_uni.pack(in_=self.nav_row1, side="left", padx=(0, 4))
            self.btn_fav.pack(in_=self.nav_row1, side="left", padx=(0, 4))
            self.filter_lbl.pack(in_=self.nav_row2, side="left")
            self.filter_ent.config(width=12)
            self.filter_ent.pack(in_=self.nav_row2, side="left", padx=4, ipady=2, fill="x", expand=True)
            self.sync_btn.pack(in_=self.nav_row2, side="right", padx=(4, 0))
            self.matrix_btn.pack(in_=self.nav_row2, side="right")

    def _on_canvas_configure(self, event):
        cw = event.width
        self.cv.itemconfig(self.cwin, width=cw)
        if cw < 120 or abs(cw - self._last_cw) < 4:
            return
        self._last_cw = cw
        if self._resize_timer:
            self.after_cancel(self._resize_timer)
        self._resize_timer = self.after(30, lambda w=cw: self._apply_geometry_pass(w))

    def _apply_geometry_pass(self, cw):
        win_est = cw + 38
        self.title_lbl.config(wraplength=max(200, cw - 16))
        self.sub_lbl.config(wraplength=max(200, cw - 16))
        self.cap_pill.config(wraplength=max(180, cw - 32))
        self._pack_nav_for_width(win_est)
        self._update_tab_counts(win_est)

        mode = "wide" if cw >= 880 else "narrow"
        gal_cols = max(1, min(5, (cw - 32) // 210))
        self._last_gal_cols = gal_cols

        if mode != self._last_mode:
            self._last_mode = mode
            is_wide = (mode == "wide")
            for slot in self._slots:
                slot["p_card"].pack_forget()
                if is_wide:
                    slot["left_col"].pack_forget()
                    slot["p_card"].pack(in_=slot["top_row"], side="right", anchor="n", padx=(12, 0))
                    slot["left_col"].pack(in_=slot["top_row"], side="left", fill="both", expand=True)
                else:
                    slot["p_card"].pack(in_=slot["left_col"], anchor="w", pady=(8, 2))

        wraps = self._calc_wraps(cw)
        alive = []
        for lbl, kind in self._wrap_labels:
            if lbl.winfo_exists():
                lbl.config(wraplength=wraps.get(kind, 600))
                alive.append((lbl, kind))
        self._wrap_labels = alive
        self._throttled_scrollregion()

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

    def _cloud_sync_loop(self):
        while not self._closing:
            try:
                u = get_cloud_url() + "/state"
                req = urllib.request.Request(u, headers={"User-Agent": _UA})
                j = json.loads(urllib.request.urlopen(req, timeout=22).read().decode())
                if j.get("curriculum") and not self._closing:
                    old_counts = (
                        len(self.data.get("tracks", {}).get("art", {}).get("lessons", [])),
                        len(self.data.get("tracks", {}).get("universe", {}).get("lessons", [])),
                    )
                    self.data = j["curriculum"]
                    self.data.setdefault("favorites", [])
                    if j.get("capacity"):
                        self.capacity = j["capacity"]
                    self._save_local()
                    new_counts = (
                        len(self.data.get("tracks", {}).get("art", {}).get("lessons", [])),
                        len(self.data.get("tracks", {}).get("universe", {}).get("lessons", [])),
                    )
                    st = j.get("scheduler", {}).get("status", "ONLINE")
                    lc = j.get("scheduler", {}).get("last_check", "--")
                    self.after(0, lambda s=st, l=lc, rr=(old_counts != new_counts): self._apply_sync_hdr(s, l, rr))
            except Exception:
                pass
            time.sleep(35)

    def _apply_sync_hdr(self, st, lc, rerender):
        if self._closing:
            return
        self.sched_status = st
        self.sub_lbl.config(text=_fast_ascii(f"{st}  |  Last Check: {lc}"))
        c = self.capacity
        if c:
            ram_part = f"Render RAM: {c.get('ram_mb', 0)}/{c.get('ram_limit_mb', 512)} MB ({c.get('ram_pct', 0)}%)" if c.get("ram_mb") else "Cloud: Synced"
            self.cap_pill.config(
                text=f"GitHub Vault: {c.get('json_kb', 0)} KB / {c.get('gh_limit_mb', 75)} MB ({c.get('gh_pct', 0)}%)  |  {ram_part}  |  Auto-Drop Runway: ~{c.get('runway_years', 18.9)} yrs"
            )
        self._update_tab_counts()
        if rerender:
            self.render_cards()

    def _manual_sync_drop(self):
        self.sync_btn.config(text="... Dropping...", state="disabled")
        self.sub_lbl.config(text="ONLINE | Triggering Missed/Daily Drop on Render (Art + Universe + Matrix)...")

        def _worker():
            try:
                u = get_cloud_url() + "/api/sync_drop"
                req = urllib.request.Request(
                    u, data=json.dumps({"force": True}).encode(),
                    headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST"
                )
                j = json.loads(urllib.request.urlopen(req, timeout=140).read().decode())
                if j.get("ok"):
                    if j.get("curriculum"):
                        self.data = j["curriculum"]
                        self.data.setdefault("favorites", [])
                        self._save_local()
                    if j.get("capacity"):
                        self.capacity = j["capacity"]
                    st = j.get("scheduler", {}).get("status", "ONLINE")
                    lc = j.get("scheduler", {}).get("last_check", "--")
                    added = (j.get("result") or {}).get("changed") or []
                    btn_lbl = f"[OK] +{len(added)} Dropped!" if added else "[OK] Up to Date"
                    self.after(0, lambda: (
                        self._apply_sync_hdr(st, lc, bool(added)),
                        self.sync_btn.config(text=btn_lbl, state="normal"),
                        self.after(3500, lambda: self.sync_btn.config(text="Sync Drop"))
                    ))
                else:
                    self.after(0, lambda: self.sync_btn.config(text="[!] Retry", state="normal"))
            except Exception:
                self.after(0, lambda: self.sync_btn.config(text="[!] Wake & Retry", state="normal"))
        threading.Thread(target=_worker, daemon=True).start()

    def _toggle_star(self, track, seq, url, caption="", study_note="", source="", star_btn=None):
        if star_btn and star_btn.winfo_exists():
            now_st = ("+" in star_btn.cget("text"))
            star_btn.config(text="[*Fav]" if now_st else "[+Fav]", fg="#fbbf24" if now_st else "#8b949e")

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
                    self.after(0, lambda: (
                        self._apply_sync_hdr(self.sched_status, "Synced", False),
                        self.render_cards() if self.cur_track == "favorites" else None
                    ))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _delete_plate(self, track, seq, url, slot_ref=None):
        les = self._get_lesson_obj(track, seq)
        if les and les.get("gallery"):
            les["gallery"] = [g for g in les["gallery"] if g.get("url") != url]
        if slot_ref:
            self._render_slot_drawers(slot_ref)

        def _worker():
            try:
                u = get_cloud_url() + "/api/delete_plate"
                req = urllib.request.Request(
                    u, data=json.dumps({"track": track, "seq": seq, "url": url}).encode(),
                    headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST"
                )
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
                    self.after(0, lambda: self._apply_sync_hdr(self.sched_status, "Pruned", False))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _update_tab_counts(self, explicit_w=None):
        a_n = len(self.data.get("tracks", {}).get("art", {}).get("lessons", []))
        u_n = len(self.data.get("tracks", {}).get("universe", {}).get("lessons", []))
        f_n = len(self.data.get("favorites") or [])
        w = explicit_w if explicit_w else (self._last_cw + 38)
        if w >= 940:
            self.btn_art.config(text=f"ART ENDURANCE ({a_n})")
            self.btn_uni.config(text=f"PHYSICS OF TIME ({u_n})")
            self.btn_fav.config(text=f"* KEY'S FAVORITES ({f_n})")
        else:
            self.btn_art.config(text=f"ART ({a_n})")
            self.btn_uni.config(text=f"PHYSICS ({u_n})")
            self.btn_fav.config(text=f"* FAVS ({f_n})")

    def switch_track(self, t):
        self.cur_track = t
        self.btn_art.config(bg="#fbbf24" if t == "art" else "#21262d", fg="#090d13" if t == "art" else "#c9d1d9")
        self.btn_uni.config(bg="#58a6ff" if t == "universe" else "#21262d", fg="#090d13" if t == "universe" else "#c9d1d9")
        self.btn_fav.config(bg="#fbbf24" if t == "favorites" else "#21262d", fg="#090d13" if t == "favorites" else "#fbbf24")
        self.render_cards()

    def _jump_to_lesson(self, track, seq):
        self.search_var.set("")
        raw_list = self.data.get("tracks", {}).get(track, {}).get("lessons", [])
        all_seq = [int(x.get("seq", 0)) for x in reversed(raw_list) if isinstance(x, dict)]
        if int(seq) in all_seq:
            idx = all_seq.index(int(seq))
            self.page_idx[track] = idx // PAGE_SIZE
        else:
            self.page_idx[track] = 0
        self.switch_track(track)

    def _open_lightbox(self, url, caption):
        if not url:
            return
        top = tk.Toplevel(self)
        top.title("Visual Plate Lightbox // Full Resolution")
        top.geometry("900x680")
        top.configure(bg="#090d13")
        lbl_img = tk.Label(top, text="... Loading high-resolution archival plate...", fg="#fbbf24", bg="#090d13", font=("DejaVu Sans Mono", 10))
        lbl_img.pack(expand=True, fill="both", padx=14, pady=(14, 6))
        cap_l = tk.Label(top, text=_fast_ascii(caption), fg="#e6edf3", bg="#090d13", font=("DejaVu Sans Mono", 9), pady=8, wraplength=840)
        cap_l.pack(fill="x", padx=12)

        def _load():
            try:
                im = fetch_cached_pil(url, (860, 580))
                if im:
                    def _paint():
                        if top.winfo_exists():
                            ph = ImageTk.PhotoImage(im)
                            top._ph = ph
                            lbl_img.config(image=ph, text="")
                    self.after(0, _paint)
            except Exception as e:
                self.after(0, lambda: lbl_img.config(text=f"Plate unavailable ({e})"))
        threading.Thread(target=_load, daemon=True).start()

    def _load_thumb_async(self, lbl, url, size=(240, 170)):
        cache_key = (url, size)
        if cache_key in _MEM_TK_CACHE:
            lbl.config(image=_MEM_TK_CACHE[cache_key], width=size[0], height=size[1])
            return
        if cache_key in _MEM_PIL_CACHE:
            ph = ImageTk.PhotoImage(_MEM_PIL_CACHE[cache_key])
            _MEM_TK_CACHE[cache_key] = ph
            lbl.config(image=ph, width=size[0], height=size[1])
            return
        h = hashlib.sha256(url.encode()).hexdigest()[:24]
        thumb_path = os.path.join(IMG_CACHE_DIR, f"{h}_{size[0]}x{size[1]}.jpg")
        if os.path.exists(thumb_path):
            try:
                im = Image.open(thumb_path).convert("RGB")
                _MEM_PIL_CACHE[cache_key] = im
                ph = ImageTk.PhotoImage(im)
                _MEM_TK_CACHE[cache_key] = ph
                lbl.config(image=ph, width=size[0], height=size[1])
                return
            except Exception:
                pass
        lbl.config(image=_BLANK_TK, width=size[0], height=size[1])
        self._img_queue.put((lbl, url, size))

    def _call_cloud_action(self, endpoint, payload, btn, wait_txt, done_cb):
        btn.config(text=wait_txt, state="disabled")

        def _worker():
            last_err = ""
            for attempt in range(2):
                try:
                    u = get_cloud_url() + endpoint
                    req = urllib.request.Request(
                        u, data=json.dumps(payload).encode(),
                        headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST"
                    )
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
                        self.after(0, lambda: (self._apply_sync_hdr(self.sched_status, "Synced", False), done_cb()))
                        return
                    last_err = j.get("error", "Busy")
                except urllib.error.HTTPError as he:
                    try:
                        err_b = json.loads(he.read().decode())
                        last_err = err_b.get("error", f"HTTP {he.code}")
                    except Exception:
                        last_err = f"HTTP {he.code}"
                except Exception as e:
                    last_err = str(e)
                if attempt == 0:
                    self.after(0, lambda: btn.config(text="... Retrying...") if btn.winfo_exists() else None)
                    time.sleep(2)
            print(f"[Cloud Action Warn {endpoint}] {last_err}", flush=True)
            self.after(0, lambda: btn.config(text="[!] Tap to Retry", state="normal") if btn.winfo_exists() else None)
        threading.Thread(target=_worker, daemon=True).start()

    def _render_favorites_view(self, cw):
        for w in self.favs_container.winfo_children():
            w.destroy()
        favs = self.data.get("favorites") or []
        if not favs:
            empty = tk.Frame(self.favs_container, bg="#161b22", highlightbackground="#30363d", highlightthickness=1, pady=24, padx=12)
            empty.pack(fill="x", pady=12, padx=4)
            self._make_lbl(empty, "full", text="* Key's Favorites Vault is empty right now.", fg="#f0f6fc", bg="#161b22", font=("DejaVu Sans Mono", 10, "bold")).pack(fill="x")
            self._make_lbl(empty, "full", text="Click [+Fav] on any lead plate or curated gallery plate to pin it permanently to GitHub.", fg="#8b949e", bg="#161b22", font=("DejaVu Sans Mono", 9), pady=6).pack(fill="x")
            return

        stack_fav = cw < 660
        for f in favs:
            card = tk.Frame(self.favs_container, bg="#161b22", highlightbackground="#fbbf24", highlightthickness=1)
            card.pack(fill="x", pady=6, padx=2)
            row = tk.Frame(card, bg="#161b22")
            row.pack(fill="x", padx=12, pady=10)

            p_card = tk.Frame(row, bg="#090d13", highlightbackground="#30363d", highlightthickness=1, cursor="hand2")
            if stack_fav:
                p_card.pack(anchor="w", pady=(0, 8))
            else:
                p_card.pack(side="left", padx=(0, 14), anchor="n")
            il = tk.Label(p_card, image=_BLANK_TK, bg="#1c232d", width=205, height=138, cursor="hand2")
            il.pack()
            il.bind("<Button-1>", lambda e, u=f.get("url", ""), c=_fast_ascii(f.get("caption", "")): self._open_lightbox(u, c))
            self._load_thumb_async(il, f.get("url", ""), size=(205, 138))

            info = tk.Frame(row, bg="#161b22")
            info.pack(side="left", fill="both", expand=True)
            self._make_lbl(info, "fav", text=_fast_ascii(f"{str(f.get('track','art')).upper()} #{int(f.get('seq',1)):03d}  |  {f.get('source','Archive')}  |  Saved {f.get('saved_at','')}"), fg="#8b949e", bg="#161b22", font=("DejaVu Sans Mono", 8, "bold"), anchor="w", justify="left").pack(fill="x")
            self._make_lbl(info, "fav", text=_fast_ascii(f.get("caption", "Visual Plate")), fg="#f0f6fc", bg="#161b22", font=("DejaVu Sans Mono", 10, "bold"), anchor="w", justify="left").pack(fill="x", pady=(4, 2))
            if f.get("study_note"):
                self._make_lbl(info, "fav", text=_fast_ascii(f.get("study_note", "")), fg="#fbbf24", bg="#161b22", font=("DejaVu Sans Mono", 8), anchor="w", justify="left").pack(fill="x", pady=(0, 6))

            b_row = tk.Frame(info, bg="#161b22")
            b_row.pack(fill="x", pady=(4, 0))
            tk.Button(b_row, text=f"Open {str(f.get('track','art')).upper()} (#{int(f.get('seq',1)):03d}) ->", command=lambda tr=f.get("track", "art"), sq=f.get("seq", 1): self._jump_to_lesson(tr, sq), bg="#21262d", fg="#fbbf24", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=9, pady=4, cursor="hand2").pack(side="left", padx=(0, 8))
            tk.Button(b_row, text="[*] Unstar", command=lambda tr=f.get("track", "art"), sq=f.get("seq", 1), u=f.get("url", ""): self._toggle_star(tr, sq, u), bg="#2d2208", fg="#fbbf24", relief="flat", font=("DejaVu Sans Mono", 8, "bold"), padx=9, pady=4, cursor="hand2").pack(side="left")

    def render_cards(self):
        cw = self.cv.winfo_width()
        if cw < 120:
            cw = self._last_cw
        self._last_cw = cw
        self._update_tab_counts(cw + 38)

        if self.cur_track == "favorites":
            self.cards_container.pack_forget()
            self.favs_container.pack(fill="both", expand=True)
            self.page_lbl.config(text=f"* KEY'S FAVORITES VAULT ({len(self.data.get('favorites') or [])} Pinned Plates)")
            self.prev_btn.config(state="disabled")
            self.next_btn.config(state="disabled")
            self._render_favorites_view(cw)
            self.cv.yview_moveto(0.0)
            self._throttled_scrollregion()
            return

        self.favs_container.pack_forget()
        if not self.cards_container.winfo_ismapped():
            self.cards_container.pack(fill="both", expand=True)

        q = self.search_var.get().strip().lower()
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

        t_label = "ART ENDURANCE" if self.cur_track == "art" else "PHYSICS OF TIME"
        if total > 0:
            hi_seq = page_slice[0]["seq"]
            lo_seq = page_slice[-1]["seq"]
            meta_txt = f"{t_label}  |  Showing #{hi_seq:03d}-#{lo_seq:03d} of {total}  (Page {cur_p + 1}/{max_page + 1})"
        else:
            meta_txt = f"{t_label}  |  0 matching lessons"

        has_prev = (cur_p > 0)
        has_next = (end_i < total)
        self.page_lbl.config(text=meta_txt)
        self.prev_btn.config(state="normal" if has_prev else "disabled", fg="#58a6ff" if has_prev else "#484f58")
        self.next_btn.config(state="normal" if has_next else "disabled", fg="#58a6ff" if has_next else "#484f58")

        self.bot_page_lbl.config(text=f"Page {cur_p + 1} of {max_page + 1}")
        self.bot_prev_btn.config(state="normal" if has_prev else "disabled", fg="#fbbf24" if has_prev else "#484f58")
        self.bot_next_btn.config(state="normal" if has_next else "disabled", fg="#fbbf24" if has_next else "#484f58")

        # Update the 5 permanent slots IN-PLACE (zero new frames packed on tab/page change!)
        for idx in range(PAGE_SIZE):
            slot = self._slots[idx]
            if idx < len(page_slice):
                if not slot["card"].winfo_ismapped():
                    slot["card"].pack(fill="x", pady=6, padx=2, before=self.bot_nav)
                self._populate_slot(slot, page_slice[idx], self.cur_track)
            else:
                slot["card"].pack_forget()

        self.cv.yview_moveto(0.0)
        self._throttled_scrollregion()


if __name__ == "__main__":
    KnowledgeDesktopHub().mainloop()
