#!/usr/bin/env python3
"""텍스트 파일을 배경음악이 들어간 세로형(9:16) 영상으로 만듭니다.

사용법:
    pip install pillow numpy imageio-ffmpeg
    python3 make_video.py script.txt -o out.mp4

script.txt 는 빈 줄로 장면을 구분합니다. 첫 장면은 제목으로 크게 표시됩니다.
줄 앞에 "# " 을 붙이면 큰 제목, "@ " 을 붙이면 작은 꼬리표로 표시됩니다.
--theme light 는 밝은 바탕, --bright 는 밝은 동요풍 음악입니다.
배경음악은 저작권 걱정 없이 코드로 직접 합성합니다.
"""
import argparse
import subprocess
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cards_to_video import synth_music as bright_music

W, H, FPS = 1080, 1920, 30
SR = 44100
FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
PALETTES = [
    ((20, 40, 90), (70, 130, 200)),
    ((40, 20, 70), (190, 90, 140)),
    ((10, 60, 60), (60, 170, 140)),
    ((70, 35, 15), (220, 140, 60)),
]


def read_scenes(path):
    text = open(path, encoding="utf-8").read().strip()
    return [s.strip() for s in text.split("\n\n") if s.strip()]


def wrap(draw, text, font, max_w):
    lines = []
    for para in text.split("\n"):
        line = ""
        for ch in para:
            if draw.textlength(line + ch, font=font) > max_w and line:
                # 가능하면 공백에서 줄바꿈
                cut = line.rfind(" ")
                if cut > 0:
                    lines.append(line[:cut])
                    line = line[cut + 1:] + ch
                else:
                    lines.append(line)
                    line = ch
            else:
                line += ch
        lines.append(line)
    return lines


def gradient(top, bottom, shift):
    t = np.linspace(0, 1, H)[:, None]
    t = np.clip(t + 0.15 * np.sin(shift), 0, 1)
    top, bottom = np.array(top), np.array(bottom)
    col = top * (1 - t) + bottom * t
    return np.repeat(col[:, None, :], W, axis=1).astype(np.uint8)


THEMES = {
    # 어두운 바탕 + 흰 글씨
    "dark": dict(palettes=PALETTES, head=(255, 255, 255), body=(255, 255, 255), label_bg=(255, 255, 255),
                 label_fg=(40, 60, 110), deco=(255, 255, 255, 18), shadow=True, bar=(255, 255, 255)),
    # 하늘색·크림색 바탕 + 파란 글씨 (카드뉴스 느낌)
    "light": dict(palettes=[((232, 243, 255), (196, 222, 250)), ((255, 250, 238), (250, 234, 208)),
                            ((236, 248, 240), (205, 234, 214)), ((244, 240, 255), (220, 214, 248))],
                  head=(28, 88, 178), body=(55, 65, 85), label_bg=(40, 105, 200), label_fg=(255, 255, 255),
                  deco=(255, 255, 255, 110), shadow=False, bar=(40, 105, 200)),
}


def parse(text, is_title):
    """'# 제목', '@ 작은 꼬리표', 나머지는 본문. 표시가 없으면 예전처럼 동작."""
    items = []
    if any(r.startswith(("# ", "@ ")) for r in text.split("\n")):
        is_title = False
    for raw in text.split("\n"):
        if raw.startswith("# "):
            items.append(("head", raw[2:]))
        elif raw.startswith("@ "):
            items.append(("label", raw[2:]))
        else:
            items.append(("title" if is_title else "body", raw))
    return items


