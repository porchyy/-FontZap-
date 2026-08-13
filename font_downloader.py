# FontZap — Font Bulk Downloader + Auto Installer
# GitHub: https://github.com/porchyy/-FontZap-
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import threading
import requests
import os, re, shutil, time, zipfile, ctypes, winreg, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, unquote

# ── Theme ──────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Palette ────────────────────────────────────────────────────
BG           = "#080818"
BG_CARD      = "#10102a"
BG_INPUT     = "#13132b"
BG_ROW       = "#181830"
ACCENT       = "#8b5cf6"
ACCENT2      = "#6d28d9"
ACCENT_GLOW  = "#a78bfa"
SUCCESS      = "#10b981"
SUCCESS_DIM  = "#065f46"
ERROR        = "#ef4444"
ERROR_DIM    = "#7f1d1d"
WARNING      = "#f59e0b"
PURPLE_DIM   = "#2e1065"
TEXT         = "#f1f5f9"
TEXT2        = "#94a3b8"
TEXT3        = "#475569"
BORDER       = "#1e1e3f"
BORDER2      = "#2d2d5e"

FONT_EXTS = {".ttf", ".otf", ".woff", ".woff2", ".eot", ".fon"}
WOFF_EXTS = {".woff", ".woff2", ".eot"}   # web fonts — limited Windows support
USER_FONTS_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"
)


# ── Font Install Logic ─────────────────────────────────────────
def install_font_to_windows(src: str) -> str:
    os.makedirs(USER_FONTS_DIR, exist_ok=True)
    fname = os.path.basename(src)
    dest  = os.path.join(USER_FONTS_DIR, fname)
    base, ext = os.path.splitext(fname)
    c = 1
    while os.path.exists(dest) and _diff(src, dest):
        dest = os.path.join(USER_FONTS_DIR, f"{base}_{c}{ext}"); c += 1
    shutil.copy2(src, dest)
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
            0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, os.path.basename(dest), 0, winreg.REG_SZ, dest)
        winreg.CloseKey(key)
    except Exception: pass
    try:
        ctypes.windll.gdi32.AddFontResourceExW(dest, 0x10, 0)
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0x0002, 1000, None)
    except Exception: pass
    return dest

def _diff(a, b):
    try: return os.path.getsize(a) != os.path.getsize(b)
    except: return True

def extract_fonts_from_zip(zpath: str) -> list[str]:
    tmp = os.path.join(os.environ.get("TEMP", "."), f"fz_{int(time.time())}")
    os.makedirs(tmp, exist_ok=True)
    found = []
    with zipfile.ZipFile(zpath, "r") as z:
        for n in z.namelist():
            if os.path.splitext(n)[1].lower() in FONT_EXTS:
                z.extract(n, tmp); found.append(os.path.join(tmp, n))
    return found

def get_filename(url, resp=None):
    if resp:
        cd = resp.headers.get("Content-Disposition", "")
        m  = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\'\n;]+)', cd, re.I)
        if m:
            n = unquote(m.group(1).strip())
            if n: return n
    name = unquote(os.path.basename(urlparse(url).path))
    return name if name and "." in name else f"font_{int(time.time())}.ttf"

def parse_drop(data: str) -> list[str]:
    return [(m.group(1) or m.group(2)).strip()
            for m in re.finditer(r'\{([^}]+)\}|(\S+)', data) if m.group(1) or m.group(2)]

def ext_badge_color(ext: str):
    return {
        ".ttf":  ("#8b5cf6", "#2e1065"),
        ".otf":  ("#06b6d4", "#164e63"),
        ".zip":  ("#f59e0b", "#78350f"),
        ".woff": ("#10b981", "#064e3b"),
        ".woff2":("#10b981", "#064e3b"),
    }.get(ext.lower(), ("#64748b", "#1e293b"))


