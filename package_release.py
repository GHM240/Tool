#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a clean zip package from PyInstaller output."""

from __future__ import annotations

import os
import stat
import sys
import zipfile
from pathlib import Path

APP_NAME = "ArtifexDisplayConverter"


def add_path_to_zip(zf: zipfile.ZipFile, path: Path, arc_root: str | None = None) -> None:
    path = path.resolve()
    if path.is_file():
        arcname = Path(arc_root) / path.name if arc_root else Path(path.name)
        zf.write(path, arcname.as_posix())
        return

    base = path.parent
    for p in path.rglob("*"):
        if p.is_file():
            zf.write(p, p.relative_to(base).as_posix())


def make_executable_if_needed(path: Path) -> None:
    if path.exists() and path.is_file() and os.name != "nt":
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> int:
    package_name = sys.argv[1] if len(sys.argv) > 1 else APP_NAME
    dist = Path("dist")
    release = Path("release")
    release.mkdir(exist_ok=True)

    candidates = [
        dist / f"{APP_NAME}.exe",
        dist / f"{APP_NAME}.app",
        dist / APP_NAME,
    ]

    target = next((p for p in candidates if p.exists()), None)
    if target is None:
        raise FileNotFoundError(f"No PyInstaller output found in {dist.resolve()}")

    if target.is_file():
        make_executable_if_needed(target)

    zip_path = release / f"{package_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        add_path_to_zip(zf, target)
        readme = Path("README.md")
        if readme.exists():
            zf.write(readme, "README.md")

    print(f"Created package: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
