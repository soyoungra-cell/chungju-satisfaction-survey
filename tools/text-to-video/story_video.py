#!/usr/bin/env python3
"""차분한 에디토리얼 스타일의 인스타그램 게시물 영상(4:5)을 만듭니다.

- 글이 흐릿하게 나타나며 또렷해지고, 선으로 그린 손그림이 그려지듯 나타납니다.
- 밝은 회색 · 남색 · 청록 바탕이 번갈아 나오고, 잔잔한 피아노 음악을 직접 합성합니다.
- 장면 내용은 아래 SCENES 에서 고칩니다.

사용법:
    pip install pillow numpy imageio-ffmpeg
    python3 story_video.py --cover 표지사진.png --logo 로고.png -o story.mp4
"""
import argparse
import math
import os
import subprocess
import tempfile
import wave
from multiprocessing import Pool

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1350, 30
S = 2                      # 선을 매끄럽게 그리기 위한 확대 배율
SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")
FONTS = {
    "light": os.path.join(FONT_DIR, "Pretendard-Light.otf"),
    "regular": os.path.join(FONT_DIR, "Pretendard-Regular.otf"),
    "semibold": os.path.join(FONT_DIR, "Pretendard-SemiBold.otf"),
}
GOLD = (228, 172, 64)
THEMES = {
    "light": dict(bg=(244, 244, 246), text=(34, 36, 44), sub=(112, 114, 124), line=(70, 72, 82),
                  card=(255, 255, 255), border=(226, 226, 232)),
    "navy": dict(bg=(22, 32, 58), text=(242, 243, 247), sub=(168, 176, 196), line=(222, 227, 238),
                 card=(31, 44, 74), border=(56, 70, 104)),
    "teal": dict(bg=(30, 102, 88), text=(246, 250, 248), sub=(192, 226, 216), line=(232, 242, 238),
                 card=(40, 117, 102), border=(78, 146, 131)),
    "white": dict(bg=(251, 251, 251), text=(34, 36, 44), sub=(112, 114, 124), line=(150, 152, 160),
                  card=(255, 255, 255), border=(226, 226, 232)),
}


def ease(k):
    k = max(0.0, min(1.0, k))
    return 1 - (1 - k) ** 3


_font_cache = {}


def font(weight, size):
    key = (weight, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONTS[weight], size * S)
    return _font_cache[key]


# ---------------------------------------------------------------- 손그림 도형
# 모든 도형은 선(점 목록)의 목록을 돌려줍니다. 좌표는 영상 기준(1080x1350)입니다.

def circle(cx, cy, r, a0=0, a1=360, n=None):
    n = n or max(12, int(abs(a1 - a0) / 8))
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]


def person(cx, base, h, arms="down", pigtails=False):
    r = h * 0.14
    head_y = base - h + r
    neck, hip = head_y + r, base - h * 0.38
    arm_y = neck + h * 0.1
    strokes = [circle(cx, head_y, r), [(cx, neck), (cx, hip)],
               [(cx - h * 0.16, base), (cx, hip), (cx + h * 0.16, base)]]
    if arms == "up":
        strokes.append([(cx - h * 0.22, arm_y - h * 0.2), (cx, arm_y), (cx + h * 0.22, arm_y - h * 0.2)])
    elif arms == "wave":
        strokes.append([(cx - h * 0.2, arm_y + h * 0.18), (cx, arm_y), (cx + h * 0.2, arm_y - h * 0.2)])
    else:
        strokes.append([(cx - h * 0.2, arm_y + h * 0.2), (cx, arm_y), (cx + h * 0.2, arm_y + h * 0.2)])
    if pigtails:
        strokes += [circle(cx - r * 1.3, head_y - r * 0.2, r * 0.35), circle(cx + r * 1.3, head_y - r * 0.2, r * 0.35)]
    # 웃는 입
    strokes.append(circle(cx, head_y + r * 0.1, r * 0.45, 30, 150, 8))
    return strokes


def heart(cx, cy, s):
    pts = []
    for i in range(41):
        t = 2 * math.pi * i / 40
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * s / 32, cy - y * s / 32))
    return [pts]


def sun(cx, cy, r):
    strokes = [circle(cx, cy, r)]
    for k in range(8):
        a = math.radians(k * 45)
        strokes.append([(cx + r * 1.4 * math.cos(a), cy + r * 1.4 * math.sin(a)),
                        (cx + r * 1.85 * math.cos(a), cy + r * 1.85 * math.sin(a))])
    return strokes


def leaf(x, y, dx, dy):
    """(x,y)에서 (x+dx, y+dy) 방향으로 뻗는 잎."""
    L = math.hypot(dx, dy)
    nx, ny = -dy / L, dx / L
    a = [(x + dx * t + nx * L * 0.3 * math.sin(math.pi * t), y + dy * t + ny * L * 0.3 * math.sin(math.pi * t))
         for t in np.linspace(0, 1, 12)]
    b = [(x + dx * t - nx * L * 0.3 * math.sin(math.pi * t), y + dy * t - ny * L * 0.3 * math.sin(math.pi * t))
         for t in np.linspace(1, 0, 12)]
    return a + b


def sprout(cx, base, h):
    top = base - h
    return [[(cx, base), (cx, top + h * 0.3)], leaf(cx, top + h * 0.35, -h * 0.45, -h * 0.3),
            leaf(cx, top + h * 0.3, h * 0.5, -h * 0.35)]


def flower(cx, base, h):
    top = base - h
    r = h * 0.12
    strokes = [[(cx, base), (cx, top + r * 2.2)], circle(cx, top + r, r * 0.8)]
    for k in range(6):
        a = math.radians(k * 60 - 90)
        strokes.append(circle(cx + r * 1.7 * math.cos(a), top + r + r * 1.7 * math.sin(a), r * 0.9))
    strokes.append(leaf(cx, base - h * 0.3, h * 0.3, -h * 0.12))
    return strokes


