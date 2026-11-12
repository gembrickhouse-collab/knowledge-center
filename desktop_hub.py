import os, io, json, time, queue, hashlib, threading, webbrowser, urllib.request
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageOps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CURRICULUM_FILE = os.path.join(BASE_DIR, "curriculum.json")
CLOUD_URL_FILE = os.path.join(BASE_DIR, "cloud_url.txt")
IMG_CACHE_DIR = os.path.expanduser("~/.cache/knowledge_hub_plates")
os.makedirs(IMG_CACHE_DIR, exist_ok=True)
_UA = "KnowledgeDesktopHub/3.1 (Ubuntu; educational)"

_MEM_PIL_CACHE = {}
_MEM_TK_CACHE = {}   # (url, size) -> ImageTk.PhotoImage (instant 0ms reuse!)
_FAILED_URLS = set()


def get_cloud_url():
    if os.path.exists(CLOUD_URL_FILE):
        u = open(CLOUD_URL_FILE).read().strip().rstrip("/")
        if u:
            return u
    return "https://knowledge-center-dsog.onrender.com"


def _normalize_pil_image(raw_im):
    """Fixes black-square bug on transparent PNG/SVG/WebP logos by compositing alpha over slate studio matte."""
    raw_im = ImageOps.exif_transpose(raw_im)
    if raw_im.mode in ("RGBA", "LA") or (raw_im.mode == "P" and "transparency" in raw_im.info):
        rgba = raw_im.convert("RGBA")
        # If image is dark/black silhouette with transparency, use a warm gallery parchment-slate matte so it pops!
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
    p = os.path.join(IMG_CACHE_DIR, f"{h}_v31.jpg")
    try:
        if not os.path.exists(p):
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            raw = urllib.request.urlopen(req, timeout=8).read()
            im = _normalize_pil_image(Image.open(io.BytesIO(raw)))
            im.save(p, "JPEG", quality=88)
        else:
            im = Image.open(p).convert("RGB")
        im.thumbnail(max_size, Image.Resampling.BILINEAR)
        _MEM_PIL_CACHE[cache_key] = im
        return im
    except Exception:
        _FAILED_URLS.add(url)
        return None


