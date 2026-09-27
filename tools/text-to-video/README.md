# 텍스트 → 영상 만들기

글(텍스트 파일)을 배경음악이 들어간 세로형(1080×1920) 영상으로 만듭니다. 인스타 릴스·쇼츠용입니다.

```bash
pip install pillow numpy imageio-ffmpeg
python3 make_video.py sample.txt -o sample.mp4
python3 make_video.py 내글.txt -o 내영상.mp4 --music 내음악.mp3   # 음악 직접 넣기
```

- 빈 줄로 장면을 나눕니다. 첫 장면은 제목처럼 크게 표시됩니다.
- 장면 길이는 글자 수에 맞춰 3~7초로 정해집니다.
- `--music`을 안 쓰면 잔잔한 배경음악을 코드로 합성해 넣습니다(저작권 걱정 없음).