def tree(cx, base, h):
    r = h * 0.3
    return [[(cx, base), (cx, base - h + r * 1.6)], circle(cx, base - h + r, r),
            [(cx, base - h * 0.45), (cx + h * 0.12, base - h * 0.58)]]


def house(x, base, w, h):
    body = h * 0.6
    return [rect(x, base - body, w, body), [(x - w * 0.08, base - body), (x + w / 2, base - h), (x + w * 1.08, base - body)],
            rect(x + w * 0.4, base - body * 0.55, w * 0.2, body * 0.55), rect(x + w * 0.12, base - body * 0.8, w * 0.18, w * 0.18),
            rect(x + w * 0.7, base - body * 0.8, w * 0.18, w * 0.18)]


def school(x, base, w, h):
    tw = w * 0.34
    tx = x + w * 0.33
    strokes = [rect(x, base - h * 0.5, w, h * 0.5), rect(tx, base - h * 0.78, tw, h * 0.28),
               [(tx - tw * 0.1, base - h * 0.78), (tx + tw / 2, base - h), (tx + tw * 1.1, base - h * 0.78)],
               circle(tx + tw / 2, base - h * 0.66, tw * 0.13), rect(x + w * 0.44, base - h * 0.24, w * 0.12, h * 0.24)]
    for k in range(2):
        strokes.append(rect(x + w * (0.08 + 0.12 * k), base - h * 0.4, w * 0.08, h * 0.1))
        strokes.append(rect(x + w * (0.72 + 0.12 * k), base - h * 0.4, w * 0.08, h * 0.1))
    return strokes


def plane(cx, cy, s):
    return [[(cx - s, cy), (cx + s, cy - s * 0.5), (cx - s * 0.2, cy + s * 0.45), (cx - s, cy)],
            [(cx + s, cy - s * 0.5), (cx - s * 0.35, cy + s * 0.08)],
            [(cx - s * 1.4, cy + s * 0.1), (cx - s * 2.4, cy + s * 0.25)]]


def star(cx, cy, r):
    pts = []
    for k in range(11):
        rr = r if k % 2 == 0 else r * 0.45
        a = math.radians(-90 + k * 36)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return [pts]


def book(cx, cy, w):
    h = w * 0.55
    return [[(cx, cy - h * 0.4), (cx - w / 2, cy - h / 2), (cx - w / 2, cy + h / 2), (cx, cy + h * 0.6)],
            [(cx, cy - h * 0.4), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx, cy + h * 0.6)],
            [(cx, cy - h * 0.4), (cx, cy + h * 0.6)],
            [(cx - w * 0.38, cy - h * 0.15), (cx - w * 0.1, cy - h * 0.08)],
            [(cx + w * 0.1, cy - h * 0.08), (cx + w * 0.38, cy - h * 0.15)]]


def bubble(cx, cy, w, h):
    x, y = cx - w / 2, cy - h / 2
    r = h * 0.3
    pts = circle(x + r, y + r, r, 180, 270, 6) + circle(x + w - r, y + r, r, 270, 360, 6) + \
        circle(x + w - r, y + h - r, r, 0, 90, 6) + [(x + w * 0.35, y + h), (x + w * 0.2, y + h + h * 0.3),
                                                     (x + w * 0.22, y + h)] + circle(x + r, y + h - r, r, 90, 180, 6)
    pts.append(pts[0])
    dots = [circle(cx + d * w * 0.2, cy, w * 0.03, n=8) for d in (-1, 0, 1)]
    return [pts] + dots


def note(cx, cy, s):
    return [circle(cx - s * 0.3, cy + s * 0.5, s * 0.25), [(cx - s * 0.05, cy + s * 0.5), (cx - s * 0.05, cy - s * 0.6),
                                                           (cx + s * 0.45, cy - s * 0.35)]]


def ball(cx, cy, r):
    return [circle(cx, cy, r), circle(cx - r * 1.2, cy, r * 0.9, -50, 50, 10), circle(cx + r * 1.2, cy, r * 0.9, 130, 230, 10)]


def screen(cx, cy, w):
    h = w * 0.62
    return [rect(cx - w / 2, cy - h / 2, w, h), [(cx, cy + h / 2), (cx, cy + h * 0.72)],
            [(cx - w * 0.22, cy + h * 0.72), (cx + w * 0.22, cy + h * 0.72)],
            [(cx - w * 0.2, cy + h * 0.05), (cx - w * 0.05, cy - h * 0.1), (cx + w * 0.08, cy + h * 0.08),
             (cx + w * 0.22, cy - h * 0.15)]]


def blocks(cx, base, s):
    return [rect(cx - s, base - s, s, s), rect(cx, base - s, s, s), rect(cx - s * 0.5, base - s * 2, s, s),
            [(cx - s * 0.5, base - s * 2), (cx, base - s * 2.7), (cx + s * 0.5, base - s * 2)]]


def eye(cx, cy, w):
    return [circle(cx, cy + w * 0.55, w * 0.75, 222, 318, 12), circle(cx, cy - w * 0.55, w * 0.75, 42, 138, 12),
            circle(cx, cy, w * 0.16)]


def hand(cx, cy, s):
    strokes = [[(cx - s * 0.35, cy + s * 0.9), (cx - s * 0.35, cy), (cx + s * 0.35, cy), (cx + s * 0.35, cy + s * 0.9)]]
    for k in range(4):
        x = cx - s * 0.3 + k * s * 0.2
        strokes.append([(x, cy), (x, cy - s * (0.5 + 0.1 * (k in (1, 2))))])
    strokes.append([(cx - s * 0.35, cy + s * 0.2), (cx - s * 0.6, cy - s * 0.1)])
    return strokes


def apple(cx, cy, r):
    return [circle(cx, cy, r, -60, 240), [(cx, cy - r * 0.8), (cx + r * 0.15, cy - r * 1.3)],
            leaf(cx + r * 0.1, cy - r * 1.1, r * 0.6, -r * 0.2)]


