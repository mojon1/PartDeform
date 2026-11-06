# -*- coding: utf-8 -*-
"""パネルの種類ボタンのアイコン（通常と、右下に緑の＋を付けた「追加」用）。"""
import math

import c4d

_cache = {}

BADGE_GREEN = (52, 190, 86)
BADGE_RING = (24, 110, 48)
BADGE_PLUS = (255, 255, 255)


def normal_icon(dtype):
    key = ("normal", dtype)
    if key not in _cache:
        src = c4d.bitmaps.InitResourceBitmap(dtype)
        _cache[key] = src.GetClone() if src is not None else None
    return _cache[key]


def add_icon(dtype):
    """標準のアイコンの右下に、緑の丸と白い＋を描いたもの（Shift＋クリックで追加の目印）。"""
    key = ("add", dtype)
    if key in _cache:
        return _cache[key]
    src = c4d.bitmaps.InitResourceBitmap(dtype)
    if src is None:
        _cache[key] = None
        return None
    bmp = src.GetClone()
    w, h = bmp.GetSize()
    alpha = bmp.GetInternalChannel()
    if alpha is None:
        alpha = bmp.AddChannel(True, False)
    s = min(w, h) / 64.0
    radius = 15.0 * s
    cx, cy = w - radius - 1.5 * s, h - radius - 1.5 * s
    ring = 2.0 * s
    bar_len, bar_half = 8.5 * s, 2.3 * s
    for y in range(max(0, int(cy - radius - 2)), min(h, int(cy + radius + 2))):
        for x in range(max(0, int(cx - radius - 2)), min(w, int(cx + radius + 2))):
            px, py = x + 0.5 - cx, y + 0.5 - cy
            d = math.hypot(px, py)
            cover = min(max(radius + 0.5 - d, 0.0), 1.0)  # 丸の縁をなめらかに
            if cover <= 0.0:
                continue
            on_plus = (abs(px) <= bar_len and abs(py) <= bar_half) or (abs(py) <= bar_len and abs(px) <= bar_half)
            if on_plus:
                col = BADGE_PLUS
            elif d >= radius - ring:
                col = BADGE_RING
            else:
                col = BADGE_GREEN
            old_a = bmp.GetAlphaPixel(alpha, x, y) if alpha is not None else 255
            if old_a == 0:
                r, g, b = col
            else:
                old = bmp.GetPixel(x, y)
                r, g, b = (int(c * cover + o * (1.0 - cover)) for c, o in zip(col, old))
            bmp.SetPixel(x, y, r, g, b)
            if alpha is not None:
                bmp.SetAlphaPixel(alpha, x, y, max(old_a, int(255 * cover)))
    _cache[key] = bmp
    return bmp
