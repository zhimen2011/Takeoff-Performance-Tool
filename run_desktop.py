"""Repository-local launcher for the STAS DearPyGui desktop UI."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))


def runtime_base_dir() -> Path:
    """Return the directory that contains user-editable runtime files."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return ROOT_DIR


def is_missing_dearpygui_error(exc: ModuleNotFoundError) -> bool:
    """Return True when startup failed because DearPyGui is not installed."""

    return exc.name == "dearpygui" or bool(exc.name and exc.name.startswith("dearpygui."))


def dearpygui_missing_message() -> str:
    """Create the user-facing missing dependency message."""

    return "当前 Python 环境缺少 DearPyGui，无法启动桌面界面。请先执行: python -m pip install dearpygui"


if __name__ == "__main__":
    try:
        from stas_app.ui.desktop_app import launch_desktop_app
        base_dir = runtime_base_dir()
        launch_desktop_app(config_path=base_dir / "config" / "app.local.toml", base_dir=base_dir)
    except ModuleNotFoundError as exc:
        if is_missing_dearpygui_error(exc):
            print(dearpygui_missing_message(), file=sys.stderr)
            raise SystemExit(2)
        raise
