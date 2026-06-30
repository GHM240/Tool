#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Artifex Display Converter
统一显示资源转换工具：LCD / MJPEG 视频转换 + 墨水屏 .epd 图片转换

依赖：
    开发环境：pip install -r requirements.txt
    客户环境：不需要安装 Python / Pillow / FFmpeg，GitHub Actions 打包产物会自带依赖。

运行：
    开发运行：python Tool.py
    CI 自检：python Tool.py --self-test
"""

import os
import re
import sys
import traceback
import subprocess
import threading
import platform
import shutil
import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# ========== 可选依赖：拖拽 ==========
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
    DND_IMPORT_ERROR = None
except Exception as e:
    DND_FILES = None
    TkinterDnD = None
    HAS_DND = False
    DND_IMPORT_ERROR = e

# HAS_DND 只代表 tkinterdnd2 import 成功；
# DND_RUNTIME_OK 代表 TkinterDnD.Tk() 真正初始化成功。
DND_RUNTIME_OK = False

# ========== 可选依赖：Pillow ==========
try:
    from PIL import Image, ImageEnhance, ImageTk, ImageOps
    HAS_PIL = True
except Exception:
    HAS_PIL = False


# =========================
# 运行环境 / 打包路径处理
# =========================
def is_frozen_app() -> bool:
    """是否为 PyInstaller 打包后的程序。"""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """
    返回用户看到的程序目录。
    - 源码运行：Tool.py 所在目录
    - PyInstaller onedir：exe/app 启动文件所在目录
    """
    if is_frozen_app():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    """
    返回 PyInstaller 放置内置资源/二进制文件的目录。
    PyInstaller 6 的 onedir 默认会把依赖放入 _internal；onefile 会解压到临时 _MEIPASS。
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass).resolve()
    return app_dir()


