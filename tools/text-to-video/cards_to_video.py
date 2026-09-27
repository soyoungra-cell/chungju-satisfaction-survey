#!/usr/bin/env python3
"""카드뉴스 이미지들을 배경음악이 들어간 세로형(9:16) 릴스 영상으로 만듭니다.

사용법:
    pip install pillow numpy imageio-ffmpeg
    python3 cards_to_video.py 1.png 2.png 3.png ... -o reels.mp4
    python3 cards_to_video.py cards/*.png -o reels.mp4 --music 내음악.mp3

- 카드는 화면 가운데에 온전히 보이고, 빈 위아래는 같은 카드를 흐리게 깔아 채웁니다.
- 카드가 천천히 확대되며, 다음 카드로 부드럽게 넘어갑니다.
- 첫 장과 마지막 장은 조금 짧게, 글이 많은 중간 장은 읽을 시간을 줍니다.
- --music 이 없으면 밝은 동요풍 배경음악을 직접 합성합니다(저작권 걱정 없음).
"""
import argparse
import subprocess
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

W, H, FPS = 1080, 1920, 30
SR = 44100
CARD_W = 1000          # 화면에 보이는 카드 너비
XFADE = 0.7            # 장면 전환 시간(초)
ZOOM = 0.035           # 장면 동안 확대되는 정도


def background(img):
    """카드를 화면 가득 채워 흐리게 만든 배경."""
    scale = max(W / img.width, H / img.height)
    bg = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
    left, top = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(40))
    bg = ImageEnhance.Brightness(bg).enhance(1.08)
    return Image.blend(bg, Image.new("RGB", (W, H), (255, 255, 255)), 0.25)


def shadow(size, radius=30, blur=25):
    """카드 뒤에 깔 부드러운 그림자."""
    pad = blur * 2
    sh = Image.new("L", (size[0] + pad * 2, size[1] + pad * 2), 0)
    sh.paste(90, (pad, pad + 12, pad + size[0], pad + size[1] + 12))
    return sh.filter(ImageFilter.GaussianBlur(blur)), pad


def frame(card, bg, p):
    """p(0~1): 장면 진행도."""
    z = 1 + ZOOM * p
    cw = int(CARD_W * z)
    ch = int(cw * card.height / card.width)
    out = bg.copy()
    sh, pad = shadow((cw, ch))
    x, y = (W - cw) // 2, (H - ch) // 2
    out.paste((0, 0, 0), (x - pad, y - pad), sh)
    out.paste(card.resize((cw, ch), Image.BILINEAR), (x, y))
    return np.asarray(out)


