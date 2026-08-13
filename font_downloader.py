# FontZap — Font Bulk Downloader
# GitHub: https://github.com/porchyy/-FontZap-
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import threading
import requests
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, unquote

# ─── Theme Setup ───────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ─── Color Palette ─────────────────────────────────────────────
BG_DARK       = "#0f0f1a"
BG_CARD       = "#1a1a2e"
BG_INPUT      = "#16213e"
ACCENT        = "#7c3aed"
ACCENT_HOVER  = "#6d28d9"
ACCENT_LIGHT  = "#a78bfa"
SUCCESS       = "#10b981"
ERROR         = "#ef4444"
WARNING       = "#f59e0b"
TEXT_PRIMARY  = "#f1f5f9"
TEXT_MUTED    = "#94a3b8"
BORDER        = "#2d2d4e"
DROP_ACTIVE   = "#2d1b69"
DROP_BORDER   = "#7c3aed"

FONT_EXTENSIONS = {".ttf", ".otf", ".zip", ".woff", ".woff2", ".eot", ".fon"}


def get_filename_from_url(url, response=None):
    """ดึงชื่อไฟล์จาก Content-Disposition header หรือ URL"""
    if response:
        cd = response.headers.get("Content-Disposition", "")
        match = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\'\n;]+)', cd, re.IGNORECASE)
        if match:
            name = unquote(match.group(1).strip())
            if name:
                return name
    parsed = urlparse(url)
    name = unquote(os.path.basename(parsed.path))
    if not name or "." not in name:
        name = f"font_{int(time.time())}.ttf"
    return name


def parse_drop_data(data: str) -> list[str]:
    """แยก path ไฟล์จาก drag-and-drop data (รองรับ path ที่มีช่องว่าง)"""
    paths = []
    # tkinterdnd2 returns paths wrapped in {} if they contain spaces
    for match in re.finditer(r'\{([^}]+)\}|(\S+)', data):
        path = match.group(1) or match.group(2)
        if path:
            paths.append(path.strip())
    return paths


# ─────────────────────────────────────────────────────────────
#  Download Row
# ─────────────────────────────────────────────────────────────

