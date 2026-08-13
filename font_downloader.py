# FontZap — Font Bulk Downloader
# GitHub: https://github.com/porchyy/-FontZap-
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import requests
import os
import re
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


class DownloadRow(ctk.CTkFrame):
    """แถวแสดงสถานะการดาวน์โหลดของแต่ละไฟล์"""

    STATUS_ICONS = {
        "waiting":      ("⏳", TEXT_MUTED),
        "downloading":  ("⬇️", ACCENT_LIGHT),
        "done":         ("✅", SUCCESS),
        "error":        ("❌", ERROR),
        "skipped":      ("⚠️", WARNING),
    }

    def __init__(self, parent, url, index, **kwargs):
        super().__init__(parent, fg_color=BG_INPUT, corner_radius=10, **kwargs)
        self.url = url
        self.index = index
        self._status = "waiting"

        self.grid_columnconfigure(1, weight=1)
        self.configure(border_width=1, border_color=BORDER)

        # ── Icon ──
        self.icon_label = ctk.CTkLabel(
            self, text="⏳", width=30, font=ctk.CTkFont(size=16)
        )
        self.icon_label.grid(row=0, column=0, padx=(12, 4), pady=10)

        # ── Info Column ──
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=0, column=1, padx=4, pady=10, sticky="ew")
        info_frame.grid_columnconfigure(0, weight=1)

        short_name = unquote(os.path.basename(urlparse(url).path)) or url
        if len(short_name) > 55:
            short_name = "…" + short_name[-52:]

        self.name_label = ctk.CTkLabel(
            info_frame, text=short_name,
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

        # ── Percent ──
        self.pct_label = ctk.CTkLabel(
            self, text="0%", width=45,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED
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
        if status == "downloading":
            self.progress_bar.configure(progress_color=ACCENT)
        elif status == "done":
            self.progress_bar.configure(progress_color=SUCCESS)
        elif status == "error":
            self.progress_bar.configure(progress_color=ERROR)


class FontDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("⚡ FontZap — Font Bulk Downloader")
        self.geometry("720x820")
        self.minsize(620, 600)
        self.configure(fg_color=BG_DARK)

        self.save_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads", "Fonts"))
        self.download_rows: list[DownloadRow] = []
        self.is_downloading = False

        self._build_ui()

    # ─────────────────────────────────────────────────────────────
    #  UI Building
    # ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # ── Header ──────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=80)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        header.grid_propagate(False)

        title_lbl = ctk.CTkLabel(
            header, text="⚡  FontZap",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=ACCENT_LIGHT
        )
        title_lbl.grid(row=0, column=0, padx=24, pady=(18, 0), sticky="w")

        sub_lbl = ctk.CTkLabel(
            header, text="⚡ โหลดฟ้อนหลายอันพร้อมกัน — วางลิงค์แล้วกดปุ่มเดียวจบ!",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED
        )
        sub_lbl.grid(row=1, column=0, padx=24, pady=(2, 14), sticky="w")

        # ── URL Input Card ───────────────────────────────────────
        url_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14, border_width=1, border_color=BORDER)
        url_card.grid(row=1, column=0, padx=16, pady=(14, 0), sticky="ew")
        url_card.grid_columnconfigure(0, weight=1)

        url_title = ctk.CTkLabel(
            url_card, text="📋  วางลิงค์ดาวน์โหลดฟ้อน",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_PRIMARY
        )
        url_title.grid(row=0, column=0, padx=18, pady=(14, 4), sticky="w")

        url_hint = ctk.CTkLabel(
            url_card, text="ใส่ URL ทีละบรรทัด รองรับ .ttf .otf .zip .woff .woff2 และอื่นๆ",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        )
        url_hint.grid(row=1, column=0, padx=18, pady=(0, 6), sticky="w")

        self.url_textbox = ctk.CTkTextbox(
            url_card, height=150,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=BG_INPUT, text_color=TEXT_PRIMARY,
            border_color=BORDER, border_width=1, corner_radius=8,
            scrollbar_button_color=BORDER
        )
        self.url_textbox.grid(row=2, column=0, padx=18, pady=(0, 6), sticky="ew")
        self.url_textbox.insert("end", "# วางลิงค์ที่นี่ ทีละบรรทัด เช่น:\n# https://example.com/myfont.ttf\n# https://example.com/fonts.zip\n")

        # Buttons row inside url card
        btn_row = ctk.CTkFrame(url_card, fg_color="transparent")
        btn_row.grid(row=3, column=0, padx=18, pady=(0, 14), sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)

        clear_btn = ctk.CTkButton(
            btn_row, text="🗑️ ล้าง", width=80, height=30,
            fg_color=BORDER, hover_color="#3d3d5c", text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12), corner_radius=6,
            command=self._clear_urls
        )
        clear_btn.grid(row=0, column=1, padx=(8, 0))

        paste_btn = ctk.CTkButton(
            btn_row, text="📋 วาง", width=80, height=30,
            fg_color=BORDER, hover_color="#3d3d5c", text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12), corner_radius=6,
            command=self._paste_clipboard
        )
        paste_btn.grid(row=0, column=2, padx=(8, 0))

        # ── Save Folder Row ──────────────────────────────────────
        folder_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14, border_width=1, border_color=BORDER)
        folder_card.grid(row=2, column=0, padx=16, pady=(10, 0), sticky="ew")
        folder_card.grid_columnconfigure(1, weight=1)

        folder_icon = ctk.CTkLabel(
            folder_card, text="📁", font=ctk.CTkFont(size=18), width=36
        )
        folder_icon.grid(row=0, column=0, padx=(14, 4), pady=12)

        self.folder_label = ctk.CTkLabel(
            folder_card, textvariable=self.save_dir,
            font=ctk.CTkFont(size=12), text_color=ACCENT_LIGHT, anchor="w"
        )
        self.folder_label.grid(row=0, column=1, padx=4, pady=12, sticky="ew")

        browse_btn = ctk.CTkButton(
            folder_card, text="เปลี่ยน", width=80, height=30,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white",
            font=ctk.CTkFont(size=12, weight="bold"), corner_radius=6,
            command=self._browse_folder
        )
        browse_btn.grid(row=0, column=2, padx=(4, 14), pady=12)

        # ── Download Button ──────────────────────────────────────
        self.dl_button = ctk.CTkButton(
            self, text="⬇️   ดาวน์โหลดทั้งหมด", height=52,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white",
            corner_radius=12, command=self._start_download
        )
        self.dl_button.grid(row=3, column=0, padx=16, pady=(12, 0), sticky="ew")

        # ── Progress Area ────────────────────────────────────────
        progress_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14, border_width=1, border_color=BORDER)
        progress_card.grid(row=4, column=0, padx=16, pady=(10, 0), sticky="nsew")
        progress_card.grid_columnconfigure(0, weight=1)
        progress_card.grid_rowconfigure(1, weight=1)

        prog_header = ctk.CTkFrame(progress_card, fg_color="transparent")
        prog_header.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")
        prog_header.grid_columnconfigure(0, weight=1)

        prog_title = ctk.CTkLabel(
            prog_header, text="📊  สถานะการดาวน์โหลด",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_PRIMARY
        )
        prog_title.grid(row=0, column=0, sticky="w")

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

        placeholder = ctk.CTkLabel(
            self.rows_frame, text="ยังไม่มีการดาวน์โหลด — วางลิงค์แล้วกดปุ่มด้านบน",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED
        )
        placeholder.grid(row=0, column=0, pady=40)
        self._placeholder = placeholder

        # ── Footer ──────────────────────────────────────────────
        footer = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=36)
        footer.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        footer.grid_propagate(False)

        self.footer_label = ctk.CTkLabel(
            footer, text="⚡ FontZap  •  รองรับ .ttf .otf .zip .woff .woff2  •  github.com/porchyy/-FontZap-",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        )
        self.footer_label.grid(row=0, column=0, padx=20, pady=8)

    # ─────────────────────────────────────────────────────────────
    #  Helpers
    # ─────────────────────────────────────────────────────────────

    def _clear_urls(self):
        self.url_textbox.delete("1.0", "end")

    def _paste_clipboard(self):
        try:
            text = self.clipboard_get()
            self.url_textbox.insert("end", text + "\n")
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
        return list(dict.fromkeys(urls))  # deduplicate

    def _clear_rows(self):
        for w in self.rows_frame.winfo_children():
            w.destroy()
        self.download_rows.clear()
        self._placeholder = None

    # ─────────────────────────────────────────────────────────────
    #  Download Logic
    # ─────────────────────────────────────────────────────────────

    def _start_download(self):
        if self.is_downloading:
            return

        urls = self._get_urls()
        if not urls:
            messagebox.showwarning("ไม่พบลิงค์", "กรุณาวางลิงค์ดาวน์โหลดอย่างน้อย 1 รายการ")
            return

        save_path = self.save_dir.get()
        os.makedirs(save_path, exist_ok=True)

        # Build rows
        self._clear_rows()
        for i, url in enumerate(urls):
            row = DownloadRow(self.rows_frame, url, i)
            row.grid(row=i, column=0, padx=4, pady=4, sticky="ew")
            self.download_rows.append(row)

        self.is_downloading = True
        self.dl_button.configure(text="⏳  กำลังดาวน์โหลด...", state="disabled", fg_color="#4a4a6a")
        self.summary_label.configure(text=f"0 / {len(urls)} เสร็จ")

        thread = threading.Thread(target=self._run_downloads, args=(urls, save_path), daemon=True)
        thread.start()

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

                # handle duplicate filenames
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
                                speed_str = f"{speed/1024/1024:.1f} MB/s" if speed > 1048576 else f"{speed/1024:.0f} KB/s"
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
                self.after(0, self.summary_label.configure,
                           {"text": f"{done} / {total} เสร็จ"})

            except requests.exceptions.Timeout:
                self.after(0, row.update_status, "error", "❌ Timeout — ลิงค์ใช้เวลานานเกินไป", 0)
                done += 1
            except requests.exceptions.HTTPError as e:
                self.after(0, row.update_status, "error", f"❌ HTTP Error {e.response.status_code}", 0)
                done += 1
            except Exception as e:
                self.after(0, row.update_status, "error", f"❌ {str(e)[:60]}", 0)
                done += 1

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(task, i, url) for i, url in enumerate(urls)]
            for f in as_completed(futures):
                _ = f.result()

        self.after(0, self._on_done, done, total)

    def _on_done(self, done: int, total: int):
        self.is_downloading = False
        self.dl_button.configure(
            text=f"✅  เสร็จแล้ว {done}/{total} ไฟล์  —  ดาวน์โหลดอีกครั้ง",
            state="normal", fg_color=SUCCESS if done == total else WARNING
        )
        self.summary_label.configure(text=f"{done} / {total} เสร็จสมบูรณ์")
        save_path = self.save_dir.get()
        msg = f"ดาวน์โหลดเสร็จสิ้น {done}/{total} ไฟล์\n📁 บันทึกที่: {save_path}"
        if done < total:
            msg += f"\n\n⚠️ มี {total - done} ไฟล์ที่ดาวน์โหลดไม่สำเร็จ"
        messagebox.showinfo("เสร็จสิ้น!", msg)
        # Reset button
        self.dl_button.configure(
            text="⬇️   ดาวน์โหลดทั้งหมด",
            fg_color=ACCENT, hover_color=ACCENT_HOVER
        )


# ─── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":
    app = FontDownloaderApp()
    app.mainloop()
