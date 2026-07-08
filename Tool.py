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
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

# ========== 可选依赖：拖拽 ==========
# 说明：
# 1. Windows 版本：保留 tkinterdnd2 拖拽功能。
# 2. macOS arm64 / M 系列版本：禁用 tkinterdnd2。
#    原因：tkinterdnd2 底层依赖 tkdnd；在 macOS arm64 打包环境里容易出现
#    “Unable to load tkdnd library.”，导致 GUI 初始化失败或 App 闪退。
# 3. 拖拽只是辅助功能，不能影响主程序打开。macOS 用户仍可用“选择文件/选择文件夹”。
DND_FILES = None
TkinterDnD = None
HAS_DND = False
DND_RUNTIME_OK = False
DND_IMPORT_ERROR = None
DND_DISABLED_REASON = None

if platform.system() == "Darwin":
    DND_DISABLED_REASON = "disabled on macOS to avoid tkdnd runtime crash"
else:
    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
        HAS_DND = True
        DND_IMPORT_ERROR = None
        DND_DISABLED_REASON = None
    except Exception as e:
        DND_FILES = None
        TkinterDnD = None
        HAS_DND = False
        DND_IMPORT_ERROR = e
        DND_DISABLED_REASON = f"import failed: {e}"

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
    返回 PyInstaller 资源目录。

    注意：macOS onefile 会解压到 /private/var/folders/.../_MEIxxxx，
    这个目录是临时目录，不能长期缓存，也不应该优先展示给用户。
    运行时检测可以使用它，但发布包优先使用 .app/Contents/Resources。
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass).resolve()
    return app_dir()


def macos_contents_dir() -> Path | None:
    """如果当前运行在 macOS .app 中，返回 Contents 目录。"""
    try:
        exe = Path(sys.executable).resolve()
        if exe.parent.name == "MacOS" and exe.parent.parent.name == "Contents":
            return exe.parent.parent
    except Exception:
        pass
    base = app_dir()
    if base.name == "MacOS" and base.parent.name == "Contents":
        return base.parent
    return None


def common_resource_dirs():
    """按优先级返回可能存在 ffmpeg 的目录。

    关键修复：macOS 优先查 .app/Contents/Resources，
    再查 PyInstaller 临时 _MEIPASS。这样可以规避 Windows 正常、
    macOS 因 _MEI 临时路径变化导致 No such file or directory 的问题。
    """
    base = app_dir()
    res = resource_dir()
    dirs = []

    contents = macos_contents_dir()
    if contents is not None:
        dirs.extend([
            contents / "Resources",
            contents / "Resources" / "bin",
            contents / "MacOS",
            contents / "Frameworks",
        ])

    # onedir / 开发目录优先于 onefile 临时目录。
    dirs.extend([
        base,
        base / "bin",
        base / "ffmpeg",
        base / "ffmpeg" / "bin",
        base / "_internal",
        base / "_internal" / "bin",
    ])

    # _MEIPASS 只作为运行时兜底，不缓存、不展示为稳定路径。
    dirs.extend([
        res,
        res / "bin",
        res / "ffmpeg",
        res / "ffmpeg" / "bin",
        res / "_internal",
        res / "_internal" / "bin",
    ])

    out = []
    seen = set()
    for d in dirs:
        try:
            d = Path(d).resolve()
        except Exception:
            d = Path(d)
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



# =========================
# 日志
# =========================
def log_dir() -> Path:
    """返回日志目录。"""
    system = platform.system()
    if system == "Darwin":
        d = Path.home() / "Library" / "Logs"
    elif system == "Windows":
        base = os.environ.get("LOCALAPPDATA")
        d = Path(base) / "ArtifexDisplayConverter" / "Logs" if base else Path.home() / "AppData" / "Local" / "ArtifexDisplayConverter" / "Logs"
    else:
        d = Path.home() / ".cache" / "ArtifexDisplayConverter" / "logs"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        d = Path.cwd()
    return d


def boot_log_path() -> Path:
    return log_dir() / "ArtifexDisplayConverter_boot.log"


