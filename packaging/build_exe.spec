# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：onedir（文件夹模式，非 onefile），Windows / macOS 通用。

Windows 生成 dist/SentimentAnalysis/：
  SentimentAnalysis.exe   ← 双击启动（自动开浏览器，关窗即停）
  _internal/              ← 运行库、词典数据、页面资源

macOS 生成 dist/SentimentAnalysis/（内含 SentimentAnalysis.app）：
  双击 .app 启动（自动开浏览器）；.icns 图标由 build_mac.command 生成

构建：
  Windows: python -m PyInstaller --noconfirm --clean packaging/build_exe.spec
  macOS  : 双击 packaging/build_mac.command（或 bash packaging/build_mac.command）
"""
import sys

from pathlib import Path

import jieba as _jieba_pkg
from PyInstaller.utils.hooks import collect_all

IS_MAC = sys.platform == "darwin"
ROOT = Path(SPECPATH).resolve().parent  # 项目根目录
_JDIR = Path(_jieba_pkg.__file__).resolve().parent

datas = [
    (str(ROOT / "trilingual_sentiment" / "data"), "trilingual_sentiment/data"),
    (str(ROOT / "webapp" / "static"), "webapp/static"),
    (str(ROOT / "README.md"), "."),  # 使用手册（/manual 页面渲染）
    # jieba 只带核心：主词典 + finalseg（HMM）；lac_small/analyse/posseg 用不到（约 24MB）
    (str(_JDIR / "dict.txt"), "jieba"),
    (str(_JDIR / "finalseg"), "jieba/finalseg"),
]
hiddenimports = []
binaries = []

# fugashi / unidic-lite 分词器与词典数据
for pkg in ("fugashi", "unidic_lite"):
    # collect_all 返回 (datas, hiddenimports, binaries)，顺序在不同版本可能不同，
    # 这里按条目类型归类：字符串 → hiddenimports，(src, dst) → datas/binaries
    for group in collect_all(pkg):
        if not group:
            continue
        if isinstance(group[0], str):
            hiddenimports += group
        elif str(group[0][0]).lower().endswith((".pyd", ".dll", ".so")):
            binaries += group
        else:
            datas += group

a = Analysis(
    [str(ROOT / "webapp" / "app.py")],
    pathex=[str(ROOT), str(ROOT / "webapp")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "numpy", "scipy", "pandas", "PIL",
        "unittest", "pydoc", "doctest", "xmlrpc", "lib2to3", "test",
        "idlelib", "turtledemo", "setuptools", "pip", "wheel",
    ],
    noarchive=False,
)

# 兜底过滤：任何来源收集进来的 jieba 无用数据一律剔除
_DROP_PREFIXES = ("jieba/lac_small", "jieba/analyse", "jieba/posseg")


def _keep(entry) -> bool:
    dest = str(entry[0]).replace("\\", "/")
    return not dest.startswith(_DROP_PREFIXES)


a.datas = [d for d in a.datas if _keep(d)]
a.binaries = [b for b in a.binaries if _keep(b)]

pyz = PYZ(a.pure)

if IS_MAC:
    _icon = str(ROOT / "packaging" / "icon.icns")
else:
    _icon = str(ROOT / "packaging" / "icon.ico")

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SentimentAnalysis",
    icon=_icon,  # 应用图标（Windows .ico / macOS .icns）
    version=None if IS_MAC else str(ROOT / "packaging" / "file_version_info.txt"),  # Windows 文件属性：1.0.0 / 版权
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 无终端窗口：后台静默运行，关闭浏览器标签页即自动退出
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SentimentAnalysis",
)

if IS_MAC:
    # macOS 应用包（.app）：Finder 双击即用；autostart 浏览器由 app.py frozen 分支处理
    app = BUNDLE(
        coll,
        name="SentimentAnalysis.app",
        icon=_icon,
        bundle_identifier="cn.workbuddy.sentiment-analysis",
        info_plist={
            "CFBundleName": "SentimentAnalysis",
            "CFBundleDisplayName": "三语情感极性分析",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "10.13",
            "NSHumanReadableCopyright": "Copyright (c) 2026 Jasonwei. MIT License.",
        },
    )