def common_resource_dirs():
    """按优先级返回可能存在 ffmpeg 的目录。"""
    base = app_dir()
    res = resource_dir()
    dirs = [
        base,
        res,
        base / "_internal",
        res / "_internal",
        base / "ffmpeg",
        base / "ffmpeg" / "bin",
        res / "ffmpeg",
        res / "ffmpeg" / "bin",
    ]

    # macOS .app 常见结构：Contents/MacOS 与 Contents/Resources
    if base.name == "MacOS" and base.parent.name == "Contents":
        dirs.extend([base.parent / "Resources", base.parent / "Frameworks"])

    # 去重并保序
    out = []
    seen = set()
    for d in dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _run_executable_version(exe_path: Path) -> bool:
    """检测候选 ffmpeg 是否真的可运行。"""
    try:
        subprocess.run(
            [str(exe_path), "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except Exception:
        return False


def find_ffmpeg_binary() -> str | None:
    """
    查找 FFmpeg。
    优先查打包目录和 PyInstaller 资源目录，最后才查系统 PATH。
    这样客户不需要自己配置 PATH。
    """
    system = platform.system()
    exe_name = "ffmpeg.exe" if system == "Windows" else "ffmpeg"

    candidates = []
    for d in common_resource_dirs():
        candidates.append(d / exe_name)

    if system == "Darwin":
        candidates.extend([
            Path("/opt/homebrew/bin/ffmpeg"),
            Path("/usr/local/bin/ffmpeg"),
            Path("/opt/local/bin/ffmpeg"),
        ])
    elif system == "Linux":
        candidates.extend([
            Path("/usr/bin/ffmpeg"),
            Path("/usr/local/bin/ffmpeg"),
            Path("/snap/bin/ffmpeg"),
        ])

    path_ffmpeg = shutil.which(exe_name) or shutil.which("ffmpeg")
    if path_ffmpeg:
        candidates.append(Path(path_ffmpeg))

    seen = set()
    for c in candidates:
        c = Path(c)
        key = str(c)
        if key in seen:
            continue
        seen.add(key)

        if c.is_absolute() and not c.exists():
            continue
        if _run_executable_version(c):
            return str(c)

    return None


def packaged_missing_message(name: str, dev_hint: str) -> str:
    """打包版给客户看重新安装；源码版给开发者看安装命令。"""
    if is_frozen_app():
        return (
            f"安装包不完整：缺少 {name}。\n\n"
            "请重新从 GitHub Actions / Release 下载对应系统的完整压缩包，"
            "不要只复制单个 exe/app 文件。"
        )
    return dev_hint


def self_test() -> int:
    """GitHub Actions 用的无 GUI 自检，不创建 Tk 窗口。"""
    print("Artifex Display Converter self-test")
    print(f"system={platform.system()}")
    print(f"python={sys.version.split()[0]}")
    print(f"frozen={is_frozen_app()}")
    print(f"app_dir={app_dir()}")
    print(f"resource_dir={resource_dir()}")
    print(f"Pillow={'OK' if HAS_PIL else 'MISSING'}")
    print(f"tkinterdnd2={'OK' if HAS_DND else 'MISSING/OPTIONAL'}")
    ffmpeg = find_ffmpeg_binary()
    print(f"ffmpeg={ffmpeg or 'MISSING'}")
    if not HAS_PIL:
        return 2
    if not ffmpeg:
        return 3
    return 0


# =========================
# 通用常量
# =========================
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm", ".mpeg", ".mpg"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS

APP_BG = "#0F172A"
PANEL_BG = "#111827"
CARD_BG = "#182235"
CARD_BG_2 = "#1E293B"
TEXT = "#E5E7EB"
MUTED = "#94A3B8"
ACCENT = "#38BDF8"
ACCENT_2 = "#F59E0B"
SUCCESS = "#22C55E"
DANGER = "#EF4444"


# =========================
# 墨水屏预设与图像处理
# =========================
EPAPER_PRESETS = {
    "Waveshare 2.15inch HAT+ (G) 160x296 四色": {
        "w": 160,
        "h": 296,
        "bpp": 2,
        "order": "高位优先",
        "palette": [
            ("BLACK", 0, "#000000"),
            ("WHITE", 1, "#FFFFFF"),
            ("YELLOW", 2, "#FFD800"),
            ("RED", 3, "#DC0000"),
        ],
        "note": "适合 2.15G 四色屏。输出 .epd 大小应为 11840 bytes。",
    },
    "Waveshare 2.13inch (G) 250x122 四色 横向": {
        "w": 250,
        "h": 122,
        "bpp": 2,
        "order": "高位优先",
        "palette": [
            ("BLACK", 0, "#000000"),
            ("WHITE", 1, "#FFFFFF"),
            ("YELLOW", 2, "#FFD800"),
            ("RED", 3, "#DC0000"),
        ],
        "note": "横向预览用。注意：当前 2.13G V2 驱动通常按 122x250、7750 bytes 读取；如要给当前驱动使用，建议选择 122x250 竖向预设并用旋转处理。",
    },
    "Waveshare 2.13inch (G) 122x250 四色 竖向": {
        "w": 122,
        "h": 250,
        "bpp": 2,
        "order": "高位优先",
        "palette": [
            ("BLACK", 0, "#000000"),
            ("WHITE", 1, "#FFFFFF"),
            ("YELLOW", 2, "#FFD800"),
            ("RED", 3, "#DC0000"),
        ],
        "note": "适合当前 2.13G V2 驱动。输出 .epd 大小应为 7750 bytes：每行 ceil(122/4)=31 字节，250 行，末尾补白。",
    },
    "自定义四色 2-bit 160x296": {
        "w": 160,
        "h": 296,
        "bpp": 2,
        "order": "高位优先",
        "palette": [
            ("BLACK", 0, "#000000"),
            ("WHITE", 1, "#FFFFFF"),
            ("YELLOW", 2, "#FFD800"),
            ("RED", 3, "#DC0000"),
        ],
        "note": "只保留四色屏逻辑；如需别的四色尺寸，可在这里改宽高。",
    },
}

def hx2rgb(s: str):
    s = s.strip().lstrip("#")
    if len(s) != 6:
        raise ValueError(f"颜色格式错误：#{s}")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def output_size(w: int, h: int, bpp: int) -> int:
    """
    按“逐行打包”计算输出大小。

    关键点：
    墨水屏驱动通常是一行一行发送数据，而不是把整张图连续打包。
    所以当宽度不能被每字节像素数整除时，每一行末尾都要补齐到 1 字节。

    例如 2.13G V2：
        122 像素宽，2bpp，4 像素/字节
        每行 ceil(122 / 4) = 31 字节
        31 * 250 = 7750 bytes

    旧算法 (w*h*bpp+7)//8 会得到 7625 bytes，这是错误的连续打包大小。
    """
    if bpp not in (1, 2, 4, 8):
        raise ValueError("bpp 只支持 1/2/4/8")

    if bpp == 8:
        return w * h

    row_bytes = (w * bpp + 7) // 8
    return row_bytes * h


def weighted_distance(a, b):
    r, g, bl = a
    rr, gg, bb = b
    return 3 * (r - rr) ** 2 + 6 * (g - gg) ** 2 + (bl - bb) ** 2


def nearest_index(rgb, palette_rgb):
    return min(range(len(palette_rgb)), key=lambda i: weighted_distance(rgb, palette_rgb[i]))


def fit_image(img, w: int, h: int, mode: str):
    img = img.convert("RGB")
    if mode == "拉伸":
        return img.resize((w, h), Image.Resampling.LANCZOS)
    if mode == "完整适配留白":
        fitted = ImageOps.contain(img, (w, h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        canvas.paste(fitted, ((w - fitted.width) // 2, (h - fitted.height) // 2))
        return canvas
    return ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def enhance_image(img, bright: float, contrast: float, sat: float, sharp: float):
    img = ImageEnhance.Brightness(img).enhance(bright)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    img = ImageEnhance.Color(img).enhance(sat)
    img = ImageEnhance.Sharpness(img).enhance(sharp)
    return img


def quantize_nearest(img, palette_rgb):
    img = img.convert("RGB")
    out = Image.new("RGB", img.size)
    pi = img.load()
    po = out.load()
    for y in range(img.height):
        for x in range(img.width):
            po[x, y] = palette_rgb[nearest_index(pi[x, y], palette_rgb)]
    return out


def quantize_fs(img, palette_rgb, strength=1.0):
    img = img.convert("RGB")
    w, h = img.size
    strength = max(0.0, min(1.5, float(strength)))
    arr = [[[float(c) for c in img.getpixel((x, y))] for x in range(w)] for y in range(h)]
    out = Image.new("RGB", (w, h))
    po = out.load()

    for y in range(h):
        for x in range(w):
            old = arr[y][x]
            old_rgb = tuple(int(max(0, min(255, c))) for c in old)
            idx = nearest_index(old_rgb, palette_rgb)
            new = palette_rgb[idx]
            po[x, y] = new
            err = [(old[i] - new[i]) * strength for i in range(3)]

            def add(nx, ny, factor):
                if 0 <= nx < w and 0 <= ny < h:
                    for c in range(3):
                        arr[ny][nx][c] += err[c] * factor

            add(x + 1, y, 7 / 16)
            add(x - 1, y + 1, 3 / 16)
            add(x, y + 1, 5 / 16)
            add(x + 1, y + 1, 1 / 16)
    return out


def image_to_codes(img, palette_rgb, palette_values):
    img = img.convert("RGB")
    exact = {palette_rgb[i]: palette_values[i] for i in range(len(palette_rgb))}
    codes = []
    for y in range(img.height):
        for x in range(img.width):
            c = img.getpixel((x, y))
            codes.append(exact[c] if c in exact else palette_values[nearest_index(c, palette_rgb)])
    return codes


def pack_codes(codes, w: int, h: int, bpp: int, order: str, pad_value: int = 0) -> bytes:
    """
    逐行打包像素码。

    不能把整张图片直接连续打包，否则 122x250 / 2bpp 会得到 7625 bytes。
    正确做法是每一行单独打包，每行最后不足 1 字节的像素用 pad_value 补齐。

    对 2.13G V2：
        每 4 个像素 1 字节
        122 像素 = 30.5 字节
        每行必须补齐成 31 字节
        31 * 250 = 7750 bytes
    """
    if bpp not in (1, 2, 4, 8):
        raise ValueError("bpp 只支持 1/2/4/8")

    if len(codes) != w * h:
        raise ValueError(f"像素数量错误：{len(codes)}，期望 {w * h}")

    if bpp == 8:
        return bytes([c & 0xFF for c in codes])

    per_byte = 8 // bpp
    mask = (1 << bpp) - 1
    out = bytearray()

    for y in range(h):
        row = codes[y * w:(y + 1) * w]

        for x in range(0, w, per_byte):
            group = row[x:x + per_byte]

            # 行尾不足 1 字节时补白。当前四色屏 WHITE 的值通常是 1。
            group += [pad_value] * (per_byte - len(group))

            b = 0
            for j, c in enumerate(group):
                shift = j * bpp if order == "低位优先" else 8 - bpp * (j + 1)
                b |= (c & mask) << shift
            out.append(b)

    return bytes(out)


# =========================
# 主程序 GUI
# =========================
class DisplayConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Artifex Display Converter  |  LCD + E-Paper")
        self.root.geometry("1280x800")
        self.root.minsize(1120, 720)

        self.mode = tk.StringVar(value="lcd")
        self.status_var = tk.StringVar(value="就绪：选择 LCD 视频转换或墨水屏图片转换。")

        # LCD 状态
        # 只在 init_runtime() 里检测一次，避免启动时弹两次 FFmpeg 提示。
        self.ffmpeg_path = None
        self.lcd_files = []
        self.lcd_output_size = tk.StringVar(value="240:320")
        self.lcd_quality = tk.IntVar(value=5)
        self.lcd_add_size_suffix = tk.BooleanVar(value=True)
        self.lcd_output_format = tk.StringVar(value=".mjpeg")

        # 墨水屏状态
        self.epaper_paths = []
        self.epaper_preview_cache = {}
        self.epaper_selected_path = None
        self.epaper_preset_var = tk.StringVar(value=list(EPAPER_PRESETS.keys())[0])
        self.epaper_fit_var = tk.StringVar(value="裁剪填满")
        self.epaper_rotate_var = tk.IntVar(value=0)
        self.epaper_dither_var = tk.BooleanVar(value=True)
        self.epaper_bright_var = tk.DoubleVar(value=1.0)
        self.epaper_contrast_var = tk.DoubleVar(value=1.2)
        self.epaper_sat_var = tk.DoubleVar(value=1.1)
        self.epaper_sharp_var = tk.DoubleVar(value=1.0)
        self.epaper_dither_strength_var = tk.DoubleVar(value=1.0)
        self.epaper_current_original_tk = None
        self.epaper_current_preview_tk = None
        self._epaper_preview_job = None

        self.apply_style()
        self.init_runtime()
        self.build_ui()
        self.setup_drag_drop()
        self.show_mode("lcd")

        if not self.ffmpeg_path:
            self.set_status("提示：未找到 FFmpeg。LCD/MJPEG 转换需要 ffmpeg.exe 或系统 PATH 中的 ffmpeg。")
        if not HAS_PIL:
            self.set_status("提示：未安装 Pillow。打包版请重新下载完整安装包；开发版请运行 pip install -r requirements.txt")

    def init_runtime(self):
        self.system = platform.system()

        # ---------- FFmpeg ----------
        self.ffmpeg_path = self.find_ffmpeg()
        if not self.ffmpeg_path:
            self.prompt_missing_ffmpeg()

        # ---------- Pillow ----------
        if not HAS_PIL:
            messagebox.showerror(
                "依赖缺失",
                packaged_missing_message(
                    "Pillow",
                    "缺少 Pillow。开发环境请运行：pip install -r requirements.txt"
                )
            )

    def app_dir(self):
        return app_dir()

    def ffmpeg_install_hint(self):
        system = getattr(self, "system", platform.system())

        if is_frozen_app():
            return (
                f"当前系统：{system}\n\n"
                "这是已经打包后的客户版本，正常情况下应该自带 FFmpeg。\n"
                "如果这里仍然提示缺少 FFmpeg，通常表示你只复制了单个 exe/app，"
                "没有复制完整 dist 文件夹或安装包内容。请重新下载对应系统的完整压缩包。"
            )

        if system == "Windows":
            return (
                "当前系统：Windows\n\n"
                "开发环境处理方式：\n"
                "1. GitHub Actions 会通过 Chocolatey 安装 FFmpeg 并打进包里。\n"
                "2. 本地测试可把 ffmpeg.exe 放到 Tool.py 同目录，或加入 PATH。"
            )

        if system == "Darwin":
            return (
                "当前系统：macOS\n\n"
                "开发环境处理方式：\n"
                "1. GitHub Actions 会通过 Homebrew 安装 FFmpeg 并打进包里。\n"
                "2. 本地测试可运行 brew install ffmpeg，或把 ffmpeg 放到 Tool.py 同目录。"
            )

        if system == "Linux":
            return (
                "当前系统：Linux\n\n"
                "开发环境处理方式：\n"
                "1. GitHub Actions 会通过 apt 安装 FFmpeg 并打进包里。\n"
                "2. 本地测试可运行 sudo apt install ffmpeg，或把 ffmpeg 放到 Tool.py 同目录。"
            )

        return f"当前系统：{system}\n\n无法识别具体系统，请检查 GitHub Actions 打包配置。"

    def ffmpeg_download_url(self):
        # FFmpeg 官方下载页会按 Windows / macOS / Linux 提供对应入口。
        return "https://ffmpeg.org/download.html"

    def open_ffmpeg_download_page(self):
        webbrowser.open(self.ffmpeg_download_url())

    def prompt_missing_ffmpeg(self):
        msg = (
            "未检测到 FFmpeg，LCD/MJPEG 转换暂时不能使用。\n\n"
            + self.ffmpeg_install_hint()
        )
        if is_frozen_app():
            messagebox.showerror("FFmpeg 未找到", msg)
            return
        msg += "\n\n是否打开 FFmpeg 官方下载页面？"
        if messagebox.askyesno("FFmpeg 未找到", msg):
            self.open_ffmpeg_download_page()

    # ---------- 风格 ----------
    def apply_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("App.TFrame", background=APP_BG)
        style.configure("Panel.TFrame", background=PANEL_BG)
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("Card2.TFrame", background=CARD_BG_2)
        style.configure("TLabel", background=APP_BG, foreground=TEXT, font=("Microsoft YaHei UI", 9))
        style.configure("Muted.TLabel", background=APP_BG, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("Panel.TLabel", background=PANEL_BG, foreground=TEXT, font=("Microsoft YaHei UI", 9))
        style.configure("Card.TLabel", background=CARD_BG, foreground=TEXT, font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", background=APP_BG, foreground=TEXT, font=("Microsoft YaHei UI", 19, "bold"))
        style.configure("SubTitle.TLabel", background=APP_BG, foreground=MUTED, font=("Microsoft YaHei UI", 10))
        style.configure("Section.TLabel", background=PANEL_BG, foreground=TEXT, font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("CardTitle.TLabel", background=CARD_BG, foreground=TEXT, font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(10, 8))
        style.configure("TButton", font=("Microsoft YaHei UI", 9), padding=(8, 6))
        style.configure("TCheckbutton", background=PANEL_BG, foreground=TEXT, font=("Microsoft YaHei UI", 9))
        style.map("TCheckbutton", background=[("active", PANEL_BG)], foreground=[("active", TEXT)])
        style.configure("TCombobox", fieldbackground="#F8FAFC", background="#F8FAFC")
        style.configure("Horizontal.TProgressbar", troughcolor="#243044", background=ACCENT)

    def card(self, parent, bg=CARD_BG):
        frame = tk.Frame(parent, bg=bg, bd=0, highlightthickness=1, highlightbackground="#243044")
        return frame

    def label(self, parent, text="", size=9, weight="normal", fg=TEXT, bg=None, **kwargs):
        return tk.Label(parent, text=text, font=("Microsoft YaHei UI", size, weight), fg=fg, bg=bg or parent.cget("bg"), **kwargs)

    def section_title(self, parent, text):
        return self.label(parent, text, size=12, weight="bold")

    def make_button(self, parent, text, command, bg="#273449", fg=TEXT, active=None):
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active or bg,
            activeforeground=fg,
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=8,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        return btn

    def create_scrollable_panel(self, parent, width=380, bg=PANEL_BG):
        """创建带纵向滚动条的左侧参数面板。窗口变小后，按钮不会被挤没。"""
        outer = tk.Frame(parent, bg=bg, width=width)
        outer.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        outer.pack_propagate(False)

        canvas = tk.Canvas(outer, bg=bg, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=bg)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def update_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def update_width(event=None):
            canvas.itemconfigure(window_id, width=canvas.winfo_width())

        def on_mousewheel(event):
            if hasattr(event, "delta") and event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")

        content.bind("<Configure>", update_scrollregion)
        canvas.bind("<Configure>", update_width)
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", on_mousewheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        canvas.bind("<Button-4>", on_mousewheel)
        canvas.bind("<Button-5>", on_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        return content

    # ---------- 主布局 ----------
    def build_ui(self):
        self.root.configure(bg=APP_BG)

        header = tk.Frame(self.root, bg=APP_BG)
        header.pack(fill=tk.X, padx=18, pady=(16, 10))

        left_header = tk.Frame(header, bg=APP_BG)
        left_header.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.label(left_header, "Artifex Display Converter", size=20, weight="bold", bg=APP_BG).pack(anchor="w")
        self.label(
            left_header,
            "一个窗口管理两条输出链路：LCD 屏幕 MJPEG/视频流 + 墨水屏四色 EPD 文件",
            size=10,
            fg=MUTED,
            bg=APP_BG,
        ).pack(anchor="w", pady=(3, 0))

        mode_bar = tk.Frame(header, bg=APP_BG)
        mode_bar.pack(side=tk.RIGHT)
        self.lcd_mode_btn = self.make_button(mode_bar, "LCD / MJPEG", lambda: self.show_mode("lcd"), bg="#0EA5E9")
        self.epaper_mode_btn = self.make_button(mode_bar, "E-Paper / EPD", lambda: self.show_mode("epaper"), bg="#334155")
        self.lcd_mode_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.epaper_mode_btn.pack(side=tk.LEFT)

        self.workspace = tk.Frame(self.root, bg=APP_BG)
        self.workspace.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 12))

        self.lcd_frame = tk.Frame(self.workspace, bg=APP_BG)
        self.epaper_frame = tk.Frame(self.workspace, bg=APP_BG)
        self.build_lcd_ui(self.lcd_frame)
        self.build_epaper_ui(self.epaper_frame)

        status = tk.Frame(self.root, bg="#020617", height=32)
        status.pack(side=tk.BOTTOM, fill=tk.X)
        self.label(status, textvariable=self.status_var, size=9, fg=MUTED, bg="#020617", anchor="w").pack(fill=tk.X, padx=14, pady=7)

    def show_mode(self, mode):
        self.mode.set(mode)
        self.lcd_frame.pack_forget()
        self.epaper_frame.pack_forget()
        if mode == "lcd":
            self.lcd_frame.pack(fill=tk.BOTH, expand=True)
            self.lcd_mode_btn.configure(bg="#0EA5E9")
            self.epaper_mode_btn.configure(bg="#334155")
            self.set_status("LCD 模式：把视频或图片转换成 MJPEG / AVI / MKV / MOV / MP4，适合 TFT 播放链路。")
        else:
            self.epaper_frame.pack(fill=tk.BOTH, expand=True)
            self.lcd_mode_btn.configure(bg="#334155")
            self.epaper_mode_btn.configure(bg="#F59E0B")
            self.set_status("墨水屏模式：把图片量化成四色预览，并导出固定大小 .epd 文件。")
            self.draw_epaper_big_preview()

    def set_status(self, msg):
        self.status_var.set(msg)

    # ---------- 拖拽 ----------
    def setup_drag_drop(self):
        """
        安全启用拖拽。

        macOS 打包版里，tkinterdnd2 可能 import 成功，
        但 TkinterDnD.Tk() 或 drop_target_register() 在运行时失败。
        拖拽只是辅助功能，失败时不能让整个 App 闪退。
        """
        if safe_bind_drop(self.root, self.on_drop):
            self.set_status("拖拽功能已启用。")
        else:
            self.set_status("拖拽功能未启用；可继续使用“选择文件/选择文件夹”按钮。")

    def on_drop(self, event):
        files = self.parse_drop_files(event.data)
        if self.mode.get() == "lcd":
            self.lcd_add_files([f for f in files if Path(f).suffix.lower() in MEDIA_EXTS])
        else:
            self.epaper_add_paths([f for f in files if Path(f).suffix.lower() in IMAGE_EXTS])

    @staticmethod
    def parse_drop_files(data):
        pattern = r"\{([^}]+)\}|(\S+)"
        matches = re.findall(pattern, data)
        files = []
        for m in matches:
            path = m[0] if m[0] else m[1]
            if os.path.isfile(path):
                files.append(path)
        return files

    # =========================
    # LCD / MJPEG 模式
    # =========================
    def build_lcd_ui(self, parent):
        left = self.create_scrollable_panel(parent, width=380, bg=PANEL_BG)

        right = tk.Frame(parent, bg=APP_BG)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.label(left, "LCD 视频转换", size=15, weight="bold", bg=PANEL_BG).pack(anchor="w", padx=18, pady=(18, 4))
        self.label(left, "目标：生成 ESP32-S3 TFT 播放更友好的 MJPEG 文件", size=9, fg=MUTED, bg=PANEL_BG, wraplength=330, justify=tk.LEFT).pack(anchor="w", padx=18, pady=(0, 12))

        chip = tk.Frame(left, bg="#0B1220", highlightthickness=1, highlightbackground="#243044")
        chip.pack(fill=tk.X, padx=18, pady=(0, 12))
        ffmpeg_text = f"FFmpeg：{self.ffmpeg_path}" if self.ffmpeg_path else "FFmpeg：未找到"
        self.label(chip, ffmpeg_text, size=8, fg=SUCCESS if self.ffmpeg_path else DANGER, bg="#0B1220", wraplength=315, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(8, 4))
        if not self.ffmpeg_path:
            self.label(chip, self.ffmpeg_install_hint(), size=8, fg=MUTED, bg="#0B1220", wraplength=315, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 8))
            if not is_frozen_app():
                self.make_button(chip, "打开 FFmpeg 下载/安装页面", self.open_ffmpeg_download_page, bg="#334155").pack(anchor="w", padx=10, pady=(0, 10))

        self.lcd_size_box = self.control_card(left, "输出尺寸", "屏幕分辨率用冒号格式，例如 240:320")
        self.lcd_size_combo = ttk.Combobox(
            self.lcd_size_box,
            textvariable=self.lcd_output_size,
            values=["240:320", "320:240", "480:800", "640:480", "1280:720", "自定义"],
            state="readonly",
        )
        self.lcd_size_combo.pack(fill=tk.X, padx=12, pady=(0, 8))
        self.lcd_size_combo.bind("<<ComboboxSelected>>", self.on_lcd_size_selected)
        self.lcd_custom_size_entry = tk.Entry(self.lcd_size_box, bg="#F8FAFC", relief=tk.FLAT)

        fmt_box = self.control_card(left, "输出格式", ".mjpeg 是裸流，更适合嵌入式；其他是容器格式。")
        ttk.Combobox(
            fmt_box,
            textvariable=self.lcd_output_format,
            values=[".mjpeg", ".avi", ".mkv", ".mov", ".mp4"],
            state="readonly",
        ).pack(fill=tk.X, padx=12, pady=(0, 8))

        q_box = self.control_card(left, "JPEG 质量", "2-31，数字越小越清晰，文件也更大。")
        tk.Scale(q_box, from_=2, to=31, orient=tk.HORIZONTAL, variable=self.lcd_quality, bg=CARD_BG, fg=TEXT,
                 highlightthickness=0, troughcolor="#334155", activebackground=ACCENT).pack(fill=tk.X, padx=10, pady=(0, 8))

        name_box = self.control_card(left, "命名", "保留原功能：可在输出文件名后追加尺寸。")
        tk.Checkbutton(
            name_box,
            text="追加尺寸信息，例如 _mjpeg_240x320",
            variable=self.lcd_add_size_suffix,
            bg=CARD_BG,
            fg=TEXT,
            activebackground=CARD_BG,
            activeforeground=TEXT,
            selectcolor="#0B1220",
        ).pack(anchor="w", padx=10, pady=(0, 10))

        btn_row = tk.Frame(left, bg=PANEL_BG)
        btn_row.pack(fill=tk.X, padx=18, pady=(8, 4))
        self.make_button(btn_row, "添加文件", self.lcd_browse_files, bg="#334155").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))
        self.make_button(btn_row, "移除选中", self.lcd_remove_selected, bg="#334155").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(6, 0))
        self.make_button(left, "清空列表", self.lcd_clear_list, bg="#334155").pack(fill=tk.X, padx=18, pady=(4, 10))

        self.lcd_convert_btn = self.make_button(left, "开始批量转换", self.lcd_start_conversion, bg=SUCCESS, fg="#052E16")
        self.lcd_convert_btn.pack(fill=tk.X, padx=18, pady=(4, 12))
        self.lcd_progress = ttk.Progressbar(left, mode="indeterminate")
        self.lcd_progress.pack(fill=tk.X, padx=18, pady=(0, 16))

        # 右侧列表与说明
        top_card = self.card(right)
        top_card.pack(fill=tk.X, pady=(0, 12))
        self.label(top_card, "LCD 转换队列", size=14, weight="bold", bg=CARD_BG).pack(anchor="w", padx=16, pady=(14, 4))
        desc = "支持拖拽添加；视频会去掉音频并统一帧率，图片会生成 2 帧 MJPEG，便于播放器识别。"
        self.label(top_card, desc, size=9, fg=MUTED, bg=CARD_BG, wraplength=760, justify=tk.LEFT).pack(anchor="w", padx=16, pady=(0, 14))

        list_card = self.card(right)
        list_card.pack(fill=tk.BOTH, expand=True)
        self.lcd_file_count_label = self.label(list_card, "待转换文件：0", size=11, weight="bold", bg=CARD_BG)
        self.lcd_file_count_label.pack(anchor="w", padx=16, pady=(14, 8))

        list_frame = tk.Frame(list_card, bg=CARD_BG)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))
        scroll = tk.Scrollbar(list_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.lcd_listbox = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            yscrollcommand=scroll.set,
            font=("Consolas", 10),
            bg="#0B1220",
            fg=TEXT,
            selectbackground="#0EA5E9",
            selectforeground="#FFFFFF",
            relief=tk.FLAT,
            highlightthickness=0,
        )
        self.lcd_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=self.lcd_listbox.yview)

    def control_card(self, parent, title, note):
        box = self.card(parent)
        box.pack(fill=tk.X, padx=18, pady=6)
        self.label(box, title, size=10, weight="bold", bg=CARD_BG).pack(anchor="w", padx=12, pady=(10, 2))
        self.label(box, note, size=8, fg=MUTED, bg=CARD_BG, wraplength=315, justify=tk.LEFT).pack(anchor="w", padx=12, pady=(0, 8))
        return box

    def find_ffmpeg(self):
        return find_ffmpeg_binary()

    def on_lcd_size_selected(self, _event=None):
        if self.lcd_output_size.get() == "自定义":
            self.lcd_custom_size_entry.pack(fill=tk.X, padx=12, pady=(0, 10))
            self.lcd_custom_size_entry.delete(0, tk.END)
            self.lcd_custom_size_entry.insert(0, "240:320")
        else:
            self.lcd_custom_size_entry.pack_forget()

    def lcd_browse_files(self):
        filenames = filedialog.askopenfilenames(
            title="选择视频或图片",
            filetypes=[("媒体文件", "*.mp4 *.avi *.mov *.mkv *.jpg *.jpeg *.png *.bmp *.webp"), ("所有文件", "*.*")],
        )
        if filenames:
            self.lcd_add_files(filenames)

    def lcd_add_files(self, file_paths):
        added = 0
        for f in file_paths:
            if f not in self.lcd_files and os.path.isfile(f):
                self.lcd_files.append(f)
                self.lcd_listbox.insert(tk.END, os.path.basename(f))
                added += 1
        self.lcd_file_count_label.config(text=f"待转换文件：{len(self.lcd_files)}")
        self.set_status(f"LCD：已添加 {added} 个文件，共 {len(self.lcd_files)} 个待转换。")

    def lcd_remove_selected(self):
        selected = self.lcd_listbox.curselection()
        for idx in reversed(selected):
            del self.lcd_files[idx]
            self.lcd_listbox.delete(idx)
        self.lcd_file_count_label.config(text=f"待转换文件：{len(self.lcd_files)}")
        self.set_status(f"LCD：剩余 {len(self.lcd_files)} 个文件。")

    def lcd_clear_list(self):
        self.lcd_files.clear()
        self.lcd_listbox.delete(0, tk.END)
        self.lcd_file_count_label.config(text="待转换文件：0")
        self.set_status("LCD：列表已清空。")

    def lcd_get_size(self):
        size = self.lcd_output_size.get()
        if size == "自定义":
            size = self.lcd_custom_size_entry.get().strip()
        if not re.match(r"^\d+[:xX]\d+$", size or ""):
            raise ValueError("请输入正确尺寸，例如 240:320")
        return size.replace("x", ":").replace("X", ":")

    def lcd_start_conversion(self):
        if not self.ffmpeg_path:
            # 用户可能在程序启动后才安装/复制 FFmpeg，因此转换前再检测一次。
            self.ffmpeg_path = self.find_ffmpeg()

        if not self.ffmpeg_path:
            self.prompt_missing_ffmpeg()
            return
        if not self.lcd_files:
            messagebox.showwarning("提示", "请先添加要转换的文件。")
            return
        try:
            size = self.lcd_get_size()
        except Exception as e:
            messagebox.showerror("尺寸错误", str(e))
            return

        self.lcd_convert_btn.config(state=tk.DISABLED)
        self.lcd_progress.start(10)
        self.set_status("LCD：开始批量转换...")
        threading.Thread(target=self.lcd_batch_convert, args=(size,), daemon=True).start()

    def lcd_batch_convert(self, size):
        total = len(self.lcd_files)
        success_count = 0
        fail_list = []
        for idx, input_path in enumerate(self.lcd_files):
            self.root.after(0, self.set_status, f"LCD：转换中 ({idx + 1}/{total}) {os.path.basename(input_path)}")
            ok, msg = self.lcd_convert_one(input_path, size)
            if ok:
                success_count += 1
            else:
                fail_list.append((os.path.basename(input_path), msg))
        self.root.after(0, self.lcd_batch_done, success_count, total, fail_list)

    def lcd_convert_one(self, input_path, size):
        base = os.path.splitext(input_path)[0]
        ext = self.lcd_output_format.get()
        if self.lcd_add_size_suffix.get():
            output_file = f"{base}_mjpeg_{size.replace(':', 'x')}{ext}"
        else:
            output_file = f"{base}{ext}"

        is_image = Path(input_path).suffix.lower() in IMAGE_EXTS
        cmd = [self.ffmpeg_path]
        if is_image:
            cmd.extend(["-loop", "1", "-i", input_path, "-r", "25", "-frames:v", "2"])
        else:
            cmd.extend(["-i", input_path, "-an", "-r", "25"])

        cmd.extend(["-vf", f"scale={size},format=yuvj420p", "-vcodec", "mjpeg", "-q:v", str(self.lcd_quality.get())])

        if ext == ".mjpeg":
            cmd.extend(["-bsf:v", "mjpeg2jpeg", "-f", "mjpeg"])
        elif ext == ".mp4":
            cmd.extend(["-f", "mp4"])
        elif ext == ".avi":
            cmd.extend(["-f", "avi"])
        elif ext == ".mkv":
            cmd.extend(["-f", "matroska"])
        elif ext == ".mov":
            cmd.extend(["-f", "mov"])
        cmd.extend(["-y", output_file])

        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True, output_file
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode(errors="ignore") if e.stderr else "未知 FFmpeg 错误"
            print(f"\n[FFmpeg Error] {input_path}\n{err}\n")
            return False, err
        except Exception as e:
            return False, str(e)

    def lcd_batch_done(self, success, total, fail_list):
        self.lcd_progress.stop()
        self.lcd_convert_btn.config(state=tk.NORMAL)
        if success == total:
            self.set_status(f"LCD：全部转换成功，共 {total} 个文件。")
            messagebox.showinfo("完成", f"全部 {total} 个文件转换成功。")
        else:
            self.set_status(f"LCD：转换完成，成功 {success}/{total}。")
            fail_msg_lines = []
            for name, err in fail_list:
                err_short = err if len(err) <= 500 else err[:500] + "..."
                fail_msg_lines.append(f"{name}: {err_short}")
            messagebox.showerror("部分失败", f"成功 {success} 个，失败 {len(fail_list)} 个。\n\n" + "\n\n".join(fail_msg_lines))

    # =========================
    # 墨水屏 / EPD 模式
    # =========================
    def build_epaper_ui(self, parent):
        left = self.create_scrollable_panel(parent, width=390, bg=PANEL_BG)

        center = tk.Frame(parent, bg=APP_BG, width=330)
        center.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 12))
        center.pack_propagate(False)

        right = tk.Frame(parent, bg=APP_BG)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.label(left, "墨水屏图片转换", size=15, weight="bold", bg=PANEL_BG).pack(anchor="w", padx=18, pady=(18, 4))
        self.label(left, "目标：预览四色量化效果，并导出 MCU 可直接读取的 .epd 数据。", size=9, fg=MUTED, bg=PANEL_BG, wraplength=340, justify=tk.LEFT).pack(anchor="w", padx=18, pady=(0, 12))

        if not HAS_PIL:
            warn = self.card(left, bg="#3B1D1D")
            warn.pack(fill=tk.X, padx=18, pady=(0, 12))
            self.label(warn, "未安装 Pillow", size=10, weight="bold", bg="#3B1D1D", fg="#FCA5A5").pack(anchor="w", padx=12, pady=(10, 2))
            self.label(warn, "请运行：pip install pillow", size=9, bg="#3B1D1D", fg="#FCA5A5").pack(anchor="w", padx=12, pady=(0, 10))

        row = tk.Frame(left, bg=PANEL_BG)
        row.pack(fill=tk.X, padx=18, pady=(0, 8))
        self.make_button(row, "选择图片", self.epaper_select_files, bg="#334155").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.make_button(row, "选择文件夹", self.epaper_select_folder, bg="#334155").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        preset_box = self.control_card(left, "屏幕预设", "包含尺寸、bpp、调色板、打包顺序。")
        ttk.Combobox(preset_box, textvariable=self.epaper_preset_var, values=list(EPAPER_PRESETS.keys()), state="readonly").pack(fill=tk.X, padx=12, pady=(0, 8))
        self.epaper_preset_var.trace_add("write", lambda *_: self.epaper_rebuild_previews())
        self.epaper_note_label = self.label(preset_box, EPAPER_PRESETS[self.epaper_preset_var.get()].get("note", ""), size=8, fg=MUTED, bg=CARD_BG, wraplength=320, justify=tk.LEFT)
        self.epaper_note_label.pack(anchor="w", padx=12, pady=(0, 10))

        fit_box = self.control_card(left, "画面适配", "裁剪填满适合屏幕展示；留白适合完整保留图。")
        ttk.Combobox(fit_box, textvariable=self.epaper_fit_var, values=["裁剪填满", "完整适配留白", "拉伸"], state="readonly").pack(fill=tk.X, padx=12, pady=(0, 8))
        self.epaper_fit_var.trace_add("write", lambda *_: self.epaper_rebuild_previews())
        ttk.Combobox(fit_box, textvariable=self.epaper_rotate_var, values=[0, 90, 180, 270], state="readonly").pack(fill=tk.X, padx=12, pady=(0, 10))
        self.epaper_rotate_var.trace_add("write", lambda *_: self.epaper_rebuild_previews())

        dither_box = self.control_card(left, "量化与抖动", "四色屏建议开启抖动，纯图标/文字可以关闭。")
        tk.Checkbutton(
            dither_box,
            text="启用 Floyd-Steinberg 抖动",
            variable=self.epaper_dither_var,
            command=self.epaper_rebuild_previews,
            bg=CARD_BG,
            fg=TEXT,
            activebackground=CARD_BG,
            activeforeground=TEXT,
            selectcolor="#0B1220",
        ).pack(anchor="w", padx=10, pady=(0, 10))

        sliders = self.control_card(left, "全局图像调节", "修改后会重新生成预览。")
        self.epaper_add_slider(sliders, "亮度", self.epaper_bright_var, 0.3, 2.5)
        self.epaper_add_slider(sliders, "对比度", self.epaper_contrast_var, 0.3, 3.0)
        self.epaper_add_slider(sliders, "饱和度", self.epaper_sat_var, 0.0, 3.0)
        self.epaper_add_slider(sliders, "锐化", self.epaper_sharp_var, 0.0, 3.0)
        self.epaper_add_slider(sliders, "抖动强度", self.epaper_dither_strength_var, 0.0, 1.5)

        self.make_button(left, "重新生成全部预览", self.epaper_rebuild_previews, bg="#334155").pack(fill=tk.X, padx=18, pady=(10, 6))
        self.make_button(left, "只导出当前选中 .epd", self.epaper_export_selected, bg=ACCENT_2, fg="#1F1300").pack(fill=tk.X, padx=18, pady=(0, 6))
        self.make_button(left, "批量导出全部 .epd", self.epaper_export_all, bg=SUCCESS, fg="#052E16").pack(fill=tk.X, padx=18, pady=(0, 12))

        # 中间列表
        list_card = self.card(center)
        list_card.pack(fill=tk.BOTH, expand=True)
        self.epaper_count_label = self.label(list_card, "图片列表：0", size=12, weight="bold", bg=CARD_BG)
        self.epaper_count_label.pack(anchor="w", padx=14, pady=(14, 8))
        list_frame = tk.Frame(list_card, bg=CARD_BG)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))
        scroll = tk.Scrollbar(list_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.epaper_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scroll.set,
            font=("Consolas", 10),
            bg="#0B1220",
            fg=TEXT,
            selectbackground="#F59E0B",
            selectforeground="#111827",
            relief=tk.FLAT,
            highlightthickness=0,
        )
        self.epaper_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.epaper_listbox.bind("<<ListboxSelect>>", self.epaper_on_select)
        scroll.config(command=self.epaper_listbox.yview)

        # 右侧预览
        preview_card = self.card(right)
        preview_card.pack(fill=tk.BOTH, expand=True)
        top = tk.Frame(preview_card, bg=CARD_BG)
        top.pack(fill=tk.X, padx=16, pady=(14, 8))
        self.label(top, "大预览", size=14, weight="bold", bg=CARD_BG).pack(side=tk.LEFT)
        self.epaper_preview_info = self.label(top, "", size=9, fg=MUTED, bg=CARD_BG)
        self.epaper_preview_info.pack(side=tk.RIGHT)

        quick = tk.Frame(preview_card, bg=CARD_BG)
        quick.pack(fill=tk.X, padx=16, pady=(0, 10))
        self.make_button(quick, "重新预览", self.epaper_rebuild_previews, bg="#334155").pack(side=tk.LEFT, padx=(0, 8))
        self.make_button(quick, "导出当前 .epd", self.epaper_export_selected, bg=ACCENT_2, fg="#1F1300").pack(side=tk.LEFT, padx=(0, 8))
        self.make_button(quick, "批量导出全部 .epd", self.epaper_export_all, bg=SUCCESS, fg="#052E16").pack(side=tk.LEFT)

        canvases = tk.Frame(preview_card, bg=CARD_BG)
        canvases.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))
        left_prev = tk.Frame(canvases, bg=CARD_BG)
        left_prev.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        right_prev = tk.Frame(canvases, bg=CARD_BG)
        right_prev.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))
        self.label(left_prev, "原图适配后", size=10, weight="bold", fg=MUTED, bg=CARD_BG).pack(anchor="w", pady=(0, 6))
        self.label(right_prev, "最终量化效果", size=10, weight="bold", fg=MUTED, bg=CARD_BG).pack(anchor="w", pady=(0, 6))
        self.epaper_orig_canvas = tk.Canvas(left_prev, bg="#E5E7EB", highlightthickness=0)
        self.epaper_conv_canvas = tk.Canvas(right_prev, bg="#E5E7EB", highlightthickness=0)
        self.epaper_orig_canvas.pack(fill=tk.BOTH, expand=True)
        self.epaper_conv_canvas.pack(fill=tk.BOTH, expand=True)
        self.epaper_orig_canvas.bind("<Configure>", lambda _e: self.draw_epaper_big_preview())
        self.epaper_conv_canvas.bind("<Configure>", lambda _e: self.draw_epaper_big_preview())

        foot = self.label(
            preview_card,
            "确认右侧效果后导出。.epd 文件名与输入图片同名，例如 sword.png → sword.epd。",
            size=9,
            fg=MUTED,
            bg=CARD_BG,
            anchor="w",
        )
        foot.pack(fill=tk.X, padx=16, pady=(0, 14))

    def epaper_add_slider(self, parent, name, var, a, b):
        row = tk.Frame(parent, bg=CARD_BG)
        row.pack(fill=tk.X, padx=10, pady=(4, 6))
        self.label(row, name, size=8, fg=MUTED, bg=CARD_BG).pack(anchor="w")
        line = tk.Frame(row, bg=CARD_BG)
        line.pack(fill=tk.X)
        scale = ttk.Scale(line, from_=a, to=b, variable=var, command=lambda _v: self.epaper_rebuild_previews_delayed())
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        value_label = self.label(line, "", size=8, fg=MUTED, bg=CARD_BG, width=5)
        value_label.pack(side=tk.RIGHT, padx=(8, 0))

        def update_label(*_):
            value_label.config(text=f"{var.get():.2f}")

        var.trace_add("write", update_label)
        update_label()

    def epaper_current_config(self):
        p = EPAPER_PRESETS[self.epaper_preset_var.get()]
        palette_rgb = [hx2rgb(c[2]) for c in p["palette"]]
        palette_values = [c[1] for c in p["palette"]]
        return {
            "w": p["w"],
            "h": p["h"],
            "bpp": p["bpp"],
            "order": p["order"],
            "palette_rgb": palette_rgb,
            "palette_values": palette_values,
            "note": p.get("note", ""),
        }

    def epaper_select_files(self):
        if not self.require_pil():
            return
        paths = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.tiff"), ("All files", "*.*")],
        )
        if paths:
            self.epaper_set_paths(list(paths))

    def epaper_select_folder(self):
        if not self.require_pil():
            return
        folder = filedialog.askdirectory(title="选择包含图片的文件夹")
        if not folder:
            return
        paths = [str(p) for p in sorted(Path(folder).iterdir()) if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
        if not paths:
            messagebox.showwarning("没有图片", "这个文件夹里没有 JPG/PNG/BMP/WEBP/TIFF 图片。")
            return
        self.epaper_set_paths(paths)

    def epaper_add_paths(self, paths):
        if not self.require_pil():
            return
        new_paths = list(self.epaper_paths)
        for p in paths:
            if p not in new_paths and os.path.isfile(p):
                new_paths.append(p)
        self.epaper_set_paths(new_paths)

    def epaper_set_paths(self, paths):
        self.epaper_paths = [p for p in paths if Path(p).suffix.lower() in IMAGE_EXTS]
        self.epaper_preview_cache.clear()
        self.epaper_selected_path = None
        self.epaper_listbox.delete(0, tk.END)
        for p in self.epaper_paths:
            self.epaper_listbox.insert(tk.END, Path(p).name)
        self.epaper_count_label.config(text=f"图片列表：{len(self.epaper_paths)}")
        if self.epaper_paths:
            self.epaper_listbox.selection_set(0)
            self.epaper_listbox.activate(0)
            self.epaper_selected_path = self.epaper_paths[0]
        self.epaper_rebuild_previews()

    def require_pil(self):
        if HAS_PIL:
            return True
        messagebox.showerror(
            "缺少依赖",
            packaged_missing_message(
                "Pillow",
                "墨水屏转换需要 Pillow。开发环境请运行：pip install -r requirements.txt"
            ),
        )
        return False

    def epaper_make_converted_preview(self, path: str):
        cfg = self.epaper_current_config()
        img = Image.open(path).convert("RGB")
        angle = int(self.epaper_rotate_var.get())
        if angle:
            img = img.rotate(-angle, expand=True)
        img = fit_image(img, cfg["w"], cfg["h"], self.epaper_fit_var.get())
        img = enhance_image(
            img,
            self.epaper_bright_var.get(),
            self.epaper_contrast_var.get(),
            self.epaper_sat_var.get(),
            self.epaper_sharp_var.get(),
        )
        if self.epaper_dither_var.get():
            return quantize_fs(img, cfg["palette_rgb"], self.epaper_dither_strength_var.get())
        return quantize_nearest(img, cfg["palette_rgb"])

    def epaper_rebuild_previews_delayed(self):
        if self._epaper_preview_job:
            self.root.after_cancel(self._epaper_preview_job)
        self._epaper_preview_job = self.root.after(250, self.epaper_rebuild_previews)

    def epaper_rebuild_previews(self):
        if not HAS_PIL:
            return
        self.epaper_note_label.config(text=self.epaper_current_config()["note"])
        if not self.epaper_paths:
            self.draw_epaper_big_preview()
            return

        self.epaper_preview_cache.clear()
        total = len(self.epaper_paths)
        self.set_status(f"墨水屏：正在生成预览 0/{total}...")

        def worker():
            for i, p in enumerate(self.epaper_paths, start=1):
                try:
                    self.epaper_preview_cache[p] = self.epaper_make_converted_preview(p)
                    self.root.after(0, self.set_status, f"墨水屏：预览生成中 {i}/{total}")
                except Exception as e:
                    self.root.after(0, messagebox.showerror, "转换失败", f"{p}\n{e}")
                    return
            self.root.after(0, self.epaper_preview_done)

        threading.Thread(target=worker, daemon=True).start()

    def epaper_preview_done(self):
        cfg = self.epaper_current_config()
        size = output_size(cfg["w"], cfg["h"], cfg["bpp"])
        self.set_status(f"墨水屏：预览完成 {len(self.epaper_paths)} 张。输出大小：{size} bytes / 张。")
        self.draw_epaper_big_preview()

    def epaper_on_select(self, _event=None):
        sel = self.epaper_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self.epaper_paths):
            self.epaper_selected_path = self.epaper_paths[idx]
            self.draw_epaper_big_preview()

    def draw_image_to_canvas(self, canvas, img, nearest=True):
        canvas.delete("all")
        if img is None:
            return None
        cw = max(1, canvas.winfo_width())
        ch = max(1, canvas.winfo_height())
        iw, ih = img.size
        scale = min(cw / iw, ch / ih) * 0.90
        new_w = max(1, int(iw * scale))
        new_h = max(1, int(ih * scale))
        resample = Image.Resampling.NEAREST if nearest else Image.Resampling.LANCZOS
        show = img.resize((new_w, new_h), resample)
        tkimg = ImageTk.PhotoImage(show)
        canvas.create_image(cw // 2, ch // 2, image=tkimg)
        return tkimg

    def draw_epaper_big_preview(self):
        if not HAS_PIL:
            return
        if not hasattr(self, "epaper_orig_canvas"):
            return
        if not self.epaper_selected_path:
            self.epaper_orig_canvas.delete("all")
            self.epaper_conv_canvas.delete("all")
            self.epaper_preview_info.config(text="")
            return
        try:
            cfg = self.epaper_current_config()
            orig = Image.open(self.epaper_selected_path).convert("RGB")
            angle = int(self.epaper_rotate_var.get())
            if angle:
                orig = orig.rotate(-angle, expand=True)
            orig = fit_image(orig, cfg["w"], cfg["h"], self.epaper_fit_var.get())
            conv = self.epaper_preview_cache.get(self.epaper_selected_path)
            if conv is None:
                conv = self.epaper_make_converted_preview(self.epaper_selected_path)
                self.epaper_preview_cache[self.epaper_selected_path] = conv
            self.epaper_current_original_tk = self.draw_image_to_canvas(self.epaper_orig_canvas, orig, nearest=False)
            self.epaper_current_preview_tk = self.draw_image_to_canvas(self.epaper_conv_canvas, conv, nearest=True)
            self.epaper_preview_info.config(text=f"{Path(self.epaper_selected_path).name} → {Path(self.epaper_selected_path).stem}.epd")
        except Exception as e:
            self.epaper_preview_info.config(text=f"预览失败：{e}")

    def epaper_preview_to_bytes(self, img) -> bytes:
        cfg = self.epaper_current_config()
        codes = image_to_codes(img, cfg["palette_rgb"], cfg["palette_values"])

        # 行尾补齐颜色。四色屏里 WHITE 通常是 palette_values[1]。
        pad_value = cfg["palette_values"][1] if len(cfg["palette_values"]) > 1 else 0

        data = pack_codes(
            codes,
            cfg["w"],
            cfg["h"],
            cfg["bpp"],
            cfg["order"],
            pad_value=pad_value,
        )

        expected = output_size(cfg["w"], cfg["h"], cfg["bpp"])
        if len(data) != expected:
            raise RuntimeError(f"输出大小错误：{len(data)}，期望 {expected}")
        return data

    def epaper_choose_output_dir(self):
        return filedialog.askdirectory(title="选择 .epd 导出文件夹")

    def epaper_export_selected(self):
        if not self.require_pil():
            return
        if not self.epaper_selected_path:
            messagebox.showwarning("没有选中图片", "请先在列表中选择一张图片。")
            return
        out_dir = self.epaper_choose_output_dir()
        if not out_dir:
            return
        try:
            img = self.epaper_preview_cache.get(self.epaper_selected_path)
            if img is None:
                img = self.epaper_make_converted_preview(self.epaper_selected_path)
            data = self.epaper_preview_to_bytes(img)
            out_path = Path(out_dir) / (Path(self.epaper_selected_path).stem + ".epd")
            out_path.write_bytes(data)
            self.set_status(f"墨水屏：已导出 {out_path.name}，大小 {len(data)} bytes。")
            messagebox.showinfo("导出完成", f"已导出：\n{out_path}\n\n大小：{len(data)} bytes")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def epaper_export_all(self):
        if not self.require_pil():
            return
        if not self.epaper_paths:
            messagebox.showwarning("没有图片", "请先选择图片或文件夹。")
            return
        out_dir = self.epaper_choose_output_dir()
        if not out_dir:
            return
        try:
            total = len(self.epaper_paths)
            cfg = self.epaper_current_config()
            expected = output_size(cfg["w"], cfg["h"], cfg["bpp"])
            for i, p in enumerate(self.epaper_paths, start=1):
                img = self.epaper_preview_cache.get(p)
                if img is None:
                    img = self.epaper_make_converted_preview(p)
                data = self.epaper_preview_to_bytes(img)
                out_path = Path(out_dir) / (Path(p).stem + ".epd")
                out_path.write_bytes(data)
                self.set_status(f"墨水屏：导出中 {i}/{total}  {out_path.name}")
                self.root.update_idletasks()
            self.set_status(f"墨水屏：导出完成 {total} 个 .epd 文件，每个文件应为 {expected} bytes。")
            messagebox.showinfo("批量导出完成", f"已导出 {total} 个 .epd 文件。\n每个文件大小应为 {expected} bytes。")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))