def crash_log_path() -> Path:
    return log_dir() / "ArtifexDisplayConverter_crash.log"


def log_event(message: str):
    """同时写入日志文件和 stderr，方便 GitHub Actions / 终端查看。"""
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    try:
        with open(boot_log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, file=sys.stderr)


def write_crash_log(context: str = "crash"):
    """把当前异常写入 crash log。必须在 except 块内调用。"""
    path = crash_log_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {context}\n")
            f.write(f"system={platform.system()} machine={platform.machine()} python={sys.version}\n")
            f.write(f"frozen={is_frozen_app()} app_dir={app_dir()} resource_dir={resource_dir()}\n")
            f.write(f"HAS_DND={HAS_DND} DND_RUNTIME_OK={DND_RUNTIME_OK} DND_DISABLED_REASON={DND_DISABLED_REASON}\n")
            traceback.print_exc(file=f)
    except Exception as e:
        print(f"[ERROR] Failed to write crash log: {e}", file=sys.stderr)
    log_event(f"[ERROR] Crash log saved to: {path}")


def log_environment(prefix: str = "ENV"):
    log_event(
        f"{prefix}: system={platform.system()} machine={platform.machine()} "
        f"python={sys.version.split()[0]} frozen={is_frozen_app()}"
    )
    log_event(f"{prefix}: app_dir={app_dir()}")
    log_event(f"{prefix}: resource_dir={resource_dir()}")
    log_event(
        f"{prefix}: HAS_DND={HAS_DND} DND_RUNTIME_OK={DND_RUNTIME_OK} "
        f"DND_DISABLED_REASON={DND_DISABLED_REASON}"
    )


def self_test() -> int:
    """GitHub Actions 用的无 GUI 自检，不创建 Tk 窗口。"""
    print("Artifex Display Converter self-test")
    print(f"system={platform.system()}")
    print(f"machine={platform.machine()}")
    print(f"python={sys.version.split()[0]}")
    print(f"frozen={is_frozen_app()}")
    print(f"app_dir={app_dir()}")
    print(f"resource_dir={resource_dir()}")
    print(f"log_dir={log_dir()}")
    print(f"Pillow={'OK' if HAS_PIL else 'MISSING'}")
    print(f"tkinterdnd2={'OK' if HAS_DND else 'DISABLED/MISSING/OPTIONAL'}")
    print(f"DND_DISABLED_REASON={DND_DISABLED_REASON}")
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
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"}
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


def safe_askopenfilenames(title: str, allowed_exts: set[str], label: str):
    """
    跨平台安全文件选择。

    修复点：
    macOS 的 Tk/Aqua 原生文件选择框对 filetypes 参数比较敏感。
    某些写法，例如 "*.png;*.jpg;*.jpeg"，在 macOS 上可能直接触发
    -[__NSArrayM insertObject:atIndex:]: object cannot be nil
    然后导致整个 app 意外退出。

    处理策略：
    - macOS：不把 filetypes 传给系统文件选择框，避免 Aqua 崩溃；
      用户选完后再由 Python 按扩展名过滤。
    - Windows / Linux：继续使用文件类型过滤，保持原来的使用体验。
    """
    normalized_exts = set()
    for ext in allowed_exts:
        ext = str(ext).strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        normalized_exts.add(ext)

    try:
        if platform.system() == "Darwin":
            selected = filedialog.askopenfilenames(title=title)
        else:
            patterns = " ".join(f"*{ext}" for ext in sorted(normalized_exts))
            selected = filedialog.askopenfilenames(
                title=title,
                filetypes=[
                    (label, patterns),
                    ("所有文件", "*.*"),
                ],
            )

        valid = []
        ignored = []

        for raw_path in selected:
            path = str(raw_path)
            if Path(path).suffix.lower() in normalized_exts:
                valid.append(path)
            else:
                ignored.append(path)

        return valid, ignored

    except Exception as e:
        log_event(f"[ERROR] safe_askopenfilenames failed: {e}")
        try:
            messagebox.showerror("选择文件失败", str(e))
        except Exception:
            pass
        return [], []


