import os, json, threading, urllib.request
import tkinter as tk
from tkinter import ttk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CURRICULUM_FILE = os.path.join(BASE_DIR, "curriculum.json")
CLOUD_URL_FILE = os.path.join(BASE_DIR, "cloud_url.txt")
_UA = "MatrixCommandCenter/2.0 (Ubuntu; educational)"


def get_cloud_url():
    if os.path.exists(CLOUD_URL_FILE):
        u = open(CLOUD_URL_FILE).read().strip().rstrip("/")
        if u:
            return u
    return "https://knowledge-center-dsog.onrender.com"


SCHEMATICS = {
    "telemetry_bus": [
        ("OANDA v20 API", "#fbbf24"), ("Render Cloud Loop", "#3fb950"),
        ("/state JSON Bus", "#58a6ff"), ("Daemon Thread (10s)", "#d2a8ff"), ("Keyless Ubuntu HUD", "#3fb950")
    ],
    "five_gate": [
        ("G1 Clock/Spread", "#3fb950"), ("G2 9>21>200+ATR", "#3fb950"),
        ("G3 21EMA Zone", "#3fb950"), ("G4 RSI Trigger", "#3fb950"), ("G5 1% + Gemini", "#fbbf24")
    ],
    "canvas_coords": [
        ("28 M15 OHLC[]", "#58a6ff"), ("Bounds Filter", "#d2a8ff"),
        ("py() Invert Y", "#fbbf24"), ("px() Slot X", "#3fb950"), ("tk.Canvas Pixels", "#3fb950")
    ],
    "git_loop": [
        ("08:30 MT Trigger", "#fbbf24"), ("Gemini JSON", "#d2a8ff"),
        ("Base64 + SHA", "#58a6ff"), ("PUT GitHub API", "#3fb950"), ("Permanent Repo", "#3fb950")
    ],
    "cascade": [
        ("Prompt + Schema", "#58a6ff"), ("3.8-Flash Try", "#fbbf24"),
        ("429/503 Catch", "#f85149"), ("3.5-Lite Fallback", "#3fb950"), ("Parsed Dict", "#3fb950")
    ],
    "cron_budget": [
        ("GH Runner UTC", "#58a6ff"), ("08:32 Wake Pulse", "#fbbf24"),
        ("65s Tick Hold", "#d2a8ff"), ("Idle 15m Sleep", "#8b949e"), ("730h Saved!", "#3fb950")
    ],
    "desktop_gui": [
        (".desktop SVG", "#3fb950"), ("WM_CLASS Bind", "#58a6ff"),
        ("Label Hook", "#fbbf24"), ("Thread Lock", "#d2a8ff"), ("60fps X11 HUD", "#3fb950")
    ],
    "vault_crypto": [
        ("Ciphertext SSD", "#f85149"), ("unlock (scrypt)", "#fbbf24"),
        ("FUSE RAM Mount", "#58a6ff"), ("git push TLS", "#3fb950"), ("lock (Unmount)", "#3fb950")
    ],
}