def tomato(cx, cy, r):
    return [circle(cx, cy, r), [(cx - r * 0.4, cy - r * 0.95), (cx, cy - r * 0.7), (cx + r * 0.4, cy - r * 0.95)],
            [(cx, cy - r * 0.7), (cx, cy - r * 1.2)]]


def snail(cx, base, s):
    spiral = [(cx + s * 0.5 * (t / 12) * math.cos(t), base - s * 0.55 + s * 0.5 * (t / 12) * math.sin(t))
              for t in np.linspace(12, 0.5, 40)]
    return [spiral, [(cx - s * 0.6, base), (cx + s * 1.1, base), (cx + s * 1.1, base - s * 0.35)],
            [(cx + s * 1.1, base - s * 0.35), (cx + s * 1.25, base - s * 0.75)],
            [(cx + s * 1.0, base - s * 0.35), (cx + s * 0.95, base - s * 0.75)]]


def watering_can(cx, cy, s):
    return [rect(cx - s * 0.5, cy - s * 0.3, s, s * 0.7), [(cx + s * 0.5, cy), (cx + s * 1.1, cy - s * 0.45)],
            circle(cx, cy - s * 0.3, s * 0.35, 180, 360, 10),
            [(cx + s * 1.2, cy - s * 0.3), (cx + s * 1.3, cy - s * 0.05)], [(cx + s * 1.35, cy - s * 0.4), (cx + s * 1.5, cy - s * 0.2)]]


def grass(x, base, s):
    return [[(x - s, base), (x - s * 0.5, base - s), (x, base)], [(x, base), (x + s * 0.5, base - s * 1.3), (x + s, base)]]


def magnifier(cx, cy, r):
    return [circle(cx, cy, r), [(cx + r * 0.7, cy + r * 0.7), (cx + r * 1.6, cy + r * 1.6)]]


def arrow(x1, y, x2):
    return [[(x1, y), (x2, y)], [(x2 - 14, y - 10), (x2, y), (x2 - 14, y + 10)]]


# ---------------------------------------------------------------- 화면 요소

class Text:
    def __init__(self, x, y, text, weight="regular", size=56, color="text", t0=0.0, align="left",
                 underline=False, dur=0.7):
        self.x, self.y, self.text, self.t0, self.dur = x, y, text, t0, dur
        self.weight, self.size, self.color, self.align, self.underline = weight, size, color, align, underline
        self.layer = None

    def prepare(self, th):
        f = font(self.weight, self.size)
        bbox = f.getbbox(self.text)
        pad = 30 * S
        w, h = bbox[2] + pad * 2, bbox[3] + pad * 2
        self.layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(self.layer).text((pad, pad), self.text, font=f, fill=th[self.color] + (255,))
        self.pad, self.tw = pad, bbox[2]
        if self.tw / S > W - 110:
            print(f"  경고: 글이 너무 깁니다 → {self.text}")
        self.blurred = {}

    def draw(self, img, d, t, th):
        k = (t - self.t0) / self.dur
        if k <= 0:
            return
        e = ease(k)
        x = self.x * S
        if self.align == "center":
            x -= self.tw / 2
        y = int((self.y + 14 * (1 - e)) * S)
        radius = round((1 - e) * 9) * S
        if radius:
            if radius not in self.blurred:
                self.blurred[radius] = self.layer.filter(ImageFilter.GaussianBlur(radius))
            layer = self.blurred[radius]
        else:
            layer = self.layer
        if e < 1:
            layer = layer.copy()
            layer.putalpha(layer.getchannel("A").point(lambda a: int(a * e)))
        img.alpha_composite(layer, (int(x - self.pad), int(y - self.pad)))
        if self.underline:
            u = ease((t - self.t0 - 0.5) / 0.6)
            if u > 0:
                uy = (self.y + self.size * 1.22) * S
                d.line([(x, uy), (x + self.tw * u, uy)], fill=GOLD, width=3 * S)


class Doodle:
    def __init__(self, strokes, t0=0.0, dur=1.2, color="line", width=3):
        self.strokes = [[(px * S, py * S) for px, py in s] for s in strokes]
        self.t0, self.dur, self.color, self.width = t0, dur, color, width
        self.lengths = [sum(math.dist(a, b) for a, b in zip(s, s[1:])) for s in self.strokes]
        self.total = sum(self.lengths) or 1

    def draw(self, img, d, t, th):
        k = ease((t - self.t0) / self.dur)
        if k <= 0:
            return
        color = GOLD if self.color == "gold" else th[self.color]
        budget = self.total * k
        w = self.width * S
        for s, L in zip(self.strokes, self.lengths):
            if budget <= 0:
                break
            if budget >= L:
                pts = s
            else:
                pts, acc = [s[0]], 0.0
                for a, b in zip(s, s[1:]):
                    seg = math.dist(a, b)
                    if acc + seg >= budget:
                        r = (budget - acc) / seg if seg else 0
                        pts.append((a[0] + (b[0] - a[0]) * r, a[1] + (b[1] - a[1]) * r))
                        break
                    pts.append(b)
                    acc += seg
            budget -= L
            if len(pts) > 1:
                d.line(pts, fill=color, width=w, joint="curve")
                for p in (pts[0], pts[-1]):
                    d.ellipse([p[0] - w / 2 + 1, p[1] - w / 2 + 1, p[0] + w / 2 - 1, p[1] + w / 2 - 1], fill=color)


class Card:
    def __init__(self, x, y, w, h, t0=0.0, radius=22):
        self.box, self.t0, self.radius = (x * S, y * S, (x + w) * S, (y + h) * S), t0, radius * S

    def draw(self, img, d, t, th):
        k = ease((t - self.t0) / 0.5)
        if k <= 0:
            return
        a = int(255 * k)
        d.rounded_rectangle(self.box, radius=self.radius, fill=th["card"] + (a,), outline=th["border"] + (a,),
                            width=2 * S)


