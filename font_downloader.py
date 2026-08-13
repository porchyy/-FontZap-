# FontZap — Font Bulk Downloader + Auto Installer
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
import zipfile
import ctypes
import winreg
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, unquote

# ─── Theme ─────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG_DARK      = "#0f0f1a"
BG_CARD      = "#1a1a2e"
BG_INPUT     = "#16213e"
ACCENT       = "#7c3aed"
ACCENT_HOVER = "#6d28d9"
ACCENT_LIGHT = "#a78bfa"
SUCCESS      = "#10b981"
ERROR        = "#ef4444"
WARNING      = "#f59e0b"
TEXT_PRIMARY = "#f1f5f9"
TEXT_MUTED   = "#94a3b8"
BORDER       = "#2d2d4e"
DROP_ACTIVE  = "#1e1245"
DROP_BORDER  = "#7c3aed"

FONT_EXTS = {".ttf", ".otf", ".woff", ".woff2", ".eot", ".fon"}

# โฟลเดอร์ฟ้อนของ User (ไม่ต้องการสิทธิ์ Admin)
USER_FONTS_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Microsoft", "Windows", "Fonts"
)


# ──────────────────────────────────────────────────────────────
#  Font Installation
# ──────────────────────────────────────────────────────────────

def install_font_to_windows(src_path: str) -> str:
    """ติดตั้งฟ้อนเข้า Windows (User Fonts — ไม่ต้อง Admin)"""
    os.makedirs(USER_FONTS_DIR, exist_ok=True)
    fname = os.path.basename(src_path)
    dest  = os.path.join(USER_FONTS_DIR, fname)

    # ถ้าชื่อซ้ำให้เพิ่มเลข
    base, ext = os.path.splitext(fname)
    c = 1
    while os.path.exists(dest) and not _same_file(src_path, dest):
        dest = os.path.join(USER_FONTS_DIR, f"{base}_{c}{ext}")
        c += 1

    shutil.copy2(src_path, dest)

    # ลงทะเบียนใน Registry
    try:
        reg = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(reg, os.path.basename(dest), 0, winreg.REG_SZ, dest)
        winreg.CloseKey(reg)
    except Exception:
        pass

    # แจ้ง Windows ให้โหลดฟ้อนใหม่ทันที
    try:
        ctypes.windll.gdi32.AddFontResourceExW(dest, 0x10, 0)
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001D, 0, 0, 0x0002, 1000, None
        )
    except Exception:
        pass

    return dest


def _same_file(a, b):
    try:
        return os.path.getsize(a) == os.path.getsize(b)
    except Exception:
        return False


def extract_fonts_from_zip(zip_path: str) -> list[str]:
    """แตกไฟล์ zip และคืนรายการ path ของไฟล์ฟ้อน"""
    tmp = os.path.join(os.environ.get("TEMP", "."), f"fontzap_{int(time.time())}")
    os.makedirs(tmp, exist_ok=True)
    found = []
    with zipfile.ZipFile(zip_path, "r") as z:
        for name in z.namelist():
            if os.path.splitext(name)[1].lower() in FONT_EXTS:
                z.extract(name, tmp)
                found.append(os.path.join(tmp, name))
    return found


def get_filename_from_url(url, response=None):
    if response:
        cd = response.headers.get("Content-Disposition", "")
        m  = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\'\n;]+)', cd, re.IGNORECASE)
        if m:
            n = unquote(m.group(1).strip())
            if n:
                return n
    parsed = urlparse(url)
    name   = unquote(os.path.basename(parsed.path))
    return name if name and "." in name else f"font_{int(time.time())}.ttf"


def parse_drop_data(data: str) -> list[str]:
    paths = []
    for m in re.finditer(r'\{([^}]+)\}|(\S+)', data):
        p = (m.group(1) or m.group(2)).strip()
        if p:
            paths.append(p)
    return paths


