import os
import json
import threading
import time
import urllib.request
import tkinter as tk
from tkinter import ttk

BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, "curriculum.json")
URL_FILE = os.path.join(BASE_DIR, "cloud_url.txt")


def _get_cloud_url():
    if os.getenv("KNOWLEDGE_RENDER_URL"):
        return os.getenv("KNOWLEDGE_RENDER_URL").strip().rstrip("/")
    if os.path.exists(URL_FILE):
        return open(URL_FILE).read().strip().rstrip("/")
    return ""


def _cloud_sync():
    while True:
        url = _get_cloud_url()
        if url:
            try:
                with urllib.request.urlopen(f"{url}/state", timeout=8) as r:
                    payload = json.loads(r.read().decode())
                    cur = payload.get("curriculum")
                    if cur and cur.get("tracks"):
                        with open(DATA_FILE, "w") as f:
                            json.dump(cur, f, indent=2)
            except Exception:
                pass
        time.sleep(30)


threading.Thread(target=_cloud_sync, daemon=True).start()


class KnowledgeCommandCenter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Knowledge Command Center // Keyshawn")
        self.geometry("1080x740")
        self.configure(bg="#0d1117")

        self.study_mode = False
        self.expanded_keys = set()
        self.active_track = None
        self._last_sig = None

        top = tk.Frame(self, bg="#0d1117")
        top.pack(pady=(10, 2))
        tk.Label(
            top, text="🧠 KNOWLEDGE COMMAND CENTER // ART & UNIVERSE ARCHIVE",
            fg="#58a6ff", bg="#0d1117", font=("Monospace", 14, "bold")
        ).pack()

        cloud_u = _get_cloud_url() or "Local Archive Active (Save Render URL to cloud_url.txt after deploy)"
        self.sub_lbl = tk.Label(
            self, text=f"08:30 AM MT Auto-Drop Curriculum  |  Sync: {cloud_u}",
            fg="#8b949e", bg="#0d1117", font=("Monospace", 9)
        )
        self.sub_lbl.pack(pady=(0, 6))

        # Dynamic Track Tabs + Search + Study Mode Bar
        self.nav = tk.Frame(self, bg="#161b22", highlightbackground="#30363d", highlightthickness=1)
        self.nav.pack(fill="x", padx=16, pady=4)
        self.tabs_frame = tk.Frame(self.nav, bg="#161b22")
        self.tabs_frame.pack(side="left", padx=8, pady=6)

        right_ctrl = tk.Frame(self.nav, bg="#161b22")
        right_ctrl.pack(side="right", padx=8, pady=6)

        tk.Label(right_ctrl, text="Filter:", fg="#8b949e", bg="#161b22", font=("Monospace", 9)).pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._force_redraw())
        self.search_entry = tk.Entry(
            right_ctrl, textvariable=self.search_var, bg="#0d1117", fg="#e6edf3",
            insertbackground="#e6edf3", relief="flat", highlightbackground="#30363d",
            highlightthickness=1, font=("Monospace", 9), width=20
        )
        self.search_entry.pack(side="left", padx=(0, 10), ipady=3)

        self.btn_study = tk.Button(
            right_ctrl, text="📚 Study Mode: Expand All", command=self.toggle_study,
            bg="#2d2208", fg="#fbbf24", activebackground="#fbbf24", activeforeground="#0d1117",
            highlightbackground="#fbbf24", highlightthickness=1,
            relief="flat", font=("Monospace", 9, "bold"), padx=10, pady=3, cursor="hand2"
        )
        self.btn_study.pack(side="left")

        self.desc_lbl = tk.Label(
            self, text="", fg="#c9d1d9", bg="#161b22",
            font=("Monospace", 9, "bold"), anchor="w", padx=12, pady=7
        )
        self.desc_lbl.pack(fill="x", padx=16, pady=(4, 4))

        wrap = tk.Frame(self, bg="#0d1117")
        wrap.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.cv = tk.Canvas(wrap, bg="#0d1117", highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.cv.yview)
        self.inner = tk.Frame(self.cv, bg="#0d1117")

        self.inner.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.win_id = self.cv.create_window((0, 0), window=self.inner, anchor="nw")
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfig(self.win_id, width=e.width))
        self.cv.configure(yscrollcommand=sb.set)

        self.cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.bind_all("<Button-4>", lambda e: self.cv.yview_scroll(-1, "units"))
        self.bind_all("<Button-5>", lambda e: self.cv.yview_scroll(1, "units"))

        self.tab_buttons = {}
        self.refresh_ui()

    def _force_redraw(self):
        self._last_sig = None
        self.refresh_ui(scheduled=False)

    def select_track(self, k):
        self.active_track = k
        self.cv.yview_moveto(0)
        self._force_redraw()

    def toggle_study(self):
        self.study_mode = not self.study_mode
        if self.study_mode:
            self.btn_study.config(text="📚 Study Mode: ON (Collapse All)", bg="#fbbf24", fg="#0d1117")
        else:
            self.expanded_keys.clear()
            self.btn_study.config(text="📚 Study Mode: Expand All", bg="#2d2208", fg="#fbbf24")
        self._force_redraw()

    def toggle_row(self, row_key):
        if self.study_mode:
            return
        if row_key in self.expanded_keys:
            self.expanded_keys.remove(row_key)
        else:
            self.expanded_keys.add(row_key)
        self._force_redraw()

    def refresh_ui(self, scheduled=True):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
            tracks = data.get("tracks", {})
            if tracks and self.active_track not in tracks:
                self.active_track = next(iter(tracks.keys()))

            q = self.search_var.get().lower().strip()
            sig = (
                self.active_track,
                self.study_mode,
                q,
                tuple(sorted(self.expanded_keys)),
                tuple((k, len(v.get("lessons", []))) for k, v in tracks.items()),
            )
            if sig != self._last_sig:
                self._last_sig = sig
                for w in self.tabs_frame.winfo_children():
                    w.destroy()
                for k, tr in tracks.items():
                    is_act = (k == self.active_track)
                    b = tk.Button(
                        self.tabs_frame,
                        text=f"{tr['icon']} {tr['title']} ({len(tr.get('lessons', []))})",
                        command=lambda tk_k=k: self.select_track(tk_k),
                        bg="#1f6feb" if is_act else "#21262d",
                        fg="#ffffff" if is_act else "#c9d1d9",
                        activebackground="#388bfd", activeforeground="#ffffff",
                        relief="flat", font=("Monospace", 9, "bold"), padx=10, pady=4, cursor="hand2"
                    )
                    b.pack(side="left", padx=(0, 6))

                cur_tr = tracks.get(self.active_track, {})
                accent = cur_tr.get("accent", "#58a6ff")
                self.desc_lbl.config(
                    text=f"{cur_tr.get('icon', '')} {cur_tr.get('title', '')}: {cur_tr.get('description', '')}  (Click any lesson to inspect)",
                    fg=accent
                )

                for w in self.inner.winfo_children():
                    w.destroy()

                for item in reversed(cur_tr.get("lessons", [])):
                    hay = f"{item['title']} {item['core']} {item['maker']} {' '.join(item.get('tags', []))}".lower()
                    if q and q not in hay:
                        continue
                    r_key = f"{self.active_track}:{item['seq']}"
                    is_open = self.study_mode or (r_key in self.expanded_keys)
                    arrow = "▼" if is_open else "▶"

                    box = tk.Frame(self.inner, bg="#161b22", highlightbackground="#30363d", highlightthickness=1)
                    box.pack(fill="x", pady=4, padx=2)

                    hdr = tk.Frame(box, bg="#161b22", cursor="hand2")
                    hdr.pack(fill="x", padx=10, pady=8)

                    l_lbl = tk.Label(
                        hdr, text=f"{arrow} #{item['seq']:03d}  {item['title']}",
                        fg="#f0f6fc", bg="#161b22", font=("Monospace", 9, "bold"), cursor="hand2"
                    )
                    l_lbl.pack(side="left")
                    r_lbl = tk.Label(
                        hdr, text=f"{item['date']}   [ {item.get('model', 'ARCHIVE').upper()} ]",
                        fg="#fbbf24", bg="#161b22", font=("Monospace", 8, "bold"), cursor="hand2"
                    )
                    r_lbl.pack(side="right")

                    for wg in (hdr, l_lbl, r_lbl):
                        wg.bind("<Button-1>", lambda e, rk=r_key: self.toggle_row(rk))

                    if is_open:
                        body = tk.Frame(box, bg="#090d13")
                        body.pack(fill="x", padx=2, pady=(0, 2))
                        tk.Label(
                            body, text=f"📖 CORE MECHANICS: {item['core']}",
                            fg="#c9d1d9", bg="#090d13", font=("Monospace", 9),
                            justify="left", anchor="w", wraplength=990, padx=12, pady=6
                        ).pack(fill="x", anchor="w")
                        tk.Label(
                            body, text=f"🧵 STUDIO & SYSTEMS LENS: {item['maker']}",
                            fg="#fbbf24", bg="#0d131d", font=("Monospace", 9),
                            justify="left", anchor="w", wraplength=990, padx=12, pady=6
                        ).pack(fill="x", anchor="w")
        except Exception as e:
            self.sub_lbl.config(text=f"Error reading curriculum: {e}")

        if scheduled:
            self.after(10000, self.refresh_ui)


if __name__ == "__main__":
    app = KnowledgeCommandCenter()
    app.mainloop()