class Pill:
    def __init__(self, x, y, text, t0=0.0):
        self.x, self.y, self.text, self.t0 = x, y, text, t0

    def width(self):
        return font("regular", 26).getlength(self.text) / S + 44

    def draw(self, img, d, t, th):
        k = ease((t - self.t0) / 0.5)
        if k <= 0:
            return
        a = int(255 * k)
        w = self.width()
        x, y = self.x * S, (self.y + 8 * (1 - k)) * S
        d.rounded_rectangle([x, y, x + w * S, y + 50 * S], radius=25 * S, fill=th["card"] + (a,),
                            outline=th["line"] + (int(a * 0.7),), width=2 * S)
        d.text((x + 22 * S, y + 11 * S), self.text, font=font("regular", 26), fill=th["text"] + (a,))


class Rule:
    def __init__(self, x1, y, x2, t0=0.0, dur=0.8, color="border"):
        self.x1, self.y, self.x2, self.t0, self.dur, self.color = x1, y, x2, t0, dur, color

    def draw(self, img, d, t, th):
        k = ease((t - self.t0) / self.dur)
        if k > 0:
            d.line([(self.x1 * S, self.y * S), ((self.x1 + (self.x2 - self.x1) * k) * S, self.y * S)],
                   fill=th[self.color], width=2 * S)


class Photo:
    """가운데 가는 띠에서 위아래로 펼쳐지는 사진."""

    def __init__(self, path, x, y, w, t0=0.0, dur=1.0, radius=16):
        self.src, self.x, self.y, self.w, self.t0, self.dur, self.radius = path, x, y, w, t0, dur, radius
        self.img = None

    def prepare(self, th):
        im = self.src if isinstance(self.src, Image.Image) else Image.open(self.src)
        im = im.convert("RGBA")
        self.h = self.w * im.height / im.width
        self.img = im.resize((int(self.w * S), int(self.h * S)), Image.LANCZOS)
        mask = Image.new("L", self.img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, *self.img.size], radius=self.radius * S, fill=255)
        self.img.putalpha(mask)

    def draw(self, img, d, t, th):
        k = ease((t - self.t0) / self.dur)
        if k <= 0:
            return
        full_h = self.img.height
        vis = max(4 * S, int(full_h * (0.04 + 0.96 * k)))
        top = (full_h - vis) // 2
        crop = self.img.crop((0, top, self.img.width, top + vis))
        img.alpha_composite(crop, (int(self.x * S), int(self.y * S + top)))


class Logo(Photo):
    def draw(self, img, d, t, th):
        k = ease((t - self.t0) / self.dur)
        if k <= 0:
            return
        layer = self.img
        r = round((1 - k) * 8) * S
        if r:
            layer = layer.filter(ImageFilter.GaussianBlur(r))
        layer = layer.copy()
        layer.putalpha(layer.getchannel("A").point(lambda a: int(a * k)))
        img.alpha_composite(layer, (int(self.x * S), int((self.y + 12 * (1 - k)) * S)))


# ---------------------------------------------------------------- 장면 도우미

M = 64               # 왼쪽 여백
GROUND = 1180        # 바닥선 높이


def ground(extras, t0=0.6):
    """화면 아래 바닥선과 작은 낙서들."""
    items = [Doodle([[(30, GROUND), (1050, GROUND)]], t0=t0, dur=1.4, width=2)]
    for i, (strokes, color) in enumerate(extras):
        items.append(Doodle(strokes, t0=t0 + 0.8 + i * 0.25, dur=1.0, color=color, width=2))
    return items


def heading(lines, y=100, t0=0.5, gap=0.28):
    """[(글, 'big'|'small'|'label'|'mid'), ...] 를 위에서부터 쌓습니다."""
    styles = {"big": ("regular", 58, "text", 80), "small": ("light", 30, "sub", 50),
              "label": ("semibold", 26, "sub", 52), "mid": ("semibold", 36, "text", 58)}
    out = []
    for i, (txt, st) in enumerate(lines):
        wgt, size, color, lh = styles[st]
        out.append(Text(M, y, txt, wgt, size, color, t0=t0 + i * gap))
        y += lh
    return out, y


def grid_item(x, y, icon, lines, t0, icon_color="line"):
    items = [Doodle(icon, t0=t0, dur=0.9, color=icon_color)]
    for i, txt in enumerate(lines):
        items.append(Text(x, y + 88 + i * 42, txt, "regular", 30, "text", t0=t0 + 0.25 + i * 0.1))
    return items


# ---------------------------------------------------------------- 장면 내용