def show_ignored_files_warning(ignored):
    """选择文件后提醒被过滤掉的不支持文件，最多显示 20 个，避免弹窗过长。"""
    if not ignored:
        return

    shown = [Path(p).name for p in ignored[:20]]
    more = len(ignored) - len(shown)

    msg = "以下文件类型不支持，已自动忽略：\n\n" + "\n".join(shown)
    if more > 0:
        msg += f"\n\n另外还有 {more} 个文件未显示。"

    messagebox.showwarning("已忽略不支持的文件", msg)


# =========================
# 跨平台深色控件
# =========================
class FlatButton(tk.Label):
    """
    用 Label 自绘按钮，避免 macOS Aqua 原生 Button 忽略 bg/fg 导致变白。
    支持 .config(state=tk.DISABLED / tk.NORMAL)，兼容原来的调用方式。
    """

    def __init__(self, parent, text, command=None, bg="#273449", fg=TEXT, active=None, disabled_bg="#475569", disabled_fg="#94A3B8"):
        self.command = command
        self._enabled = True
        self._normal_bg = bg
        self._normal_fg = fg
        self._active_bg = active or self._lighten(bg)
        self._active_fg = fg
        self._disabled_bg = disabled_bg
        self._disabled_fg = disabled_fg
        super().__init__(
            parent,
            text=text,
            bg=bg,
            fg=fg,
            activebackground=self._active_bg,
            activeforeground=fg,
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=8,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold"),
            anchor="center",
        )
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    @staticmethod
    def _lighten(hex_color: str, amount: int = 18) -> str:
        try:
            h = hex_color.strip().lstrip("#")
            r = min(255, int(h[0:2], 16) + amount)
            g = min(255, int(h[2:4], 16) + amount)
            b = min(255, int(h[4:6], 16) + amount)
            return f"#{r:02X}{g:02X}{b:02X}"
        except Exception:
            return hex_color

    def _on_enter(self, _event=None):
        if self._enabled:
            super().configure(bg=self._active_bg, fg=self._active_fg)

    def _on_leave(self, _event=None):
        if self._enabled:
            super().configure(bg=self._normal_bg, fg=self._normal_fg)

    def _on_click(self, _event=None):
        if self._enabled and self.command:
            self.command()

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        state = kw.pop("state", None)
        if "command" in kw:
            self.command = kw.pop("command")
        if "bg" in kw or "background" in kw:
            new_bg = kw.get("bg", kw.get("background"))
            self._normal_bg = new_bg
            self._active_bg = self._lighten(new_bg)
        if "fg" in kw or "foreground" in kw:
            self._normal_fg = kw.get("fg", kw.get("foreground"))
            self._active_fg = self._normal_fg
        if state is not None:
            self._enabled = state not in (tk.DISABLED, "disabled", False)
            if self._enabled:
                kw.setdefault("bg", self._normal_bg)
                kw.setdefault("fg", self._normal_fg)
                kw.setdefault("cursor", "hand2")
            else:
                kw.setdefault("bg", self._disabled_bg)
                kw.setdefault("fg", self._disabled_fg)
                kw.setdefault("cursor", "")
        return super().configure(**kw)

    config = configure


