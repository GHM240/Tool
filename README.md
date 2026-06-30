# Artifex Display Converter

统一显示资源转换工具：LCD / MJPEG 视频转换 + 墨水屏 `.epd` 图片转换。

## 功能

- LCD / MJPEG：把视频或图片转换成适合 ESP32 / TFT 播放链路的 `.mjpeg`、`.avi`、`.mkv`、`.mov`、`.mp4`
- E-Paper / EPD：把图片转换成四色墨水屏可读取的 `.epd` 数据
- 支持 Windows / macOS / Linux 云端自动打包
- 最终用户不需要安装 Python、Pillow、tkinterdnd2 或 FFmpeg

## 本地开发运行

```bash
pip install -r requirements.txt
python Tool.py
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

## GitHub 云端自动打包

把项目推送到 GitHub 后，可以用 tag 触发自动打包：

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions 会自动生成：

- `ArtifexDisplayConverter-Windows.zip`
- `ArtifexDisplayConverter-macOS.zip`
- `ArtifexDisplayConverter-Linux.zip`

如果是 tag 触发，还会自动上传到 GitHub Release 页面。

## macOS 提醒

如果 macOS 提示“无法验证开发者”，这是因为没有 Apple Developer ID 签名。测试阶段可以右键打开，或在终端对解压后的 app 执行：

```bash
xattr -dr com.apple.quarantine ArtifexDisplayConverter.app
```

## 文件说明

```text
Tool.py                         主程序
requirements.txt                Python 打包依赖
build.py                        PyInstaller 打包脚本，会把 FFmpeg 一起打进程序
package_release.py              把打包结果压缩成 zip
.github/workflows/build.yml     GitHub Actions 云端打包配置
```
