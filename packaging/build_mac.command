#!/bin/bash
# ============================================================
#  三语情感极性分析 · macOS 一键打包脚本
#  用法：把整个项目文件夹拷到 Mac 上，双击本文件即可
#  产物：dist/三语情感极性分析-mac/（内含 SentimentAnalysis.app）
#        三语情感极性分析-mac.zip
# ============================================================
set -e
cd "$(dirname "$0")/.."   # 项目根目录

echo "=============================================="
echo "  三语情感极性分析 · macOS 打包"
echo "=============================================="

# ---------- 1/5 检查 Python ----------
PY=""
if command -v python3 >/dev/null 2>&1 && python3 -c "import sys" >/dev/null 2>&1; then
    PY=python3
fi
if [ -z "$PY" ]; then
    echo "[ERROR] 未找到 python3。"
    echo "        请先安装 Python 3.10+：https://www.python.org/downloads/macos/"
    echo "        （或 brew install python3）"
    read -r -p "按回车退出..." _
    exit 1
fi
echo "[1/5] Python: $($PY --version)"

# ---------- 2/5 安装依赖 ----------
echo "[2/5] 安装依赖（flask / jieba / fugashi / unidic-lite / pyinstaller）..."
$PY -m pip install --quiet -r requirements.txt pyinstaller pillow
if [ $? -ne 0 ]; then
    echo "[WARN] pip 安装失败，尝试用户目录安装..."
    $PY -m pip install --quiet --user -r requirements.txt pyinstaller pillow || {
        echo "[ERROR] 依赖安装失败。请检查网络 / pip 后重试。"
        read -r -p "按回车退出..." _
        exit 1
    }
fi

# ---------- 3/5 生成 macOS 图标 .icns ----------
echo "[3/5] 生成应用图标 icon.icns..."
ICONSET="packaging/icon.iconset"
rm -rf "$ICONSET" && mkdir -p "$ICONSET"
for size in 16 32 64 128 256 512; do
    sips -z $size $size packaging/icon.png --out "$ICONSET/icon_${size}x${size}.png" >/dev/null 2>&1
    sips -z $((size*2)) $((size*2)) packaging/icon.png --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null 2>&1
done
iconutil -c icns "$ICONSET" -o packaging/icon.icns
rm -rf "$ICONSET"

# ---------- 4/5 PyInstaller 打包 ----------
echo "[4/5] PyInstaller 打包中（约 2-5 分钟）..."
$PY -m PyInstaller --noconfirm --clean packaging/build_exe.spec

# ---------- 5/5 组装发行包 ----------
echo "[5/5] 组装发行包..."
APP_SRC="dist/SentimentAnalysis"
PKG_NAME="三语情感极性分析-mac"
PKG="dist/$PKG_NAME"

# 拷贝文档与词典（供核验）
cp README.md README.txt "$APP_SRC/" 2>/dev/null || true
mkdir -p "$APP_SRC/词典文件/原始资源"
cp trilingual_sentiment/data/*.csv trilingual_sentiment/data/*.txt "$APP_SRC/词典文件/" 2>/dev/null || true
for f in pn.csv.m3.120408.trim wago.121808.pn subjclueslen1-HLTEMNLP05.tff; do
    [ -f "dictionaries/$f" ] && cp "dictionaries/$f" "$APP_SRC/词典文件/原始资源/"
done
[ -d "dictionaries/hownet" ] && cp -R dictionaries/hownet "$APP_SRC/词典文件/原始资源/" 2>/dev/null || true

# macOS 使用说明
cat > "$APP_SRC/使用说明.txt" <<'EOF'
三语情感极性分析（macOS 版）
================================

【快速使用】
1. 双击 SentimentAnalysis.app 启动（首次启动约 3-10 秒）。
2. 浏览器会自动打开分析界面；若未自动打开，手动访问
   http://127.0.0.1:8765 。
3. 退出：在程序坞（Dock）图标上右键 → 退出；或活动监视器中结束进程。

【运行环境】
- macOS 10.13 及以上（Intel / Apple Silicon 均可）
- 无需安装 Python，无需联网，无需任何配置
- 端口 8765 被占用时会自动改用 8766-8784 中的空闲端口

【注意事项】
- 请保持文件夹完整：SentimentAnalysis.app 与 _internal 目录必须在一起。
- 首次打开若提示"无法验证开发者"：
  右键点击 .app → 打开 → 再点"打开"；或
  系统设置 → 隐私与安全性 → 仍要打开。
- 整个文件夹可任意移动、拷贝、U 盘分发。

【功能】
- 输入中文 / 日语 / 英语文本（可混排），自动识别语言、自动分词
- 输出：整体倾向分（-100 纯负面 ～ +100 纯正面）、极性标签
  （正面 / 负面 / 中性 / 无法判断）、逐句分析、匹配情感词明细
- 页面底部「本工具使用的词典与分词工具」注明各语言所用词典
- 判定方法与论文素材见 README.md 第二部分

【重新打包（开发者）】
  双击 packaging/build_mac.command
EOF

# 改名并打 zip
rm -rf "$PKG"
mv "$APP_SRC" "$PKG"
echo "打包 zip..."
( cd dist && rm -f "$PKG_NAME.zip" && zip -qry "$PKG_NAME.zip" "$PKG_NAME" )

echo "=============================================="
echo "  完成！"
echo "  发行包：dist/$PKG_NAME/    （内含 SentimentAnalysis.app）"
echo "  压缩包：dist/$PKG_NAME.zip"
echo "=============================================="
read -r -p "按回车退出..." _
