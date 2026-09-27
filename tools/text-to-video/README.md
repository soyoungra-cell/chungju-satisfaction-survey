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

## 꾸밈 표시 (make_video.py)

- `# 글` → 큰 제목, `@ 글` → 파란 꼬리표, 나머지 → 본문
- `--theme light` 하늘색·크림색 바탕에 파란 글씨, `--bright` 밝은 동요풍 음악

```bash
python3 make_video.py chungju_script.txt --theme light --bright -o 충주어린이집_텍스트영상.mp4
```

## 에디토리얼 스토리 영상 (story_video.py)

인스타그램 게시물(4:5, 1080×1350)용 차분한 영상입니다. 글이 흐릿하게 나타나며 또렷해지고,
선으로 그린 손그림이 그려지듯 나타납니다. 잔잔한 피아노 음악을 직접 합성합니다.

```bash
python3 story_video.py --cover 표지사진.png --logo 로고.png -o story.mp4
python3 story_video.py --cover 표지사진.png --logo 로고.png --only 3   # 3번 장면만 확인
```

장면 글·그림은 `build_scenes()`에서 고칩니다. 글꼴은 Pretendard(OFL, `fonts/`)를 씁니다.