class DarkDropdown(tk.Frame):
    """自绘下拉框，替代 ttk.Combobox，避免 macOS 上变成白色原生控件。"""

    def __init__(self, parent, textvariable, values, bg=CARD_BG, fg=TEXT, popup_bg="#0B1220", highlight="#243044", width=None, state="readonly"):
        super().__init__(parent, bg=bg, highlightthickness=1, highlightbackground=highlight)
        self.variable = textvariable
        self.values = list(values)
        self.bg = bg
        self.fg = fg
        self.popup_bg = popup_bg
        self.highlight = highlight
        self._callbacks = {}
        self._popup = None
        self._state = state
        self._button = tk.Label(
            self,
            text="",
            bg="#F8FAFC" if False else "#0B1220",
            fg=fg,
            padx=8,
            pady=6,
            anchor="w",
            font=("Microsoft YaHei UI", 10, "bold"),
            cursor="hand2",
            width=width,
        )
        self._button.pack(fill=tk.X)
        self._button.bind("<Button-1>", self._open_popup)
        self._button.bind("<Enter>", lambda _e: self._button.configure(bg="#111827"))
        self._button.bind("<Leave>", lambda _e: self._button.configure(bg="#0B1220"))
        try:
            self.variable.trace_add("write", lambda *_: self._refresh_text())
        except Exception:
            pass
        self._refresh_text()

    def _display(self, value):
        return str(value)

    def _refresh_text(self):
        try:
            value = self.variable.get()
        except Exception:
            value = ""
        self._button.configure(text=f"{value}  ▾")

    def bind(self, sequence=None, func=None, add=None):
        if sequence == "<<ComboboxSelected>>" and func is not None:
            self._callbacks.setdefault(sequence, []).append(func)
            return None
        return super().bind(sequence, func, add)

    def _fire(self, sequence):
        class Event:
            pass
        event = Event()
        event.widget = self
        for cb in self._callbacks.get(sequence, []):
            try:
                cb(event)
            except Exception:
                traceback.print_exc()

    def _open_popup(self, _event=None):
        if self._state in (tk.DISABLED, "disabled"):
            return
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            return

        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=self.popup_bg, highlightthickness=1, highlightbackground=self.highlight)
        self._popup = popup

        lb = tk.Listbox(
            popup,
            bg=self.popup_bg,
            fg=self.fg,
            selectbackground=ACCENT,
            selectforeground="#FFFFFF",
            relief=tk.FLAT,
            highlightthickness=0,
            activestyle="none",
            font=("Microsoft YaHei UI", 10),
            exportselection=False,
            height=min(max(len(self.values), 1), 8),
        )
        for v in self.values:
            lb.insert(tk.END, self._display(v))
        lb.pack(fill=tk.BOTH, expand=True)

        try:
            current = self.variable.get()
            for i, v in enumerate(self.values):
                if str(v) == str(current):
                    lb.selection_set(i)
                    lb.activate(i)
                    lb.see(i)
                    break
        except Exception:
            pass

        def choose(_event=None):
            sel = lb.curselection()
            if not sel:
                return
            value = self.values[sel[0]]
            try:
                self.variable.set(value)
            except Exception:
                self.variable.set(str(value))
            self._refresh_text()
            self._fire("<<ComboboxSelected>>")
            popup.destroy()
            self._popup = None

        lb.bind("<ButtonRelease-1>", choose)
        lb.bind("<Return>", choose)
        popup.bind("<Escape>", lambda _e: popup.destroy())
        popup.bind("<FocusOut>", lambda _e: popup.after(150, lambda: popup.destroy() if popup.winfo_exists() else None))

        self.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        w = max(self.winfo_width(), 180)
        row_h = 26
        h = min(max(len(self.values), 1), 8) * row_h + 4
        popup.geometry(f"{w}x{h}+{x}+{y}")
        popup.lift()
        popup.focus_force()
        lb.focus_set()

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        if "state" in kw:
            self._state = kw.pop("state")
        if "values" in kw:
            self.values = list(kw.pop("values"))
        return super().configure(**kw)

    config = configure


class DarkCheckbox(tk.Frame):
    """自绘复选框，避免 macOS 原生 Checkbutton 背景变白。"""

    def __init__(self, parent, text, variable, command=None, bg=CARD_BG, fg=TEXT):
        super().__init__(parent, bg=bg)
        self.variable = variable
        self.command = command
        self.bg = bg
        self.fg = fg
        self.box = tk.Label(self, text="", width=2, bg="#0B1220", fg=ACCENT, font=("Microsoft YaHei UI", 9, "bold"), relief=tk.FLAT, highlightthickness=1, highlightbackground="#64748B")
        self.box.pack(side=tk.LEFT, padx=(0, 8))
        self.text = tk.Label(self, text=text, bg=bg, fg=fg, font=("Microsoft YaHei UI", 9), anchor="w")
        self.text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        for w in (self, self.box, self.text):
            w.bind("<Button-1>", self._toggle)
            w.configure(cursor="hand2")
        try:
            self.variable.trace_add("write", lambda *_: self._refresh())
        except Exception:
            pass
        self._refresh()

    def _refresh(self):
        checked = bool(self.variable.get())
        self.box.configure(text="✓" if checked else "", bg="#0B1220" if checked else "#111827")

    def _toggle(self, _event=None):
        self.variable.set(not bool(self.variable.get()))
        self._refresh()
        if self.command:
            self.command()


