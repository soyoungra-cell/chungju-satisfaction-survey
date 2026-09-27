# 영상 파일 다시 만들기

`chungju-reels.html`의 문구·사진을 바꾼 뒤 MP4를 다시 만들 때 사용합니다.

```bash
pip install numpy imageio-ffmpeg
npm i playwright-core @fontsource/nanum-gothic @fontsource/gowun-dodum
FF=$(python3 -c "import imageio_ffmpeg as f;print(f.get_ffmpeg_exe())")
# 배경음악: 어린이집 노래(원곡 약 65.5초)를 4% 빠르게 해 63초에 맞춤
$FF -y -i 충주어린이집.mp3 -map 0:a -af "atempo=1.041,afade=t=in:d=0.3,afade=t=out:st=62.2:d=0.8" -t 63 -ar 44100 -c:a libmp3lame -b:a 192k bgm.mp3
# (make_music.py는 이전에 쓰던 합성 피아노 음악 생성기입니다)
node export_video.js $FF ../chungju-reels.html ../chungju-reels.mp4
```

- 1080×1920, 30fps, H.264 + AAC, 64초
- `export_video.js`의 `executablePath`는 사용하는 Chromium 경로로 바꿔주세요.