def synth_music(seconds, bpm=104, seed=7):
    """밝은 동요풍: 오르골 멜로디 + 피아노 코드 + 베이스 + 가벼운 박수 (C-G-Am-F)."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    beat = 60 / bpm
    bar = beat * 4
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    chords = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]
    # 한 마디당 8분음표 8개 멜로디 (None = 쉼표), 4마디 반복 + 변주
    melody = [
        [72, 76, 79, 76, 77, 76, 74, None],
        [74, 71, 74, 79, 77, 74, 71, None],
        [72, 76, 81, 79, 76, 72, 76, None],
        [77, 76, 74, 72, 74, 77, 79, None],
        [79, 81, 79, 76, 77, 79, 76, None],
        [74, 76, 74, 71, 67, 71, 74, None],
        [76, 72, 76, 81, 79, 76, 72, None],
        [72, 74, 77, 76, 74, 72, 72, None],
    ]

    def add(start, dur, f, amp, decay, harm=(1, 0.5, 0.25)):
        s = int(start * SR)
        e = min(n, s + int(dur * SR))
        if s >= n:
            return
        nt = t[s:e] - t[s]
        env = np.exp(-nt * decay) * np.minimum(1, nt / 0.005)
        wave_ = sum(a * np.sin(2 * np.pi * f * (k + 1) * nt) for k, a in enumerate(harm))
        out[s:e] += amp * env * wave_

    bars = int(seconds / bar) + 1
    for i in range(bars):
        b0 = i * bar
        chord = chords[i % 4]
        intro = i < 2  # 처음 두 마디는 멜로디 없이 시작
        # 피아노 코드 (2박마다)
        for half in (0, 2):
            for m in chord:
                add(b0 + half * beat, beat * 2, hz(m), 0.05, 2.5, (1, 0.4, 0.15))
        # 베이스 (1, 3박)
        add(b0, beat * 1.8, hz(chord[0] - 24), 0.16, 1.8, (1, 0.3))
        add(b0 + 2 * beat, beat * 1.8, hz(chord[0] - 17), 0.13, 1.8, (1, 0.3))
        # 오르골 멜로디
        if not intro:
            for j, m in enumerate(melody[(i - 2) % 8]):
                if m is not None:
                    add(b0 + j * beat / 2, beat * 1.5, hz(m), 0.09, 5, (1, 0.2, 0.0, 0.12))
        # 킥 + 박수(2, 4박) + 쉐이커(8분)
        for j in range(4):
            ks = int((b0 + j * beat) * SR)
            if ks >= n:
                break
            if j % 2 == 0:
                ke = min(n, ks + int(0.2 * SR))
                kt = t[ks:ke] - t[ks]
                out[ks:ke] += 0.22 * np.exp(-kt * 20) * np.sin(2 * np.pi * (55 + 70 * np.exp(-kt * 35)) * kt)
            elif not intro:
                ce = min(n, ks + int(0.12 * SR))
                out[ks:ce] += 0.06 * rng.standard_normal(ce - ks) * np.exp(-np.arange(ce - ks) / SR * 35)
            for hh in (0, 0.5):
                hs = ks + int(hh * beat * SR)
                he = min(n, hs + int(0.04 * SR))
                if hs < he:
                    out[hs:he] += 0.015 * rng.standard_normal(he - hs) * np.exp(-np.arange(he - hs) / SR * 90)

    fade_in, fade_out = int(0.5 * SR), int(2.5 * SR)
    out[:fade_in] *= np.linspace(0, 1, fade_in)
    out[-fade_out:] *= np.linspace(1, 0, fade_out)
    out /= np.max(np.abs(out)) + 1e-9
    return (out * 0.85 * 32767).astype(np.int16)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cards", nargs="+", help="카드 이미지들 (순서대로)")
    ap.add_argument("-o", "--out", default="reels.mp4")
    ap.add_argument("--sec", type=float, default=5.0, help="중간 카드 한 장당 시간(초)")
    ap.add_argument("--music", help="직접 준비한 음악 파일(mp3/wav). 없으면 자동 합성")
    args = ap.parse_args()

    cards = [Image.open(p).convert("RGB") for p in args.cards]
    bgs = [background(c) for c in cards]
    durs = [args.sec] * len(cards)
    durs[0] = durs[-1] = max(3.0, args.sec - 1)
    total = sum(durs) - XFADE * (len(cards) - 1)

    silent = args.out + ".video.mp4"
    writer = imageio_ffmpeg.write_frames(silent, (W, H), fps=FPS, codec="libx264",
                                         pix_fmt_out="yuv420p", quality=None, macro_block_size=8,
                                         output_params=["-crf", "21"])
    writer.send(None)
    xf = int(XFADE * FPS)
    for i, (card, bg, dur) in enumerate(zip(cards, bgs, durs)):
        nf = int(dur * FPS)
        # 다음 장면과 겹치는 마지막 xf 프레임은 전환 구간에서 함께 그림
        body = nf - (xf if i < len(cards) - 1 else 0)
        start = xf if i > 0 else 0
        for f in range(start, body):
            writer.send(frame(card, bg, f / nf))
        if i < len(cards) - 1:
            nxt, nbg, nnf = cards[i + 1], bgs[i + 1], int(durs[i + 1] * FPS)
            for k in range(xf):
                a = frame(card, bg, (body + k) / nf).astype(np.float32)
                b = frame(nxt, nbg, k / nnf).astype(np.float32)
                w = 0.5 - 0.5 * np.cos(np.pi * (k + 1) / (xf + 1))
                writer.send((a * (1 - w) + b * w).astype(np.uint8))
        print(f"카드 {i + 1}/{len(cards)} 완료")
    writer.close()

    if args.music:
        audio_in = ["-stream_loop", "-1", "-i", args.music]
        afilter = ["-af", f"afade=t=out:st={max(0, total - 2.5):.2f}:d=2.5"]
    else:
        wav = args.out + ".music.wav"
        with wave.open(wav, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(synth_music(total).tobytes())
        audio_in, afilter = ["-i", wav], []

    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
                    "-i", silent, *audio_in, *afilter,
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{total:.2f}", "-movflags", "+faststart", args.out], check=True)
    print(f"완료: {args.out} ({total:.1f}초)")


if __name__ == "__main__":
    main()