def render_scene(text, is_title, palette, n_frames, idx, total, theme):
    th = THEMES[theme]
    fonts = {k: ImageFont.truetype(FONT, s) for k, s in
             dict(head=104, title=96, body=58, label=40).items()}
    small = ImageFont.truetype(FONT, 34)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    # 줄 단위 배치 계산: (종류, 글자, 높이)
    rows = []
    for kind, s in parse(text, is_title):
        font = fonts[kind]
        if kind == "label":
            rows.append((kind, s, 100))
            continue
        for ln in wrap(probe, s, font, W - 160):
            rows.append((kind, ln, int(font.size * (1.3 if kind == "head" else 1.55))))
        if kind == "head":
            rows.append(("gap", "", 50))
    block_h = sum(h for _, _, h in rows)

    frames = []
    for f in range(n_frames):
        p = f / n_frames
        img = Image.fromarray(gradient(*palette, shift=(idx + p) * 1.3))
        d = ImageDraw.Draw(img, "RGBA")
        # 부드럽게 떠다니는 원 장식
        for k in range(3):
            cx = W * (0.2 + 0.3 * k) + 60 * np.sin(p * 6 + k)
            cy = H * (0.2 + 0.3 * k) + 80 * np.cos(p * 5 + k)
            r = 220 + 40 * k
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=th["deco"])

        out_fade = min(1.0, (n_frames - f) / (FPS * 0.4))
        y = (H - block_h) // 2 - 40
        for i, (kind, line, h) in enumerate(rows):
            # 줄마다 조금씩 늦게 떠오르게
            local = (f - i * FPS * 0.12) / (FPS * 0.5)
            fade = max(0.0, min(1.0, local, out_fade))
            a = int(255 * fade)
            rise = int(30 * (1 - min(1.0, max(0.0, local))))
            if kind == "gap" or a == 0:
                y += h
                continue
            font = fonts[kind]
            lw = d.textlength(line, font=font)
            x = (W - lw) / 2
            if kind == "label":
                d.rounded_rectangle([x - 36, y + rise + 8, x + lw + 36, y + rise + 76], radius=34,
                                    fill=th["label_bg"] + (a,))
                d.text((x, y + rise + 18), line, font=font, fill=th["label_fg"] + (a,))
            else:
                color = th["head"] if kind in ("head", "title") else th["body"]
                if th["shadow"]:
                    d.text((x + 3, y + rise + 3), line, font=font, fill=(0, 0, 0, a // 3))
                bold = 2 if kind in ("head", "title") else 0
                d.text((x, y + rise), line, font=font, fill=color + (a,),
                       stroke_width=bold, stroke_fill=color + (a,))
            y += h

        # 진행 표시줄
        bar = (idx + p) / total
        d.rectangle([80, H - 140, W - 80, H - 132], fill=th["bar"] + (60,))
        d.rectangle([80, H - 140, 80 + (W - 160) * bar, H - 132], fill=th["bar"] + (220,))
        d.text((80, H - 120), f"{idx + 1} / {total}", font=small, fill=th["bar"] + (180,))
        frames.append(np.asarray(img))
    return frames


def synth_music(seconds, bpm=84):
    """잔잔한 코드 패드 + 아르페지오 + 가벼운 비트 (C - G - Am - F)."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    beat = 60 / bpm
    bar = beat * 4
    chords = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)

    for i in range(int(seconds / bar) + 1):
        s = int(i * bar * SR)
        e = min(n, int((i + 1) * bar * SR))
        if s >= n:
            break
        seg = t[s:e] - t[s]
        env = np.minimum(1, seg / 0.8) * np.minimum(1, (bar - seg) / 0.5)
        chord = chords[i % 4]
        for m in chord:
            f = hz(m)
            out[s:e] += 0.06 * env * (np.sin(2 * np.pi * f * seg) + 0.3 * np.sin(2 * np.pi * f * 2 * seg))
        out[s:e] += 0.08 * env * np.sin(2 * np.pi * hz(chord[0] - 12) * seg)  # 베이스
        # 8분음표 아르페지오
        pattern = chord + [chord[0] + 12]
        for j in range(8):
            ns = s + int(j * beat / 2 * SR)
            if ns >= e:
                break
            ne = min(e, ns + int(beat * SR))
            nt = t[ns:ne] - t[ns]
            f = hz(pattern[[0, 1, 2, 3, 2, 1, 0, 1][j]] + 12)
            out[ns:ne] += 0.05 * np.exp(-nt * 4) * np.sin(2 * np.pi * f * nt)
        # 킥(1,3박) + 하이햇(8분)
        for j in range(4):
            ks = s + int(j * beat * SR)
            if ks >= e:
                break
            if j % 2 == 0:
                ke = min(e, ks + int(0.25 * SR))
                kt = t[ks:ke] - t[ks]
                out[ks:ke] += 0.25 * np.exp(-kt * 18) * np.sin(2 * np.pi * (50 + 60 * np.exp(-kt * 30)) * kt)
            for hh in (0, 0.5):
                hs = ks + int(hh * beat * SR)
                he = min(e, hs + int(0.05 * SR))
                if hs < he:
                    out[hs:he] += 0.02 * np.random.randn(he - hs) * np.exp(-np.arange(he - hs) / SR * 80)

    fade = int(2 * SR)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    out /= np.max(np.abs(out)) + 1e-9
    return (out * 0.8 * 32767).astype(np.int16)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("-o", "--out", default="video.mp4")
    ap.add_argument("--music", help="직접 준비한 음악 파일(mp3/wav). 없으면 자동 합성")
    ap.add_argument("--theme", choices=THEMES, default="dark", help="dark(기본) 또는 light")
    ap.add_argument("--bright", action="store_true", help="밝은 동요풍 음악으로 합성")
    args = ap.parse_args()

    scenes = read_scenes(args.script)
    # 글자 수에 비례한 장면 길이 (3.5~8초)
    durations = [min(8.0, max(3.5, 1.8 + len(s) * 0.065)) for s in scenes]
    total = sum(durations)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    silent = args.out + ".video.mp4"
    writer = imageio_ffmpeg.write_frames(silent, (W, H), fps=FPS, codec="libx264",
                                         pix_fmt_out="yuv420p", quality=None, macro_block_size=8,
                                         output_params=["-crf", "21"])
    writer.send(None)
    pal = THEMES[args.theme]["palettes"]
    for i, (s, dur) in enumerate(zip(scenes, durations)):
        for fr in render_scene(s, i == 0, pal[i % len(pal)], int(dur * FPS), i, len(scenes), args.theme):
            writer.send(fr)
        print(f"장면 {i + 1}/{len(scenes)} 완료")
    writer.close()

    if args.music:
        audio_args = ["-stream_loop", "-1", "-i", args.music,
                      "-af", f"afade=t=out:st={max(0, total - 2)}:d=2"]
    else:
        wav = args.out + ".music.wav"
        with wave.open(wav, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            music = bright_music(total) if args.bright else synth_music(total)
            w.writeframes(music.tobytes())
        audio_args = ["-i", wav]

    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", silent, *audio_args,
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{total:.2f}", "-movflags", "+faststart", args.out], check=True)
    print(f"완료: {args.out} ({total:.1f}초)")


if __name__ == "__main__":
    main()
