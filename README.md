# ⚡ FontZap

> ดาวน์โหลดและติดตั้งฟ้อนเข้า Windows แบบ Bulk — ไม่ต้องใช้ Admin!

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ ฟีเจอร์

| ฟีเจอร์ | รายละเอียด |
|---|---|
| 📂 **Drag & Drop** | ลากไฟล์ `.ttf` `.otf` `.zip` `.woff` `.woff2` มาวางได้เลย |
| 🔗 **URL Download** | วางลิงค์ทีละบรรทัด — ดาวน์โหลด + ติดตั้งให้อัตโนมัติ |
| ⚡ **Auto Install** | ติดตั้งเข้า User Fonts โดยไม่ต้องใช้สิทธิ์ Administrator |
| 📦 **ZIP Support** | แตก `.zip` แล้วติดตั้งฟ้อนทุกตัวในไฟล์ให้เลย |
| 🚫 **Cancel** | ยกเลิกการติดตั้ง/ดาวน์โหลดได้ทุกเมื่อ |
| 📊 **Progress** | แสดง progress + speed แบบ Real-time ทุกไฟล์ |
| 📂 **เปิดโฟลเดอร์** | กดเปิดโฟลเดอร์ฟ้อนได้ทันทีหลังเสร็จ |
| 🎨 **Dark UI** | หน้าตาสวยงาม ใช้งานง่าย |

---

## 🖥️ Screenshots

> ลากไฟล์ฟ้อนมาวางในช่อง Drop Zone — ติดตั้งทันที!

---

## 📦 Requirements

- **Windows 10 / 11**
- **Python 3.10+**

---

## 🚀 วิธีใช้งาน

### 1. ติดตั้ง Dependencies

```bash
pip install -r requirements.txt
```

### 2. รันโปรแกรม

```bash
python font_downloader.py
```

---

## 🛠️ วิธีติดตั้ง Dependencies ทีละตัว (กรณีมีปัญหา)

```bash
pip install customtkinter
pip install requests
pip install tkinterdnd2
```

---

## 📂 โหมดการใช้งาน

### 📂 โหมด Drag & Drop (ลากไฟล์)
1. เปิดโปรแกรม → แท็บ **"📂 ลากไฟล์"**
2. ลากไฟล์ฟ้อน (`.ttf`, `.otf`, `.zip`) มาวางในกรอบ
3. โปรแกรมจะติดตั้งเข้า Windows ให้ทันที
4. กด **"📂 เปิดโฟลเดอร์"** เพื่อดูฟ้อนที่ติดตั้ง

### 🔗 โหมด URL (ดาวน์โหลด)
1. เปิดโปรแกรม → แท็บ **"🔗 วางลิงค์"**
2. วาง URL ทีละบรรทัด (รองรับ `.ttf`, `.otf`, `.zip`)
3. เลือกโฟลเดอร์บันทึก (ถ้าต้องการเปลี่ยน)
4. กด **"⬇️ ดาวน์โหลดและติดตั้งทั้งหมด"**

---

## ⚠️ หมายเหตุ

- ฟ้อนถูกติดตั้งใน **User Fonts** (`%LOCALAPPDATA%\Microsoft\Windows\Fonts`) — ไม่ต้องใช้ Admin
- ฟ้อนพร้อมใช้งานทันทีใน Word, Photoshop, Figma โดยไม่ต้อง Restart
- ไฟล์ `.woff` / `.woff2` ออกแบบมาสำหรับเว็บ อาจไม่รองรับในโปรแกรมทั่วไป
- ดาวน์โหลดพร้อมกัน **5 ลิงค์** ในคราวเดียว

---

## 📁 โครงสร้างโปรเจกต์

```
FontZap/
├── font_downloader.py   # โปรแกรมหลัก
├── requirements.txt     # Python dependencies
└── README.md            # ไฟล์นี้
```

---

## 📄 License

MIT License — ใช้งานได้ฟรี ทั้งส่วนตัวและเชิงพาณิชย์

---

Made with ❤️ by [porchyy](https://github.com/porchyy)