# ── Animated Drop Zone (Canvas-based) ─────────────────────────
class DropZone(tk.Frame):
    DASH_COLORS = ["#8b5cf6", "#7c3aed", "#6d28d9", "#7c3aed"]

    def __init__(self, parent, on_drop, **kw):
        super().__init__(parent, bg=BG, **kw)
        self.on_drop   = on_drop
        self._hover    = False
        self._dash_off = 0
        self._anim_id  = None
        self._build()
        self._setup_dnd()
        self._animate()

    def _build(self):
        self.canvas = tk.Canvas(self, bg=BG_INPUT, highlightthickness=0, height=210)
        self.canvas.pack(fill="both", expand=True, padx=2, pady=2)
        self.canvas.bind("<Configure>", lambda e: self._redraw())

        self._icon  = self.canvas.create_text(0, 0, text="🖋", font=("Segoe UI Emoji", 42), fill=ACCENT_GLOW, anchor="center", tags="content")
        self._title = self.canvas.create_text(0, 0, text="ลากไฟล์ฟ้อนมาวางที่นี่", font=("Segoe UI", 15, "bold"), fill=TEXT, anchor="center", tags="content")
        self._sub   = self.canvas.create_text(0, 0, text=".ttf  •  .otf  •  .zip  •  .woff  •  .woff2", font=("Segoe UI", 10), fill=TEXT2, anchor="center", tags="content")
        self._hint  = self.canvas.create_text(0, 0, text="ติดตั้งเข้า Windows อัตโนมัติ  ⚡", font=("Segoe UI", 10), fill=ACCENT_GLOW, anchor="center", tags="content")

    def _redraw(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10: return
        cx, cy = w // 2, h // 2

        self.canvas.delete("bg", "border")
        r  = 14
        bg = "#1a0a3a" if self._hover else BG_INPUT
        bc = ACCENT_GLOW if self._hover else ACCENT
        self.canvas.create_arc(4, 4, 4+2*r, 4+2*r,          start=90,  extent=90, fill=bg, outline=bg, tags="bg")
        self.canvas.create_arc(w-4-2*r, 4, w-4, 4+2*r,      start=0,   extent=90, fill=bg, outline=bg, tags="bg")
        self.canvas.create_arc(4, h-4-2*r, 4+2*r, h-4,      start=180, extent=90, fill=bg, outline=bg, tags="bg")
        self.canvas.create_arc(w-4-2*r, h-4-2*r, w-4, h-4,  start=270, extent=90, fill=bg, outline=bg, tags="bg")
        self.canvas.create_rectangle(4+r, 4, w-4-r, h-4,    fill=bg, outline=bg, tags="bg")
        self.canvas.create_rectangle(4, 4+r, w-4, h-4-r,    fill=bg, outline=bg, tags="bg")

        pts = [4+r,4, w-4-r,4, w-4,4+r, w-4,h-4-r, w-4-r,h-4, 4+r,h-4, 4,h-4-r, 4,4+r, 4+r,4]
        self.canvas.create_line(*pts, fill=bc, width=2,
                                dash=(8, 6), dashoffset=self._dash_off, tags="border")

        self.canvas.tag_raise("content")
        self.canvas.coords(self._icon,  cx, cy-62)
        self.canvas.coords(self._title, cx, cy-10)
        self.canvas.coords(self._sub,   cx, cy+22)
        self.canvas.coords(self._hint,  cx, cy+48)

        if self._hover:
            self.canvas.itemconfig(self._title, text="วางได้เลย! ⚡", fill=ACCENT_GLOW)
            self.canvas.itemconfig(self._icon,  text="✨")
        else:
            self.canvas.itemconfig(self._title, text="ลากไฟล์ฟ้อนมาวางที่นี่", fill=TEXT)
            self.canvas.itemconfig(self._icon,  text="🖋")

    def _animate(self):
        self._dash_off = (self._dash_off + 1) % 28
        self._redraw()
        self._anim_id = self.after(40, self._animate)

    def _setup_dnd(self):
        for w in [self, self.canvas]:
            w.drop_target_register(DND_FILES)
            w.dnd_bind("<<DropEnter>>", self._enter)
            w.dnd_bind("<<DropLeave>>", self._leave)
            w.dnd_bind("<<Drop>>",      self._drop)

    def _enter(self, _): self._hover = True;  self._redraw()
    def _leave(self, _): self._hover = False; self._redraw()
    def _drop(self, ev):
        self._hover = False; self._redraw()
        self.on_drop(parse_drop(ev.data))

    def destroy(self):
        if self._anim_id: self.after_cancel(self._anim_id)
        super().destroy()


# ── Item Row ───────────────────────────────────────────────────
class ItemRow(tk.Frame):
    STATUS = {
        "waiting":   ("⏳", TEXT3,      BG_ROW,     BORDER2),
        "working":   ("⚙️",  ACCENT_GLOW, "#16133a",  ACCENT),
        "done":      ("✅", SUCCESS,    "#0d2a1f",  SUCCESS),
        "error":     ("❌", ERROR,      "#2a0d0d",  ERROR),
        "cancelled": ("🚫", TEXT3,      BG_ROW,     TEXT3),
    }

    def __init__(self, parent, label: str, file_ext: str = "", **kw):
        super().__init__(parent, bg=BG, **kw)
        self._status = "waiting"
        self.columnconfigure(1, weight=1)

        self._bar_canvas = tk.Canvas(self, width=4, bg=TEXT3, highlightthickness=0)
        self._bar_canvas.grid(row=0, column=0, sticky="ns")

        self._card = tk.Frame(self, bg=BG_ROW, padx=12, pady=8)
        self._card.grid(row=0, column=1, sticky="ew", padx=(1, 0), pady=1)
        self._card.columnconfigure(0, weight=1)

        top = tk.Frame(self._card, bg=BG_ROW)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)

        short = label if len(label) <= 52 else "…" + label[-49:]
        self._name = tk.Label(top, text=short, bg=BG_ROW,
                              fg=TEXT, font=("Segoe UI", 11, "bold"), anchor="w")
        self._name.grid(row=0, column=0, sticky="ew")

        if file_ext:
            fg_b, bg_b = ext_badge_color(file_ext)
            badge = tk.Label(top, text=file_ext.lstrip(".").upper(),
                             bg=bg_b, fg=fg_b,
                             font=("Segoe UI", 8, "bold"), padx=6, pady=1)
            badge.grid(row=0, column=1, padx=(6, 0))

        self._status_lbl = tk.Label(self._card, text="รอ...",
                                    bg=BG_ROW, fg=TEXT3,
                                    font=("Segoe UI", 10), anchor="w")
        self._status_lbl.grid(row=1, column=0, sticky="ew", pady=(2, 4))

        self._pb_bg = tk.Frame(self._card, bg=BORDER2, height=5)
        self._pb_bg.grid(row=2, column=0, sticky="ew")
        self._pb_bg.columnconfigure(0, weight=1)
        self._pb_fill = tk.Frame(self._pb_bg, bg=ACCENT, height=5)
        self._pb_fill.place(x=0, y=0, relheight=1, relwidth=0)

    def update(self, status: str, text: str = "", pct: float = 0, name: str = None):
        self._status = status
        icon, color, bg, bar_col = self.STATUS.get(status, self.STATUS["waiting"])
        self._card.configure(bg=bg)
        self._name.configure(bg=bg)
        self._status_lbl.configure(text=f"{icon}  {text}", fg=color, bg=bg)
        self._bar_canvas.configure(bg=bar_col)
        self._pb_fill.configure(bg=bar_col)
        self._pb_fill.place(relwidth=min(pct / 100, 1))
        if name:
            short = name if len(name) <= 52 else "…" + name[-49:]
            self._name.configure(text=short)