def create_root():
    """
    创建 GUI 根窗口。

    tkinterdnd2 是可选拖拽功能：
    - TkinterDnD.Tk() 成功：启用拖拽
    - TkinterDnD.Tk() 失败：自动降级普通 tk.Tk()
    """
    global HAS_DND, DND_RUNTIME_OK

    DND_RUNTIME_OK = False

    if HAS_DND and TkinterDnD is not None:
        try:
            root = TkinterDnD.Tk()
            DND_RUNTIME_OK = True
            setattr(root, "_artifex_dnd_ready", True)
            print("[BOOT] TkinterDnD root created", file=sys.stderr)
            return root
        except Exception as e:
            # 关键：拖拽只是辅助功能，不能因为它失败导致整个 App 闪退。
            HAS_DND = False
            DND_RUNTIME_OK = False
            print(f"[WARN] tkinterdnd2 初始化失败，已回退到普通 Tk：{e}", file=sys.stderr)
            traceback.print_exc()

    root = tk.Tk()
    setattr(root, "_artifex_dnd_ready", False)
    print("[BOOT] normal Tk root created", file=sys.stderr)
    return root


def is_dnd_ready(widget=None):
    """
    判断拖拽功能是否真的可用。

    不能只看 HAS_DND，因为 HAS_DND 只说明 import 成功；
    真正能不能拖拽，要看 TkinterDnD.Tk() 是否初始化成功。
    """
    if not (HAS_DND and DND_RUNTIME_OK and DND_FILES is not None):
        return False

    if widget is None:
        return True

    return hasattr(widget, "drop_target_register") and hasattr(widget, "dnd_bind")


