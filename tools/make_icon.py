"""生成应用图标：极性仪表盘 App 图标 → icon.png / icon.ico。

设计：圆角方块 + 靛蓝渐变底 + 白色极性仪表环（绿=负面 / 红=正面，与界面配色一致）
+ 指针指向正面侧 + 三语文字「中 あ A」。

用法：python tools/make_icon.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packaging"
S = 1024  # 超采样边长

# 配色（与界面一致：正面=红，负面=绿）
C_GRAD_TOP = (79, 70, 229)     # indigo-600
C_GRAD_BOT = (59, 130, 246)    # blue-500
C_RING = (255, 255, 255)
C_POS = (220, 38, 38)          # 红：正面
C_NEG = (22, 163, 74)          # 绿：负面
C_NEEDLE = (30, 41, 59)        # slate-800
C_TEXT = (255, 255, 255)


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient_bg(size: int) -> Image.Image:
    """45° 对角渐变。"""
    img = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(img)
    for i in range(size * 2):
        t = i / (size * 2 - 1)
        d.line([(i, 0), (0, i)], fill=lerp(C_GRAD_TOP, C_GRAD_BOT, t) + (255,))
    return img


def radial_glow(size: int) -> Image.Image:
    """左上柔光。"""
    grad = Image.radial_gradient("L").resize((size, size))
    glow = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    glow.putalpha(grad.point(lambda v: int(v * 0.22)))
    return glow


def rounded_mask(size: int, radius: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def draw_gauge(img: Image.Image) -> None:
    """白色仪表环 + 红绿极性段 + 指针（指向正面侧）。"""
    d = ImageDraw.Draw(img)
    cx, cy = 512, 470
    r = 306
    width = 66
    bbox = [cx - r, cy - r, cx + r, cy + r]

    # PIL 弧度：0°=3 点钟，顺时针增大；速度表式开口朝下：148°→392°
    d.arc(bbox, 148, 392, fill=C_RING + (255,), width=width)   # 白色轨道
    d.arc(bbox, 148, 214, fill=C_NEG + (255,), width=width)    # 左：负面（绿）
    d.arc(bbox, 326, 392, fill=C_POS + (255,), width=width)    # 右：正面（红）

    # 仅外端做圆帽，与弧同宽，视觉连贯
    for ang, col in ((148, C_NEG), (392, C_POS)):
        a = math.radians(ang)
        px, py = cx + r * math.cos(a), cy + r * math.sin(a)
        rr = width / 2
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=col + (255,))

    # 指针：指向 334°（正面上方）
    ang = math.radians(334)
    tip = (cx + (r - 66) * math.cos(ang), cy + (r - 66) * math.sin(ang))
    perp = ang + math.pi / 2
    w = 34
    base1 = (cx + w * math.cos(perp), cy + w * math.sin(perp))
    base2 = (cx - w * math.cos(perp), cy - w * math.sin(perp))
    d.polygon([base1, base2, tip], fill=C_NEEDLE + (255,))
    d.ellipse([cx - 56, cy - 56, cx + 56, cy + 56], fill=C_RING + (255,))
    d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=C_NEEDLE + (255,))


def _font(size: int, which: str) -> ImageFont.FreeTypeFont:
    candidates = {
        "zh": ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"],
        "ja": ["C:/Windows/Fonts/ugothic.ttc", "C:/Windows/Fonts/msgothic.ttc", "C:/Windows/Fonts/msyh.ttc"],
        "en": ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeui.ttf"],
    }[which]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def draw_lang_glyphs(img: Image.Image) -> None:
    """底部三语文字：中 あ A。"""
    d = ImageDraw.Draw(img)
    items = [("中", "zh"), ("あ", "ja"), ("A", "en")]
    xs = [320, 512, 704]
    y = 800
    for (char, kind), x in zip(items, xs):
        font = _font(128, kind)
        # 轻微阴影
        d.text((x + 5, y + 5), char, font=font, fill=(23, 37, 84, 110), anchor="mm")
        d.text((x, y), char, font=font, fill=C_TEXT + (255,), anchor="mm")


def main() -> None:
    OUT.mkdir(exist_ok=True)

    img = gradient_bg(S)
    img = Image.alpha_composite(img, radial_glow(S))
    draw_gauge(img)
    draw_lang_glyphs(img)

    # 圆角遮罩
    mask = rounded_mask(S, 232)
    final = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    final.paste(img, (0, 0), mask)

    icon_256 = final.resize((256, 256), Image.LANCZOS)
    icon_256.save(OUT / "icon.png")

    sizes = [16, 24, 32, 48, 64, 128, 256]
    icons = [final.resize((s, s), Image.LANCZOS) for s in sizes]
    icons[-1].save(OUT / "icon.ico", format="ICO", sizes=[(s, s) for s in sizes], append_images=icons[:-1])

    print(f"生成: {OUT / 'icon.png'} , {OUT / 'icon.ico'}")


if __name__ == "__main__":
    main()