def build_scenes(cover, logo):
    scenes = []

    # 1. 표지
    els, y = heading([("충주어린이집", "label")], y=96)
    els.append(Rule(M, 140, W - M, t0=0.4))
    h2, y = heading([("아이들의 꿈이", "big"), ("자라는 곳", "big")], y=176, t0=0.8)
    els += h2
    els.append(Text(M, y + 18, "매일이 즐겁고, 성장이 특별한 공간", "light", 30, "sub", t0=1.5))
    photo = Photo(cover, M, 410, W - 2 * M, t0=2.0)
    cw, ch = Image.open(cover).size
    below = 410 + (W - 2 * M) * ch / cw + 36   # 사진 높이에 맞춰 아래 글 위치를 정함
    els.append(photo)
    els += [Text(M, below, "충주어린이집의 운영철학과 프로그램,", "light", 30, "sub", t0=3.0),
            Text(M, below + 44, "지금부터 하나씩 들려드릴게요", "light", 30, "sub", t0=3.25)]
    els += ground([(sprout(180, GROUND, 60), "line"), (plane(560, 1120, 34), "line"),
                   (sun(900, 1060, 26), "gold"), (tree(980, GROUND, 110), "line")], t0=2.4)
    scenes.append(("light", 6.3, els))

    # 2. 여섯 가지 약속
    els, y = heading([("충주어린이집이 약속합니다", "big"), ("아이를 바라보는 여섯 가지 마음", "small")], y=100)
    els.append(Rule(M, 262, W - M, t0=1.0))
    cells = [(heart, "건강한", "가정", "gold"), (sun, "행복한", "어린이", "gold"), (sprout, "보람있는", "교직원", "line"),
             (house, "0세부터 7세까지", "이어지는 교육", "line"), (book, "그림책으로", "자라는 생각", "line"),
             (flower, "자연에서", "배우는 아이", "line")]
    for i, (fn, a, b, col) in enumerate(cells):
        cx = M if i % 2 == 0 else 560
        cy = 300 + (i // 2) * 250
        icon = {heart: lambda: heart(cx + 34, cy + 36, 58), sun: lambda: sun(cx + 32, cy + 36, 18),
                sprout: lambda: sprout(cx + 32, cy + 70, 64), house: lambda: house(cx + 4, cy + 72, 60, 70),
                book: lambda: book(cx + 34, cy + 38, 64), flower: lambda: flower(cx + 32, cy + 74, 72)}[fn]()
        els += grid_item(cx, cy, icon, [a, b], t0=1.3 + i * 0.55, icon_color=col)
        if i % 2 == 1 and i < 5:
            els.append(Rule(M, cy + 222, W - M, t0=1.3 + i * 0.55))
    scenes.append(("navy", 7.0, els))

    # 3. 건강한 가정
    els, y = heading([("우리 아이가 행복하게 자라기 위해서는", "small"), ("가정의 건강함이", "big"),
                      ("가장 중요합니다", "big")], y=100)
    els.append(Card(M, 340, W - 2 * M, 330, t0=1.4))
    fam = person(420, 620, 190) + person(660, 620, 180, pigtails=True) + person(540, 620, 120, arms="up", pigtails=True)
    els.append(Doodle(fam, t0=1.8, dur=1.8))
    els.append(Doodle(heart(540, 420, 44), t0=3.2, dur=0.6, color="gold"))
    els.append(Doodle(sun(830, 420, 18), t0=3.4, dur=0.6, color="gold"))
    els.append(Doodle(tree(230, 620, 150) + grass(300, 620, 12) + grass(780, 620, 12), t0=2.6, dur=1.2, width=2))
    els += [Text(M, 710, "부모가 서로를 존중하고, 따뜻하게 바라볼 때", "light", 30, "sub", t0=3.6)]
    px = M
    for i, txt in enumerate(["안정감을 느끼고", "스스로 자라는", "힘을 얻어요"]):
        p = Pill(px, 780, txt, t0=4.0 + i * 0.35)
        els.append(p)
        px += p.width() + 14
    els += ground([(house(150, GROUND, 70, 80), "line"), (plane(820, 1110, 30), "line"), (star(960, 1100, 14), "gold")], t0=2.0)
    scenes.append(("light", 6.3, els))

    # 4. 행복한 어린이
    els, y = heading([("아이는", "big"), ("웃음과 행복이 가장 빛나는 곳에서", "small"), ("마음껏", "big"),
                      ("꿈을 키워갑니다", "big")], y=96)
    els.append(Card(M, 430, W - 2 * M, 300, t0=1.6))
    kids = []
    for i, x in enumerate([250, 420, 590, 760]):
        kids += person(x, 690, 150 if i % 2 else 135, arms="up", pigtails=i % 2 == 1)
    els.append(Doodle(kids, t0=2.0, dur=1.8))
    els.append(Doodle(heart(505, 500, 36), t0=3.4, dur=0.5, color="gold"))
    els.append(Doodle(star(680, 490, 16) + star(330, 500, 12), t0=3.6, dur=0.6, color="gold"))
    els.append(Doodle(sun(900, 500, 20), t0=3.5, dur=0.7, color="gold"))
    els += [Text(M, 780, "스스로 삶을 즐기는", "light", 30, "sub", t0=3.9),
            Text(M, 824, "행복한 어린이", "semibold", 36, "text", t0=4.2, underline=True)]
    els += ground([(sprout(130, GROUND, 50), "line"), (sprout(210, GROUND, 40), "line"),
                   (ball(600, GROUND - 22, 22), "line"), (flower(930, GROUND, 80), "line")], t0=2.2)
    scenes.append(("teal", 6.3, els))

    # 5. 보람있는 교직원
    els, y = heading([("교직원이 행복해야", "big"), ("아이들이 행복합니다", "big")], y=100)
    cw, gap = 222, 24
    minis = [(lambda cx, cy: book(cx, cy, 90), "전문성"), (lambda cx, cy: sun(cx, cy, 24), "열정"),
             (lambda cx, cy: person(cx - 30, cy + 55, 110) + person(cx + 30, cy + 55, 110, arms="wave"), "존중"),
             (lambda cx, cy: sprout(cx, cy + 50, 100), "함께 성장")]
    for i, (fn, label) in enumerate(minis):
        x = M + i * (cw + gap)
        els.append(Card(x, 290, cw, 240, t0=1.2 + i * 0.3))
        els.append(Doodle(fn(x + cw / 2, 385), t0=1.5 + i * 0.3, dur=1.0, color="gold" if label == "열정" else "line"))
        els.append(Text(x + cw / 2, 470, label, "regular", 26, "text", t0=1.8 + i * 0.3, align="center"))
    els += [Text(M, 590, "서로 존중하고 함께 성장하며", "light", 30, "sub", t0=3.2),
            Text(M, 636, "보람과 긍지를 느끼는 교직문화", "semibold", 36, "text", t0=3.5, underline=True),
            Text(M, 720, "교직원의 성장이 곧 아이들의 더 큰 행복으로 이어집니다", "light", 28, "sub", t0=4.2)]
    els += ground([(school(120, GROUND, 170, 150), "line"), (star(560, 1110, 14), "gold"),
                   (plane(820, 1100, 30), "line")], t0=2.4)
    scenes.append(("light", 6.3, els))

    # 6. 0~7세
    els, y = heading([("0세부터 7세까지", "big"), ("끊김 없이 이어집니다", "big")], y=100)
    for i, (label, x) in enumerate([("영아반", M), ("유아반", 552)]):
        els.append(Card(x, 290, 464, 300, t0=1.2 + i * 0.4))
        els.append(Text(x + 26, 312, label, "semibold", 26, "sub", t0=1.5 + i * 0.4))
    els.append(Doodle(person(200, 550, 110, arms="up", pigtails=True) + blocks(360, 550, 40), t0=1.7, dur=1.4))
    els.append(Doodle(person(680, 550, 170, arms="wave") + school(790, 550, 170, 150), t0=2.2, dur=1.6))
    els.append(Doodle(arrow(488, 440, 576), t0=2.0, dur=0.6, color="gold"))
    els += [Text(M, 640, "연령의 경계 없이,", "light", 30, "sub", t0=3.4),
            Text(M, 684, "자연스럽게 이어지는 배움과 돌봄", "light", 30, "sub", t0=3.6),
            Text(M, 740, "아이의 전인적 성장을 함께 만들어갑니다", "semibold", 36, "text", t0=4.0, underline=True)]
    els += ground([(sprout(160, GROUND, 40), "line"), (flower(270, GROUND, 70), "line"), (sun(880, 1080, 22), "gold"),
                   (tree(990, GROUND, 110), "line")], t0=2.6)
    scenes.append(("navy", 6.3, els))

    # 7. 그림책 질문놀이 · 문해력
    els, y = heading([("특색프로그램", "label"), ("그림책을 펼치면", "big"), ("질문이 자랍니다", "big")], y=96)
    cw = 222
    minis = [(lambda cx, cy: person(cx, cy + 60, 130, arms="wave"), "손을 들고"),
             (lambda cx, cy: bubble(cx, cy, 110, 64), "잘 듣고"),
             (lambda cx, cy: book(cx, cy, 100), "책을 보며"),
             (lambda cx, cy: magnifier(cx - 10, cy - 10, 30), "생각을 말해요")]
    for i, (fn, label) in enumerate(minis):
        x = M + i * (cw + 24)
        els.append(Card(x, 330, cw, 230, t0=1.3 + i * 0.3))
        els.append(Doodle(fn(x + cw / 2, 420), t0=1.6 + i * 0.3, dur=1.0))
        els.append(Text(x + cw / 2, 504, label, "regular", 26, "text", t0=1.9 + i * 0.3, align="center"))
    els += [Text(M, 610, "그림책을 매개로 질문하고 생각을 나누며", "light", 30, "sub", t0=3.2),
            Text(M, 656, "스스로 이해하고 표현하는 힘을 키웁니다", "semibold", 36, "text", t0=3.5, underline=True),
            Text(M, 740, "읽고 · 생각하고 · 말하는 경험이 튼튼한 문해력의 기초가 돼요", "light", 28, "sub", t0=4.2)]
    els += ground([(book(170, GROUND - 30, 70), "line"), (star(420, 1120, 12), "gold"),
                   (tree(900, GROUND, 120), "line")], t0=2.4)
    scenes.append(("light", 6.3, els))

    # 8. K-사회정서학습
    els, y = heading([("초등연계 K-사회정서학습", "label"), ("서로를 이해하고", "big"), ("존중하는 마음", "big")], y=96)
    els.append(Card(M, 330, W - 2 * M, 300, t0=1.3))
    els.append(Doodle(person(330, 590, 160, arms="wave") + person(500, 590, 160, arms="wave", pigtails=True)
                      + person(760, 590, 150, pigtails=True), t0=1.7, dur=1.8))
    els.append(Doodle(ball(415, 500, 16), t0=3.0, dur=0.5, color="gold"))
    els.append(Doodle(heart(760, 390, 36), t0=3.3, dur=0.5, color="gold"))
    els.append(Doodle(bubble(880, 410, 100, 56), t0=3.0, dur=0.8))
    px = M
    for i, txt in enumerate(["양보해요", "기다려요", "감정을 표현해요"]):
        p = Pill(px, 680, txt, t0=3.6 + i * 0.35)
        els.append(p)
        px += p.width() + 14
    els.append(Text(M, 770, "건강한 마음이 행복한 관계를 만듭니다", "light", 30, "sub", t0=4.6))
    els += ground([(grass(140, GROUND, 14), "line"), (grass(220, GROUND, 10), "line"), (house(760, GROUND, 80, 90), "line"),
                   (sun(960, 1090, 20), "gold")], t0=2.2)
    scenes.append(("teal", 6.3, els))

    # 9. 오감놀이
    els, y = heading([("식습관향상을 위한", "label"), ("오감으로 만나는", "big"), ("건강한 식탁", "big")], y=96)
    cw, gap = 172, 22
    senses = [(lambda cx, cy: eye(cx, cy, 44), "보고"), (lambda cx, cy: hand(cx, cy - 10, 70), "만지고"),
              (lambda cx, cy: flower(cx, cy + 40, 90), "냄새 맡고"), (lambda cx, cy: apple(cx, cy + 6, 32), "맛보고"),
              (lambda cx, cy: bubble(cx, cy, 90, 54), "이야기해요")]
    for i, (fn, label) in enumerate(senses):
        x = M + i * (cw + gap)
        els.append(Card(x, 330, cw, 220, t0=1.2 + i * 0.25))
        els.append(Doodle(fn(x + cw / 2, 415), t0=1.5 + i * 0.25, dur=0.9, color="gold" if label == "맛보고" else "line"))
        els.append(Text(x + cw / 2, 496, label, "regular", 25, "text", t0=1.8 + i * 0.25, align="center"))
    els += [Text(M, 610, "보고, 만지고, 냄새 맡고, 맛보며", "light", 30, "sub", t0=3.2),
            Text(M, 656, "건강한 식습관은 행복한 삶의 시작입니다", "semibold", 36, "text", t0=3.6, underline=True)]
    els += ground([(sprout(150, GROUND, 50), "line"), (tomato(300, GROUND - 24, 22), "gold"),
                   (apple(840, GROUND - 26, 22), "line"), (sprout(950, GROUND, 60), "line")], t0=2.4)
    scenes.append(("light", 6.3, els))

    # 10. 특별 · 특성화 프로그램
    els, y = heading([("특별 · 특성화 프로그램", "label"), ("다양한 경험이", "big"), ("꿈과 자신감을 키워요", "big")], y=96)
    rows = [(lambda x, y: note(x, y, 30), "악기놀이", "실로폰 · 리코더 · 칼림바 · 장구 · 핸드벨"),
            (lambda x, y: screen(x, y - 4, 56), "디지털교육", "생각을 키우는 코딩 놀이"),
            (lambda x, y: bubble(x, y, 56, 36), "영어놀이", "English High"),
            (lambda x, y: ball(x, y, 22), "신체놀이", "몸으로 배우는 즐거움"),
            (lambda x, y: blocks(x, y + 26, 20), "가베", "쌓고 만들며 키우는 창의력")]
    for i, (fn, name, desc) in enumerate(rows):
        ry = 330 + i * 96
        els.append(Doodle(fn(M + 34, ry + 30), t0=1.3 + i * 0.4, dur=0.8, color="gold" if i == 0 else "line"))
        els.append(Text(M + 100, ry + 10, name, "semibold", 30, "text", t0=1.5 + i * 0.4))
        els.append(Text(M + 280, ry + 14, desc, "light", 27, "sub", t0=1.6 + i * 0.4))
        els.append(Rule(M, ry + 82, W - M, t0=1.4 + i * 0.4))
    els += ground([(note(200, 1150, 26), "gold"), (note(260, 1120, 20), "line"), (sun(880, 1080, 22), "gold"),
                   (flower(990, GROUND, 80), "line")], t0=2.8)
    scenes.append(("navy", 6.3, els))

    # 11. 생태체험
    els, y = heading([("텃밭과 전용농장에서", "label"), ("자연이 교실이고,", "big"), ("모든 것이 배움이에요", "big")], y=96)
    cards = [("토마토 수확", lambda x, y: tomato(x - 40, y + 20, 28) + tomato(x + 30, y + 30, 24) + sprout(x + 110, y + 70, 80)),
             ("달팽이 발견", lambda x, y: snail(x - 30, y + 60, 60) + [leaf(x + 90, y + 60, 60, -50)]),
             ("해바라기 키 재기", lambda x, y: flower(x + 60, y + 80, 150) + person(x - 50, y + 80, 110, pigtails=True)),
             ("봉숭아 물주기", lambda x, y: watering_can(x - 60, y + 20, 50) + flower(x + 60, y + 80, 80) + flower(x + 120, y + 80, 60))]
    for i, (label, fn) in enumerate(cards):
        x = M if i % 2 == 0 else 552
        y0 = 330 + (i // 2) * 250
        els.append(Card(x, y0, 464, 230, t0=1.3 + i * 0.35))
        els.append(Text(x + 24, y0 + 20, label, "semibold", 26, "sub", t0=1.6 + i * 0.35))
        els.append(Doodle(fn(x + 232, y0 + 120), t0=1.7 + i * 0.35, dur=1.2, color="line"))
    els.append(Text(M, 860, "생명의 소중함을 배우고, 감성과 창의력을 키워요", "light", 30, "sub", t0=3.8))
    els += ground([(sprout(140, GROUND, 50), "line"), (sprout(200, GROUND, 36), "line"), (sun(560, 1090, 22), "gold"),
                   (tree(960, GROUND, 120), "line")], t0=2.8)
    scenes.append(("teal", 7.0, els))

    # 12. 마무리 문구
    els = [Text(W / 2, 430, "오늘의 놀이가", "regular", 60, "text", t0=0.6, align="center"),
           Text(W / 2, 512, "내일의 꿈이 됩니다", "regular", 60, "text", t0=1.1, align="center"),
           Text(W / 2, 612, "충주어린이집에서 함께 자라요", "light", 30, "sub", t0=1.8, align="center"),
           Doodle([[(120, 880), (960, 880)]], t0=1.8, dur=1.2, width=2),
           Doodle(school(150, 880, 190, 160), t0=2.2, dur=1.4),
           Doodle(person(460, 880, 120, arms="up") + person(560, 880, 130, arms="up", pigtails=True)
                  + person(660, 880, 120, arms="up"), t0=2.6, dur=1.6),
           Doodle(heart(560, 700, 34), t0=3.6, dur=0.5, color="gold"),
           Doodle(tree(860, 880, 140), t0=3.0, dur=1.0),
           Doodle(star(760, 730, 14), t0=3.8, dur=0.5, color="gold")]
    scenes.append(("navy", 5.5, els))

    # 13. 로고
    els = [Logo(logo, 150, 330, 780, t0=0.5, dur=1.0),
           Text(W / 2, 700, "건강한 가정 · 행복한 어린이 · 보람있는 교직원", "regular", 30, "text", t0=1.4, align="center"),
           Rule(380, 780, 700, t0=1.8, color="border"),
           Text(W / 2, 810, "사회복지법인 충주어린이집", "light", 28, "sub", t0=2.0, align="center"),
           Text(W / 2, 852, "충북 충주시 원호암4길 12 · 043-852-2493", "light", 28, "sub", t0=2.2, align="center"),
           Text(W / 2, 894, "@043_852_2493", "light", 28, "sub", t0=2.4, align="center")]
    els += ground([(sprout(160, GROUND, 40), "line"), (star(900, 1150, 12), "gold")], t0=2.0)
    scenes.append(("white", 5.5, els))
    return scenes


# ---------------------------------------------------------------- 렌더링

def render_scene(job):
    idx, theme, dur, prev_theme, cover, logo, path = job
    scenes = build_scenes(cover, logo)
    _, _, els = scenes[idx]
    th = THEMES[theme]
    for e in els:
        if hasattr(e, "prepare"):
            e.prepare(th)
    bg = np.array(th["bg"], dtype=np.float32)
    pbg = np.array(THEMES[prev_theme]["bg"], dtype=np.float32) if prev_theme else bg
    n = int(dur * FPS)
    writer = imageio_ffmpeg.write_frames(path, (W, H), fps=FPS, codec="libx264", pix_fmt_out="yuv420p",
                                         quality=None, macro_block_size=2, output_params=["-crf", "18"])
    writer.send(None)
    fade_out = 0.45
    for f in range(n):
        t = f / FPS
        # 앞 장면 바탕색에서 부드럽게 바뀜
        c = ease(t / 0.4)
        col = tuple(int(v) for v in pbg * (1 - c) + bg * c)
        img = Image.new("RGBA", (W * S, H * S), col + (255,))
        d = ImageDraw.Draw(img, "RGBA")
        for e in els:
            e.draw(img, d, t, th)
        frame = np.asarray(img.convert("RGB").resize((W, H), Image.LANCZOS)).astype(np.float32)
        k = (dur - t) / fade_out
        if k < 1:  # 장면 끝에서 내용이 사라짐
            frame = frame * max(0.0, k) + bg * (1 - max(0.0, k))
        writer.send(frame.astype(np.uint8))
    writer.close()
    return idx


def piano_music(seconds, bpm=72, seed=3):
    """잔잔한 피아노: 분산화음 + 느린 멜로디 + 약한 울림 (C - G - Am - F)."""
    n = int((seconds + 1) * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    beat = 60 / bpm
    bar = beat * 4
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    chords = [[48, 55, 60, 64, 67], [43, 50, 59, 62, 67], [45, 52, 60, 64, 69], [41, 48, 57, 60, 65]]
    melody = [[76, None, 74, 72], [74, None, 71, 67], [72, 74, 76, None], [77, 76, 72, None],
              [79, None, 76, 74], [74, 72, 71, None], [72, None, 76, 79], [77, None, 72, None]]

    def key(start, m, amp, length=2.5):
        s = int(start * SR)
        e = min(n, s + int(length * SR))
        if s >= n:
            return
        nt = t[s:e] - t[s]
        f = hz(m)
        tone = np.zeros_like(nt)
        for h, a in enumerate((1, 0.45, 0.22, 0.1, 0.05), start=1):
            tone += a * np.sin(2 * np.pi * f * h * (1 + 0.0004 * h) * nt) * np.exp(-nt * (1.6 + 0.9 * h))
        out[s:e] += amp * tone * np.minimum(1, nt / 0.004)

    bars = int(seconds / bar) + 1
    for i in range(bars):
        b0 = i * bar
        ch = chords[i % 4]
        key(b0, ch[0] - 12, 0.18, 4)
        key(b0 + beat * 2, ch[1] - 12, 0.1, 3)
        for j, idx in enumerate([1, 2, 3, 4, 3, 2, 3, 4]):
            key(b0 + j * beat / 2, ch[idx], 0.07, 2)
        if i >= 2:
            for j, m in enumerate(melody[(i - 2) % 8]):
                if m is not None:
                    key(b0 + j * beat, m, 0.14, 3)
    # 간단한 울림(여러 개의 지연 신호)
    wet = np.zeros(n)
    for delay, g in ((0.031, 0.5), (0.053, 0.42), (0.089, 0.35), (0.137, 0.28), (0.211, 0.2), (0.33, 0.14)):
        dly = int(delay * SR)
        wet[dly:] += g * out[:-dly]
    out = out + 0.5 * wet
    out = out[:int(seconds * SR)]
    fi, fo = int(0.8 * SR), int(3 * SR)
    out[:fi] *= np.linspace(0, 1, fi)
    out[-fo:] *= np.linspace(1, 0, fo)
    out /= np.max(np.abs(out)) + 1e-9
    return (out * 0.8 * 32767).astype(np.int16)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cover", required=True, help="첫 장면 사진")
    ap.add_argument("--logo", required=True, help="마지막 장면 로고 이미지")
    ap.add_argument("-o", "--out", default="story.mp4")
    ap.add_argument("--music", help="직접 준비한 음악 파일. 없으면 피아노 음악 합성")
    ap.add_argument("--only", type=int, help="이 번호 장면만 만들기(확인용, 1부터)")
    args = ap.parse_args()

    scenes = build_scenes(args.cover, args.logo)
    tmp = tempfile.mkdtemp(prefix="story_")
    jobs = []
    for i, (theme, dur, _) in enumerate(scenes):
        if args.only and i + 1 != args.only:
            continue
        prev = scenes[i - 1][0] if i > 0 else None
        jobs.append((i, theme, dur, prev, args.cover, args.logo, os.path.join(tmp, f"s{i:02d}.mp4")))
    with Pool(min(4, os.cpu_count() or 1)) as pool:
        for i in pool.imap_unordered(render_scene, jobs):
            print(f"장면 {i + 1}/{len(scenes)} 완료")

    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as fh:
        fh.writelines(f"file '{j[-1]}'\n" for j in jobs)
    total = sum(j[2] for j in jobs)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    video = os.path.join(tmp, "video.mp4")
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", video], check=True)

    if args.music:
        audio_in = ["-stream_loop", "-1", "-i", args.music, "-af", f"afade=t=out:st={max(0, total - 3):.2f}:d=3"]
    else:
        wav = os.path.join(tmp, "music.wav")
        with wave.open(wav, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(piano_music(total).tobytes())
        audio_in = ["-i", wav]
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", video, *audio_in, "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-crf", "21", "-preset", "slow", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}", "-movflags", "+faststart", args.out], check=True)
    print(f"완료: {args.out} ({total:.1f}초)")


if __name__ == "__main__":
    main()