class DownloadRow(ctk.CTkFrame):
    STATUS_ICONS = {
        "waiting":      ("⏳", TEXT_MUTED),
        "downloading":  ("⬇️", ACCENT_LIGHT),
        "copying":      ("📋", ACCENT_LIGHT),
        "done":         ("✅", SUCCESS),
        "error":        ("❌", ERROR),
    }

    def __init__(self, parent, label, **kwargs):
        super().__init__(parent, fg_color=BG_INPUT, corner_radius=10, **kwargs)
        self.configure(border_width=1, border_color=BORDER)
        self.grid_columnconfigure(1, weight=1)

        self.icon_label = ctk.CTkLabel(self, text="⏳", width=30, font=ctk.CTkFont(size=16))
        self.icon_label.grid(row=0, column=0, padx=(12, 4), pady=10)

        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=0, column=1, padx=4, pady=10, sticky="ew")
        info_frame.grid_columnconfigure(0, weight=1)

        short = label if len(label) <= 55 else "…" + label[-52:]
        self.name_label = ctk.CTkLabel(
            info_frame, text=short,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_PRIMARY, anchor="w"
        )
        self.name_label.grid(row=0, column=0, sticky="ew")

        self.status_label = ctk.CTkLabel(
            info_frame, text="รอดาวน์โหลด...",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED, anchor="w"
        )
        self.status_label.grid(row=1, column=0, sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(
            info_frame, height=6, progress_color=ACCENT,
            fg_color=BORDER, corner_radius=3
        )
        self.progress_bar.set(0)
        self.progress_bar.grid(row=2, column=0, sticky="ew", pady=(4, 0))

        self.pct_label = ctk.CTkLabel(
            self, text="0%", width=45,
            font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED
        )
        self.pct_label.grid(row=0, column=2, padx=(4, 12), pady=10)

    def update_status(self, status, text="", percent=0, filename=None):
        icon, color = self.STATUS_ICONS.get(status, ("❓", TEXT_MUTED))
        self.icon_label.configure(text=icon)
        self.status_label.configure(text=text, text_color=color)
        self.progress_bar.set(percent / 100)
        self.pct_label.configure(text=f"{percent:.0f}%", text_color=color)
        if filename:
            short = filename if len(filename) <= 55 else "…" + filename[-52:]
            self.name_label.configure(text=short)
        colors = {"downloading": ACCENT, "copying": ACCENT, "done": SUCCESS, "error": ERROR}
        self.progress_bar.configure(progress_color=colors.get(status, ACCENT))


# ─────────────────────────────────────────────────────────────
#  Drop Zone Widget
# ─────────────────────────────────────────────────────────────

class DropZone(ctk.CTkFrame):
    """พื้นที่ลากวางไฟล์ฟ้อน"""

    def __init__(self, parent, on_drop_files, on_drop_urls, **kwargs):
        super().__init__(parent, fg_color=BG_INPUT, corner_radius=14,
                         border_width=2, border_color=BORDER, **kwargs)
        self.on_drop_files = on_drop_files
        self.on_drop_urls  = on_drop_urls
        self._build()
        self._register_dnd()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        self.icon_lbl = ctk.CTkLabel(
            self, text="📂", font=ctk.CTkFont(size=36)
        )
        self.icon_lbl.grid(row=0, column=0, pady=(20, 4))

        self.main_lbl = ctk.CTkLabel(
            self, text="ลากไฟล์มาวางที่นี่",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT_PRIMARY
        )
        self.main_lbl.grid(row=1, column=0, pady=(0, 4))

        self.sub_lbl = ctk.CTkLabel(
            self,
            text="🖋️ ไฟล์ฟ้อน (.ttf .otf .zip .woff ฯลฯ)  •  📄 ไฟล์ .txt ที่มีลิงค์",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        )
        self.sub_lbl.grid(row=2, column=0, pady=(0, 20))

    def _register_dnd(self):
        for widget in [self, self.icon_lbl, self.main_lbl, self.sub_lbl]:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<DropEnter>>", self._on_enter)
            widget.dnd_bind("<<DropLeave>>", self._on_leave)
            widget.dnd_bind("<<Drop>>",      self._on_drop)

    def _on_enter(self, event):
        self.configure(fg_color=DROP_ACTIVE, border_color=DROP_BORDER)
        self.main_lbl.configure(text="วางไฟล์ได้เลย! ⚡")

    def _on_leave(self, event):
        self.configure(fg_color=BG_INPUT, border_color=BORDER)
        self.main_lbl.configure(text="ลากไฟล์มาวางที่นี่")

    def _on_drop(self, event):
        self.configure(fg_color=BG_INPUT, border_color=BORDER)
        self.main_lbl.configure(text="ลากไฟล์มาวางที่นี่")

        paths = parse_drop_data(event.data)
        font_files, txt_files = [], []

        for p in paths:
            ext = os.path.splitext(p)[1].lower()
            if ext in FONT_EXTENSIONS:
                font_files.append(p)
            elif ext == ".txt":
                txt_files.append(p)

        if font_files:
            self.on_drop_files(font_files)
        if txt_files:
            self.on_drop_urls(txt_files)
        if not font_files and not txt_files:
            messagebox.showwarning(
                "ไฟล์ไม่รองรับ",
                "กรุณาลากไฟล์ฟ้อน (.ttf .otf .zip ฯลฯ)\nหรือไฟล์ .txt ที่มีลิงค์ดาวน์โหลด"
            )


# ─────────────────────────────────────────────────────────────
#  Main App
# ─────────────────────────────────────────────────────────────

class FontDownloaderApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)

        self.title("⚡ FontZap — Font Bulk Downloader")
        self.geometry("740x900")
        self.minsize(640, 680)
        self.configure(fg_color=BG_DARK)

        self.save_dir = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Downloads", "Fonts")
        )
        self.download_rows: list[DownloadRow] = []
        self.is_downloading = False

        self._build_ui()

    # ─────────────────────────────────────────────────────────
    #  UI Building
    # ─────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        # ── Header ──────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=80)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        header.grid_propagate(False)

        ctk.CTkLabel(
            header, text="⚡  FontZap",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=ACCENT_LIGHT
        ).grid(row=0, column=0, padx=24, pady=(18, 0), sticky="w")

        ctk.CTkLabel(
            header,
            text="⚡ โหลดฟ้อนหลายอันพร้อมกัน — วางลิงค์หรือลากไฟล์มาเลย!",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED
        ).grid(row=1, column=0, padx=24, pady=(2, 14), sticky="w")

        # ── Tab Switcher ────────────────────────────────────
        tab_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=44)
        tab_frame.grid(row=1, column=0, sticky="ew")
        tab_frame.grid_columnconfigure((0, 1), weight=1)
        tab_frame.grid_propagate(False)

        self.tab_url_btn = ctk.CTkButton(
            tab_frame, text="🔗  วางลิงค์", height=36,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=0, command=lambda: self._switch_tab("url")
        )
        self.tab_url_btn.grid(row=0, column=0, sticky="ew", padx=(0, 1))

        self.tab_drop_btn = ctk.CTkButton(
            tab_frame, text="📂  ลากไฟล์", height=36,
            fg_color=BORDER, hover_color="#3d3d5c",
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=0, command=lambda: self._switch_tab("drop")
        )
        self.tab_drop_btn.grid(row=0, column=1, sticky="ew")

        # ── URL Panel ───────────────────────────────────────
        self.url_panel = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                                       border_width=1, border_color=BORDER)
        self.url_panel.grid(row=2, column=0, padx=16, pady=(10, 0), sticky="ew")
        self.url_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.url_panel, text="📋  วางลิงค์ดาวน์โหลดฟ้อน",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_PRIMARY
        ).grid(row=0, column=0, padx=18, pady=(14, 4), sticky="w")

        ctk.CTkLabel(
            self.url_panel,
            text="ใส่ URL ทีละบรรทัด รองรับ .ttf .otf .zip .woff .woff2 และอื่นๆ",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        ).grid(row=1, column=0, padx=18, pady=(0, 6), sticky="w")

        self.url_textbox = ctk.CTkTextbox(
            self.url_panel, height=140,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=BG_INPUT, text_color=TEXT_PRIMARY,
            border_color=BORDER, border_width=1, corner_radius=8,
            scrollbar_button_color=BORDER
        )
        self.url_textbox.grid(row=2, column=0, padx=18, pady=(0, 6), sticky="ew")
        self.url_textbox.insert("end", "# วางลิงค์ที่นี่ ทีละบรรทัด เช่น:\n# https://example.com/myfont.ttf\n# https://example.com/fonts.zip\n")

        # Register URL textbox as drop target for .txt files too
        self.url_textbox.drop_target_register(DND_FILES)
        self.url_textbox.dnd_bind("<<Drop>>", self._on_textbox_drop)

        btn_row = ctk.CTkFrame(self.url_panel, fg_color="transparent")
        btn_row.grid(row=3, column=0, padx=18, pady=(0, 14), sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            btn_row, text="🗑️ ล้าง", width=80, height=30,
            fg_color=BORDER, hover_color="#3d3d5c", text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12), corner_radius=6,
            command=self._clear_urls
        ).grid(row=0, column=1, padx=(8, 0))

        ctk.CTkButton(
            btn_row, text="📋 วาง", width=80, height=30,
            fg_color=BORDER, hover_color="#3d3d5c", text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12), corner_radius=6,
            command=self._paste_clipboard
        ).grid(row=0, column=2, padx=(8, 0))

        # ── Drop Panel ──────────────────────────────────────
        self.drop_panel = DropZone(
            self,
            on_drop_files=self._handle_dropped_fonts,
            on_drop_urls=self._handle_dropped_txt
        )
        self.drop_panel.grid(row=2, column=0, padx=16, pady=(10, 0), sticky="ew")
        self.drop_panel.grid_remove()   # hidden by default

        # ── Save Folder Row ─────────────────────────────────
        folder_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                                    border_width=1, border_color=BORDER)
        folder_card.grid(row=3, column=0, padx=16, pady=(10, 0), sticky="ew")
        folder_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(folder_card, text="📁", font=ctk.CTkFont(size=18), width=36
                     ).grid(row=0, column=0, padx=(14, 4), pady=12)

        ctk.CTkLabel(
            folder_card, textvariable=self.save_dir,
            font=ctk.CTkFont(size=12), text_color=ACCENT_LIGHT, anchor="w"
        ).grid(row=0, column=1, padx=4, pady=12, sticky="ew")

        ctk.CTkButton(
            folder_card, text="เปลี่ยน", width=80, height=30,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white",
            font=ctk.CTkFont(size=12, weight="bold"), corner_radius=6,
            command=self._browse_folder
        ).grid(row=0, column=2, padx=(4, 14), pady=12)

        # ── Download Button ──────────────────────────────────
        self.dl_button = ctk.CTkButton(
            self, text="⬇️   ดาวน์โหลดทั้งหมด", height=52,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white",
            corner_radius=12, command=self._start_download
        )
        self.dl_button.grid(row=4, column=0, padx=16, pady=(12, 0), sticky="ew")

        # ── Progress Area ────────────────────────────────────
        progress_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                                      border_width=1, border_color=BORDER)
        progress_card.grid(row=5, column=0, padx=16, pady=(10, 0), sticky="nsew")
        progress_card.grid_columnconfigure(0, weight=1)
        progress_card.grid_rowconfigure(1, weight=1)

        prog_header = ctk.CTkFrame(progress_card, fg_color="transparent")
        prog_header.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")
        prog_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            prog_header, text="📊  สถานะการดาวน์โหลด",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_PRIMARY
        ).grid(row=0, column=0, sticky="w")

        self.summary_label = ctk.CTkLabel(
            prog_header, text="",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        )
        self.summary_label.grid(row=0, column=1, sticky="e")

        self.rows_frame = ctk.CTkScrollableFrame(
            progress_card, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=ACCENT
        )
        self.rows_frame.grid(row=1, column=0, padx=8, pady=(0, 12), sticky="nsew")
        self.rows_frame.grid_columnconfigure(0, weight=1)

        self._placeholder = ctk.CTkLabel(
            self.rows_frame,
            text="ยังไม่มีการดาวน์โหลด\nวางลิงค์หรือลากไฟล์มาเพื่อเริ่ม ⚡",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED, justify="center"
        )
        self._placeholder.grid(row=0, column=0, pady=40)

        # ── Footer ───────────────────────────────────────────
        footer = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=36)
        footer.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        footer.grid_propagate(False)
        ctk.CTkLabel(
            footer,
            text="⚡ FontZap  •  รองรับ .ttf .otf .zip .woff .woff2  •  github.com/porchyy/-FontZap-",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        ).grid(row=0, column=0, padx=20, pady=8)

        self._current_tab = "url"

    # ─────────────────────────────────────────────────────────
    #  Tab Switching
    # ─────────────────────────────────────────────────────────

    def _switch_tab(self, tab: str):
        if tab == "url":
            self.url_panel.grid()
            self.drop_panel.grid_remove()
            self.dl_button.configure(text="⬇️   ดาวน์โหลดทั้งหมด", state="normal")
            self.tab_url_btn.configure(fg_color=ACCENT)
            self.tab_drop_btn.configure(fg_color=BORDER)
        else:
            self.url_panel.grid_remove()
            self.drop_panel.grid()
            self.dl_button.configure(
                text="📂  ลากไฟล์ฟ้อนมาวางในกรอบด้านบน", state="disabled",
                fg_color="#4a4a6a"
            )
            self.tab_url_btn.configure(fg_color=BORDER)
            self.tab_drop_btn.configure(fg_color=ACCENT)
        self._current_tab = tab

    # ─────────────────────────────────────────────────────────
    #  Drag & Drop Handlers
    # ─────────────────────────────────────────────────────────

    def _on_textbox_drop(self, event):
        """รองรับลาก .txt ไฟล์มาวางใน URL textbox"""
        paths = parse_drop_data(event.data)
        for p in paths:
            if p.lower().endswith(".txt"):
                self._load_urls_from_txt(p)

    def _handle_dropped_fonts(self, paths: list[str]):
        """ลากไฟล์ฟ้อนโดยตรง → คัดลอกไปยังโฟลเดอร์ที่เลือก"""
        save_path = self.save_dir.get()
        os.makedirs(save_path, exist_ok=True)

        # clear rows
        self._clear_rows()
        for i, path in enumerate(paths):
            row = DownloadRow(self.rows_frame, os.path.basename(path))
            row.grid(row=i, column=0, padx=4, pady=4, sticky="ew")
            self.download_rows.append(row)

        self.summary_label.configure(text=f"0 / {len(paths)} เสร็จ")

        def copy_task():
            done = 0
            total = len(paths)
            for i, src in enumerate(paths):
                row = self.download_rows[i]
                fname = os.path.basename(src)
                self.after(0, row.update_status, "copying", f"กำลังคัดลอก: {fname}", 50, fname)
                try:
                    dst = os.path.join(save_path, fname)
                    base, ext = os.path.splitext(fname)
                    counter = 1
                    while os.path.exists(dst):
                        dst = os.path.join(save_path, f"{base}_{counter}{ext}")
                        counter += 1
                    shutil.copy2(src, dst)
                    size_kb = os.path.getsize(dst) / 1024
                    done += 1
                    self.after(0, row.update_status, "done",
                               f"คัดลอกเสร็จ! {size_kb:.0f} KB", 100, os.path.basename(dst))
                except Exception as e:
                    done += 1
                    self.after(0, row.update_status, "error", f"❌ {str(e)[:60]}", 0)
                self.after(0, self.summary_label.configure, {"text": f"{done} / {total} เสร็จ"})
            self.after(0, self._on_copy_done, done, total, save_path)

        threading.Thread(target=copy_task, daemon=True).start()

    def _handle_dropped_txt(self, txt_paths: list[str]):
        """ลาก .txt ที่มีลิงค์ → โหลด URL เข้า textbox แล้วสลับไปแท็บ URL"""
        for path in txt_paths:
            self._load_urls_from_txt(path)
        self._switch_tab("url")

    def _load_urls_from_txt(self, path: str):
        """อ่าน URL จากไฟล์ .txt แล้วใส่ใน textbox"""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            self.url_textbox.delete("1.0", "end")
            self.url_textbox.insert("end", content)
        except Exception as e:
            messagebox.showerror("อ่านไฟล์ไม่ได้", str(e))

    def _on_copy_done(self, done: int, total: int, save_path: str):
        msg = f"คัดลอกเสร็จสิ้น {done}/{total} ไฟล์\n📁 บันทึกที่: {save_path}"
        messagebox.showinfo("เสร็จสิ้น!", msg)

    # ─────────────────────────────────────────────────────────
    #  URL Mode Helpers
    # ─────────────────────────────────────────────────────────

    def _clear_urls(self):
        self.url_textbox.delete("1.0", "end")

    def _paste_clipboard(self):
        try:
            self.url_textbox.insert("end", self.clipboard_get() + "\n")
        except Exception:
            pass

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="เลือกโฟลเดอร์บันทึกฟ้อน")
        if folder:
            self.save_dir.set(folder)

    def _get_urls(self) -> list[str]:
        raw = self.url_textbox.get("1.0", "end")
        urls = []
        for line in raw.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith("http"):
                urls.append(line)
        return list(dict.fromkeys(urls))

    def _clear_rows(self):
        for w in self.rows_frame.winfo_children():
            w.destroy()
        self.download_rows.clear()
        self._placeholder = None

    # ─────────────────────────────────────────────────────────
    #  Download Logic (URL Mode)
    # ─────────────────────────────────────────────────────────

    def _start_download(self):
        if self.is_downloading:
            return
        urls = self._get_urls()
        if not urls:
            messagebox.showwarning("ไม่พบลิงค์", "กรุณาวางลิงค์ดาวน์โหลดอย่างน้อย 1 รายการ")
            return

        save_path = self.save_dir.get()
        os.makedirs(save_path, exist_ok=True)

        self._clear_rows()
        for i, url in enumerate(urls):
            row = DownloadRow(self.rows_frame, url)
            row.grid(row=i, column=0, padx=4, pady=4, sticky="ew")
            self.download_rows.append(row)

        self.is_downloading = True
        self.dl_button.configure(text="⏳  กำลังดาวน์โหลด...", state="disabled", fg_color="#4a4a6a")
        self.summary_label.configure(text=f"0 / {len(urls)} เสร็จ")

        threading.Thread(target=self._run_downloads, args=(urls, save_path), daemon=True).start()

    def _run_downloads(self, urls: list[str], save_path: str):
        done = 0
        total = len(urls)

        def task(idx: int, url: str):
            nonlocal done
            row = self.download_rows[idx]
            self.after(0, row.update_status, "downloading", "กำลังเชื่อมต่อ...", 0)
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Font Downloader)"}
                resp = requests.get(url, stream=True, timeout=30, headers=headers)
                resp.raise_for_status()

                filename = get_filename_from_url(url, resp)
                filepath = os.path.join(save_path, filename)
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(filepath):
                    filepath = os.path.join(save_path, f"{base}_{counter}{ext}")
                    counter += 1
                filename = os.path.basename(filepath)

                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                start_t = time.time()
                self.after(0, row.update_status, "downloading", f"ดาวน์โหลด: {filename}", 0, filename)

                with open(filepath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size:
                                pct = downloaded / total_size * 100
                                elapsed = time.time() - start_t
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                speed_str = (f"{speed/1048576:.1f} MB/s"
                                             if speed > 1048576 else f"{speed/1024:.0f} KB/s")
                                self.after(0, row.update_status, "downloading",
                                           f"{filename}  •  {speed_str}", pct, filename)
                            else:
                                mb = downloaded / 1048576
                                self.after(0, row.update_status, "downloading",
                                           f"{filename}  •  {mb:.1f} MB", 1, filename)

                done += 1
                size_kb = os.path.getsize(filepath) / 1024
                self.after(0, row.update_status, "done",
                           f"เสร็จ! {size_kb:.0f} KB  •  {filename}", 100, filename)
                self.after(0, self.summary_label.configure, {"text": f"{done} / {total} เสร็จ"})

            except requests.exceptions.Timeout:
                self.after(0, row.update_status, "error", "❌ Timeout — ลิงค์ใช้เวลานานเกินไป", 0)
                done += 1
            except requests.exceptions.HTTPError as e:
                self.after(0, row.update_status, "error",
                           f"❌ HTTP Error {e.response.status_code}", 0)
                done += 1
            except Exception as e:
                self.after(0, row.update_status, "error", f"❌ {str(e)[:60]}", 0)
                done += 1

        with ThreadPoolExecutor(max_workers=5) as executor:
            for f in as_completed([executor.submit(task, i, u) for i, u in enumerate(urls)]):
                _ = f.result()

        self.after(0, self._on_done, done, total)

    def _on_done(self, done: int, total: int):
        self.is_downloading = False
        color = SUCCESS if done == total else WARNING
        self.dl_button.configure(
            text=f"✅  เสร็จแล้ว {done}/{total} ไฟล์  —  ดาวน์โหลดอีกครั้ง",
            state="normal", fg_color=color
        )
        self.summary_label.configure(text=f"{done} / {total} เสร็จสมบูรณ์")
        save_path = self.save_dir.get()
        msg = f"ดาวน์โหลดเสร็จสิ้น {done}/{total} ไฟล์\n📁 บันทึกที่: {save_path}"
        if done < total:
            msg += f"\n\n⚠️ มี {total - done} ไฟล์ที่ดาวน์โหลดไม่สำเร็จ"
        messagebox.showinfo("เสร็จสิ้น!", msg)
        self.dl_button.configure(
            text="⬇️   ดาวน์โหลดทั้งหมด",
            fg_color=ACCENT, hover_color=ACCENT_HOVER
        )


# ─── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":
    app = FontDownloaderApp()
    app.mainloop()