class KnowledgeDesktopHub(tk.Tk):
    def __init__(self):
        super().__init__(className="knowledge-hub")
        self.title("Knowledge Command Center // v3.1 Instant Zero-Reload Engine")
        self.geometry("960x760")
        self.minsize(440, 440)
        self.configure(bg="#0d1117")

        # Instant kernel exit on window close so X11/XWayland never freezes Firefox typing (#6)!
        self.protocol("WM_DELETE_WINDOW", self._instant_quit)

        self.cur_track = "art"
        self.data = {"tracks": {"art": {"lessons": []}, "universe": {"lessons": []}}, "favorites": []}
        self.capacity = {}
        self.open_dd = set()
        self.open_gal = set()
        self._card_registry = {}
        self._wrap_labels = []
        self._pending_lessons = []
        self._img_queue = queue.Queue()
        self._last_cw = 920
        self._last_mode = "wide"
        self._last_gal_cols = 4
        self._resize_timer = None
        self._closing = False
        self.sched_status = "Syncing Render cloud..."

        # Header Frame
        self.top_hdr = tk.Frame(self, bg="#090d13", pady=8, padx=12)
        self.top_hdr.pack(fill="x")

        self.title_lbl = tk.Label(
            self.top_hdr,
            text="🧠 KNOWLEDGE COMMAND CENTER // VISUAL MONOGRAPH ARCHIVE",
            fg="#fbbf24", bg="#090d13", font=("Monospace", 12, "bold"),
            justify="center", anchor="center", wraplength=900
        )
        self.title_lbl.pack(fill="x")

        self.sub_lbl = tk.Label(
            self.top_hdr, text=self.sched_status,
            fg="#8b949e", bg="#090d13", font=("Monospace", 8),
            justify="center", anchor="center", wraplength=900
        )
        self.sub_lbl.pack(fill="x", pady=(3, 4))

        self.cap_pill = tk.Label(
            self.top_hdr,
            text="💾 GitHub Vault: -- KB  •  ⚡ Cloud RAM: --  •  🛣️ Auto-Drop Runway: ~18.9 yrs",
            fg="#3fb950", bg="#111822", font=("Monospace", 8, "bold"),
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
            self.nav_row1, text="🎨 ART (0)", command=lambda: self.switch_track("art"),
            bg="#fbbf24", fg="#090d13", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2"
        )
        self.btn_uni = tk.Button(
            self.nav_row1, text="🌌 PHYSICS (0)", command=lambda: self.switch_track("universe"),
            bg="#21262d", fg="#c9d1d9", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2"
        )
        self.btn_fav = tk.Button(
            self.nav_row1, text="⭐ FAVS (0)", command=lambda: self.switch_track("favorites"),
            bg="#21262d", fg="#fbbf24", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2"
        )

        self.filter_lbl = tk.Label(self.nav_row1, text="🔍", fg="#8b949e", bg="#0d1117", font=("Monospace", 9))
        self.search_var = tk.StringVar()
        self._search_timer = None
        self.search_var.trace_add("write", self._on_search_type)
        self.filter_ent = tk.Entry(
            self.nav_row1, textvariable=self.search_var, bg="#161b22", fg="#e6edf3",
            insertbackground="#fbbf24", relief="flat", highlightbackground="#30363d",
            highlightthickness=1, font=("Monospace", 9), width=16
        )

        self.sync_btn = tk.Button(
            self.nav_row1, text="⚡ Sync Drop", command=self._manual_sync_drop,
            bg="#192b20", fg="#3fb950", activebackground="#238636", relief="flat",
            font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2"
        )
        self.matrix_btn = tk.Button(
            self.nav_row1, text="🧬 Matrix ↗", command=lambda: webbrowser.open(get_cloud_url() + "/matrix"),
            bg="#21262d", fg="#58a6ff", relief="flat", font=("Monospace", 8, "bold"), padx=8, pady=4, cursor="hand2"
        )

        # Scrollable Main Feed
        wrap = tk.Frame(self, bg="#0d1117")
        wrap.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.cv = tk.Canvas(wrap, bg="#0d1117", highlightthickness=0)
        self.sb = ttk.Scrollbar(wrap, orient="vertical", command=self._on_scrollbar)
        self.inner = tk.Frame(self.cv, bg="#0d1117")
        self.inner.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cwin = self.cv.create_window((0, 0), window=self.inner, anchor="nw")
        self.cv.bind("<Configure>", self._on_canvas_configure)
        self.cv.configure(yscrollcommand=self._on_yscroll)
        self.cv.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.bind_all("<Button-4>", lambda e: self._scroll_wheel(-1))
        self.bind_all("<Button-5>", lambda e: self._scroll_wheel(1))

        self._pack_nav_for_width(960)

        # Force X11 window to map and paint on screen IMMEDIATELY (<0.05s) before reading JSON or building cards!
        self.update_idletasks()
        self.deiconify()
        self.update()

        threading.Thread(target=self._image_worker_loop, daemon=True).start()
        self.after(5, self._boot_sequence)

    def _instant_quit(self):
        """Releases X11 window & exits kernel process immediately so Xorg/Firefox never stalls."""
        self._closing = True
        try:
            self.withdraw()
            self.update_idletasks()
        except Exception:
            pass
        os._exit(0)

    def _boot_sequence(self):
        self._load_local()
        self.render_cards()
        threading.Thread(target=self._cloud_sync_loop, daemon=True).start()

    def _on_search_type(self, *_):
        if self._search_timer:
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(180, self.render_cards)

    def _scroll_wheel(self, delta):
        self.cv.yview_scroll(delta, "units")
        self._check_infinite_scroll()

    def _on_scrollbar(self, *args):
        self.cv.yview(*args)
        self._check_infinite_scroll()

    def _on_yscroll(self, first, last):
        self.sb.set(first, last)
        if float(last) > 0.75:
            self._check_infinite_scroll()

    def _check_infinite_scroll(self):
        if self._pending_lessons:
            batch = self._pending_lessons[:3]
            self._pending_lessons = self._pending_lessons[3:]
            is_wide = (self._last_mode == "wide")
            for les in batch:
                self._build_single_card(les, is_wide, self._last_gal_cols)

    def _image_worker_loop(self):
        while not self._closing:
            try:
                lbl, url, size = self._img_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if self._closing:
                break
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
                            l.config(image=ph, text="", width=sz[0], height=sz[1])
                    self.after(0, _paint)
                elif not self._closing:
                    self.after(0, lambda l=lbl: l.config(text="🖼️ Unavailable") if l.winfo_exists() else None)
            except Exception:
                pass
            time.sleep(0.012)

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

        if mode != self._last_mode:
            self._last_mode = mode
            self._reflow_existing_cards(mode == "wide")

        if gal_cols != self._last_gal_cols:
            self._last_gal_cols = gal_cols
            for reg in self._card_registry.values():
                self._regrid_gallery_cells(reg)

        wraps = self._calc_wraps(cw)
        alive = []
        for lbl, kind in self._wrap_labels:
            if lbl.winfo_exists():
                lbl.config(wraplength=wraps.get(kind, 600))
                alive.append((lbl, kind))
        self._wrap_labels = alive

    def _regrid_gallery_cells(self, reg):
        cells = [c for c in (reg.get("gal_cells") or []) if c.winfo_exists()]
        reg["gal_cells"] = cells
        gal_cols = self._last_gal_cols
        for idx_g, cell in enumerate(cells):
            r_i, c_i = divmod(idx_g, gal_cols)
            cell.grid(row=r_i, column=c_i, padx=4, pady=4, sticky="n")

    def _reflow_existing_cards(self, is_wide):
        for reg in self._card_registry.values():
            p_card = reg.get("p_card")
            top_row = reg.get("top_row")
            left_col = reg.get("left_col")
            act_r1 = reg.get("act_r1")
            act_r2 = reg.get("act_r2")
            ask_ent = reg.get("ask_ent")
            ask_btn = reg.get("ask_btn")
            if not top_row or not top_row.winfo_exists():
                continue
            if p_card and p_card.winfo_exists():
                p_card.pack_forget()
                if is_wide:
                    left_col.pack_forget()
                    p_card.pack(in_=top_row, side="right", anchor="n", padx=(12, 0))
                    left_col.pack(in_=top_row, side="left", fill="both", expand=True)
                else:
                    p_card.pack(in_=left_col, anchor="w", pady=(8, 2))
            if act_r1 and act_r2 and ask_ent and ask_btn:
                ask_ent.pack_forget()
                ask_btn.pack_forget()
                act_r2.pack_forget()
                if is_wide:
                    ask_ent.pack(in_=act_r1, side="left", fill="x", expand=True, padx=(0, 6), ipady=3)
                    ask_btn.pack(in_=act_r1, side="right")
                else:
                    act_r2.pack(fill="x", pady=(5, 0))
                    ask_ent.pack(in_=act_r2, side="left", fill="x", expand=True, padx=(0, 6), ipady=3)
                    ask_btn.pack(in_=act_r2, side="right")

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
                    old_lesson_counts = (
                        len(self.data.get("tracks", {}).get("art", {}).get("lessons", [])),
                        len(self.data.get("tracks", {}).get("universe", {}).get("lessons", [])),
                    )
                    self.data = j["curriculum"]
                    self.data.setdefault("favorites", [])
                    if j.get("capacity"):
                        self.capacity = j["capacity"]
                    self._save_local()
                    new_lesson_counts = (
                        len(self.data.get("tracks", {}).get("art", {}).get("lessons", [])),
                        len(self.data.get("tracks", {}).get("universe", {}).get("lessons", [])),
                    )
                    st = j.get("scheduler", {}).get("status", "ONLINE")
                    lc = j.get("scheduler", {}).get("last_check", "--")
                    self.after(0, lambda s=st, l=lc, rr=(old_lesson_counts != new_lesson_counts): self._apply_sync_hdr(s, l, rr))
            except Exception:
                pass
            time.sleep(35)

    def _apply_sync_hdr(self, st, lc, rerender):
        if self._closing:
            return
        self.sched_status = st
        self.sub_lbl.config(text=f"{st}  •  Last Check: {lc}")
        c = self.capacity
        if c:
            ram_part = f"⚡ Render RAM: {c.get('ram_mb', 0)}/{c.get('ram_limit_mb', 512)} MB ({c.get('ram_pct', 0)}%)" if c.get("ram_mb") else "⚡ Cloud: Synced"
            self.cap_pill.config(
                text=f"💾 GitHub Vault: {c.get('json_kb', 0)} KB / {c.get('gh_limit_mb', 75)} MB ({c.get('gh_pct', 0)}%)  •  {ram_part}  •  🛣️ Auto-Drop Runway: ~{c.get('runway_years', 18.9)} yrs"
            )
        self._update_tab_counts()
        if rerender:
            self.render_cards()

    def _manual_sync_drop(self):
        self.sync_btn.config(text="⏳ Dropping...", state="disabled")
        self.sub_lbl.config(text="ONLINE • Triggering Missed/Daily Drop on Render (Art + Universe + Matrix)...")

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
                    errs = (j.get("result") or {}).get("errors") or {}
                    btn_lbl = f"✅ +{len(added)} Dropped!" if added else ("⚠️ Check Warn" if errs else "✅ Up to Date")
                    self.after(0, lambda: (
                        self._apply_sync_hdr(st, lc, bool(added)),
                        self.sync_btn.config(text=btn_lbl, state="normal"),
                        self.after(3500, lambda: self.sync_btn.config(text="⚡ Sync Drop"))
                    ))
                else:
                    self.after(0, lambda: self.sync_btn.config(text="⚠️ Retry", state="normal"))
            except Exception:
                self.after(0, lambda: self.sync_btn.config(text="⚠️ Wake & Retry", state="normal"))
        threading.Thread(target=_worker, daemon=True).start()

    def _toggle_star(self, track, seq, url, caption="", study_note="", source="", star_btn=None):
        if star_btn and star_btn.winfo_exists():
            now_st = (star_btn.cget("text") == "☆")
            star_btn.config(text="★" if now_st else "☆", fg="#fbbf24" if now_st else "#8b949e")

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

    def _delete_plate(self, track, seq, url, cell_widget=None):
        key = (track, int(seq))
        reg = self._card_registry.get(key)

        # 1. Remove ONLY that single cell in 0ms and re-grid remaining cells without touching any other plate (#4)!
        if cell_widget and cell_widget.winfo_exists():
            cell_widget.destroy()
        if reg:
            self._regrid_gallery_cells(reg)
            rem_n = len(reg.get("gal_cells") or [])
            reg["gal_btn"].config(text=f"🖼️ Hide Plates ({rem_n})")

        # Also update local curriculum list immediately
        les = self._get_lesson_obj(track, seq)
        if les and les.get("gallery"):
            les["gallery"] = [g for g in les["gallery"] if g.get("url") != url]

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
            self.btn_art.config(text=f"🎨 ART ENDURANCE ({a_n})")
            self.btn_uni.config(text=f"🌌 PHYSICS OF TIME ({u_n})")
            self.btn_fav.config(text=f"⭐ KEY'S FAVORITES ({f_n})")
        else:
            self.btn_art.config(text=f"🎨 ART ({a_n})")
            self.btn_uni.config(text=f"🌌 PHYSICS ({u_n})")
            self.btn_fav.config(text=f"⭐ FAVS ({f_n})")

    def switch_track(self, t):
        self.cur_track = t
        self.btn_art.config(bg="#fbbf24" if t == "art" else "#21262d", fg="#090d13" if t == "art" else "#c9d1d9")
        self.btn_uni.config(bg="#58a6ff" if t == "universe" else "#21262d", fg="#090d13" if t == "universe" else "#c9d1d9")
        self.btn_fav.config(bg="#fbbf24" if t == "favorites" else "#21262d", fg="#090d13" if t == "favorites" else "#fbbf24")
        self.cv.yview_moveto(0)
        self.render_cards()

    def _jump_to_lesson(self, track, seq):
        self.search_var.set("")
        self.cur_track = track
        self.switch_track(track)

    def _open_lightbox(self, url, caption):
        if not url:
            return
        top = tk.Toplevel(self)
        top.title("Visual Plate Lightbox // Full Resolution")
        top.geometry("900x680")
        top.configure(bg="#090d13")
        lbl_img = tk.Label(top, text="⏳ Loading high-resolution archival plate...", fg="#fbbf24", bg="#090d13", font=("Monospace", 10))
        lbl_img.pack(expand=True, fill="both", padx=14, pady=(14, 6))
        cap_l = tk.Label(top, text=caption, fg="#e6edf3", bg="#090d13", font=("Monospace", 9), pady=8, wraplength=840)
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
            ph = _MEM_TK_CACHE[cache_key]
            lbl.config(image=ph, text="", width=size[0], height=size[1])
            return
        if cache_key in _MEM_PIL_CACHE:
            ph = ImageTk.PhotoImage(_MEM_PIL_CACHE[cache_key])
            _MEM_TK_CACHE[cache_key] = ph
            lbl.config(image=ph, text="", width=size[0], height=size[1])
            return
        self._img_queue.put((lbl, url, size))

    def _call_cloud_action(self, endpoint, payload, btn, wait_txt, done_cb):
        btn.config(text=wait_txt, state="disabled")

        def _worker():
            try:
                u = get_cloud_url() + endpoint
                req = urllib.request.Request(
                    u, data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST"
                )
                j = json.loads(urllib.request.urlopen(req, timeout=65).read().decode())
                if j.get("ok") and j.get("lesson"):
                    arr = self.data["tracks"][payload["track"]]["lessons"]
                    for idx, item in enumerate(arr):
                        if int(item["seq"]) == int(payload["seq"]):
                            arr[idx] = j["lesson"]
                            break
                    if j.get("capacity"):
                        self.capacity = j["capacity"]
                    self._save_local()
                    self.after(0, done_cb)
                else:
                    self.after(0, lambda: btn.config(text="⚠️ Busy - Retry", state="normal"))
            except Exception:
                self.after(0, lambda: btn.config(text="⚠️ Wake & Retry", state="normal"))
        threading.Thread(target=_worker, daemon=True).start()

    def _render_favorites(self, cw):
        favs = self.data.get("favorites") or []
        if not favs:
            empty = tk.Frame(self.inner, bg="#161b22", highlightbackground="#30363d", highlightthickness=1, pady=24, padx=12)
            empty.pack(fill="x", pady=12, padx=4)
            self._make_lbl(empty, "full", text="⭐ Key's Favorites Vault is empty right now.", fg="#f0f6fc", bg="#161b22", font=("Monospace", 10, "bold")).pack(fill="x")
            self._make_lbl(empty, "full", text="Click ☆ on any lead plate or curated gallery plate to pin it permanently to GitHub.", fg="#8b949e", bg="#161b22", font=("Monospace", 9), pady=6).pack(fill="x")
            return

        stack_fav = cw < 660
        for f in favs:
            card = tk.Frame(self.inner, bg="#161b22", highlightbackground="#fbbf24", highlightthickness=1)
            card.pack(fill="x", pady=6, padx=2)
            row = tk.Frame(card, bg="#161b22")
            row.pack(fill="x", padx=12, pady=10)

            p_card = tk.Frame(row, bg="#090d13", highlightbackground="#30363d", highlightthickness=1, cursor="hand2")
            if stack_fav:
                p_card.pack(anchor="w", pady=(0, 8))
            else:
                p_card.pack(side="left", padx=(0, 14), anchor="n")
            il = tk.Label(p_card, text="⏳", fg="#8b949e", bg="#090d13", width=26, height=8, cursor="hand2")
            il.pack()
            il.bind("<Button-1>", lambda e, u=f.get("url", ""), c=f.get("caption", ""): self._open_lightbox(u, c))
            self._load_thumb_async(il, f.get("url", ""), size=(205, 138))

            info = tk.Frame(row, bg="#161b22")
            info.pack(side="left", fill="both", expand=True)
            self._make_lbl(
                info, "fav", text=f"{str(f.get('track','art')).upper()} #{int(f.get('seq',1)):03d}  •  {f.get('source','Archive')}  •  Saved {f.get('saved_at','')}",
                fg="#8b949e", bg="#161b22", font=("Monospace", 8, "bold"), anchor="w", justify="left"
            ).pack(fill="x")

            self._make_lbl(
                info, "fav", text=f.get("caption", "Visual Plate"), fg="#f0f6fc", bg="#161b22",
                font=("Monospace", 10, "bold"), anchor="w", justify="left"
            ).pack(fill="x", pady=(4, 2))

            if f.get("study_note"):
                self._make_lbl(
                    info, "fav", text=f.get("study_note", ""), fg="#fbbf24", bg="#161b22",
                    font=("Monospace", 8), anchor="w", justify="left"
                ).pack(fill="x", pady=(0, 6))

            b_row = tk.Frame(info, bg="#161b22")
            b_row.pack(fill="x", pady=(4, 0))
            tk.Button(
                b_row, text=f"↗ Open {str(f.get('track','art')).upper()} (#{int(f.get('seq',1)):03d})",
                command=lambda tr=f.get("track", "art"), sq=f.get("seq", 1): self._jump_to_lesson(tr, sq),
                bg="#21262d", fg="#fbbf24", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2"
            ).pack(side="left", padx=(0, 8))
            tk.Button(
                b_row, text="★ Unstar",
                command=lambda tr=f.get("track", "art"), sq=f.get("seq", 1), u=f.get("url", ""): self._toggle_star(tr, sq, u),
                bg="#2d2208", fg="#fbbf24", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2"
            ).pack(side="left")

    def render_cards(self):
        cw = self.cv.winfo_width()
        if cw < 120:
            cw = self._last_cw
        self._last_cw = cw
        is_wide = cw >= 880
        gal_cols = max(1, min(5, (cw - 32) // 210))
        self._last_mode = "wide" if is_wide else "narrow"
        self._last_gal_cols = gal_cols

        self._update_tab_counts(cw + 38)
        self._card_registry.clear()
        self._wrap_labels.clear()
        self._pending_lessons.clear()
        for w in self.inner.winfo_children():
            w.destroy()

        if self.cur_track == "favorites":
            self._render_favorites(cw)
            return

        q = self.search_var.get().strip().lower()
        all_lessons = list(reversed(self.data.get("tracks", {}).get(self.cur_track, {}).get("lessons", [])))
        filtered = [
            les for les in all_lessons
            if not q or q in f"#{les.get('seq',0):03d} {les.get('title','')} {les.get('core','')} {' '.join(les.get('tags',[]))}".lower()
        ]

        # Build ONLY top 3 cards initially (#029, #028, #027 Steadman) so startup & scrolling past Steadman is instantaneous!
        initial = filtered[:3]
        self._pending_lessons = filtered[3:]
        for les in initial:
            self._build_single_card(les, is_wide, gal_cols)

    def _toggle_dd_drawer(self, key, force_rebuild=False):
        """Shows/hides Deep Dive in 0ms without destroying existing widgets!"""
        reg = self._card_registry.get(key)
        if not reg:
            return
        track, seq = key
        les = self._get_lesson_obj(track, seq) or {}
        has_dd = bool(les.get("deep_dive") and len(les["deep_dive"]) > 120)
        dd_btn = reg["dd_btn"]
        dd_frame = reg.get("dd_frame")

        if key in self.open_dd and has_dd:
            dd_btn.config(text="📖 Hide Deep Dive", state="normal")
            if force_rebuild and dd_frame and dd_frame.winfo_exists():
                dd_frame.destroy()
                dd_frame = None
            if not dd_frame or not dd_frame.winfo_exists():
                dd_frame = tk.Frame(reg["dd_holder"], bg="#090d13", highlightbackground="#30363d", highlightthickness=1)
                tk.Label(dd_frame, text="📖 DEEP DIVE MONOGRAPH", fg="#58a6ff", bg="#090d13", font=("Monospace", 8, "bold"), anchor="w", padx=10, pady=6).pack(fill="x")
                self._make_lbl(dd_frame, "full", text=les["deep_dive"], fg="#d0d7de", bg="#090d13", font=("Monospace", 9), justify="left", anchor="w", padx=10, pady=6).pack(fill="x")
                reg["dd_frame"] = dd_frame
            dd_frame.pack(fill="x", padx=12, pady=(0, 8))
        else:
            dd_btn.config(text="📖 Read Deep Dive" if has_dd else "📖 Deep Dive", state="normal")
            if dd_frame and dd_frame.winfo_exists():
                dd_frame.pack_forget()

    def _toggle_gal_drawer(self, key, force_rebuild=False):
        """Shows/hides Gallery Strip in 0ms using pack/pack_forget so plates NEVER reload on Hide/Show (#5)!"""
        reg = self._card_registry.get(key)
        if not reg:
            return
        track, seq = key
        les = self._get_lesson_obj(track, seq) or {}
        gal_list = les.get("gallery") or []
        has_gal = len(gal_list) >= 1
        gal_btn = reg["gal_btn"]
        g_strip = reg.get("g_strip")

        if key in self.open_gal and has_gal:
            gal_btn.config(text=f"🖼️ Hide Plates ({len(gal_list)})", state="normal")
            if force_rebuild and g_strip and g_strip.winfo_exists():
                g_strip.destroy()
                g_strip = None
            if not g_strip or not g_strip.winfo_exists():
                g_strip = tk.Frame(reg["gal_holder"], bg="#090d13", highlightbackground="#30363d", highlightthickness=1)
                grid_f = tk.Frame(g_strip, bg="#090d13")
                grid_f.pack(fill="x", padx=8, pady=(8, 4))
                cell_widgets = []
                gal_cols = self._last_gal_cols
                for idx_g, g_item in enumerate(gal_list):
                    r_i, c_i = divmod(idx_g, gal_cols)
                    gu = g_item.get("url", "")
                    gc = f"{g_item.get('caption', '')} — {g_item.get('study_note', '')}".strip(" —")
                    gs = g_item.get("source", "Archive")
                    g_star = self._is_starred(gu)
                    cell = tk.Frame(grid_f, bg="#161b22", highlightbackground="#30363d", highlightthickness=1)
                    cell.grid(row=r_i, column=c_i, padx=4, pady=4, sticky="n")
                    cell_widgets.append(cell)

                    hdr_c = tk.Frame(cell, bg="#161b22")
                    hdr_c.pack(fill="x")
                    tk.Button(
                        hdr_c, text="×", fg="#f85149", bg="#161b22", activebackground="#f85149", activeforeground="#fff",
                        relief="flat", font=("Monospace", 9, "bold"), padx=5, pady=0, cursor="hand2",
                        command=lambda tr=track, sq=seq, u=gu, cw_ref=cell: self._delete_plate(tr, sq, u, cw_ref)
                    ).pack(side="left")
                    tk.Label(hdr_c, text=gs[:16], fg="#58a6ff", bg="#161b22", font=("Monospace", 6)).pack(side="left", padx=2)
                    st_btn = tk.Button(
                        hdr_c, text="★" if g_star else "☆", fg="#fbbf24" if g_star else "#8b949e", bg="#161b22",
                        relief="flat", font=("Monospace", 9, "bold"), padx=5, pady=0, cursor="hand2"
                    )
                    st_btn.config(command=lambda tr=track, sq=seq, u=gu, cp=g_item.get("caption", ""), sn=g_item.get("study_note", ""), sr=gs, b_ref=st_btn: self._toggle_star(tr, sq, u, cp, sn, sr, b_ref))
                    st_btn.pack(side="right")

                    gl = tk.Label(cell, text="⏳", fg="#8b949e", bg="#1c232d", width=23, height=7, cursor="hand2")
                    gl.pack()
                    cl = tk.Label(cell, text=(g_item.get("caption") or "Plate")[:24] + " 🔍", fg="#c9d1d9", bg="#161b22", font=("Monospace", 7), pady=3, cursor="hand2")
                    cl.pack(fill="x")
                    for wg in (gl, cl):
                        wg.bind("<Button-1>", lambda e, u=gu, c=gc: self._open_lightbox(u, c))
                    self._load_thumb_async(gl, gu, size=(190, 126))
                reg["gal_cells"] = cell_widgets

                cur_bar = tk.Frame(g_strip, bg="#090d13")
                cur_bar.pack(fill="x", padx=10, pady=(4, 8))
                c_btn = tk.Button(cur_bar, text="+ Curate 5 Plates", bg="#1f2937", fg="#fbbf24", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2")
                c_ent = tk.Entry(
                    cur_bar, bg="#161b22", fg="#e6edf3", insertbackground="#fbbf24", relief="flat",
                    highlightbackground="#30363d", highlightthickness=1, font=("Monospace", 8), width=16
                )
                c_ent.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=3)
                c_btn.pack(side="right")

                def _on_more_gal(t=track, s=seq, ent=c_ent, b=c_btn, k=key):
                    cq = ent.get().strip()
                    self._call_cloud_action("/api/gallery", {"track": t, "seq": s, "append": True, "query": cq}, b, "⏳ Routing...", lambda: (self.open_gal.add(k), self._toggle_gal_drawer(k, force_rebuild=True)))
                c_btn.config(command=_on_more_gal)
                c_ent.bind("<Return>", lambda e, fn=_on_more_gal: fn())
                reg["g_strip"] = g_strip

            g_strip.pack(fill="x", padx=12, pady=(0, 8))
        else:
            gal_btn.config(text=f"🖼️ Plates ({len(gal_list)})" if has_gal else "🖼️ Curate Plates", state="normal")
            if g_strip and g_strip.winfo_exists():
                g_strip.pack_forget()

    def _rebuild_qa_drawer(self, key):
        reg = self._card_registry.get(key)
        if not reg:
            return
        track, seq = key
        les = self._get_lesson_obj(track, seq) or {}
        qa_holder = reg["qa_holder"]
        for w in qa_holder.winfo_children():
            w.destroy()
        for qa in les.get("qa_log") or []:
            qa_box = tk.Frame(qa_holder, bg="#0c131d", highlightbackground="#6e40c9", highlightthickness=1)
            qa_box.pack(fill="x", padx=12, pady=(0, 6))
            self._make_lbl(
                qa_box, "full", text=f"💬 Q: {qa.get('q','')}   [ {qa.get('model','GEMINI')} • {qa.get('ts','')} ]",
                fg="#d2a8ff", bg="#0c131d", font=("Monospace", 8, "bold"), anchor="w", justify="left", padx=10, pady=4
            ).pack(fill="x")
            self._make_lbl(
                qa_box, "full", text=qa.get("a", ""), fg="#e6edf3", bg="#0c131d",
                font=("Monospace", 9), justify="left", anchor="w", padx=10, pady=6
            ).pack(fill="x")

    def _build_single_card(self, les, is_wide, gal_cols):
        seq = les["seq"]
        key = (self.cur_track, seq)
        card = tk.Frame(self.inner, bg="#161b22", highlightbackground="#30363d", highlightthickness=1)
        card.pack(fill="x", pady=6, padx=2)

        top_row = tk.Frame(card, bg="#161b22")
        top_row.pack(fill="x", padx=12, pady=(10, 4))

        left_col = tk.Frame(top_row, bg="#161b22")

        img_url = les.get("image_url", "")
        p_card = None
        if img_url:
            p_card = tk.Frame(top_row, bg="#090d13", highlightbackground="#30363d", highlightthickness=1, cursor="hand2")
            img_lbl = tk.Label(p_card, text="⏳ Loading Plate...", fg="#8b949e", bg="#1c232d", font=("Monospace", 8), width=29, height=10, cursor="hand2")
            img_lbl.pack()
            starred = self._is_starred(img_url)
            b_bar = tk.Frame(p_card, bg="#161b22")
            b_bar.pack(fill="x")
            cap_txt = (les.get("image_caption") or les.get("title", ""))[:30]
            cap_lbl = tk.Label(b_bar, text=f"📸 {cap_txt} 🔍", fg="#8b949e", bg="#161b22", font=("Monospace", 7, "bold"), padx=5, pady=3, cursor="hand2")
            cap_lbl.pack(side="left")
            lead_st_btn = tk.Button(
                b_bar, text="★" if starred else "☆",
                fg="#fbbf24" if starred else "#8b949e", bg="#161b22", relief="flat", font=("Monospace", 9, "bold"), padx=4, pady=0, cursor="hand2"
            )
            lead_st_btn.config(command=lambda tr=self.cur_track, sq=seq, url_p=img_url, cp=les.get("image_caption") or les.get("title", ""), b_ref=lead_st_btn: self._toggle_star(tr, sq, url_p, cp, "", "Lead Plate", b_ref))
            lead_st_btn.pack(side="right")
            for w_click in (img_lbl, cap_lbl):
                w_click.bind("<Button-1>", lambda e, url_p=img_url, c=les.get("image_caption") or les.get("title", ""): self._open_lightbox(url_p, c))
            self._load_thumb_async(img_lbl, img_url)

        if is_wide and p_card:
            p_card.pack(in_=top_row, side="right", anchor="n", padx=(12, 0))
        left_col.pack(in_=top_row, side="left", fill="both", expand=True)

        tags_str = "  ".join(f"#{t}" for t in (les.get("tags") or []))
        meta_txt = f"#{seq:03d} • {les.get('date','')}   [ {str(les.get('model','ARCHIVE')).upper()} ]   {tags_str}".strip()
        self._make_lbl(left_col, "body", text=meta_txt, fg="#58a6ff", bg="#161b22", font=("Monospace", 8, "bold"), anchor="w", justify="left").pack(fill="x")
        self._make_lbl(left_col, "body", text=les.get("title", ""), fg="#f0f6fc", bg="#161b22", font=("Monospace", 11, "bold"), anchor="w", justify="left").pack(fill="x", pady=(5, 4))
        self._make_lbl(left_col, "body", text=les.get("core", ""), fg="#c9d1d9", bg="#161b22", font=("Monospace", 9), anchor="w", justify="left").pack(fill="x", pady=(0, 6))

        maker_box = tk.Frame(left_col, bg="#0f141b", highlightbackground="#fbbf24", highlightthickness=1)
        maker_box.pack(fill="x", pady=(2, 4))
        self._make_lbl(
            maker_box, "maker", text=f"🧵 Studio Craft Lens: {les.get('maker', '')}",
            fg="#fbbf24", bg="#0f141b", font=("Monospace", 8), anchor="w", justify="left", padx=8, pady=6
        ).pack(fill="x")

        if (not is_wide) and p_card:
            p_card.pack(in_=left_col, anchor="w", pady=(8, 2))

        act_wrap = tk.Frame(card, bg="#161b22")
        act_wrap.pack(fill="x", padx=12, pady=(4, 8))
        act_r1 = tk.Frame(act_wrap, bg="#161b22")
        act_r1.pack(fill="x")
        act_r2 = tk.Frame(act_wrap, bg="#161b22")

        dd_btn = tk.Button(act_r1, text="📖 Deep Dive", bg="#21262d", fg="#58a6ff", activebackground="#30363d", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2")
        dd_btn.pack(side="left", padx=(0, 6))

        gal_btn = tk.Button(act_r1, text="🖼️ Plates", bg="#21262d", fg="#3fb950", activebackground="#30363d", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2")
        gal_btn.pack(side="left", padx=(0, 8))

        ask_btn = tk.Button(act_wrap, text="💬 Ask Gemini", bg="#251736", fg="#d2a8ff", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2")
        ask_ent = tk.Entry(
            act_wrap, bg="#090d13", fg="#e6edf3", insertbackground="#d2a8ff", relief="flat",
            highlightbackground="#30363d", highlightthickness=1, font=("Monospace", 8), width=16
        )
        if is_wide:
            ask_ent.pack(in_=act_r1, side="left", fill="x", expand=True, padx=(0, 6), ipady=3)
            ask_btn.pack(in_=act_r1, side="right")
        else:
            act_r2.pack(fill="x", pady=(5, 0))
            ask_ent.pack(in_=act_r2, side="left", fill="x", expand=True, padx=(0, 6), ipady=3)
            ask_btn.pack(in_=act_r2, side="right")

        # Separate persistent sub-containers so Deep Dive, Gallery, and Q&A toggle independently in 0ms!
        dd_holder = tk.Frame(card, bg="#161b22")
        dd_holder.pack(fill="x")
        gal_holder = tk.Frame(card, bg="#161b22")
        gal_holder.pack(fill="x")
        qa_holder = tk.Frame(card, bg="#161b22")
        qa_holder.pack(fill="x")

        self._card_registry[key] = {
            "p_card": p_card, "top_row": top_row, "left_col": left_col,
            "act_r1": act_r1, "act_r2": act_r2, "ask_ent": ask_ent, "ask_btn": ask_btn,
            "dd_btn": dd_btn, "gal_btn": gal_btn,
            "dd_holder": dd_holder, "gal_holder": gal_holder, "qa_holder": qa_holder,
            "dd_frame": None, "g_strip": None, "gal_cells": []
        }

        def _on_dd(k=key, t=self.cur_track, s=seq, b=dd_btn):
            cur_les = self._get_lesson_obj(t, s) or {}
            ready = bool(cur_les.get("deep_dive") and len(cur_les["deep_dive"]) > 120)
            if ready:
                if k in self.open_dd:
                    self.open_dd.remove(k)
                else:
                    self.open_dd.add(k)
                self._toggle_dd_drawer(k, force_rebuild=False)
            else:
                self._call_cloud_action("/api/deep_dive", {"track": t, "seq": s}, b, "⏳ Writing...", lambda: (self.open_dd.add(k), self._toggle_dd_drawer(k, force_rebuild=True)))
        dd_btn.config(command=_on_dd)

        def _on_gal(k=key, t=self.cur_track, s=seq, b=gal_btn):
            cur_les = self._get_lesson_obj(t, s) or {}
            ready = len(cur_les.get("gallery") or []) >= 1
            if ready:
                if k in self.open_gal:
                    self.open_gal.remove(k)
                else:
                    self.open_gal.add(k)
                self._toggle_gal_drawer(k, force_rebuild=False)
            else:
                self._call_cloud_action("/api/gallery", {"track": t, "seq": s}, b, "⏳ Curating...", lambda: (self.open_gal.add(k), self._toggle_gal_drawer(k, force_rebuild=True)))
        gal_btn.config(command=_on_gal)

        def _on_ask(k=key, t=self.cur_track, s=seq, ent=ask_ent, b=ask_btn):
            q_str = ent.get().strip()
            if not q_str:
                return
            ent.delete(0, "end")
            self._call_cloud_action("/api/ask", {"track": t, "seq": s, "question": q_str}, b, "⏳ Asking...", lambda: (b.config(text="💬 Ask Gemini", state="normal"), self._rebuild_qa_drawer(k)))
        ask_btn.config(command=_on_ask)
        ask_ent.bind("<Return>", lambda e, fn=_on_ask: fn())

        self._toggle_dd_drawer(key, force_rebuild=False)
        self._toggle_gal_drawer(key, force_rebuild=False)
        self._rebuild_qa_drawer(key)


if __name__ == "__main__":
    KnowledgeDesktopHub().mainloop()