# ── Pill Tab Bar ───────────────────────────────────────────────
class PillTabs(tk.Frame):
    def __init__(self, parent, tabs: list[tuple], **kw):
        super().__init__(parent, bg=BG_CARD, **kw)
        self._btns = {}
        self._active = None
        self._callbacks = {}
        container = tk.Frame(self, bg="#1a1a35", bd=0)
        container.pack(padx=16, pady=8)
        for i, (key, label, cb) in enumerate(tabs):
            btn = tk.Label(
                container, text=label, cursor="hand2",
                font=("Segoe UI", 11, "bold"), padx=20, pady=6,
                bg="#1a1a35", fg=TEXT3
            )
            btn.pack(side="left", padx=2)
            btn.bind("<Button-1>", lambda e, k=key: self._click(k))
            self._btns[key] = btn
            self._callbacks[key] = cb

    def _click(self, key: str):
        if self._active == key: return
        self._active = key
        for k, btn in self._btns.items():
            btn.configure(bg=ACCENT if k == key else "#1a1a35",
                          fg=TEXT   if k == key else TEXT3)
        self._callbacks[key]()

    def set_active(self, key: str):
        self._click(key)


# ── Main App ───────────────────────────────────────────────────
class FontZapApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        self.title("⚡ FontZap")
        self.geometry("760x940")
        self.minsize(640, 720)
        self.configure(fg_color=BG)

        self.save_dir = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Downloads", "Fonts"))
        self.rows: list[ItemRow] = []
        self.busy    = False
        self._cancel = False          # ← cancel flag
        self._last_open_path = ""     # ← for "open folder" button
        self._total_installed = 0

        self._build()

    # ── Build ──────────────────────────────────────────────────
    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # ── HEADER ───────────────────────────────────────────
        hdr = tk.Frame(self, bg=BG_CARD)
        hdr.grid(row=0, column=0, sticky="ew")
        tk.Frame(hdr, bg=ACCENT, height=3).pack(fill="x")

        inner_hdr = tk.Frame(hdr, bg=BG_CARD)
        inner_hdr.pack(fill="x", padx=28, pady=(18, 14))

        left_hdr = tk.Frame(inner_hdr, bg=BG_CARD)
        left_hdr.pack(side="left")
        tk.Label(left_hdr, text="⚡  FontZap",
                 bg=BG_CARD, fg=ACCENT_GLOW,
                 font=("Segoe UI", 26, "bold")).pack(anchor="w")
        tk.Label(left_hdr,
                 text="ลากไฟล์ฟ้อน → ติดตั้งเข้า Windows อัตโนมัติทันที",
                 bg=BG_CARD, fg=TEXT2,
                 font=("Segoe UI", 11)).pack(anchor="w", pady=(2, 0))

        right_hdr = tk.Frame(inner_hdr, bg=BG_CARD)
        right_hdr.pack(side="right", anchor="center")
        stats_bg = tk.Frame(right_hdr, bg=PURPLE_DIM, padx=14, pady=8)
        stats_bg.pack()
        tk.Label(stats_bg, text="ฟ้อนที่ติดตั้งแล้ว",
                 bg=PURPLE_DIM, fg=TEXT2, font=("Segoe UI", 9)).pack()
        self._stat_lbl = tk.Label(stats_bg, text="0",
                                   bg=PURPLE_DIM, fg=ACCENT_GLOW,
                                   font=("Segoe UI", 22, "bold"))
        self._stat_lbl.pack()

        # ── TAB BAR ──────────────────────────────────────────
        self._tabs = PillTabs(self, [
            ("drop", "📂  ลากไฟล์  (Auto Install)", lambda: self._switch("drop")),
            ("url",  "🔗  วางลิงค์  (Download)",    lambda: self._switch("url")),
        ])
        self._tabs.grid(row=1, column=0, sticky="ew")

        # ── CONTENT AREA ─────────────────────────────────────
        content = tk.Frame(self, bg=BG)
        content.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 0))
        content.columnconfigure(0, weight=1)

        # Drop Panel
        self._drop_panel = DropZone(content, on_drop=self._on_files_dropped)
        self._drop_panel.grid(row=0, column=0, sticky="ew")

        # URL Panel
        self._url_panel = tk.Frame(content, bg=BG_CARD)
        self._url_panel.grid(row=0, column=0, sticky="ew")
        self._url_panel.columnconfigure(0, weight=1)
        tk.Frame(self._url_panel, bg=ACCENT, height=2).grid(row=0, column=0, sticky="ew")

        url_inner = tk.Frame(self._url_panel, bg=BG_CARD)
        url_inner.grid(row=1, column=0, padx=18, pady=14, sticky="ew")
        url_inner.columnconfigure(0, weight=1)
        tk.Label(url_inner, text="📋  วางลิงค์ดาวน์โหลดฟ้อน",
                 bg=BG_CARD, fg=TEXT, font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(url_inner,
                 text="ใส่ URL ทีละบรรทัด  •  ดาวน์โหลด + ติดตั้งเข้า Windows ให้เลย",
                 bg=BG_CARD, fg=TEXT2,
                 font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", pady=(2, 8))

        self._url_box = ctk.CTkTextbox(
            url_inner, height=130,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=BG_INPUT, text_color=TEXT,
            border_color=BORDER2, border_width=1, corner_radius=8
        )
        self._url_box.grid(row=2, column=0, sticky="ew")
        self._url_box.insert("end", "# วางลิงค์ที่นี่ ทีละบรรทัด:\n# https://example.com/font.ttf\n# https://example.com/fonts.zip\n")

        btn_row = tk.Frame(url_inner, bg=BG_CARD)
        btn_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        for txt, cmd in [("🗑️  ล้าง", self._clear_urls), ("📋  วาง", self._paste_clip)]:
            ctk.CTkButton(
                btn_row, text=txt, width=90, height=30,
                fg_color=BORDER2, hover_color="#2d2d5e", text_color=TEXT2,
                font=ctk.CTkFont(size=12), corner_radius=6, command=cmd
            ).pack(side="right", padx=(6, 0))

        # Folder row (URL mode)
        self._folder_card = tk.Frame(content, bg=BG_CARD)
        self._folder_card.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        tk.Frame(self._folder_card, bg=BORDER2, height=1).pack(fill="x")
        fc_inner = tk.Frame(self._folder_card, bg=BG_CARD)
        fc_inner.pack(fill="x", padx=14, pady=8)
        tk.Label(fc_inner, text="📁", bg=BG_CARD, fg=ACCENT_GLOW,
                 font=("Segoe UI Emoji", 16)).pack(side="left", padx=(0, 8))
        self._folder_lbl = tk.Label(fc_inner, textvariable=self.save_dir,
                                     bg=BG_CARD, fg=ACCENT_GLOW, font=("Segoe UI", 11))
        self._folder_lbl.pack(side="left", fill="x", expand=True, anchor="w")
        ctk.CTkButton(
            fc_inner, text="เปลี่ยน", width=80, height=28,
            fg_color=ACCENT, hover_color=ACCENT2, text_color="white",
            font=ctk.CTkFont(size=12, weight="bold"), corner_radius=6,
            command=self._browse
        ).pack(side="right")

        # Download button (URL mode)
        self._dl_btn = ctk.CTkButton(
            content, text="⬇️   ดาวน์โหลดและติดตั้งทั้งหมด", height=50,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT2, text_color="white",
            corner_radius=10, command=self._start_url
        )
        self._dl_btn.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        # ── PROGRESS AREA ────────────────────────────────────
        prog_outer = tk.Frame(self, bg=BG_CARD)
        prog_outer.grid(row=3, column=0, padx=16, pady=(10, 0), sticky="nsew")
        prog_outer.columnconfigure(0, weight=1)
        prog_outer.rowconfigure(1, weight=1)

        prog_top = tk.Frame(prog_outer, bg=BG_CARD)
        prog_top.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 4))
        prog_top.columnconfigure(0, weight=1)

        tk.Label(prog_top, text="📊  สถานะ",
                 bg=BG_CARD, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")

        self._summary_lbl = tk.Label(prog_top, text="",
                                      bg=BG_CARD, fg=TEXT2, font=("Segoe UI", 10))
        self._summary_lbl.grid(row=0, column=1, sticky="e", padx=(0, 8))

        # ← Cancel button (always visible, disabled when idle)
        self._cancel_btn = ctk.CTkButton(
            prog_top, text="🚫  ยกเลิก", width=90, height=26,
            fg_color=ERROR_DIM, hover_color="#991b1b", text_color=ERROR,
            font=ctk.CTkFont(size=11), corner_radius=6,
            command=self._cancel_task, state="disabled"
        )
        self._cancel_btn.grid(row=0, column=2, padx=(0, 6))

        # ← Open folder button (hidden until a task finishes)
        self._open_folder_btn = ctk.CTkButton(
            prog_top, text="📂  เปิดโฟลเดอร์", width=120, height=26,
            fg_color=SUCCESS_DIM, hover_color="#047857", text_color=SUCCESS,
            font=ctk.CTkFont(size=11), corner_radius=6,
            command=self._open_last_folder
        )
        # (not gridded yet — shown after tasks finish)

        tk.Frame(prog_outer, bg=BORDER2, height=1).grid(
            row=0, column=0, sticky="ew", padx=16, pady=(36, 0))

        self._scroll_container = ctk.CTkScrollableFrame(
            prog_outer, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=BORDER2,
            scrollbar_button_hover_color=ACCENT
        )
        self._scroll_container.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self._scroll_container.columnconfigure(0, weight=1)

        self._placeholder = tk.Label(
            self._scroll_container,
            text="ลากไฟล์ฟ้อนมาวาง หรือวางลิงค์แล้วกดดาวน์โหลด ⚡",
            bg=BG, fg=TEXT3, font=("Segoe UI", 11)
        )
        self._placeholder.grid(row=0, column=0, pady=40)

        # ── FOOTER ───────────────────────────────────────────
        footer = tk.Frame(self, bg=BG_CARD, height=34)
        footer.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        footer.grid_propagate(False)
        tk.Label(
            footer,
            text="⚡ FontZap  •  User Fonts (ไม่ต้อง Admin)  •  github.com/porchyy/-FontZap-",
            bg=BG_CARD, fg=TEXT3, font=("Segoe UI", 9)
        ).place(relx=0.5, rely=0.5, anchor="center")

        self._tabs.set_active("drop")

    # ── Tab Switch ─────────────────────────────────────────────
    def _switch(self, tab: str):
        if tab == "drop":
            self._drop_panel.grid()
            self._url_panel.grid_remove()
            self._folder_card.grid_remove()
            self._dl_btn.grid_remove()
        else:
            self._drop_panel.grid_remove()
            self._url_panel.grid()
            self._folder_card.grid()
            self._dl_btn.grid()

    # ── Drop Handler ────────────────────────────────────────────
    def _on_files_dropped(self, paths: list[str]):
        if self.busy: return
        fonts, zips = [], []
        for p in paths:
            e = os.path.splitext(p)[1].lower()
            if e in FONT_EXTS: fonts.append(p)
            elif e == ".zip":  zips.append(p)
        if not fonts and not zips:
            messagebox.showwarning("ไม่รองรับ",
                "กรุณาลากไฟล์ฟ้อน\n.ttf  .otf  .zip  .woff  .woff2"); return

        # Warn about web fonts
        woff_files = [p for p in fonts if os.path.splitext(p)[1].lower() in WOFF_EXTS]
        if woff_files:
            messagebox.showwarning("⚠️ หมายเหตุ Web Font",
                f"พบไฟล์ .woff / .woff2 / .eot จำนวน {len(woff_files)} ไฟล์\n\n"
                "ฟ้อนเหล่านี้ออกแบบมาสำหรับเว็บ อาจไม่รองรับใน\n"
                "Word, Photoshop หรือโปรแกรมทั่วไปบน Windows\n\n"
                "แนะนำใช้ไฟล์ .ttf หรือ .otf แทน")

        items = [(os.path.basename(p), "font", p, os.path.splitext(p)[1].lower())
                 for p in fonts]
        items += [(f"📦 {os.path.basename(p)}", "zip", p, ".zip") for p in zips]

        self._clear_rows()
        self._hide_open_folder()
        self._stat_lbl.configure(text="0")     # reset counter each session
        for label, kind, path, ext in items:
            row = ItemRow(self._scroll_container, label, ext)
            row.grid(sticky="ew", pady=(0, 3))
            self._scroll_container.columnconfigure(0, weight=1)
            row.columnconfigure(1, weight=1)
            self.rows.append(row)

        self._summary_lbl.configure(text=f"0 / {len(items)} เสร็จ")
        self.busy    = True
        self._cancel = False
        self._cancel_btn.configure(state="normal", text="🚫  ยกเลิก")
        self._last_open_path = USER_FONTS_DIR
        threading.Thread(target=self._run_install, args=(items,), daemon=True).start()

    def _run_install(self, items):
        done = 0; total = len(items); installed_n = []
        for i, (label, kind, path, ext) in enumerate(items):
            if self._cancel:
                for j in range(i, len(self.rows)):
                    self.after(0, self.rows[j].update, "cancelled", "ยกเลิกแล้ว", 0)
                break

            row = self.rows[i]
            if kind == "font":
                self.after(0, row.update, "working", "กำลังติดตั้ง...", 50)
                try:
                    dest = install_font_to_windows(path)
                    installed_n.append(os.path.basename(dest))
                    done += 1
                    self.after(0, row.update, "done",
                               "ติดตั้งแล้ว! พร้อมใช้งานทันที", 100, os.path.basename(dest))
                except Exception as e:
                    done += 1
                    print(f"[FontZap] install error: {e}")
                    self.after(0, row.update, "error", f"❗ {e}", 0)
            else:
                self.after(0, row.update, "working", "กำลังแตกไฟล์ .zip ...", 15)
                try:
                    fonts = extract_fonts_from_zip(path)
                    if not fonts:
                        done += 1
                        self.after(0, row.update, "error", "ไม่พบไฟล์ฟ้อนใน zip", 0)
                    else:
                        sub = 0
                        for fi, fp in enumerate(fonts):
                            if self._cancel: break
                            pct = 15 + int((fi + 1) / len(fonts) * 85)
                            self.after(0, row.update, "working",
                                       f"ติดตั้ง {os.path.basename(fp)} ({fi+1}/{len(fonts)})", pct)
                            try:
                                dest = install_font_to_windows(fp)
                                installed_n.append(os.path.basename(dest)); sub += 1
                            except Exception as e:
                                print(f"[FontZap] zip-item install error: {e}")
                        done += 1
                        self.after(0, row.update, "done",
                                   f"ติดตั้ง {sub}/{len(fonts)} ฟ้อนแล้ว!", 100,
                                   f"📦 {os.path.basename(path)}")
                except Exception as e:
                    done += 1
                    print(f"[FontZap] zip extract error: {e}")
                    self.after(0, row.update, "error", f"❗ {e}", 0)

            self.after(0, self._summary_lbl.configure,
                       {"text": f"{done} / {total} เสร็จ"})
            self.after(0, self._stat_lbl.configure,
                       {"text": str(len(installed_n))})

        self.after(0, self._install_done, done, total, installed_n)

    def _install_done(self, done, total, names):
        self.busy    = False
        self._cancel = False
        self._cancel_btn.configure(state="disabled", text="🚫  ยกเลิก")
        n = len(names)

        # Show open-folder button pointing to User Fonts
        self._show_open_folder()

        if n == 0:
            messagebox.showinfo("ยกเลิก / ไม่มีฟ้อน", "ไม่มีฟ้อนที่ติดตั้งสำเร็จ")
            return
        preview = "\n".join(f"  • {x}" for x in names[:8])
        if len(names) > 8: preview += f"\n  ... และอีก {len(names)-8} ฟ้อน"
        messagebox.showinfo("ติดตั้งเสร็จแล้ว! ⚡",
            f"ติดตั้ง {n} ฟ้อนเข้า Windows เรียบร้อย!\n"
            f"พร้อมใช้งานทันทีใน Word, Photoshop, Figma\n\n{preview}")

    # ── URL Mode ────────────────────────────────────────────────
    def _start_url(self):
        if self.busy: return
        urls = self._get_urls()
        if not urls:
            messagebox.showwarning("ไม่พบลิงค์", "วางลิงค์อย่างน้อย 1 รายการ"); return
        save_path = self.save_dir.get()
        os.makedirs(save_path, exist_ok=True)
        self._clear_rows()
        self._hide_open_folder()
        self._stat_lbl.configure(text="0")    # reset counter each session
        for url in urls:
            ext = os.path.splitext(urlparse(url).path)[1].lower()
            row = ItemRow(self._scroll_container, url, ext)
            row.grid(sticky="ew", pady=(0, 3))
            row.columnconfigure(1, weight=1)
            self.rows.append(row)
        self.busy    = True
        self._cancel = False
        self._cancel_btn.configure(state="normal", text="🚫  ยกเลิก")
        self._last_open_path = save_path
        self._dl_btn.configure(text="⏳  กำลังดาวน์โหลด...", state="disabled",
                                fg_color="#3a1f8a")
        self._summary_lbl.configure(text=f"0 / {len(urls)} เสร็จ")
        threading.Thread(target=self._run_url, args=(urls, save_path), daemon=True).start()

    def _run_url(self, urls, save_path):
        done = 0; total = len(urls); installed = []

        def task(idx, url):
            nonlocal done
            row = self.rows[idx]
            if self._cancel:
                self.after(0, row.update, "cancelled", "ยกเลิกแล้ว", 0)
                done += 1
                self.after(0, self._summary_lbl.configure, {"text": f"{done}/{total} เสร็จ"})
                return
            self.after(0, row.update, "working", "กำลังเชื่อมต่อ...", 0)
            try:
                hdrs = {"User-Agent": "Mozilla/5.0 (FontZap)"}
                resp = requests.get(url, stream=True, timeout=30, headers=hdrs)
                resp.raise_for_status()
                fname = get_filename(url, resp)
                fpath = os.path.join(save_path, fname)
                base, ext = os.path.splitext(fname); c = 1
                while os.path.exists(fpath):
                    fpath = os.path.join(save_path, f"{base}_{c}{ext}"); c += 1
                fname = os.path.basename(fpath)
                total_size = int(resp.headers.get("content-length", 0))
                dl = 0; t0 = time.time()
                self.after(0, row.update, "working", f"⬇️ {fname}", 0, fname)
                with open(fpath, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        if self._cancel:
                            self.after(0, row.update, "cancelled", "ยกเลิกแล้ว", 0)
                            done += 1
                            self.after(0, self._summary_lbl.configure, {"text": f"{done}/{total} เสร็จ"})
                            return
                        if chunk:
                            f.write(chunk); dl += len(chunk)
                            if total_size:
                                pct = dl / total_size * 90
                                elapsed = time.time() - t0
                                spd = dl / elapsed if elapsed > 0 else 0
                                ss = f"{spd/1048576:.1f} MB/s" if spd > 1048576 else f"{spd/1024:.0f} KB/s"
                                self.after(0, row.update, "working",
                                           f"⬇️ {fname}  •  {ss}", pct, fname)
                self.after(0, row.update, "working", "⚙️ กำลังติดตั้ง...", 93)
                elow = os.path.splitext(fpath)[1].lower()
                if elow == ".zip":
                    fonts = extract_fonts_from_zip(fpath)
                    for fp in fonts:
                        d = install_font_to_windows(fp); installed.append(os.path.basename(d))
                    self.after(0, row.update, "done",
                               f"ติดตั้ง {len(fonts)} ฟ้อนจาก zip แล้ว!", 100, fname)
                elif elow in FONT_EXTS:
                    d = install_font_to_windows(fpath); installed.append(os.path.basename(d))
                    self.after(0, row.update, "done", "ดาวน์โหลด + ติดตั้งแล้ว! ⚡", 100, fname)
                else:
                    self.after(0, row.update, "done", f"บันทึกที่ {save_path}", 100, fname)
                done += 1
                self.after(0, self._summary_lbl.configure, {"text": f"{done}/{total} เสร็จ"})
                self.after(0, self._stat_lbl.configure, {"text": str(len(installed))})
            except requests.exceptions.Timeout:
                print(f"[FontZap] timeout: {url}")
                self.after(0, row.update, "error", "❗ Timeout — เชื่อมต่อนานเกินไป", 0)
                done += 1
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response else "?"
                print(f"[FontZap] HTTP {status}: {url}")
                self.after(0, row.update, "error", f"❗ HTTP {status} — ลิงค์ใช้ไม่ได้", 0)
                done += 1
            except Exception as e:
                print(f"[FontZap] download error: {e}  url={url}")
                self.after(0, row.update, "error", f"❗ {e}", 0)
                done += 1

        with ThreadPoolExecutor(max_workers=5) as ex:
            for f in as_completed([ex.submit(task, i, u) for i, u in enumerate(urls)]):
                _ = f.result()
        self.after(0, self._url_done, done, total, installed)

    def _url_done(self, done, total, installed):
        self.busy    = False
        self._cancel = False
        self._cancel_btn.configure(state="disabled", text="🚫  ยกเลิก")
        n = len(installed)
        msg = f"เสร็จสิ้น {done}/{total} รายการ"
        if n: msg += f"\n✅ ติดตั้ง {n} ฟ้อนเข้า Windows แล้ว!"
        self._dl_btn.configure(
            text="⬇️   ดาวน์โหลดและติดตั้งทั้งหมด",
            state="normal", fg_color=ACCENT, hover_color=ACCENT2
        )
        self._show_open_folder()
        messagebox.showinfo("เสร็จสิ้น! ⚡", msg)

    # ── Helpers ─────────────────────────────────────────────────
    def _cancel_task(self):
        """Set cancel flag — running threads will stop at next check point."""
        if self.busy:
            self._cancel = True
            self._cancel_btn.configure(state="disabled", text="⏳ กำลังยกเลิก...")

    def _show_open_folder(self):
        self._open_folder_btn.grid(row=0, column=3, padx=(0, 0))

    def _hide_open_folder(self):
        self._open_folder_btn.grid_remove()

    def _open_last_folder(self):
        path = self._last_open_path
        if not path:
            path = self.save_dir.get()
        os.makedirs(path, exist_ok=True)
        subprocess.Popen(["explorer", os.path.normpath(path)])

    def _clear_urls(self): self._url_box.delete("1.0", "end")
    def _paste_clip(self):
        try: self._url_box.insert("end", self.clipboard_get() + "\n")
        except: pass
    def _browse(self):
        d = filedialog.askdirectory(title="เลือกโฟลเดอร์บันทึก")
        if d: self.save_dir.set(d)
    def _get_urls(self):
        raw = self._url_box.get("1.0", "end")
        return list(dict.fromkeys(
            l.strip() for l in raw.splitlines()
            if l.strip() and not l.strip().startswith("#") and l.strip().startswith("http")
        ))
    def _clear_rows(self):
        for w in self._scroll_container.winfo_children(): w.destroy()
        self.rows.clear()


if __name__ == "__main__":
    app = FontZapApp()
    app.mainloop()