def draw_schematic(cv, dtype, width, height):
    cv.delete("all")
    nodes = SCHEMATICS.get(dtype) or [
        ("Input Stream", "#58a6ff"), ("Core Engine", "#fbbf24"),
        ("Guardrail", "#d2a8ff"), ("Persistence", "#3fb950")
    ]
    # Subtle Matrix coordinate grid
    for gx in range(0, width, 24):
        cv.create_line(gx, 0, gx, height, fill="#0d1612", width=1)
    for gy in range(0, height, 24):
        cv.create_line(0, gy, width, gy, fill="#0d1612", width=1)

    cv.create_text(10, 12, text=f"⚡ ARCHITECTURE BLUEPRINT // {dtype.upper()}", fill="#3fb950", font=("Monospace", 8, "bold"), anchor="w")

    n = len(nodes)
    pad_y = 32
    slot_h = (height - pad_y - 10) / max(n, 1)
    cx = width // 2
    bw = min(width - 36, 290)

    for i, (label, col) in enumerate(nodes):
        cy = int(pad_y + (i + 0.45) * slot_h)
        bh = min(26, int(slot_h * 0.66))
        cv.create_rectangle(cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2, fill="#0d1914", outline=col, width=1)
        cv.create_text(cx, cy, text=f"[{i+1}] {label}", fill=col, font=("Monospace", 8, "bold"))
        if i < n - 1:
            ny = int(pad_y + (i + 1.45) * slot_h) - bh // 2
            cv.create_line(cx, cy + bh // 2, cx, ny, fill="#3fb950", width=2, arrow=tk.LAST)


class MatrixCommandCenter(tk.Tk):
    def __init__(self):
        super().__init__(className="matrix-hub")
        self.title("Matrix Command Center // How The Spaceship Flies")
        self.geometry("1280x800")
        self.configure(bg="#060b09")
        self.data = {"tracks": {"matrix": {"lessons": []}}}
        self.open_decode = {1}
        self.open_dd = set()

        hdr = tk.Frame(self, bg="#040806", pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🧬 MATRIX SYSTEMS COMMAND CENTER // HOW THE SPACESHIP FLIES",
                 fg="#3fb950", bg="#040806", font=("Monospace", 13, "bold")).pack()
        self.sub_lbl = tk.Label(hdr, text=" Keith Stoner Engineering Mode • OANDA + Knowledge + Linux Stack Anatomy",
                                fg="#7ee787", bg="#040806", font=("Monospace", 9))
        self.sub_lbl.pack(pady=(3, 0))

        bar = tk.Frame(self, bg="#060b09", pady=6)
        bar.pack(fill="x", padx=16)
        self.cnt_lbl = tk.Label(bar, text="MODULES: --", fg="#3fb950", bg="#0d1914", font=("Monospace", 9, "bold"), padx=10, pady=4)
        self.cnt_lbl.pack(side="left", padx=(0, 10))

        for label, fpath in [
            ("📂 Inspect Live OANDA HUD", os.path.expanduser("~/.local/share/oanda-hub/dashboard.py")),
            ("📂 Inspect knowledge_engine.py", os.path.join(BASE_DIR, "knowledge_engine.py")),
            ("📂 Inspect morning_pulse.yml", os.path.join(BASE_DIR, ".github/workflows/morning_pulse.yml")),
        ]:
            tk.Button(bar, text=label, command=lambda p=fpath: self._inspect_live_file(p),
                      bg="#0f1f18", fg="#7ee787", activebackground="#193529", relief="flat",
                      font=("Monospace", 8, "bold"), padx=10, pady=4, cursor="hand2").pack(side="left", padx=4)

        wrap = tk.Frame(self, bg="#060b09")
        wrap.pack(fill="both", expand=True, padx=16, pady=(2, 10))
        self.cv = tk.Canvas(wrap, bg="#060b09", highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.cv.yview)
        self.inner = tk.Frame(self.cv, bg="#060b09")
        self.inner.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cwin = self.cv.create_window((0, 0), window=self.inner, anchor="nw")
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfig(self.cwin, width=e.width))
        self.cv.configure(yscrollcommand=sb.set)
        self.cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.bind_all("<Button-4>", lambda e: self.cv.yview_scroll(-1, "units"))
        self.bind_all("<Button-5>", lambda e: self.cv.yview_scroll(1, "units"))

        self._load_local()
        self.render_modules()
        threading.Thread(target=self._sync_cloud, daemon=True).start()

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

    def _sync_cloud(self):
        import time
        while True:
            try:
                req = urllib.request.Request(get_cloud_url() + "/state", headers={"User-Agent": _UA})
                j = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
                if j.get("curriculum"):
                    old_n = len(self.data.get("tracks", {}).get("matrix", {}).get("lessons", []))
                    self.data = j["curriculum"]
                    self._save_local()
                    new_n = len(self.data.get("tracks", {}).get("matrix", {}).get("lessons", []))
                    if new_n != old_n:
                        self.after(0, self.render_modules)
            except Exception:
                pass
            time.sleep(40)

    def _inspect_live_file(self, path):
        top = tk.Toplevel(self)
        top.title(f"Live Source Inspector // {path}")
        top.geometry("980x660")
        top.configure(bg="#060b09")
        tk.Label(top, text=f"📂 LIVE LOCAL SOURCE FILE: {path}", fg="#3fb950", bg="#0d1914", font=("Monospace", 9, "bold"), anchor="w", padx=12, pady=7).pack(fill="x")
        txt = tk.Text(top, bg="#060b09", fg="#c9d1d9", insertbackground="#3fb950", font=("Monospace", 9), wrap="none")
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        if os.path.exists(path):
            for idx, line in enumerate(open(path, errors="replace"), 1):
                txt.insert("end", f"{idx:4d} │ {line}")
        else:
            txt.insert("end", f"File currently inside locked vault or missing: {path}\nRun `unlock` only when editing encrypted OANDA engine files.")
        txt.config(state="disabled")

    def _zoom_schematic(self, les):
        top = tk.Toplevel(self)
        top.title(f"Blueprint Zoom // {les['title']}")
        top.geometry("680x520")
        top.configure(bg="#060b09")
        zcv = tk.Canvas(top, width=640, height=470, bg="#08110d", highlightbackground="#238636", highlightthickness=1)
        zcv.pack(padx=18, pady=18)
        draw_schematic(zcv, les.get("diagram_type", "pipeline"), 640, 470)

    def _cloud_post(self, endpoint, payload, btn, wait_lbl, cb):
        btn.config(text=wait_lbl, state="disabled")
        def _w():
            try:
                req = urllib.request.Request(get_cloud_url() + endpoint, data=json.dumps(payload).encode(),
                                             headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST")
                j = json.loads(urllib.request.urlopen(req, timeout=55).read().decode())
                if j.get("ok") and j.get("lesson"):
                    arr = self.data["tracks"]["matrix"]["lessons"]
                    for i, it in enumerate(arr):
                        if int(it["seq"]) == int(payload["seq"]):
                            arr[i] = j["lesson"]
                            break
                    self._save_local()
                    self.after(0, cb)
                else:
                    self.after(0, lambda: btn.config(text="⚠️ Retry", state="normal"))
            except Exception:
                self.after(0, lambda: btn.config(text="⚠️ Cloud Waking - Retry", state="normal"))
        threading.Thread(target=_w, daemon=True).start()

    def render_modules(self):
        for w in self.inner.winfo_children():
            w.destroy()
        modules = list(reversed(self.data.get("tracks", {}).get("matrix", {}).get("lessons", [])))
        self.cnt_lbl.config(text=f"⚡ {len(modules)} LIVE ARCHITECTURE MODULES (+ 08:30 MT DAILY DROP)")

        for les in modules:
            seq = les["seq"]
            card = tk.Frame(self.inner, bg="#0b1410", highlightbackground="#238636", highlightthickness=1)
            card.pack(fill="x", pady=7, padx=2)

            top_grid = tk.Frame(card, bg="#0b1410")
            top_grid.pack(fill="x", padx=12, pady=(10, 6))

            left = tk.Frame(top_grid, bg="#0b1410")
            left.pack(side="left", fill="both", expand=True, padx=(0, 12))

            m_row = tk.Frame(left, bg="#0b1410")
            m_row.pack(fill="x")
            tk.Label(m_row, text=f"MODULE #{seq:03d}  •  {les.get('date','')}", fg="#7ee787", bg="#0b1410", font=("Monospace", 8, "bold")).pack(side="left")
            tk.Label(m_row, text=f" [ {les.get('model','ARCHITECT')} ] ", fg="#fbbf24", bg="#2d2208", font=("Monospace", 8, "bold")).pack(side="left", padx=8)
            if les.get("file_ref"):
                tk.Label(m_row, text=f"📂 {les['file_ref']}", fg="#58a6ff", bg="#0b1410", font=("Monospace", 8, "bold")).pack(side="left", padx=4)

            tk.Label(left, text=les.get("title", ""), fg="#f0f6fc", bg="#0b1410", font=("Monospace", 11, "bold"), anchor="w", justify="left", wraplength=810).pack(fill="x", pady=(5, 4))
            tk.Label(left, text=f"🛰️ Flight Deck Overview: {les.get('core', '')}", fg="#c9d1d9", bg="#0b1410", font=("Monospace", 9), anchor="w", justify="left", wraplength=810).pack(fill="x", pady=(0, 6))

            craft_f = tk.Frame(left, bg="#07100c", highlightbackground="#fbbf24", highlightthickness=1)
            craft_f.pack(fill="x", pady=(0, 6))
            tk.Label(craft_f, text=f"🧵 Structural Parallel: {les.get('maker', '')}", fg="#fbbf24", bg="#07100c", font=("Monospace", 8), anchor="w", justify="left", wraplength=790, padx=8, pady=5).pack(fill="x")

            if les.get("code_snippet"):
                code_f = tk.Frame(left, bg="#040806", highlightbackground="#1f6feb", highlightthickness=1)
                code_f.pack(fill="x", pady=(2, 4))
                tk.Label(code_f, text=les["code_snippet"], fg="#7ee787", bg="#040806", font=("Monospace", 8), justify="left", anchor="w", padx=10, pady=8).pack(fill="x")

            # Right-Side Vector Blueprint Schematic
            schem_box = tk.Frame(top_grid, bg="#060d0a", highlightbackground="#238636", highlightthickness=1, cursor="hand2")
            schem_box.pack(side="right", anchor="n")
            scv = tk.Canvas(schem_box, width=320, height=235, bg="#060d0a", highlightthickness=0, cursor="hand2")
            scv.pack()
            draw_schematic(scv, les.get("diagram_type", "pipeline"), 320, 235)
            z_lbl = tk.Label(schem_box, text="📐 Data-Flow Schematic • 🔍 Click to Zoom", fg="#7ee787", bg="#0d1914", font=("Monospace", 7, "bold"), pady=3, cursor="hand2")
            z_lbl.pack(fill="x")
            for sw in (schem_box, scv, z_lbl):
                sw.bind("<Button-1>", lambda e, item=les: self._zoom_schematic(item))

            # Action Bar: Line-by-Line Decode + Deep Dive + Ask Architect
            abar = tk.Frame(card, bg="#0b1410")
            abar.pack(fill="x", padx=12, pady=(2, 8))

            dec_open = seq in self.open_decode
            tk.Button(abar, text=("🧬 Hide Line-by-Line Decode" if dec_open else "🧬 Line-by-Line Code Decode"),
                      command=lambda s=seq: (self.open_decode.remove(s) if s in self.open_decode else self.open_decode.add(s), self.render_modules()),
                      bg="#12291e", fg="#3fb950", relief="flat", font=("Monospace", 8, "bold"), padx=10, pady=4, cursor="hand2").pack(side="left", padx=(0, 8))

            has_dd = bool(les.get("deep_dive") and len(les["deep_dive"]) > 120)
            dd_open = seq in self.open_dd
            dd_btn = tk.Button(abar, text=(("📖 Hide Architecture Essay" if dd_open else "📖 Full Architecture Deep Dive") if has_dd else "📖 Synthesize Deep Dive (Gemini)"),
                               bg="#131f2e", fg="#58a6ff", relief="flat", font=("Monospace", 8, "bold"), padx=10, pady=4, cursor="hand2")
            dd_btn.pack(side="left", padx=(0, 12))

            def _toggle_dd(s=seq, ready=has_dd, b=dd_btn):
                if ready:
                    if s in self.open_dd: self.open_dd.remove(s)
                    else: self.open_dd.add(s)
                    self.render_modules()
                else:
                    self._cloud_post("/api/deep_dive", {"track": "matrix", "seq": s}, b, "⏳ Decoding...", lambda: (self.open_dd.add(s), self.render_modules()))
            dd_btn.config(command=_toggle_dd)

            ask_e = tk.Entry(abar, bg="#040806", fg="#e6edf3", insertbackground="#3fb950", relief="flat",
                             highlightbackground="#238636", highlightthickness=1, font=("Monospace", 8), width=42)
            ask_e.pack(side="left", padx=(4, 6), ipady=3)
            ask_b = tk.Button(abar, text="💬 Ask Architect", bg="#251736", fg="#d2a8ff", relief="flat", font=("Monospace", 8, "bold"), padx=10, pady=4, cursor="hand2")
            ask_b.pack(side="left")

            def _do_ask(s=seq, ent=ask_e, b=ask_b):
                q = ent.get().strip()
                if q:
                    self._cloud_post("/api/ask", {"track": "matrix", "seq": s, "question": q}, b, "⏳ Asking Gemini...", self.render_modules)
            ask_b.config(command=_do_ask)
            ask_e.bind("<Return>", lambda e, fn=_do_ask: fn())

            # Line-by-Line Matrix Decode Drawer
            if dec_open and les.get("line_decode"):
                df = tk.Frame(card, bg="#050a08", highlightbackground="#238636", highlightthickness=1)
                df.pack(fill="x", padx=12, pady=(0, 8))
                tk.Label(df, text="🧬 LINE-BY-LINE SYNTAX & OPERATION DECODE", fg="#3fb950", bg="#050a08", font=("Monospace", 8, "bold"), anchor="w", padx=10, pady=5).pack(fill="x")
                for row in les["line_decode"]:
                    rf = tk.Frame(df, bg="#08120e")
                    rf.pack(fill="x", padx=8, pady=2)
                    tk.Label(rf, text=f"▸ {row.get('code','')}", fg="#79c0ff", bg="#08120e", font=("Monospace", 8, "bold"), anchor="w", padx=8, pady=2).pack(fill="x")
                    tk.Label(rf, text=f"   ↳ {row.get('meaning','')}", fg="#c9d1d9", bg="#08120e", font=("Monospace", 8), anchor="w", justify="left", wraplength=1120, padx=8).pack(fill="x", pady=(0, 4))

            # Deep Dive Essay Drawer
            if dd_open and les.get("deep_dive"):
                ef = tk.Frame(card, bg="#050a08", highlightbackground="#1f6feb", highlightthickness=1)
                ef.pack(fill="x", padx=12, pady=(0, 8))
                tk.Label(ef, text="📖 SYSTEMS ENGINEERING DEEP DIVE", fg="#58a6ff", bg="#050a08", font=("Monospace", 8, "bold"), anchor="w", padx=10, pady=5).pack(fill="x")
                tk.Label(ef, text=les["deep_dive"], fg="#d0d7de", bg="#050a08", font=("Monospace", 9), justify="left", anchor="w", wraplength=1120, padx=10, pady=6).pack(fill="x")

            # Saved Q&A Log
            for qa in les.get("qa_log") or []:
                qf = tk.Frame(card, bg="#0c131d", highlightbackground="#6e40c9", highlightthickness=1)
                qf.pack(fill="x", padx=12, pady=(0, 6))
                tk.Label(qf, text=f"💬 Q: {qa.get('q','')}   [ {qa.get('model','GEMINI')} • {qa.get('ts','')} ]",
                         fg="#d2a8ff", bg="#0c131d", font=("Monospace", 8, "bold"), anchor="w", padx=10, pady=4).pack(fill="x")
                tk.Label(qf, text=qa.get("a", ""), fg="#e6edf3", bg="#0c131d", font=("Monospace", 9), justify="left", anchor="w", wraplength=1120, padx=10, pady=6).pack(fill="x")


if __name__ == "__main__":
    MatrixCommandCenter().mainloop()
