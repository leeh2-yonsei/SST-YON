# SST-YON

`uv`와 PATH에 설치된 `ffmpeg`를 사용합니다. 아래 명령은 프로젝트 루트에서 실행합니다.

```powershell
uv sync
```

## 링크 다운로드

쿠키 옵션을 생략하면 프로젝트 루트의 `asset/cookie/cookies.txt`를 자동으로 사용합니다.
`--cookies` 또는 `--cookies-from-browser`를 지정하면 해당 옵션을 우선 사용합니다.
쿠키 파일을 찾을 수 없으면 오류로 중단합니다.

```powershell
# asset/cookie/cookies.txt 자동 사용
uv run download "https://www.youtube.com/watch?v=VIDEO_ID"

# 파일 이름 지정 -> asset/mp4/1주차 강의.mp4
uv run download "URL" -n "1주차 강의"

# Netscape 형식으로 내보낸 쿠키 파일 사용
uv run download "https://www.youtube.com/watch?v=VIDEO_ID" --cookies cookies.txt

# 로그인된 브라우저의 쿠키 사용
uv run download "https://www.youtube.com/watch?v=VIDEO_ID" --cookies-from-browser firefox

# 저장 위치 변경, 여러 링크 지정
uv run download "URL1" "URL2" -o asset/mp4

# 재생목록 전체 다운로드
uv run download "PLAYLIST_URL" --playlist
```

기본 출력은 `asset/mp4/제목 [영상ID].mp4`입니다. 영상과 오디오를 다운로드한 뒤
ffmpeg로 병합하고 MP4 컨테이너로 리먹싱합니다. 기존 파일은 덮어쓰지 않습니다.
기본적으로 재생목록 전체 다운로드는 꺼져 있습니다.
`-n` 또는 `--name`으로 이름을 지정할 수 있으며 `.mp4` 확장자는 생략해도 됩니다.
이름에는 폴더 경로를 넣을 수 없고, 단일 URL에서 `--playlist` 없이 사용할 때만 허용합니다.
이후 `to-mp3`와 `transcribe`도 원본 이름을 유지합니다.

브라우저 지정값은 yt-dlp의 `--cookies-from-browser` 형식을 그대로 받습니다
(예: `firefox`, `chrome:Default`, `edge`). 브라우저 쿠키 추출이 실패하면
내보낸 쿠키 파일을 `--cookies`로 지정하세요. 쿠키 파일 형식과 내보내기는
[yt-dlp 공식 FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)를 참고하세요.
`asset/cookie/`, `cookie/` 폴더, 쿠키 파일과 `.env`는 `.gitignore`에 등록되어 있습니다.

## MP3 변환

```powershell
# asset/mp4 바로 아래의 모든 MP4 -> asset/mp3
uv run to-mp3

# 파일 하나 변환 (공백이나 대괄호가 있는 경로는 따옴표 사용)
uv run to-mp3 "asset/mp4/index [index].mp4"

# 폴더 또는 여러 파일 지정, 출력 폴더와 품질 변경
uv run to-mp3 asset/mp4 -o asset/mp3 --quality 2
uv run to-mp3 "first.mp4" "second.mp4" -o asset/mp3

# 기존 MP3 덮어쓰기
uv run to-mp3 "asset/mp4/index [index].mp4" --overwrite
```

출력 이름은 `원본이름.mp3`이며 기본 출력 폴더는 `asset/mp3`입니다.
첫 번째 오디오 트랙을 MP3 VBR로 인코딩합니다. 품질은 `0`(최고)부터 `9`(최저)까지이며
기본값은 `2`입니다. 원본 파일은 유지합니다. 폴더를 지정하면 바로 아래의 MP4만 변환하고,
파일을 직접 지정하면 ffmpeg가 읽을 수 있는 다른 미디어 형식도 변환할 수 있습니다.
기존 출력이나 같은 이름의 출력이 겹치면 실행 전에 오류로 중단합니다.

## 로컬 음성 전사 (faster-whisper)

`transcribe`는 API 키 없이 로컬에서 실행합니다. 기본 설정은 RTX 3060 Ti 8GB를 고려한
`turbo` 모델, CUDA, `int8_float16`, beam 크기 `5`, 무음 구간 필터(VAD) 사용입니다.
파일을 순차 처리하고 모델은 한 번만 로딩합니다.
모델 로딩, 전체 파일 처리 현황, 파일별 전사 진행률과 예상 남은 시간을 Rich 진행 막대로 표시합니다.
전사 진행률은 원본 음성 길이와 마지막으로 처리한 구간의 타임스탬프를 기준으로 계산합니다.

Windows GPU 실행에는 CUDA 12의 cuBLAS와 cuDNN 9 라이브러리가 필요합니다.
CUDA 선택 의존성을 설치하면 명령 실행 중 가상환경의 DLL 경로를 자동 등록합니다.
별도로 CUDA 툴킷을 설치하거나 시스템 PATH를 수정할 필요는 없습니다.
NVIDIA 드라이버는 설치되어 있어야 합니다.

```powershell
# Windows GPU 런타임 설치 (대용량: cuBLAS + cuDNN 약 1.3GB 다운로드)
uv sync --extra cuda

# asset/mp3의 모든 음성 파일 -> asset/txt
uv run --extra cuda transcribe

# 파일 하나, 한국어 지정 (영어는 --language en, 생략하면 자동 감지)
uv run --extra cuda transcribe "asset/mp3/index [index].mp3" --language ko

# 모델을 바꿔 인식 결과 비교
uv run --extra cuda transcribe "asset/mp3/index [index].mp3" --model large-v3 --language ko -o asset/txt/large-v3

# GPU 메모리가 부족하면 더 작은 모델 사용
uv run --extra cuda transcribe "asset/mp3/index [index].mp3" --model medium

# CPU 실행
uv run transcribe "asset/mp3/index [index].mp3" --device cpu --model small

# 이미 다운로드된 모델만 사용, 기존 결과 덮어쓰기
uv run --extra cuda transcribe --local-files-only --overwrite
```

