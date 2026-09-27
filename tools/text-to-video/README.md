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

## 카드뉴스 이미지 → 릴스 영상

```bash
python3 cards_to_video.py 1.png 2.png 3.png ... -o reels.mp4            # 음악 자동 합성
python3 cards_to_video.py cards/*.png -o reels.mp4 --sec 6 --music 음악.mp3
```

- 카드는 가운데에 온전히 보이고, 위아래 빈 곳은 같은 카드를 흐리게 깔아 채웁니다.
- 카드가 천천히 확대되고, 다음 카드로 부드럽게 넘어갑니다. 중간 카드는 한 장에 5초(`--sec`)씩 보여줍니다.
