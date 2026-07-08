# Artifex Display Converter

统一显示资源转换工具：LCD / MJPEG 视频转换 + 墨水屏 `.epd` 图片转换。

## 本版修复重点

1. **macOS FFmpeg 路径修复**
   - 打包改为 `--onedir`，不再使用 `--onefile`。
   - macOS 发布包会把 `ffmpeg` 固定放到：

     ```text
     ArtifexDisplayConverter.app/Contents/Resources/ffmpeg
     ```

   - 程序优先读取 `.app/Contents/Resources/ffmpeg`，再兜底读取 `_MEIPASS`、开发目录和系统 PATH。
   - 避免 `/private/var/folders/.../_MEIxxxx/ffmpeg` 临时路径变化导致的 `No such file or directory`。

2. **macOS 深色界面修复**
   - macOS 的 Tk/Aqua 原生 `Button`、`ttk.Combobox`、`ttk.Progressbar` 经常忽略自定义颜色，导致控件变白。
   - 本版用自绘控件替代：
     - `FlatButton`
     - `DarkDropdown`
     - `DarkCheckbox`
     - `TinyProgress`
   - Windows / macOS / Linux 使用同一套深色控件，减少平台差异。

3. **拖拽功能兼容**
   - Windows 保留 `tkinterdnd2` 拖拽。
   - macOS 禁用 `tkinterdnd2`，避免 `tkdnd` 运行时库加载失败导致闪退。
   - macOS 用户仍可使用“选择文件 / 选择文件夹”。

## 功能

- LCD / MJPEG：把视频或图片转换成适合 ESP32 / TFT 播放链路的 `.mjpeg`、`.avi`、`.mkv`、`.mov`、`.mp4`
- E-Paper / EPD：把图片转换成四色墨水屏可读取的 `.epd` 数据
- 支持 Windows / macOS / Linux 打包
- 最终用户不需要安装 Python、Pillow、tkinterdnd2 或 FFmpeg

## 本地开发运行

```bash
pip install -r requirements.txt
python Tool.py
```

## 自检

```bash
python Tool.py --self-test
```

GUI 烟雾测试：

```bash
python Tool.py --tk-smoke-test
python Tool.py --gui-smoke-test
```

## 本地打包

```bash
pip install -r requirements.txt
python build.py
python package_release.py Local
```

打包结果会生成在：

```text
dist/
release/
```

## macOS 提醒

如果 macOS 提示“无法验证开发者”，这是因为测试阶段没有 Apple Developer ID 签名。

可以右键打开，或者在终端对解压后的 app 执行：

```bash
xattr -dr com.apple.quarantine ArtifexDisplayConverter.app
```

如果仍然无法运行，检查 FFmpeg 是否在 app 内：

```bash
find ArtifexDisplayConverter.app -name ffmpeg -type f
```

正常应看到：

```text
ArtifexDisplayConverter.app/Contents/Resources/ffmpeg
```

并检查权限：

```bash
chmod +x ArtifexDisplayConverter.app/Contents/Resources/ffmpeg
```

## 文件说明

```text
Tool.py                         主程序
requirements.txt                Python 打包依赖
build.py                        PyInstaller 打包脚本，会把 FFmpeg 放入稳定位置
package_release.py              把打包结果压缩成 zip
.gitignore                      忽略 build/dist/release 等产物
```
