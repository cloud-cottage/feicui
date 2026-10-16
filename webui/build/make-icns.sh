#!/bin/bash
# webui/build/make-icns.sh —— 从 **SVG 矢量源**无损导出 ≥1024 母图，生成 `webui/build/feicui.icns`（10 槽）
#
# 依据：Kevin 2026-10-17 确认 `webui/assets/feicui.svg`（viewBox 0 0 480 480）与
#       `webui/assets/feicui.png`（480×480）**是同一设计** ⇒ 改用 SVG 出母图，
#       使 ≥1024 槽为**原生分辨率**（旧 icns 的 1024 槽是 sips 从 480 PNG 放大，见 feicui.spec 旧注）。
#
# ── 取图工具比选（2026-10-17 本机实测，逐条留档）────────────────────────────────
#   ① `qlmanage -t -s 1024 -o <dir> <svg>`  ✅ **采用**（macOS 自带，QuickLook/WebKit 渲染）
#        产出 `<svg名>.png` 恰为 **1024×1024**；其直方图与 `assets/feicui.png` 完全同族，
#        边缘能量（FIND_EDGES 均值）**5.3942** vs 480 PNG 放大到 1024 的 **3.7802** ⇒ 真矢量重渲染，非放大。
#   ② `venv/bin/python -c "import pymupdf; pymupdf.open(svg)"`  ❌ **不可用（实测失败）**
#        MuPDF 能把 SVG 当文档打开（page.rect = 480×480），但**忽略 SVG 内嵌 `<style>` 的 class 填充**
#        ⇒ 渲染结果全黑：1024×1024 里 `(0,0,0,255)` 占 1007937 px、只有 255 种颜色（对照 qlmanage 4085 种）。
#   ③ `magick -density 300 -background none <svg> -resize 1024x1024 out.png` ❌ **不可用（实测失败）**
#        原样报错：`magick: vector graphics nested too deeply 'cls-12' @ error/draw.c/RenderMVGContent/2804.`
#        （ImageMagick 走内部 MSVG 解析器，不支持该 SVG 的 class/样式）
#   ④ 系统 `rsvg-convert` / `inkscape` —— 本机 **未安装**（`command -v` MISSING），未测。
#   ⇒ 结论：**qlmanage 是唯一跑通且保真的路径**；全流程只用 macOS 自带工具，**零新增 Python 依赖**。
#
# 槽位：icon_16x16 / @2x(32) / 32x32 / @2x(64) / 128x128 / @2x(256) / 256x256 / @2x(512) /
#       512x512 / @2x(**1024**) = **10 槽**；其中 1024 槽**直接复制母图**（不重采样）。
#
# 跑法：  bash webui/build/make-icns.sh
set -euo pipefail

cd "$(dirname "$0")/../.."                     # 仓根
SVG="webui/assets/feicui.svg"
OUT="webui/build/feicui.icns"
MASTER_KEEP="webui/build/feicui-1024.png"      # 母图随仓留档（≥1024 原生分辨率）
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== ① qlmanage 出母图（目标 1024）=="
mkdir -p "$WORK/raw"
qlmanage -t -s 1024 -o "$WORK/raw" "$SVG" >/dev/null 2>&1
MASTER="$WORK/raw/$(basename "$SVG").png"
test -f "$MASTER" || { echo "MASTER_MISSING: $MASTER"; exit 1; }
W=$(sips -g pixelWidth  "$MASTER" | awk '/pixelWidth/{print $2}')
H=$(sips -g pixelHeight "$MASTER" | awk '/pixelHeight/{print $2}')
echo "母图 $MASTER = ${W}x${H}"
if [ "$W" -lt 1024 ] || [ "$H" -lt 1024 ]; then echo "MASTER_TOO_SMALL: ${W}x${H}"; exit 1; fi
cp "$MASTER" "$MASTER_KEEP"

echo "== ② 组装 10 槽 iconset（1024 槽＝母图原样，不重采样）=="
IS="$WORK/feicui.iconset"; mkdir -p "$IS"
#          槽名                  边长
for pair in "icon_16x16     16" "icon_16x16@2x   32" "icon_32x32      32" "icon_32x32@2x   64" \
            "icon_128x128  128" "icon_128x128@2x 256" "icon_256x256   256" "icon_256x256@2x 512" \
            "icon_512x512  512"; do
  set -- $pair
  sips -z "$2" "$2" "$MASTER" --out "$IS/$1.png" >/dev/null
done
cp "$MASTER" "$IS/icon_512x512@2x.png"          # ★ 1024 槽：原生母图，非放大

echo "== ③ iconutil 组装 icns =="
iconutil -c icns "$IS" -o "$OUT"
ls -l "$OUT"

echo "== ④ 反解复验（iconutil -c iconset ⇒ 逐槽尺寸）=="
mkdir -p "$WORK/verify.iconset"
iconutil -c iconset -o "$WORK/verify.iconset" "$OUT"
for f in "$WORK/verify.iconset"/*.png; do
  printf '%-22s %sx%s\n' "$(basename "$f")" \
    "$(sips -g pixelWidth "$f" | awk '/pixelWidth/{print $2}')" \
    "$(sips -g pixelHeight "$f" | awk '/pixelHeight/{print $2}')"
done
echo "OK: $OUT"