def safe_bind_drop(widget, callback):
    """
    安全绑定拖拽事件。

    拖拽不可用时直接返回 False，不抛异常，不影响主程序打开。
    """
    if not is_dnd_ready(widget):
        return False

    try:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", callback)
        print("[BOOT] drag-and-drop enabled", file=sys.stderr)
        return True
    except Exception as e:
        print(f"[WARN] 拖拽绑定失败，已跳过拖拽功能：{e}", file=sys.stderr)
        traceback.print_exc()
        return False


def write_crash_log():
    """
    GUI 闪退时，把完整 Python 异常写入日志。
    macOS 下写到 ~/Library/Logs，方便用户找到。
    """
    try:
        log_dir = Path.home() / "Library" / "Logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "ArtifexDisplayConverter_crash.log"
    except Exception:
        log_path = Path.cwd() / "ArtifexDisplayConverter_crash.log"

    try:
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        print(f"[ERROR] Crash log saved to: {log_path}", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] Failed to write crash log: {e}", file=sys.stderr)


def main():
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())

    if "--gui-smoke-test" in sys.argv:
        try:
            print("[BOOT] GUI smoke test start", file=sys.stderr)
            root = create_root()
            app = DisplayConverterApp(root)
            root.update_idletasks()
            root.update()
            root.destroy()
            print("GUI smoke test OK")
            raise SystemExit(0)
        except Exception:
            write_crash_log()
            traceback.print_exc()
            raise SystemExit(10)

    try:
        print("[BOOT] create root", file=sys.stderr)
        root = create_root()

        print("[BOOT] create app", file=sys.stderr)
        app = DisplayConverterApp(root)

        print("[BOOT] mainloop", file=sys.stderr)
        root.mainloop()

    except Exception:
        write_crash_log()
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