`uv run --extra cuda`처럼 실행할 때도 extra를 지정해야 GPU 패키지가 유지됩니다.
필요한 CUDA DLL이 이미 시스템 PATH에 있으면 `uv run transcribe`로 실행할 수 있습니다.
이 GPU extra는 Windows용이며 다른 운영체제에서는 해당 CUDA 런타임을 따로 준비하세요.

첫 실행 시 선택한 모델을 Hugging Face에서 `.cache/whisper`로 다운로드합니다.
이후에는 캐시를 재사용합니다. 모델 다운로드는 인터넷이 필요하고 전사는 로컬에서 실행됩니다.
`--model-dir`로 캐시 위치를 바꿀 수 있습니다. 모델이나 CUDA 런타임은 명령을 실행할 때 설치하며,
전사 테스트는 별도로 수행해야 합니다.

기본 출력은 `asset/txt/원본이름.txt`이며 인식 구간별 텍스트를 UTF-8로 저장합니다.
전사가 완료된 파일만 결과로 저장하고, 기본적으로 기존 파일은 덮어쓰지 않습니다.
폴더 입력은 바로 아래의 MP3, MP4, WAV, FLAC, M4A, OGG, OPUS, WEBM을 처리합니다.
MP4도 직접 읽으므로 전사만 필요하면 MP3 변환 단계를 생략할 수 있습니다.
`--initial-prompt "전문 용어와 문맥"`로 인식을 돕고, `--no-vad`로 무음 필터를 끌 수 있습니다.

GPU 요구 사항과 사용법은 [faster-whisper 공식 문서](https://github.com/SYSTRAN/faster-whisper#gpu)를 참고하세요.
위 설정의 실제 속도와 인식 품질은 음성 파일 및 GPU 가용 메모리에 따라 달라집니다.

현재 faster-whisper 1.2.1은 PyAV 19에서 제거된 `metadata_errors` 인자를 사용하므로
호환되는 `av<19`로 제한합니다. 관련 변경 후에는 `uv sync --extra cuda`로 환경을 동기화하세요.
[공식 호환성 이슈](https://github.com/SYSTRAN/faster-whisper/issues/1589)
Hugging Face의 Windows 심볼릭 링크 경고와 토큰 미설정 경고는 이 디코딩 오류의 원인이 아닙니다.

## URL에서 전사까지 한 번에 실행

```powershell
# 현재 기본 쿠키 파일(asset/cookie/cookies.txt) 사용, 한국어 전사
uv run --extra cuda pipeline "https://www.youtube.com/watch?v=VIDEO_ID" --language ko

# 이름을 지정하고 언어 옵션의 단축형 사용
uv run --extra cuda pipeline "URL" -n "1주차 강의" -l ko

# 쿠키 파일 또는 브라우저 지정
uv run --extra cuda pipeline "URL" --cookies "custom-cookies.txt"
uv run --extra cuda pipeline "URL" --cookies-from-browser firefox

# 여러 링크 또는 재생목록
uv run --extra cuda pipeline "URL1" "URL2" --language ko
uv run --extra cuda pipeline "PLAYLIST_URL" --playlist --language ko

# 출력 위치 변경, 캐시된 모델만 사용
uv run --extra cuda pipeline "URL" -o asset/lecture --local-files-only

# 기존 MP3/TXT를 다시 생성
uv run --extra cuda pipeline "URL" --overwrite

# CPU 사용
uv run pipeline "URL" --device cpu --model small
```

`pipeline`은 다운로드 → MP3 변환 → 전사를 순서대로 실행합니다.
기본 결과는 `asset/mp4/제목 [ID].mp4`, `asset/mp3/제목 [ID].mp3`,
`asset/txt/제목 [ID].txt`에 저장됩니다. `-o`를 지정하면 그 폴더 아래에 `mp4`, `mp3`, `txt`를 생성합니다.
이번 URL의 다운로드 결과만 다음 단계에 전달하며 기존 폴더의 다른 파일은 처리하지 않습니다.
`-n "1주차 강의"`를 지정하면 결과는 각각 `1주차 강의.mp4`, `1주차 강의.mp3`,
`1주차 강의.txt`로 저장됩니다. `transcribe`와 `pipeline` 모두 `--language` 대신 `-l`을 사용할 수 있습니다.
재생목록과 여러 링크의 MP3도 한 번의 전사 명령에 넘겨 모델을 한 번만 로딩합니다.

한 단계가 실패하면 이후 단계는 실행하지 않습니다. 완료된 MP4/MP3/TXT는 유지합니다.
다운로드된 MP4는 재사용하고, 기존 MP3/TXT가 있으면 기본적으로 오류로 중단합니다.
실패 후 다시 실행하거나 기존 결과를 다시 만들려면 `--overwrite`를 지정하세요.
`--overwrite`는 MP3와 TXT에 적용되며 MP4 다운로드는 기존 파일을 덮어쓰지 않습니다.
모델, 언어, 정밀도, VAD 등 전사 옵션은 `transcribe`와 동일합니다.

각 명령의 전체 옵션은 `uv run download --help`, `uv run to-mp3 --help`,
`uv run transcribe --help`, `uv run pipeline --help`로 확인합니다.