# ──────────────────────────────────────────────────────────────
#  Download / Install Row Widget
# ──────────────────────────────────────────────────────────────

class ItemRow(ctk.CTkFrame):
    ICONS = {
        "waiting":     ("⏳", TEXT_MUTED),
        "working":     ("⚙️", ACCENT_LIGHT),
        "done":        ("✅", SUCCESS),
        "error":       ("❌", ERROR),
    }

    def __init__(self, parent, label: str, **kwargs):
        super().__init__(parent, fg_color=BG_INPUT, corner_radius=10,
                         border_width=1, border_color=BORDER, **kwargs)
        self.grid_columnconfigure(1, weight=1)

        self.icon_lbl = ctk.CTkLabel(self, text="⏳", width=30,
                                      font=ctk.CTkFont(size=16))
        self.icon_lbl.grid(row=0, column=0, padx=(12, 4), pady=10)

        info = ctk.CTkFrame(self, fg_color="transparent")
        info.grid(row=0, column=1, padx=4, pady=10, sticky="ew")
        info.grid_columnconfigure(0, weight=1)

        short = label if len(label) <= 55 else "…" + label[-52:]
        self.name_lbl = ctk.CTkLabel(
            info, text=short,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_PRIMARY, anchor="w"
        )
        self.name_lbl.grid(row=0, column=0, sticky="ew")

        self.status_lbl = ctk.CTkLabel(
            info, text="รอ...", font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED, anchor="w"
        )
        self.status_lbl.grid(row=1, column=0, sticky="ew")

        self.bar = ctk.CTkProgressBar(
            info, height=6, progress_color=ACCENT,
            fg_color=BORDER, corner_radius=3
        )
        self.bar.set(0)
        self.bar.grid(row=2, column=0, sticky="ew", pady=(4, 0))

        self.pct_lbl = ctk.CTkLabel(
            self, text="0%", width=45,
            font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED
        )
        self.pct_lbl.grid(row=0, column=2, padx=(4, 12), pady=10)

    def update(self, status: str, text: str = "", pct: float = 0, name: str = None):
        icon, color = self.ICONS.get(status, ("❓", TEXT_MUTED))
        self.icon_lbl.configure(text=icon)
        self.status_lbl.configure(text=text, text_color=color)
        self.bar.set(pct / 100)
        self.pct_lbl.configure(text=f"{pct:.0f}%", text_color=color)
        if name:
            short = name if len(name) <= 55 else "…" + name[-52:]
            self.name_lbl.configure(text=short)
        bar_colors = {"working": ACCENT, "done": SUCCESS, "error": ERROR}
        self.bar.configure(progress_color=bar_colors.get(status, ACCENT))


# ──────────────────────────────────────────────────────────────
#  Drop Zone
# ──────────────────────────────────────────────────────────────

class DropZone(ctk.CTkFrame):
    def __init__(self, parent, on_drop, **kwargs):
        super().__init__(parent, fg_color=BG_INPUT, corner_radius=16,
                         border_width=2, border_color=BORDER, **kwargs)
        self.on_drop = on_drop
        self._build()
        self._setup_dnd()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        self.icon = ctk.CTkLabel(self, text="📂", font=ctk.CTkFont(size=48))
        self.icon.grid(row=0, column=0, pady=(28, 6))

        self.title = ctk.CTkLabel(
            self, text="ลากไฟล์ฟ้อนมาวางที่นี่",
            font=ctk.CTkFont(size=17, weight="bold"), text_color=TEXT_PRIMARY
        )
        self.title.grid(row=1, column=0, pady=(0, 6))

        self.sub = ctk.CTkLabel(
            self,
            text="รองรับ .ttf  .otf  .zip  .woff  .woff2\nและจะติดตั้งเข้า Windows ให้อัตโนมัติเลย ⚡",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED, justify="center"
        )
        self.sub.grid(row=2, column=0, pady=(0, 28))

    def _setup_dnd(self):
        for w in [self, self.icon, self.title, self.sub]:
            w.drop_target_register(DND_FILES)
            w.dnd_bind("<<DropEnter>>", self._enter)
            w.dnd_bind("<<DropLeave>>", self._leave)
            w.dnd_bind("<<Drop>>",      self._drop)

    def _enter(self, _):
        self.configure(fg_color=DROP_ACTIVE, border_color=DROP_BORDER)
        self.title.configure(text="วางได้เลย! ⚡")
        self.icon.configure(text="✨")

    def _leave(self, _):
        self.configure(fg_color=BG_INPUT, border_color=BORDER)
        self.title.configure(text="ลากไฟล์ฟ้อนมาวางที่นี่")
        self.icon.configure(text="📂")

    def _drop(self, event):
        self._leave(None)
        paths = parse_drop_data(event.data)
        self.on_drop(paths)


