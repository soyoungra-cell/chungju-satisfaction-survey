#!/usr/bin/env python3
"""텍스트 파일을 배경음악이 들어간 세로형(9:16) 영상으로 만듭니다.

사용법:
    pip install pillow numpy imageio-ffmpeg
    python3 make_video.py script.txt -o out.mp4

script.txt 는 빈 줄로 장면을 구분합니다. 첫 장면은 제목으로 크게 표시됩니다.
배경음악은 저작권 걱정 없이 코드로 직접 합성합니다.
"""
import argparse
import subprocess
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

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


def render_scene(text, is_title, palette, n_frames, idx, total):
    size = 96 if is_title else 68
    font = ImageFont.truetype(FONT, size)
    small = ImageFont.truetype(FONT, 34)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines = wrap(probe, text, font, W - 180)
    line_h = int(size * 1.45)
    block_h = line_h * len(lines)

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
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 18))

        fade = min(1.0, f / (FPS * 0.6), (n_frames - f) / (FPS * 0.4))
        alpha = int(255 * max(0.0, fade))
        rise = int(40 * (1 - min(1.0, f / (FPS * 0.6))))
        y = (H - block_h) // 2 + rise
        for line in lines:
            lw = d.textlength(line, font=font)
            x = (W - lw) / 2
            d.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0, alpha // 3))
            d.text((x, y), line, font=font, fill=(255, 255, 255, alpha))
            y += line_h

        # 진행 표시줄
        bar = (idx + p) / total
        d.rectangle([80, H - 140, W - 80, H - 132], fill=(255, 255, 255, 60))
        d.rectangle([80, H - 140, 80 + (W - 160) * bar, H - 132], fill=(255, 255, 255, 220))
        d.text((80, H - 120), f"{idx + 1} / {total}", font=small, fill=(255, 255, 255, 180))
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
    args = ap.parse_args()

    scenes = read_scenes(args.script)
    # 글자 수에 비례한 장면 길이 (3~7초)
    durations = [min(7.0, max(3.0, 1.5 + len(s) * 0.09)) for s in scenes]
    total = sum(durations)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    silent = args.out + ".video.mp4"
    writer = imageio_ffmpeg.write_frames(silent, (W, H), fps=FPS, codec="libx264",
                                         pix_fmt_out="yuv420p", quality=8, macro_block_size=8)
    writer.send(None)
    for i, (s, dur) in enumerate(zip(scenes, durations)):
        for fr in render_scene(s, i == 0, PALETTES[i % len(PALETTES)], int(dur * FPS), i, len(scenes)):
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
            w.writeframes(synth_music(total).tobytes())
        audio_args = ["-i", wav]

    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", silent, *audio_args,
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{total:.2f}", "-movflags", "+faststart", args.out], check=True)
    print(f"완료: {args.out} ({total:.1f}초)")


if __name__ == "__main__":
    main()
