import os, io, json, time, hashlib, threading, webbrowser, urllib.request
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CURRICULUM_FILE = os.path.join(BASE_DIR, "curriculum.json")
CLOUD_URL_FILE = os.path.join(BASE_DIR, "cloud_url.txt")
IMG_CACHE_DIR = os.path.expanduser("~/.cache/knowledge_hub_plates")
os.makedirs(IMG_CACHE_DIR, exist_ok=True)
_UA = "KnowledgeDesktopHub/2.3 (Ubuntu; educational)"


def get_cloud_url():
    if os.path.exists(CLOUD_URL_FILE):
        u = open(CLOUD_URL_FILE).read().strip().rstrip("/")
        if u:
            return u
    return "https://knowledge-center-dsog.onrender.com"


def fetch_cached_pil(url, max_size):
    if not url:
        return None
    h = hashlib.sha256(url.encode()).hexdigest()[:24]
    p = os.path.join(IMG_CACHE_DIR, f"{h}.jpg")
    if not os.path.exists(p):
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        raw = urllib.request.urlopen(req, timeout=14).read()
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.save(p, "JPEG", quality=88)
    else:
        im = Image.open(p).convert("RGB")
    im.thumbnail(max_size, Image.Resampling.LANCZOS)
    return im


class KnowledgeDesktopHub(tk.Tk):
    def __init__(self):
        super().__init__(className="knowledge-hub")
        self.title("Knowledge Command Center // Art Endurance, Physics of Time & Favorites Vault")
        self.geometry("1260x800")
        self.minsize(480, 460)
        self.configure(bg="#0d1117")

        self.cur_track = "art"
        self.data = {"tracks": {"art": {"lessons": []}, "universe": {"lessons": []}}, "favorites": []}
        self.capacity = {}
        self.open_dd = set()
        self.open_gal = set()
        self._photo_refs = []
        self._wrap_targets = []  # (widget, mode) for instant dynamic text wrapping!
        self._last_layout_bucket = None  # ("wide"|"narrow", gal_cols)
        self._resize_job = None
        self.sched_status = "Syncing Render cloud..."

        # Header Frame (100% Dynamic Wrap at any width)
        self.top_hdr = tk.Frame(self, bg="#090d13", pady=8, padx=12)
        self.top_hdr.pack(fill="x")

        self.title_lbl = tk.Label(
            self.top_hdr,
            text="🧠 KNOWLEDGE COMMAND CENTER // VISUAL MONOGRAPH ARCHIVE",
            fg="#fbbf24", bg="#090d13", font=("Monospace", 12, "bold"), justify="center"
        )
        self.title_lbl.pack(fill="x")

        self.sub_lbl = tk.Label(
            self.top_hdr, text=self.sched_status,
            fg="#8b949e", bg="#090d13", font=("Monospace", 8), justify="center"
        )
        self.sub_lbl.pack(fill="x", pady=(3, 4))

        self.cap_pill = tk.Label(
            self.top_hdr,
            text="💾 GitHub Vault: -- KB  •  ⚡ Cloud RAM: --  •  🛣️ Auto-Drop Runway: ~18.9 yrs",
            fg="#3fb950", bg="#111822", font=("Monospace", 8, "bold"),
            padx=10, pady=4, highlightbackground="#238636", highlightthickness=1, justify="center"
        )
        self.cap_pill.pack(pady=(1, 0))

        # Responsive Navigation Container (auto-flows into 2 rows on narrow split-screen!)
        self.nav_outer = tk.Frame(self, bg="#0d1117", pady=6, padx=14)
        self.nav_outer.pack(fill="x")
        self.nav_row1 = tk.Frame(self.nav_outer, bg="#0d1117")
        self.nav_row1.pack(fill="x")
        self.nav_row2 = tk.Frame(self.nav_outer, bg="#0d1117")

        self.btn_art = tk.Button(self.nav_row1, text="🎨 ART (0)", command=lambda: self.switch_track("art"),
                                 bg="#fbbf24", fg="#090d13", relief="flat", font=("Monospace", 8, "bold"), padx=10, pady=4, cursor="hand2")
        self.btn_uni = tk.Button(self.nav_row1, text="🌌 PHYSICS (0)", command=lambda: self.switch_track("universe"),
                                 bg="#21262d", fg="#c9d1d9", relief="flat", font=("Monospace", 8, "bold"), padx=10, pady=4, cursor="hand2")
        self.btn_fav = tk.Button(self.nav_row1, text="⭐ FAVORITES (0)", command=lambda: self.switch_track("favorites"),
                                 bg="#21262d", fg="#fbbf24", relief="flat", font=("Monospace", 8, "bold"), padx=10, pady=4, cursor="hand2")

        self.filter_lbl = tk.Label(self.nav_row1, text="🔍", fg="#8b949e", bg="#0d1117", font=("Monospace", 9))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.render_cards())
        self.filter_ent = tk.Entry(
            self.nav_row1, textvariable=self.search_var, bg="#161b22", fg="#e6edf3",
            insertbackground="#fbbf24", relief="flat", highlightbackground="#30363d",
            highlightthickness=1, font=("Monospace", 9), width=18
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
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.cv.yview)
        self.inner = tk.Frame(self.cv, bg="#0d1117")
        self.inner.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cwin = self.cv.create_window((0, 0), window=self.inner, anchor="nw")
        self.cv.bind("<Configure>", self._on_canvas_configure)
        self.cv.configure(yscrollcommand=sb.set)
        self.cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.bind_all("<Button-4>", lambda e: self.cv.yview_scroll(-1, "units"))
        self.bind_all("<Button-5>", lambda e: self.cv.yview_scroll(1, "units"))
        self.bind("<Configure>", self._on_window_configure)

        self._pack_nav_for_width(1260)
        self._load_local()
        self.render_cards()
        threading.Thread(target=self._cloud_sync_loop, daemon=True).start()

    def _get_win_w(self):
        w = self.winfo_width()
        return w if w > 200 else 1260

    def _pack_nav_for_width(self, w):
        for child in (self.btn_art, self.btn_uni, self.btn_fav, self.filter_lbl, self.filter_ent, self.sync_btn, self.matrix_btn):
            child.pack_forget()
        self.nav_row2.pack_forget()

        if w >= 920:
            self.btn_art.pack(in_=self.nav_row1, side="left", padx=(0, 6))
            self.btn_uni.pack(in_=self.nav_row1, side="left", padx=(0, 6))
            self.btn_fav.pack(in_=self.nav_row1, side="left", padx=(0, 10))
            self.filter_lbl.pack(in_=self.nav_row1, side="left")
            self.filter_ent.config(width=20)
            self.filter_ent.pack(in_=self.nav_row1, side="left", padx=5, ipady=3)
            self.sync_btn.pack(in_=self.nav_row1, side="right", padx=(6, 0))
            self.matrix_btn.pack(in_=self.nav_row1, side="right")
        else:
            # Compact 2-row toolbar so zero buttons or search bars ever clip off-screen!
            self.nav_row2.pack(fill="x", pady=(6, 0))
            self.btn_art.pack(in_=self.nav_row1, side="left", padx=(0, 4))
            self.btn_uni.pack(in_=self.nav_row1, side="left", padx=(0, 4))
            self.btn_fav.pack(in_=self.nav_row1, side="left", padx=(0, 4))
            self.filter_lbl.pack(in_=self.nav_row2, side="left")
            self.filter_ent.config(width=14)
            self.filter_ent.pack(in_=self.nav_row2, side="left", padx=4, ipady=2, fill="x", expand=True)
            self.sync_btn.pack(in_=self.nav_row2, side="right", padx=(4, 0))
            self.matrix_btn.pack(in_=self.nav_row2, side="right")

    def _on_canvas_configure(self, event):
        self.cv.itemconfig(self.cwin, width=event.width)
        self._apply_dynamic_wraps(event.width)

    def _on_window_configure(self, event):
        if event.widget is not self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(90, self._handle_resize)

    def _handle_resize(self):
        w = self._get_win_w()
        hdr_wrap = max(300, w - 36)
        self.title_lbl.config(wraplength=hdr_wrap)
        self.sub_lbl.config(wraplength=hdr_wrap)
        self.cap_pill.config(wraplength=max(280, w - 52))
        self._pack_nav_for_width(w)

        cw = self.cv.winfo_width()
        if cw < 200:
            cw = w - 40
        mode = "wide" if cw >= 780 else "narrow"
        gal_cols = max(1, min(5, (cw - 36) // 215))
        bucket = (mode, gal_cols)
        if self._last_layout_bucket is not None and bucket != self._last_layout_bucket:
            self._last_layout_bucket = bucket
            self.render_cards()
        else:
            self._last_layout_bucket = bucket
            self._apply_dynamic_wraps(cw)

    def _reg_wrap(self, widget, kind):
        self._wrap_targets.append((widget, kind))

    def _apply_dynamic_wraps(self, canvas_w):
        if canvas_w < 200:
            canvas_w = self._get_win_w() - 40
        is_wide = canvas_w >= 780
        # Subtract right-side 265px plate column when side-by-side; use full card width when stacked narrow!
        body_w = max(240, (canvas_w - 315) if is_wide else (canvas_w - 48))
        maker_w = max(220, body_w - 22)
        full_w = max(240, canvas_w - 58)
        fav_w = max(220, (canvas_w - 275) if canvas_w >= 640 else (canvas_w - 54))

        alive = []
        for wdg, kind in self._wrap_targets:
            if not wdg.winfo_exists():
                continue
            alive.append((wdg, kind))
            if kind == "body":
                wdg.config(wraplength=body_w)
            elif kind == "maker":
                wdg.config(wraplength=maker_w)
            elif kind == "full":
                wdg.config(wraplength=full_w)
            elif kind == "fav":
                wdg.config(wraplength=fav_w)
        self._wrap_targets = alive

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

    def _cloud_sync_loop(self):
        while True:
            try:
                u = get_cloud_url() + "/state"
                req = urllib.request.Request(u, headers={"User-Agent": _UA})
                j = json.loads(urllib.request.urlopen(req, timeout=22).read().decode())
                if j.get("curriculum"):
                    old_sig = (
                        len(self.data.get("tracks", {}).get("art", {}).get("lessons", [])),
                        len(self.data.get("tracks", {}).get("universe", {}).get("lessons", [])),
                        len(self.data.get("favorites") or []),
                    )
                    self.data = j["curriculum"]
                    self.data.setdefault("favorites", [])
                    if j.get("capacity"):
                        self.capacity = j["capacity"]
                    self._save_local()
                    new_sig = (
                        len(self.data.get("tracks", {}).get("art", {}).get("lessons", [])),
                        len(self.data.get("tracks", {}).get("universe", {}).get("lessons", [])),
                        len(self.data.get("favorites") or []),
                    )
                    st = j.get("scheduler", {}).get("status", "ONLINE")
                    lc = j.get("scheduler", {}).get("last_check", "--")
                    self.after(0, lambda s=st, l=lc, rr=(old_sig != new_sig): self._apply_sync_hdr(s, l, rr))
            except Exception:
                pass
            time.sleep(35)

    def _apply_sync_hdr(self, st, lc, rerender):
        self.sched_status = st
        self.sub_lbl.config(text=f"{st}  •  Last Check: {lc}")
        c = self.capacity
        if c:
            ram_part = f"⚡ Render RAM: {c.get('ram_mb', 0)}/{c.get('ram_limit_mb', 512)} MB ({c.get('ram_pct', 0)}%)" if c.get("ram_mb") else "⚡ Cloud: Synced"
            self.cap_pill.config(
                text=f"💾 GitHub Vault: {c.get('json_kb', 0)} KB / {c.get('gh_limit_mb', 75)} MB ({c.get('gh_pct', 0)}%)  •  {ram_part}  •  🛣️ Auto-Drop Runway: ~{c.get('runway_years', 18.9)} yrs"
            )
        w = self._get_win_w()
        self.sub_lbl.config(wraplength=max(300, w - 36))
        self.cap_pill.config(wraplength=max(280, w - 52))
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
                        self._apply_sync_hdr(st, lc, True),
                        self.sync_btn.config(text=btn_lbl, state="normal"),
                        self.after(3500, lambda: self.sync_btn.config(text="⚡ Sync Drop"))
                    ))
                else:
                    self.after(0, lambda: self.sync_btn.config(text="⚠️ Retry", state="normal"))
            except Exception:
                self.after(0, lambda: self.sync_btn.config(text="⚠️ Wake & Retry", state="normal"))
        threading.Thread(target=_worker, daemon=True).start()

    def _toggle_star(self, track, seq, url, caption="", study_note="", source=""):
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
                    self.after(0, lambda: (self._apply_sync_hdr(self.sched_status, "Synced", False), self.render_cards()))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _delete_plate(self, track, seq, url):
        def _worker():
            try:
                u = get_cloud_url() + "/api/delete_plate"
                req = urllib.request.Request(u, data=json.dumps({"track": track, "seq": seq, "url": url}).encode(),
                                             headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST")
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
                    self.open_gal.add((track, int(seq)))
                    self.after(0, lambda: (self._apply_sync_hdr(self.sched_status, "Pruned", False), self.render_cards()))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _update_tab_counts(self):
        a_n = len(self.data.get("tracks", {}).get("art", {}).get("lessons", []))
        u_n = len(self.data.get("tracks", {}).get("universe", {}).get("lessons", []))
        f_n = len(self.data.get("favorites") or [])
        w = self._get_win_w()
        if w >= 920:
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
        cap_l = tk.Label(top, text=caption, fg="#e6edf3", bg="#090d13", font=("Monospace", 9), wraplength=840, pady=8)
        cap_l.pack(fill="x", padx=12)
        top.bind("<Configure>", lambda e: cap_l.config(wraplength=max(260, top.winfo_width() - 40)) if e.widget is top else None)

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
        def _worker():
            try:
                im = fetch_cached_pil(url, size)
                if im:
                    def _set():
                        if lbl.winfo_exists():
                            ph = ImageTk.PhotoImage(im)
                            self._photo_refs.append(ph)
                            lbl.config(image=ph, text="", width=size[0], height=size[1])
                    self.after(0, _set)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _call_cloud_action(self, endpoint, payload, btn, wait_txt, done_cb):
        btn.config(text=wait_txt, state="disabled")
        def _worker():
            try:
                u = get_cloud_url() + endpoint
                req = urllib.request.Request(u, data=json.dumps(payload).encode(),
                                             headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST")
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
            l1 = tk.Label(empty, text="⭐ Key's Favorites Vault is empty right now.", fg="#f0f6fc", bg="#161b22", font=("Monospace", 10, "bold"))
            l1.pack(fill="x")
            l2 = tk.Label(empty, text="Click ☆ on any lead plate or curated gallery plate to pin it permanently to GitHub.", fg="#8b949e", bg="#161b22", font=("Monospace", 9), pady=6)
            l2.pack(fill="x")
            self._reg_wrap(l1, "full")
            self._reg_wrap(l2, "full")
            return

        stack_fav = cw < 640
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
            il.bind("<Button-1>", lambda e, u=f.get("url",""), c=f.get("caption",""): self._open_lightbox(u, c))
            self._load_thumb_async(il, f.get("url", ""), size=(205, 138))

            info = tk.Frame(row, bg="#161b22")
            info.pack(side="left", fill="both", expand=True)
            m_l = tk.Label(info, text=f"{str(f.get('track','art')).upper()} #{int(f.get('seq',1)):03d}  •  {f.get('source','Archive')}  •  Saved {f.get('saved_at','')}",
                           fg="#8b949e", bg="#161b22", font=("Monospace", 8, "bold"), anchor="w", justify="left")
            m_l.pack(fill="x")
            self._reg_wrap(m_l, "fav")

            c_l = tk.Label(info, text=f.get("caption", "Visual Plate"), fg="#f0f6fc", bg="#161b22", font=("Monospace", 10, "bold"), anchor="w", justify="left")
            c_l.pack(fill="x", pady=(4, 2))
            self._reg_wrap(c_l, "fav")

            if f.get("study_note"):
                s_l = tk.Label(info, text=f.get("study_note", ""), fg="#fbbf24", bg="#161b22", font=("Monospace", 8), anchor="w", justify="left")
                s_l.pack(fill="x", pady=(0, 6))
                self._reg_wrap(s_l, "fav")

            b_row = tk.Frame(info, bg="#161b22")
            b_row.pack(fill="x", pady=(4, 0))
            tk.Button(b_row, text=f"↗ Open {str(f.get('track','art')).upper()} (#{int(f.get('seq',1)):03d})",
                      command=lambda tr=f.get("track","art"), sq=f.get("seq",1): self._jump_to_lesson(tr, sq),
                      bg="#21262d", fg="#fbbf24", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2").pack(side="left", padx=(0, 8))
            tk.Button(b_row, text="★ Unstar",
                      command=lambda tr=f.get("track","art"), sq=f.get("seq",1), u=f.get("url",""): self._toggle_star(tr, sq, u),
                      bg="#2d2208", fg="#fbbf24", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2").pack(side="left")

    def render_cards(self):
        self._update_tab_counts()
        self._photo_refs.clear()
        self._wrap_targets.clear()
        for w in self.inner.winfo_children():
            w.destroy()

        cw = self.cv.winfo_width()
        if cw < 200:
            cw = self._get_win_w() - 40
        is_wide = cw >= 780
        gal_cols = max(1, min(5, (cw - 36) // 215))
        self._last_layout_bucket = ("wide" if is_wide else "narrow", gal_cols)

        if self.cur_track == "favorites":
            self._render_favorites(cw)
            self._apply_dynamic_wraps(cw)
            return

        q = self.search_var.get().strip().lower()
        lessons = list(reversed(self.data.get("tracks", {}).get(self.cur_track, {}).get("lessons", [])))
        for les in lessons:
            blob = f"#{les.get('seq',0):03d} {les.get('title','')} {les.get('core','')} {' '.join(les.get('tags',[]))}".lower()
            if q and q not in blob:
                continue

            seq = les["seq"]
            key = (self.cur_track, seq)
            card = tk.Frame(self.inner, bg="#161b22", highlightbackground="#30363d", highlightthickness=1)
            card.pack(fill="x", pady=6, padx=2)

            top_row = tk.Frame(card, bg="#161b22")
            top_row.pack(fill="x", padx=12, pady=(10, 4))

            # Build Visual Plate helper so we can place side-by-side (wide) or cleanly stacked below text (narrow)!
            img_url = les.get("image_url", "")
            def _mount_plate(parent, side_mode):
                if not img_url:
                    return
                p_card = tk.Frame(parent, bg="#090d13", highlightbackground="#30363d", highlightthickness=1, cursor="hand2")
                if side_mode:
                    p_card.pack(side="right", anchor="n", padx=(10, 0))
                else:
                    p_card.pack(anchor="w", pady=(6, 2))
                img_lbl = tk.Label(p_card, text="⏳ Loading Plate...", fg="#8b949e", bg="#090d13", font=("Monospace", 8), width=29, height=10, cursor="hand2")
                img_lbl.pack()
                starred = self._is_starred(img_url)
                b_bar = tk.Frame(p_card, bg="#161b22")
                b_bar.pack(fill="x")
                cap_txt = (les.get("image_caption") or les.get("title", ""))[:32]
                cap_lbl = tk.Label(b_bar, text=f"📸 {cap_txt} 🔍", fg="#8b949e", bg="#161b22", font=("Monospace", 7, "bold"), padx=5, pady=3, cursor="hand2")
                cap_lbl.pack(side="left")
                tk.Button(
                    b_bar, text="★" if starred else "☆",
                    fg="#fbbf24" if starred else "#8b949e", bg="#161b22", relief="flat", font=("Monospace", 9, "bold"), padx=4, pady=0, cursor="hand2",
                    command=lambda tr=self.cur_track, sq=seq, u=img_url, cp=les.get("image_caption") or les.get("title",""): self._toggle_star(tr, sq, u, cp, "", "Lead Plate")
                ).pack(side="right")
                for w_click in (img_lbl, cap_lbl):
                    w_click.bind("<Button-1>", lambda e, u=img_url, c=les.get("image_caption") or les.get("title", ""): self._open_lightbox(u, c))
                self._load_thumb_async(img_lbl, img_url)

            if is_wide:
                _mount_plate(top_row, True)

            left_col = tk.Frame(top_row, bg="#161b22")
            left_col.pack(side="left", fill="both", expand=True)

            # Wrapping metadata + tags line so tags never push off-screen
            tags_str = "  ".join(f"#{t}" for t in (les.get("tags") or []))
            meta_txt = f"#{seq:03d} • {les.get('date','')}   [ {str(les.get('model','ARCHIVE')).upper()} ]   {tags_str}".strip()
            meta_lbl = tk.Label(left_col, text=meta_txt, fg="#58a6ff", bg="#161b22", font=("Monospace", 8, "bold"), anchor="w", justify="left")
            meta_lbl.pack(fill="x")
            self._reg_wrap(meta_lbl, "body")

            t_lbl = tk.Label(left_col, text=les.get("title", ""), fg="#f0f6fc", bg="#161b22", font=("Monospace", 11, "bold"), anchor="w", justify="left")
            t_lbl.pack(fill="x", pady=(5, 4))
            self._reg_wrap(t_lbl, "body")

            c_lbl = tk.Label(left_col, text=les.get("core", ""), fg="#c9d1d9", bg="#161b22", font=("Monospace", 9), anchor="w", justify="left")
            c_lbl.pack(fill="x", pady=(0, 6))
            self._reg_wrap(c_lbl, "body")

            maker_box = tk.Frame(left_col, bg="#0f141b", highlightbackground="#fbbf24", highlightthickness=1)
            maker_box.pack(fill="x", pady=(2, 4))
            m_lbl = tk.Label(maker_box, text=f"🧵 Studio Craft Lens: {les.get('maker', '')}", fg="#fbbf24", bg="#0f141b", font=("Monospace", 8), anchor="w", justify="left", padx=8, pady=6)
            m_lbl.pack(fill="x")
            self._reg_wrap(m_lbl, "maker")

            if not is_wide:
                _mount_plate(left_col, False)

            # Responsive Action Bar (splits onto 2 lines automatically when narrow!)
            act_wrap = tk.Frame(card, bg="#161b22")
            act_wrap.pack(fill="x", padx=12, pady=(2, 8))
            act_r1 = tk.Frame(act_wrap, bg="#161b22")
            act_r1.pack(fill="x")
            act_r2 = act_r1 if is_wide else tk.Frame(act_wrap, bg="#161b22")
            if not is_wide:
                act_r2.pack(fill="x", pady=(5, 0))

            has_dd = bool(les.get("deep_dive") and len(les["deep_dive"]) > 120)
            dd_txt = ("📖 Hide Deep Dive" if key in self.open_dd else "📖 Read Deep Dive") if has_dd else "📖 Deep Dive"
            dd_btn = tk.Button(act_r1, text=dd_txt, bg="#21262d", fg="#58a6ff", activebackground="#30363d", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2")
            dd_btn.pack(side="left", padx=(0, 6))

            def _on_dd(k=key, t=self.cur_track, s=seq, b=dd_btn, ready=has_dd):
                if ready:
                    if k in self.open_dd: self.open_dd.remove(k)
                    else: self.open_dd.add(k)
                    self.render_cards()
                else:
                    self._call_cloud_action("/api/deep_dive", {"track": t, "seq": s}, b, "⏳ Writing...", lambda: (self.open_dd.add(k), self.render_cards()))
            dd_btn.config(command=_on_dd)

            gal_list = les.get("gallery") or []
            has_gal = len(gal_list) >= 1
            gal_txt = (f"🖼️ Hide Plates ({len(gal_list)})" if key in self.open_gal else f"🖼️ Plates ({len(gal_list)})") if has_gal else "🖼️ Curate Plates"
            gal_btn = tk.Button(act_r1, text=gal_txt, bg="#21262d", fg="#3fb950", activebackground="#30363d", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2")
            gal_btn.pack(side="left", padx=(0, 8))

            def _on_gal(k=key, t=self.cur_track, s=seq, b=gal_btn, ready=has_gal):
                if ready:
                    if k in self.open_gal: self.open_gal.remove(k)
                    else: self.open_gal.add(k)
                    self.render_cards()
                else:
                    self._call_cloud_action("/api/gallery", {"track": t, "seq": s}, b, "⏳ Curating...", lambda: (self.open_gal.add(k), self.render_cards()))
            gal_btn.config(command=_on_gal)

            ask_btn = tk.Button(act_r2, text="💬 Ask Gemini", bg="#251736", fg="#d2a8ff", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2")
            ask_ent = tk.Entry(act_r2, bg="#090d13", fg="#e6edf3", insertbackground="#d2a8ff", relief="flat",
                               highlightbackground="#30363d", highlightthickness=1, font=("Monospace", 8), width=18)
            ask_ent.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=3)
            ask_btn.pack(side="right")

            def _on_ask(t=self.cur_track, s=seq, ent=ask_ent, b=ask_btn):
                q_str = ent.get().strip()
                if not q_str:
                    return
                self._call_cloud_action("/api/ask", {"track": t, "seq": s, "question": q_str}, b, "⏳ Asking...", self.render_cards)
            ask_btn.config(command=_on_ask)
            ask_ent.bind("<Return>", lambda e, fn=_on_ask: fn())

            if key in self.open_dd and les.get("deep_dive"):
                dd_frame = tk.Frame(card, bg="#090d13", highlightbackground="#30363d", highlightthickness=1)
                dd_frame.pack(fill="x", padx=12, pady=(0, 8))
                tk.Label(dd_frame, text="📖 DEEP DIVE MONOGRAPH", fg="#58a6ff", bg="#090d13", font=("Monospace", 8, "bold"), anchor="w", padx=10, pady=6).pack(fill="x")
                dd_body = tk.Label(dd_frame, text=les["deep_dive"], fg="#d0d7de", bg="#090d13", font=("Monospace", 9), justify="left", anchor="w", padx=10, pady=6)
                dd_body.pack(fill="x")
                self._reg_wrap(dd_body, "full")

            if key in self.open_gal:
                g_strip = tk.Frame(card, bg="#090d13", highlightbackground="#30363d", highlightthickness=1)
                g_strip.pack(fill="x", padx=12, pady=(0, 8))

                grid_f = tk.Frame(g_strip, bg="#090d13")
                grid_f.pack(fill="x", padx=8, pady=(8, 4))
                for idx_g, g_item in enumerate(gal_list):
                    r_i, c_i = divmod(idx_g, gal_cols)
                    gu = g_item.get("url", "")
                    gc = f"{g_item.get('caption', '')} — {g_item.get('study_note', '')}".strip(" —")
                    gs = g_item.get("source", "Archive")
                    g_star = self._is_starred(gu)
                    cell = tk.Frame(grid_f, bg="#161b22", highlightbackground="#30363d", highlightthickness=1)
                    cell.grid(row=r_i, column=c_i, padx=4, pady=4, sticky="n")

                    hdr_c = tk.Frame(cell, bg="#161b22")
                    hdr_c.pack(fill="x")
                    tk.Button(hdr_c, text="×", fg="#f85149", bg="#161b22", activebackground="#f85149", activeforeground="#fff",
                              relief="flat", font=("Monospace", 9, "bold"), padx=5, pady=0, cursor="hand2",
                              command=lambda tr=self.cur_track, sq=seq, u=gu: self._delete_plate(tr, sq, u)).pack(side="left")
                    tk.Label(hdr_c, text=gs[:16], fg="#58a6ff", bg="#161b22", font=("Monospace", 6)).pack(side="left", padx=2)
                    tk.Button(hdr_c, text="★" if g_star else "☆", fg="#fbbf24" if g_star else "#8b949e", bg="#161b22",
                              relief="flat", font=("Monospace", 9, "bold"), padx=5, pady=0, cursor="hand2",
                              command=lambda tr=self.cur_track, sq=seq, u=gu, cp=g_item.get("caption",""), sn=g_item.get("study_note",""), sr=gs: self._toggle_star(tr, sq, u, cp, sn, sr)).pack(side="right")

                    gl = tk.Label(cell, text="⏳", fg="#8b949e", bg="#090d13", width=23, height=7, cursor="hand2")
                    gl.pack()
                    cl = tk.Label(cell, text=(g_item.get("caption") or "Plate")[:24] + " 🔍", fg="#c9d1d9", bg="#161b22", font=("Monospace", 7), pady=3, cursor="hand2")
                    cl.pack(fill="x")
                    for wg in (gl, cl):
                        wg.bind("<Button-1>", lambda e, u=gu, c=gc: self._open_lightbox(u, c))
                    self._load_thumb_async(gl, gu, size=(190, 126))

                cur_bar = tk.Frame(g_strip, bg="#090d13")
                cur_bar.pack(fill="x", padx=10, pady=(4, 8))
                c_btn = tk.Button(cur_bar, text="+ Curate 5 Plates", bg="#1f2937", fg="#fbbf24", relief="flat", font=("Monospace", 8, "bold"), padx=9, pady=4, cursor="hand2")
                c_ent = tk.Entry(cur_bar, bg="#161b22", fg="#e6edf3", insertbackground="#fbbf24", relief="flat",
                                 highlightbackground="#30363d", highlightthickness=1, font=("Monospace", 8), width=18)
                c_ent.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=3)
                c_btn.pack(side="right")

                def _on_more_gal(t=self.cur_track, s=seq, ent=c_ent, b=c_btn, k=key):
                    cq = ent.get().strip()
                    self._call_cloud_action("/api/gallery", {"track": t, "seq": s, "append": True, "query": cq}, b, "⏳ Routing...", lambda: (self.open_gal.add(k), self.render_cards()))
                c_btn.config(command=_on_more_gal)
                c_ent.bind("<Return>", lambda e, fn=_on_more_gal: fn())

            for qa in les.get("qa_log") or []:
                qa_box = tk.Frame(card, bg="#0c131d", highlightbackground="#6e40c9", highlightthickness=1)
                qa_box.pack(fill="x", padx=12, pady=(0, 6))
                q_hdr = tk.Label(qa_box, text=f"💬 Q: {qa.get('q','')}   [ {qa.get('model','GEMINI')} • {qa.get('ts','')} ]",
                                 fg="#d2a8ff", bg="#0c131d", font=("Monospace", 8, "bold"), anchor="w", justify="left", padx=10, pady=4)
                q_hdr.pack(fill="x")
                q_ans = tk.Label(qa_box, text=qa.get("a", ""), fg="#e6edf3", bg="#0c131d", font=("Monospace", 9), justify="left", anchor="w", padx=10, pady=6)
                q_ans.pack(fill="x")
                self._reg_wrap(q_hdr, "full")
                self._reg_wrap(q_ans, "full")

        self._apply_dynamic_wraps(cw)


if __name__ == "__main__":
    KnowledgeDesktopHub().mainloop()
