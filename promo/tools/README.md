# 영상 파일 다시 만들기

`chungju-reels.html`의 문구·사진을 바꾼 뒤 MP4를 다시 만들 때 사용합니다.

```bash
pip install numpy imageio-ffmpeg
npm i playwright-core @fontsource/nanum-gothic @fontsource/gowun-dodum
python3 make_music.py                                   # bgm.wav 생성 (직접 합성한 피아노 음악)
FF=$(python3 -c "import imageio_ffmpeg as f;print(f.get_ffmpeg_exe())")
$FF -y -i bgm.wav -c:a aac -b:a 160k bgm.m4a
node export_video.js $FF ../chungju-reels.html ../chungju-reels.mp4
```

- 1080×1920, 30fps, H.264 + AAC, 64초
- `export_video.js`의 `executablePath`는 사용하는 Chromium 경로로 바꿔주세요.
