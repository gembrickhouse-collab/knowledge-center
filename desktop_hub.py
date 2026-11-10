import os, io, json, hashlib, threading, urllib.request
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CURRICULUM_FILE = os.path.join(BASE_DIR, "curriculum.json")
CLOUD_URL_FILE = os.path.join(BASE_DIR, "cloud_url.txt")
IMG_CACHE_DIR = os.path.expanduser("~/.cache/knowledge_hub_plates")
os.makedirs(IMG_CACHE_DIR, exist_ok=True)
_UA = "KnowledgeDesktopHub/2.0 (Ubuntu; educational)"


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
        self.title("Knowledge Command Center // Art Endurance & Physics of Time")
        self.geometry("1260x780")
        self.configure(bg="#0d1117")
        self.cur_track = "art"
        self.data = {"tracks": {"art": {"lessons": []}, "universe": {"lessons": []}}}
        self.open_dd = set()
        self.open_gal = set()
        self._photo_refs = []
        self.sched_status = "Syncing Render cloud..."

        top = tk.Frame(self, bg="#090d13", pady=10)
        top.pack(fill="x")
        tk.Label(top, text="🧠 KNOWLEDGE COMMAND CENTER // VISUAL MONOGRAPH ARCHIVE",
                 fg="#fbbf24", bg="#090d13", font=("Monospace", 13, "bold")).pack()
        self.sub_lbl = tk.Label(top, text=self.sched_status, fg="#8b949e", bg="#090d13", font=("Monospace", 9))
        self.sub_lbl.pack(pady=(3, 0))

        nav = tk.Frame(self, bg="#0d1117", pady=8)
        nav.pack(fill="x", padx=16)
        self.btn_art = tk.Button(nav, text="🎨 ART ENDURANCE", command=lambda: self.switch_track("art"),
                                 bg="#fbbf24", fg="#090d13", relief="flat", font=("Monospace", 9, "bold"), padx=14, pady=5, cursor="hand2")
        self.btn_art.pack(side="left", padx=(0, 8))
        self.btn_uni = tk.Button(nav, text="🌌 PHYSICS OF TIME", command=lambda: self.switch_track("universe"),
                                 bg="#21262d", fg="#c9d1d9", relief="flat", font=("Monospace", 9, "bold"), padx=14, pady=5, cursor="hand2")
        self.btn_uni.pack(side="left", padx=(0, 12))

        tk.Label(nav, text="🔍 Filter:", fg="#8b949e", bg="#0d1117", font=("Monospace", 9)).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.render_cards())
        tk.Entry(nav, textvariable=self.search_var, bg="#161b22", fg="#e6edf3", insertbackground="#fbbf24",
                 relief="flat", highlightbackground="#30363d", highlightthickness=1, font=("Monospace", 9), width=28).pack(side="left", padx=6, ipady=3)

        wrap = tk.Frame(self, bg="#0d1117")
        wrap.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        self.cv = tk.Canvas(wrap, bg="#0d1117", highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.cv.yview)
        self.inner = tk.Frame(self.cv, bg="#0d1117")
        self.inner.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cwin = self.cv.create_window((0, 0), window=self.inner, anchor="nw")
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfig(self.cwin, width=e.width))
        self.cv.configure(yscrollcommand=sb.set)
        self.cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.bind_all("<Button-4>", lambda e: self.cv.yview_scroll(-1, "units"))
        self.bind_all("<Button-5>", lambda e: self.cv.yview_scroll(1, "units"))

        self._load_local()
        self.render_cards()
        threading.Thread(target=self._cloud_sync_loop, daemon=True).start()

    def _load_local(self):
        if os.path.exists(CURRICULUM_FILE):
            try:
                self.data = json.load(open(CURRICULUM_FILE))
            except Exception:
                pass

    def _save_local(self):
        try:
            with open(CURRICULUM_FILE, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def _cloud_sync_loop(self):
        while True:
            try:
                u = get_cloud_url() + "/state"
                req = urllib.request.Request(u, headers={"User-Agent": _UA})
                j = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
                if j.get("curriculum"):
                    old_counts = (
                        len(self.data.get("tracks", {}).get("art", {}).get("lessons", [])),
                        len(self.data.get("tracks", {}).get("universe", {}).get("lessons", [])),
                    )
                    self.data = j["curriculum"]
                    self._save_local()
                    new_counts = (
                        len(self.data.get("tracks", {}).get("art", {}).get("lessons", [])),
                        len(self.data.get("tracks", {}).get("universe", {}).get("lessons", [])),
                    )
                    st = j.get("scheduler", {}).get("status", "ONLINE")
                    lc = j.get("scheduler", {}).get("last_check", "--")
                    self.after(0, lambda s=st, l=lc, rerender=(old_counts != new_counts): self._apply_sync_hdr(s, l, rerender))
            except Exception:
                pass
            import time
            time.sleep(35)

    def _apply_sync_hdr(self, st, lc, rerender):
        self.sub_lbl.config(text=f"{st}   |   Last Check: {lc}")
        self._update_tab_counts()
        if rerender:
            self.render_cards()

    def _update_tab_counts(self):
        a_n = len(self.data.get("tracks", {}).get("art", {}).get("lessons", []))
        u_n = len(self.data.get("tracks", {}).get("universe", {}).get("lessons", []))
        self.btn_art.config(text=f"🎨 ART ENDURANCE ({a_n})")
        self.btn_uni.config(text=f"🌌 PHYSICS OF TIME ({u_n})")

    def switch_track(self, t):
        self.cur_track = t
        if t == "art":
            self.btn_art.config(bg="#fbbf24", fg="#090d13")
            self.btn_uni.config(bg="#21262d", fg="#c9d1d9")
        else:
            self.btn_uni.config(bg="#58a6ff", fg="#090d13")
            self.btn_art.config(bg="#21262d", fg="#c9d1d9")
        self.cv.yview_moveto(0)
        self.render_cards()

    def _open_lightbox(self, url, caption):
        if not url:
            return
        top = tk.Toplevel(self)
        top.title("Visual Plate Lightbox // Full Resolution")
        top.geometry("900x680")
        top.configure(bg="#090d13")
        lbl_img = tk.Label(top, text="⏳ Loading high-resolution archival plate...", fg="#fbbf24", bg="#090d13", font=("Monospace", 10))
        lbl_img.pack(expand=True, fill="both", padx=14, pady=(14, 6))
        tk.Label(top, text=caption, fg="#e6edf3", bg="#090d13", font=("Monospace", 9), wraplength=840, pady=8).pack()

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

    def _load_thumb_async(self, lbl, url, size=(245, 175)):
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
                j = json.loads(urllib.request.urlopen(req, timeout=55).read().decode())
                if j.get("ok") and j.get("lesson"):
                    arr = self.data["tracks"][payload["track"]]["lessons"]
                    for idx, item in enumerate(arr):
                        if int(item["seq"]) == int(payload["seq"]):
                            arr[idx] = j["lesson"]
                            break
                    self._save_local()
                    self.after(0, done_cb)
                else:
                    self.after(0, lambda: btn.config(text="⚠️ Cloud Busy - Retry", state="normal"))
            except Exception as e:
                self.after(0, lambda: btn.config(text=f"⚠️ Wake Render & Retry", state="normal"))
        threading.Thread(target=_worker, daemon=True).start()

    def render_cards(self):
        self._update_tab_counts()
        self._photo_refs.clear()
        for w in self.inner.winfo_children():
            w.destroy()

        q = self.search_var.get().strip().lower()
        lessons = list(reversed(self.data.get("tracks", {}).get(self.cur_track, {}).get("lessons", [])))
        for les in lessons:
            blob = f"{les.get('title','')} {les.get('core','')} {' '.join(les.get('tags',[]))}".lower()
            if q and q not in blob:
                continue

            seq = les["seq"]
            key = (self.cur_track, seq)
            card = tk.Frame(self.inner, bg="#161b22", highlightbackground="#30363d", highlightthickness=1)
            card.pack(fill="x", pady=6, padx=2)

            top_row = tk.Frame(card, bg="#161b22")
            top_row.pack(fill="x", padx=12, pady=(10, 4))

            left_col = tk.Frame(top_row, bg="#161b22")
            left_col.pack(side="left", fill="both", expand=True, padx=(0, 12))

            meta = tk.Frame(left_col, bg="#161b22")
            meta.pack(fill="x", anchor="w")
            tk.Label(meta, text=f"#{seq:03d}  •  {les.get('date','')}", fg="#8b949e", bg="#161b22", font=("Monospace", 8, "bold")).pack(side="left")
            tk.Label(meta, text=f" [ {str(les.get('model','ARCHIVE')).upper()} ] ", fg="#fbbf24", bg="#2d2208", font=("Monospace", 8, "bold")).pack(side="left", padx=8)
            if les.get("tags"):
                tk.Label(meta, text="  ".join(f"#{t}" for t in les["tags"]), fg="#58a6ff", bg="#161b22", font=("Monospace", 8)).pack(side="left")

            tk.Label(left_col, text=les.get("title", ""), fg="#f0f6fc", bg="#161b22", font=("Monospace", 11, "bold"), anchor="w", justify="left", wraplength=820).pack(fill="x", pady=(5, 4))
            tk.Label(left_col, text=les.get("core", ""), fg="#c9d1d9", bg="#161b22", font=("Monospace", 9), anchor="w", justify="left", wraplength=820).pack(fill="x", pady=(0, 6))

            maker_box = tk.Frame(left_col, bg="#0f141b", highlightbackground="#fbbf24", highlightthickness=1)
            maker_box.pack(fill="x", pady=(2, 4))
            tk.Label(maker_box, text=f"🧵 Studio Craft Lens: {les.get('maker', '')}", fg="#fbbf24", bg="#0f141b", font=("Monospace", 8), anchor="w", justify="left", wraplength=800, padx=8, pady=6).pack(fill="x")

            # Right-Side Primary Visual Plate
            img_url = les.get("image_url", "")
            if img_url:
                p_card = tk.Frame(top_row, bg="#090d13", highlightbackground="#30363d", highlightthickness=1, cursor="hand2")
                p_card.pack(side="right", anchor="n")
                img_lbl = tk.Label(p_card, text="⏳ Loading Plate...", fg="#8b949e", bg="#090d13", font=("Monospace", 8), width=30, height=10, cursor="hand2")
                img_lbl.pack()
                cap_txt = (les.get("image_caption") or les.get("title", ""))[:42]
                cap_lbl = tk.Label(p_card, text=f"📸 {cap_txt} • 🔍 Zoom", fg="#8b949e", bg="#161b22", font=("Monospace", 7, "bold"), padx=6, pady=3, cursor="hand2")
                cap_lbl.pack(fill="x")
                for w_click in (p_card, img_lbl, cap_lbl):
                    w_click.bind("<Button-1>", lambda e, u=img_url, c=les.get("image_caption") or les.get("title", ""): self._open_lightbox(u, c))
                self._load_thumb_async(img_lbl, img_url)

            # Interactive Action Bar (Deep Dive + Curated Multi-Plates + Ask Gemini)
            act_bar = tk.Frame(card, bg="#161b22")
            act_bar.pack(fill="x", padx=12, pady=(2, 8))

            has_dd = bool(les.get("deep_dive") and len(les["deep_dive"]) > 120)
            dd_txt = ("📖 Hide Deep Dive" if key in self.open_dd else "📖 Read Deep Dive") if has_dd else "📖 Generate Deep Dive (Gemini)"
            dd_btn = tk.Button(act_bar, text=dd_txt, bg="#21262d", fg="#58a6ff", activebackground="#30363d", relief="flat", font=("Monospace", 8, "bold"), padx=10, pady=4, cursor="hand2")
            dd_btn.pack(side="left", padx=(0, 8))

            def _on_dd(k=key, t=self.cur_track, s=seq, b=dd_btn, ready=has_dd):
                if ready:
                    if k in self.open_dd: self.open_dd.remove(k)
                    else: self.open_dd.add(k)
                    self.render_cards()
                else:
                    self._call_cloud_action("/api/deep_dive", {"track": t, "seq": s}, b, "⏳ Gemini Writing Monograph...", lambda: (self.open_dd.add(k), self.render_cards()))
            dd_btn.config(command=_on_dd)

            gal_list = les.get("gallery") or []
            has_gal = len(gal_list) >= 3
            gal_txt = (f"🖼️ Hide Plates ({len(gal_list)})" if key in self.open_gal else f"🖼️ More Plates ({len(gal_list)})") if has_gal else "🖼️ Curate 5 Extra Plates"
            gal_btn = tk.Button(act_bar, text=gal_txt, bg="#21262d", fg="#3fb950", activebackground="#30363d", relief="flat", font=("Monospace", 8, "bold"), padx=10, pady=4, cursor="hand2")
            gal_btn.pack(side="left", padx=(0, 12))

            def _on_gal(k=key, t=self.cur_track, s=seq, b=gal_btn, ready=has_gal):
                if ready:
                    if k in self.open_gal: self.open_gal.remove(k)
                    else: self.open_gal.add(k)
                    self.render_cards()
                else:
                    self._call_cloud_action("/api/gallery", {"track": t, "seq": s}, b, "⏳ Fetching Archival Plates...", lambda: (self.open_gal.add(k), self.render_cards()))
            gal_btn.config(command=_on_gal)

            # On-Demand Ask Gemini Bar
            ask_ent = tk.Entry(act_bar, bg="#090d13", fg="#e6edf3", insertbackground="#d2a8ff", relief="flat",
                               highlightbackground="#30363d", highlightthickness=1, font=("Monospace", 8), width=42)
            ask_ent.pack(side="left", padx=(4, 6), ipady=3)
            ask_btn = tk.Button(act_bar, text="💬 Ask Gemini", bg="#251736", fg="#d2a8ff", relief="flat", font=("Monospace", 8, "bold"), padx=10, pady=4, cursor="hand2")
            ask_btn.pack(side="left")

            def _on_ask(t=self.cur_track, s=seq, ent=ask_ent, b=ask_btn):
                q_str = ent.get().strip()
                if not q_str:
                    return
                self._call_cloud_action("/api/ask", {"track": t, "seq": s, "question": q_str}, b, "⏳ Asking Gemini...", self.render_cards)
            ask_btn.config(command=_on_ask)
            ask_ent.bind("<Return>", lambda e, fn=_on_ask: fn())

            # Expanded Deep Dive Drawer
            if key in self.open_dd and les.get("deep_dive"):
                dd_frame = tk.Frame(card, bg="#090d13", highlightbackground="#30363d", highlightthickness=1)
                dd_frame.pack(fill="x", padx=12, pady=(0, 8))
                tk.Label(dd_frame, text="📖 DEEP DIVE MONOGRAPH", fg="#58a6ff", bg="#090d13", font=("Monospace", 8, "bold"), anchor="w", padx=10, pady=6).pack(fill="x")
                tk.Label(dd_frame, text=les["deep_dive"], fg="#d0d7de", bg="#090d13", font=("Monospace", 9), justify="left", anchor="w", wraplength=1120, padx=10, pady=6).pack(fill="x")

            # Expanded Multi-Plate Strip
            if key in self.open_gal and gal_list:
                g_strip = tk.Frame(card, bg="#090d13", highlightbackground="#30363d", highlightthickness=1)
                g_strip.pack(fill="x", padx=12, pady=(0, 8))
                row_g = tk.Frame(g_strip, bg="#090d13")
                row_g.pack(fill="x", padx=8, pady=8)
                for g_item in gal_list[:5]:
                    gu = g_item.get("url", "")
                    gc = f"{g_item.get('caption', '')} — {g_item.get('study_note', '')}".strip(" —")
                    cell = tk.Frame(row_g, bg="#161b22", highlightbackground="#30363d", highlightthickness=1, cursor="hand2")
                    cell.pack(side="left", padx=5, anchor="n")
                    gl = tk.Label(cell, text="⏳", fg="#8b949e", bg="#090d13", width=22, height=7, cursor="hand2")
                    gl.pack()
                    cl = tk.Label(cell, text=(g_item.get("caption") or "Plate")[:24] + " 🔍", fg="#c9d1d9", bg="#161b22", font=("Monospace", 7), pady=2, cursor="hand2")
                    cl.pack(fill="x")
                    for wg in (cell, gl, cl):
                        wg.bind("<Button-1>", lambda e, u=gu, c=gc: self._open_lightbox(u, c))
                    self._load_thumb_async(gl, gu, size=(185, 125))

            # Saved Q&A Thread
            for qa in les.get("qa_log") or []:
                qa_box = tk.Frame(card, bg="#0c131d", highlightbackground="#6e40c9", highlightthickness=1)
                qa_box.pack(fill="x", padx=12, pady=(0, 6))
                tk.Label(qa_box, text=f"💬 Q: {qa.get('q','')}   [ {qa.get('model','GEMINI')} • {qa.get('ts','')} ]",
                         fg="#d2a8ff", bg="#0c131d", font=("Monospace", 8, "bold"), anchor="w", padx=10, pady=4).pack(fill="x")
                tk.Label(qa_box, text=qa.get("a", ""), fg="#e6edf3", bg="#0c131d", font=("Monospace", 9), justify="left", anchor="w", wraplength=1120, padx=10, pady=6).pack(fill="x")


if __name__ == "__main__":
    KnowledgeDesktopHub().mainloop()