class TinyProgress(tk.Frame):
    """自绘进度条，替代 ttk.Progressbar，避免 macOS 原生控件发白。"""

    def __init__(self, parent, bg=PANEL_BG, trough="#243044", fill=ACCENT, height=14):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, height=height, bg=trough, highlightthickness=1, highlightbackground="#64748B", bd=0)
        self.canvas.pack(fill=tk.X, expand=True)
        self.trough = trough
        self.fill = fill
        self._running = False
        self._pos = 0
        self._after = None

    def start(self, interval=20):
        self._running = True
        self._animate(max(10, int(interval)))

    def stop(self):
        self._running = False
        if self._after:
            try:
                self.after_cancel(self._after)
            except Exception:
                pass
            self._after = None
        self.canvas.delete("bar")

    def _animate(self, interval):
        if not self._running:
            return
        self.canvas.delete("bar")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        bar_w = max(28, int(w * 0.18))
        x = self._pos % (w + bar_w) - bar_w
        self.canvas.create_rectangle(x, 2, x + bar_w, h - 2, fill=self.fill, width=0, tags="bar")
        self._pos += max(4, w // 60)
        self._after = self.after(interval, lambda: self._animate(interval))


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

    def ffmpeg_display_text(self):
        if not self.ffmpeg_path:
            return "FFmpeg：未找到"
        # 客户版不显示 /private/var/folders/.../_MEIxxxx 这种临时路径，避免误导。
        if is_frozen_app():
            return "FFmpeg：内置版本已就绪"
        return f"FFmpeg：{self.ffmpeg_path}"

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
        return FlatButton(parent, text=text, command=command, bg=bg, fg=fg, active=active)

    def make_dropdown(self, parent, textvariable, values, bg=CARD_BG):
        return DarkDropdown(parent, textvariable=textvariable, values=values, bg=bg)

    def make_checkbox(self, parent, text, variable, command=None, bg=CARD_BG, fg=TEXT):
        return DarkCheckbox(parent, text=text, variable=variable, command=command, bg=bg, fg=fg)

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
        ffmpeg_text = self.ffmpeg_display_text()
        self.label(chip, ffmpeg_text, size=8, fg=SUCCESS if self.ffmpeg_path else DANGER, bg="#0B1220", wraplength=315, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(8, 4))
        if not self.ffmpeg_path:
            self.label(chip, self.ffmpeg_install_hint(), size=8, fg=MUTED, bg="#0B1220", wraplength=315, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 8))
            if not is_frozen_app():
                self.make_button(chip, "打开 FFmpeg 下载/安装页面", self.open_ffmpeg_download_page, bg="#334155").pack(anchor="w", padx=10, pady=(0, 10))

        self.lcd_size_box = self.control_card(left, "输出尺寸", "屏幕分辨率用冒号格式，例如 240:320")
        self.lcd_size_combo = self.make_dropdown(
            self.lcd_size_box,
            textvariable=self.lcd_output_size,
            values=["240:320", "320:240", "480:800", "640:480", "1280:720", "自定义"],
        )
        self.lcd_size_combo.pack(fill=tk.X, padx=12, pady=(0, 8))
        self.lcd_size_combo.bind("<<ComboboxSelected>>", self.on_lcd_size_selected)
        self.lcd_custom_size_entry = tk.Entry(self.lcd_size_box, bg="#F8FAFC", relief=tk.FLAT)

        fmt_box = self.control_card(left, "输出格式", ".mjpeg 是裸流，更适合嵌入式；其他是容器格式。")
        self.make_dropdown(
            fmt_box,
            textvariable=self.lcd_output_format,
            values=[".mjpeg", ".avi", ".mkv", ".mov", ".mp4"],
        ).pack(fill=tk.X, padx=12, pady=(0, 8))

        q_box = self.control_card(left, "JPEG 质量", "2-31，数字越小越清晰，文件也更大。")
        tk.Scale(q_box, from_=2, to=31, orient=tk.HORIZONTAL, variable=self.lcd_quality, bg=CARD_BG, fg=TEXT,
                 highlightthickness=0, troughcolor="#334155", activebackground=ACCENT).pack(fill=tk.X, padx=10, pady=(0, 8))

        name_box = self.control_card(left, "命名", "保留原功能：可在输出文件名后追加尺寸。")
        self.make_checkbox(
            name_box,
            text="追加尺寸信息，例如 _mjpeg_240x320",
            variable=self.lcd_add_size_suffix,
            bg=CARD_BG,
            fg=TEXT,
        ).pack(anchor="w", padx=10, pady=(0, 10))

        btn_row = tk.Frame(left, bg=PANEL_BG)
        btn_row.pack(fill=tk.X, padx=18, pady=(8, 4))
        self.make_button(btn_row, "添加文件", self.lcd_browse_files, bg="#334155").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))
        self.make_button(btn_row, "移除选中", self.lcd_remove_selected, bg="#334155").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(6, 0))
        self.make_button(left, "清空列表", self.lcd_clear_list, bg="#334155").pack(fill=tk.X, padx=18, pady=(4, 10))

        self.lcd_convert_btn = self.make_button(left, "开始批量转换", self.lcd_start_conversion, bg=SUCCESS, fg="#052E16")
        self.lcd_convert_btn.pack(fill=tk.X, padx=18, pady=(4, 12))
        self.lcd_progress = TinyProgress(left, bg=PANEL_BG)
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
        filenames, ignored = safe_askopenfilenames(
            title="选择视频或图片",
            allowed_exts=MEDIA_EXTS,
            label="媒体文件",
        )
        if filenames:
            self.lcd_add_files(filenames)
        show_ignored_files_warning(ignored)

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
        self.make_dropdown(preset_box, textvariable=self.epaper_preset_var, values=list(EPAPER_PRESETS.keys())).pack(fill=tk.X, padx=12, pady=(0, 8))
        self.epaper_preset_var.trace_add("write", lambda *_: self.epaper_rebuild_previews())
        self.epaper_note_label = self.label(preset_box, EPAPER_PRESETS[self.epaper_preset_var.get()].get("note", ""), size=8, fg=MUTED, bg=CARD_BG, wraplength=320, justify=tk.LEFT)
        self.epaper_note_label.pack(anchor="w", padx=12, pady=(0, 10))

        fit_box = self.control_card(left, "画面适配", "裁剪填满适合屏幕展示；留白适合完整保留图。")
        self.make_dropdown(fit_box, textvariable=self.epaper_fit_var, values=["裁剪填满", "完整适配留白", "拉伸"]).pack(fill=tk.X, padx=12, pady=(0, 8))
        self.epaper_fit_var.trace_add("write", lambda *_: self.epaper_rebuild_previews())
        self.make_dropdown(fit_box, textvariable=self.epaper_rotate_var, values=[0, 90, 180, 270]).pack(fill=tk.X, padx=12, pady=(0, 10))
        self.epaper_rotate_var.trace_add("write", lambda *_: self.epaper_rebuild_previews())

        dither_box = self.control_card(left, "量化与抖动", "四色屏建议开启抖动，纯图标/文字可以关闭。")
        self.make_checkbox(
            dither_box,
            text="启用 Floyd-Steinberg 抖动",
            variable=self.epaper_dither_var,
            command=self.epaper_rebuild_previews,
            bg=CARD_BG,
            fg=TEXT,
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
        scale = tk.Scale(
            line,
            from_=a,
            to=b,
            resolution=0.01,
            orient=tk.HORIZONTAL,
            variable=var,
            command=lambda _v: self.epaper_rebuild_previews_delayed(),
            bg=CARD_BG,
            fg=TEXT,
            troughcolor="#334155",
            activebackground=ACCENT,
            highlightthickness=0,
            showvalue=False,
        )
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
        paths, ignored = safe_askopenfilenames(
            title="选择图片",
            allowed_exts=IMAGE_EXTS,
            label="图片文件",
        )
        if paths:
            self.epaper_set_paths(list(paths))
        show_ignored_files_warning(ignored)

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

    Windows：
        优先使用 TkinterDnD.Tk()，支持拖拽；失败则降级普通 tk.Tk()。

    macOS arm64 / M 系列：
        直接使用普通 tk.Tk()，避免 tkdnd 底层库加载失败导致闪退。
    """
    global HAS_DND, DND_RUNTIME_OK

    DND_RUNTIME_OK = False

    if platform.system() == "Darwin":
        log_event("[BOOT] macOS detected, tkinterdnd2 disabled, using normal tk.Tk()")
        root = tk.Tk()
        setattr(root, "_artifex_dnd_ready", False)
        return root

    if HAS_DND and TkinterDnD is not None:
        try:
            log_event("[BOOT] trying TkinterDnD.Tk()")
            root = TkinterDnD.Tk()
            DND_RUNTIME_OK = True
            setattr(root, "_artifex_dnd_ready", True)
            log_event("[BOOT] TkinterDnD root created")
            return root
        except Exception as e:
            HAS_DND = False
            DND_RUNTIME_OK = False
            log_event(f"[WARN] tkinterdnd2 init failed, fallback to normal Tk: {e}")
            traceback.print_exc()

    log_event("[BOOT] using normal tk.Tk()")
    root = tk.Tk()
    setattr(root, "_artifex_dnd_ready", False)
    return root


def is_dnd_ready(widget=None):
    """
    判断拖拽功能是否真的可用。
    HAS_DND 只说明 import 成功；DND_RUNTIME_OK 才说明根窗口是 TkinterDnD.Tk()。
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
    if platform.system() == "Darwin":
        log_event("[BOOT] drag-and-drop skipped on macOS")
        return False

    if not is_dnd_ready(widget):
        log_event("[BOOT] drag-and-drop unavailable")
        return False

    try:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", callback)
        log_event("[BOOT] drag-and-drop enabled")
        return True
    except Exception as e:
        log_event(f"[WARN] drag-and-drop bind failed, skipped: {e}")
        traceback.print_exc()
        return False


def main():
    log_environment("START")

    if "--self-test" in sys.argv:
        raise SystemExit(self_test())

    if "--tk-smoke-test" in sys.argv:
        try:
            log_event("[BOOT] TK smoke test start")
            root = create_root()
            root.update_idletasks()
            root.update()
            root.destroy()
            print("TK smoke test OK")
            log_event("[BOOT] TK smoke test OK")
            raise SystemExit(0)
        except Exception:
            write_crash_log("TK smoke test failed")
            traceback.print_exc()
            raise SystemExit(10)

    if "--gui-smoke-test" in sys.argv:
        try:
            log_event("[BOOT] GUI smoke test start")
            root = create_root()
            app = DisplayConverterApp(root)
            root.update_idletasks()
            root.update()
            root.destroy()
            print("GUI smoke test OK")
            log_event("[BOOT] GUI smoke test OK")
            raise SystemExit(0)
        except Exception:
            write_crash_log("GUI smoke test failed")
            traceback.print_exc()
            raise SystemExit(11)

    try:
        log_event("[BOOT] create root")
        root = create_root()

        log_event("[BOOT] create app")
        app = DisplayConverterApp(root)

        log_event("[BOOT] mainloop")
        root.mainloop()

    except Exception:
        write_crash_log("App crashed")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