# ──────────────────────────────────────────────────────────────
#  Main App
# ──────────────────────────────────────────────────────────────

class FontZapApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)

        self.title("⚡ FontZap — Font Installer & Downloader")
        self.geometry("740x920")
        self.minsize(640, 700)
        self.configure(fg_color=BG_DARK)

        self.save_dir     = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Downloads", "Fonts")
        )
        self.rows: list[ItemRow] = []
        self.busy = False
        self._current_tab = "drop"

        self._build_ui()
        self._switch_tab("drop")   # เปิดหน้า Drop ก่อน

    # ──────────────────────────────────────────────────────────
    #  Build UI
    # ──────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=80)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)
        hdr.grid_propagate(False)

        ctk.CTkLabel(
            hdr, text="⚡  FontZap",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=ACCENT_LIGHT
        ).grid(row=0, column=0, padx=24, pady=(18, 0), sticky="w")

        ctk.CTkLabel(
            hdr, text="ลากไฟล์ฟ้อนมาวาง — ติดตั้งเข้า Windows ให้อัตโนมัติทันที",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED
        ).grid(row=1, column=0, padx=24, pady=(2, 14), sticky="w")

        # Tab Bar
        tabs = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=44)
        tabs.grid(row=1, column=0, sticky="ew")
        tabs.grid_columnconfigure((0, 1), weight=1)
        tabs.grid_propagate(False)

        self.btn_drop = ctk.CTkButton(
            tabs, text="📂  ลากไฟล์ (Auto Install)", height=36,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=0, command=lambda: self._switch_tab("drop")
        )
        self.btn_drop.grid(row=0, column=0, sticky="ew", padx=(0, 1))

        self.btn_url = ctk.CTkButton(
            tabs, text="🔗  วางลิงค์ (Download)", height=36,
            fg_color=BORDER, hover_color="#3d3d5c",
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=0, command=lambda: self._switch_tab("url")
        )
        self.btn_url.grid(row=0, column=1, sticky="ew")

        # ── Drop Panel ──────────────────────────────────────
        self.drop_panel = DropZone(self, on_drop=self._on_files_dropped)
        self.drop_panel.grid(row=2, column=0, padx=16, pady=(14, 0), sticky="ew")

        # ── URL Panel ───────────────────────────────────────
        self.url_panel = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                                       border_width=1, border_color=BORDER)
        self.url_panel.grid(row=2, column=0, padx=16, pady=(14, 0), sticky="ew")
        self.url_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.url_panel, text="📋  วางลิงค์ดาวน์โหลดฟ้อน",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_PRIMARY
        ).grid(row=0, column=0, padx=18, pady=(14, 4), sticky="w")

        ctk.CTkLabel(
            self.url_panel, text="ใส่ URL ทีละบรรทัด  •  ฟ้อนจะถูกดาวน์โหลดและติดตั้งเข้า Windows ให้เลย",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        ).grid(row=1, column=0, padx=18, pady=(0, 6), sticky="w")

        self.url_box = ctk.CTkTextbox(
            self.url_panel, height=130,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=BG_INPUT, text_color=TEXT_PRIMARY,
            border_color=BORDER, border_width=1, corner_radius=8
        )
        self.url_box.grid(row=2, column=0, padx=18, pady=(0, 8), sticky="ew")
        self.url_box.insert("end", "# วางลิงค์ที่นี่ ทีละบรรทัด:\n# https://example.com/font.ttf\n# https://example.com/fonts.zip\n")

        br = ctk.CTkFrame(self.url_panel, fg_color="transparent")
        br.grid(row=3, column=0, padx=18, pady=(0, 14), sticky="ew")
        br.grid_columnconfigure(0, weight=1)

        for col, (txt, cmd) in enumerate([
            ("🗑️ ล้าง", self._clear_urls),
            ("📋 วาง",  self._paste_clip),
        ]):
            ctk.CTkButton(
                br, text=txt, width=80, height=30,
                fg_color=BORDER, hover_color="#3d3d5c", text_color=TEXT_MUTED,
                font=ctk.CTkFont(size=12), corner_radius=6, command=cmd
            ).grid(row=0, column=col + 1, padx=(8, 0))

        # ── Save folder (URL mode only) ─────────────────────
        self.folder_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                                         border_width=1, border_color=BORDER)
        self.folder_card.grid(row=3, column=0, padx=16, pady=(10, 0), sticky="ew")
        self.folder_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.folder_card, text="📁", font=ctk.CTkFont(size=18), width=36
                     ).grid(row=0, column=0, padx=(14, 4), pady=12)
        ctk.CTkLabel(
            self.folder_card, textvariable=self.save_dir,
            font=ctk.CTkFont(size=12), text_color=ACCENT_LIGHT, anchor="w"
        ).grid(row=0, column=1, padx=4, pady=12, sticky="ew")
        ctk.CTkButton(
            self.folder_card, text="เปลี่ยน", width=80, height=30,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white",
            font=ctk.CTkFont(size=12, weight="bold"), corner_radius=6,
            command=self._browse_folder
        ).grid(row=0, column=2, padx=(4, 14), pady=12)

        # ── Action Button ───────────────────────────────────
        self.action_btn = ctk.CTkButton(
            self, text="⬇️   ดาวน์โหลดและติดตั้งทั้งหมด", height=52,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white",
            corner_radius=12, command=self._start_url_download
        )
        self.action_btn.grid(row=3, column=0, padx=16, pady=(12, 0), sticky="ew")

        # ── Progress Area ───────────────────────────────────
        prog_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                                  border_width=1, border_color=BORDER)
        prog_card.grid(row=4, column=0, padx=16, pady=(10, 0), sticky="nsew")
        prog_card.grid_columnconfigure(0, weight=1)
        prog_card.grid_rowconfigure(1, weight=1)

        ph = ctk.CTkFrame(prog_card, fg_color="transparent")
        ph.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")
        ph.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            ph, text="📊  สถานะ",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_PRIMARY
        ).grid(row=0, column=0, sticky="w")

        self.summary_lbl = ctk.CTkLabel(
            ph, text="", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        )
        self.summary_lbl.grid(row=0, column=1, sticky="e")

        self.rows_frame = ctk.CTkScrollableFrame(
            prog_card, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=ACCENT
        )
        self.rows_frame.grid(row=1, column=0, padx=8, pady=(0, 12), sticky="nsew")
        self.rows_frame.grid_columnconfigure(0, weight=1)

        self._placeholder = ctk.CTkLabel(
            self.rows_frame,
            text="ลากไฟล์ฟ้อนมาวาง หรือวางลิงค์แล้วกดดาวน์โหลด ⚡",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED
        )
        self._placeholder.grid(row=0, column=0, pady=40)

        # Footer
        footer = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=36)
        footer.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        footer.grid_propagate(False)
        ctk.CTkLabel(
            footer,
            text="⚡ FontZap  •  ติดตั้งฟ้อนเข้า Windows อัตโนมัติ  •  github.com/porchyy/-FontZap-",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        ).grid(row=0, column=0, padx=20, pady=8)

    # ──────────────────────────────────────────────────────────
    #  Tab Switch
    # ──────────────────────────────────────────────────────────

    def _switch_tab(self, tab: str):
        self._current_tab = tab
        if tab == "drop":
            self.drop_panel.grid()
            self.url_panel.grid_remove()
            self.folder_card.grid_remove()
            self.action_btn.grid_remove()
            self.btn_drop.configure(fg_color=ACCENT)
            self.btn_url.configure(fg_color=BORDER)
        else:
            self.drop_panel.grid_remove()
            self.url_panel.grid()
            self.folder_card.grid()
            self.action_btn.grid(row=3, column=0, padx=16, pady=(12, 0), sticky="ew")
            self.btn_drop.configure(fg_color=BORDER)
            self.btn_url.configure(fg_color=ACCENT)

    # ──────────────────────────────────────────────────────────
    #  Drop Handler → Auto Install
    # ──────────────────────────────────────────────────────────

    def _on_files_dropped(self, paths: list[str]):
        if self.busy:
            return

        # รวบรวมไฟล์ฟ้อนทั้งหมด (รวม zip)
        font_files = []
        zip_files  = []
        for p in paths:
            ext = os.path.splitext(p)[1].lower()
            if ext in FONT_EXTS:
                font_files.append(p)
            elif ext == ".zip":
                zip_files.append(p)

        if not font_files and not zip_files:
            messagebox.showwarning(
                "ไม่รองรับ",
                "กรุณาลากไฟล์ฟ้อน\n(.ttf  .otf  .zip  .woff  .woff2)"
            )
            return

        # สร้าง rows แบบ placeholder สำหรับ zip ก่อน
        self._clear_rows()
        all_items: list[tuple] = []   # (label, type, path)
        for p in font_files:
            all_items.append((os.path.basename(p), "font", p))
        for p in zip_files:
            all_items.append((f"📦 {os.path.basename(p)}", "zip", p))

        for i, (label, _, _) in enumerate(all_items):
            row = ItemRow(self.rows_frame, label)
            row.grid(row=i, column=0, padx=4, pady=4, sticky="ew")
            self.rows.append(row)

        self.summary_lbl.configure(text=f"0 / {len(all_items)} เสร็จ")
        self.busy = True

        threading.Thread(
            target=self._run_install, args=(all_items,), daemon=True
        ).start()

    def _run_install(self, items: list[tuple]):
        done  = 0
        total = len(items)
        installed_names = []

        for i, (label, kind, path) in enumerate(items):
            row = self.rows[i]

            if kind == "font":
                self.after(0, row.update, "working", "กำลังติดตั้ง...", 50)
                try:
                    dest = install_font_to_windows(path)
                    fname = os.path.basename(dest)
                    installed_names.append(fname)
                    done += 1
                    self.after(0, row.update, "done",
                               f"✅ ติดตั้งแล้ว! พร้อมใช้งานทันที", 100, fname)
                except Exception as e:
                    done += 1
                    self.after(0, row.update, "error", f"❌ {str(e)[:60]}", 0)

            elif kind == "zip":
                self.after(0, row.update, "working", "กำลังแตกไฟล์ zip...", 20)
                try:
                    fonts = extract_fonts_from_zip(path)
                    if not fonts:
                        done += 1
                        self.after(0, row.update, "error",
                                   "❌ ไม่พบไฟล์ฟ้อนใน zip นี้", 0)
                    else:
                        sub_done = 0
                        for fi, fp in enumerate(fonts):
                            pct = 20 + int((fi + 1) / len(fonts) * 80)
                            fname = os.path.basename(fp)
                            self.after(0, row.update, "working",
                                       f"ติดตั้ง {fname} ({fi+1}/{len(fonts)})", pct)
                            try:
                                dest = install_font_to_windows(fp)
                                installed_names.append(os.path.basename(dest))
                                sub_done += 1
                            except Exception:
                                pass
                        done += 1
                        self.after(0, row.update, "done",
                                   f"✅ ติดตั้งแล้ว {sub_done}/{len(fonts)} ฟ้อน", 100,
                                   f"📦 {os.path.basename(path)}")
                except Exception as e:
                    done += 1
                    self.after(0, row.update, "error", f"❌ {str(e)[:60]}", 0)

            self.after(0, self.summary_lbl.configure, {"text": f"{done} / {total} เสร็จ"})

        self.after(0, self._install_done, done, total, installed_names)

    def _install_done(self, done: int, total: int, names: list[str]):
        self.busy = False
        self.summary_lbl.configure(text=f"{done} / {total} เสร็จสมบูรณ์")
        n = len(names)
        preview = "\n".join(f"  • {x}" for x in names[:8])
        if len(names) > 8:
            preview += f"\n  ... และอีก {len(names)-8} ฟ้อน"
        messagebox.showinfo(
            "ติดตั้งเสร็จแล้ว! ⚡",
            f"ติดตั้งฟ้อน {n} รายการเข้า Windows เรียบร้อยแล้ว!\n"
            f"พร้อมใช้งานทันทีใน Word, Photoshop, Figma ฯลฯ\n\n"
            f"ฟ้อนที่ติดตั้ง:\n{preview}"
        )

    # ──────────────────────────────────────────────────────────
    #  URL Download + Install
    # ──────────────────────────────────────────────────────────

    def _start_url_download(self):
        if self.busy:
            return
        urls = self._get_urls()
        if not urls:
            messagebox.showwarning("ไม่พบลิงค์", "กรุณาวางลิงค์อย่างน้อย 1 รายการ")
            return

        save_path = self.save_dir.get()
        os.makedirs(save_path, exist_ok=True)

        self._clear_rows()
        for i, url in enumerate(urls):
            row = ItemRow(self.rows_frame, url)
            row.grid(row=i, column=0, padx=4, pady=4, sticky="ew")
            self.rows.append(row)

        self.busy = True
        self.action_btn.configure(
            text="⏳  กำลังดาวน์โหลดและติดตั้ง...", state="disabled", fg_color="#4a4a6a"
        )
        self.summary_lbl.configure(text=f"0 / {len(urls)} เสร็จ")

        threading.Thread(
            target=self._run_url_tasks, args=(urls, save_path), daemon=True
        ).start()

    def _run_url_tasks(self, urls: list[str], save_path: str):
        done = 0
        total = len(urls)
        installed = []

        def task(idx: int, url: str):
            nonlocal done
            row = self.rows[idx]
            self.after(0, row.update, "working", "กำลังดาวน์โหลด...", 0)
            try:
                headers = {"User-Agent": "Mozilla/5.0 (FontZap)"}
                resp = requests.get(url, stream=True, timeout=30, headers=headers)
                resp.raise_for_status()

                filename = get_filename_from_url(url, resp)
                filepath = os.path.join(save_path, filename)
                base, ext = os.path.splitext(filename)
                c = 1
                while os.path.exists(filepath):
                    filepath = os.path.join(save_path, f"{base}_{c}{ext}")
                    c += 1
                filename = os.path.basename(filepath)

                total_size = int(resp.headers.get("content-length", 0))
                downloaded_bytes = 0
                start_t = time.time()
                self.after(0, row.update, "working", f"⬇️ {filename}", 0, filename)

                with open(filepath, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                            if total_size:
                                pct = downloaded_bytes / total_size * 90
                                elapsed = time.time() - start_t
                                spd = downloaded_bytes / elapsed if elapsed > 0 else 0
                                spd_s = (f"{spd/1048576:.1f} MB/s"
                                         if spd > 1048576 else f"{spd/1024:.0f} KB/s")
                                self.after(0, row.update, "working",
                                           f"⬇️ {filename}  •  {spd_s}", pct, filename)

                # ติดตั้ง
                self.after(0, row.update, "working", "⚙️ กำลังติดตั้งเข้า Windows...", 92)
                ext_low = os.path.splitext(filepath)[1].lower()
                if ext_low == ".zip":
                    fonts = extract_fonts_from_zip(filepath)
                    for fp in fonts:
                        dest = install_font_to_windows(fp)
                        installed.append(os.path.basename(dest))
                    n = len(fonts)
                    self.after(0, row.update, "done",
                               f"✅ ดาวน์โหลด + ติดตั้ง {n} ฟ้อนแล้ว!", 100, filename)
                elif ext_low in FONT_EXTS:
                    dest = install_font_to_windows(filepath)
                    installed.append(os.path.basename(dest))
                    self.after(0, row.update, "done",
                               "✅ ดาวน์โหลด + ติดตั้งแล้ว! พร้อมใช้งาน", 100, filename)
                else:
                    self.after(0, row.update, "done",
                               f"✅ ดาวน์โหลดแล้ว (บันทึกที่ {save_path})", 100, filename)

                done += 1
                self.after(0, self.summary_lbl.configure, {"text": f"{done} / {total} เสร็จ"})

            except requests.exceptions.Timeout:
                self.after(0, row.update, "error", "❌ Timeout", 0)
                done += 1
            except requests.exceptions.HTTPError as e:
                self.after(0, row.update, "error", f"❌ HTTP {e.response.status_code}", 0)
                done += 1
            except Exception as e:
                self.after(0, row.update, "error", f"❌ {str(e)[:60]}", 0)
                done += 1

        with ThreadPoolExecutor(max_workers=5) as ex:
            for f in as_completed([ex.submit(task, i, u) for i, u in enumerate(urls)]):
                _ = f.result()

        self.after(0, self._url_done, done, total, installed)

    def _url_done(self, done: int, total: int, installed: list[str]):
        self.busy = False
        color = SUCCESS if done == total else WARNING
        self.action_btn.configure(
            text=f"✅  เสร็จ {done}/{total}  —  ดาวน์โหลดอีกครั้ง",
            state="normal", fg_color=color
        )
        self.summary_lbl.configure(text=f"{done} / {total} เสร็จสมบูรณ์")
        n = len(installed)
        msg = f"เสร็จสิ้น! ดาวน์โหลด {done}/{total} รายการ"
        if n:
            msg += f"\n✅ ติดตั้งฟ้อน {n} รายการเข้า Windows แล้ว\nพร้อมใช้งานทันที!"
        messagebox.showinfo("เสร็จสิ้น! ⚡", msg)
        self.action_btn.configure(
            text="⬇️   ดาวน์โหลดและติดตั้งทั้งหมด",
            fg_color=ACCENT, hover_color=ACCENT_HOVER
        )

    # ──────────────────────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────────────────────

    def _clear_urls(self):
        self.url_box.delete("1.0", "end")

    def _paste_clip(self):
        try:
            self.url_box.insert("end", self.clipboard_get() + "\n")
        except Exception:
            pass

    def _browse_folder(self):
        d = filedialog.askdirectory(title="เลือกโฟลเดอร์บันทึก")
        if d:
            self.save_dir.set(d)

    def _get_urls(self) -> list[str]:
        raw = self.url_box.get("1.0", "end")
        urls = []
        for line in raw.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith("http"):
                urls.append(line)
        return list(dict.fromkeys(urls))

    def _clear_rows(self):
        for w in self.rows_frame.winfo_children():
            w.destroy()
        self.rows.clear()


# ─── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":
    app = FontZapApp()
    app.mainloop()
