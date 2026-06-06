# VASS — 지능형 음성 비서

## VASS란 무엇인가

VASS는 Windows, macOS, Linux용 음성 비서입니다. 음성 명령에 응답하고, 스크립트를 실행하며, 이벤트와 알림을 관리하고, OpenAI 호환 API를 통해 로컬 또는 원격 AI와 상호작용합니다.

**기본 웨이크워드:** "Erika"

**주요 기능:**
- Whisper(faster-whisper)를 통한 음성 인식
- Kokoro TTS를 통한 자연스러운 음성 합성
- 로컬 또는 원격 AI (llama.cpp, OpenAI, 호환 서버)
- 데스크톱 자동화를 위한 VASScript 스크립팅
- 이벤트 및 알림 관리
- AI 오케스트레이션을 위한 15개 도구가 포함된 MCP 서버
- 대화 기록
- 9개 언어 지원 (이탈리아어, 영어, 독일어, 프랑스어, 스페인어, 포르투갈어, 일본어, 한국어, 중국어)

---

## 요구 사항

- **Python 3.13** 이상
- **인터넷 연결** (모델 다운로드 및 원격 AI용)
- 로컬 AI용 **NVIDIA GPU 권장** (CPU 가능하지만 느림)
- 작동하는 **마이크**
- Windows 10+, macOS 12+ 또는 최신 Linux

---

## 설치

### 안내 설치

프로젝트를 다운로드 또는 클론한 후 폴더에 들어가서 스크립트를 실행합니다:

```bash
cd vass
python install.py
```

**참고:** 안내식 설치는 아직 실험적이며 모든 시스템에서 작동하지 않을 수 있습니다. 문제가 발생하면 아래 수동 설치를 사용하세요.

마법사가 다음을 안내합니다:
1. 언어 선택
2. 사전 요구 사항 확인 (Python 3.13+, pip)
3. 대상 폴더
4. 매개변수 구성 (AI URL, 모델, 웨이크워드)
5. 파일 복사
6. Python 가상 환경 생성 (.venv)
7. pip 종속성 설치
8. settings.ini 파일 생성
9. 런처 생성

### 수동 설치

```bash
# 원하는 폴더에 파일 복제 또는 복사
cd VASS

# 가상 환경 생성
python -m venv .venv

# 활성화 (Windows)
.venv\Scripts\activate
# 또는 (macOS/Linux)
source .venv/bin/activate

# 종속성 설치
pip install -r requirements.txt

# Playwright용 Chromium 설치 (웹 검색)
playwright install chromium

# settings.ini 생성 (예제 settings.ini에서 복사)
```

---

## 구성

`settings.ini` 파일에 모든 설정이 포함됩니다. 가장 중요한 항목은 다음과 같습니다:

| 섹션 | 매개변수 | 설명 |
|---------|-----------|-------------|
| `[locale]` | `language` | 언어 (it/en/de/fr/es/pt/ja/ko/zh) |
| `[ai]` | `url` | OpenAI 호환 AI 서버 URL |
| `[ai]` | `model` | AI 모델 이름 |
| `[ai]` | `system_message` | 비서 성격 |
| `[ai]` | `memory_tokens` | 최대 메모리 크기 |
| `[wakeword]` | `wakeword` | 웨이크워드 (기본값: erika) |
| `[wakeword]` | `sensitivity` | 감지 감도 (0-1) |
| `[tts]` | `volume` | TTS 볼륨 (0-1) |

VASS 실행 중 설정이 수정되면 자동으로 다시 로드됩니다.

---

## 일상 사용

### 시작

`vass.bat` (Windows) 또는 `vass.sh`/`vass.command` (macOS/Linux)를 더블 클릭하세요.

또는 터미널에서:
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

### 웨이크워드

"**Erika**"라고 말한 다음 명령을 말하세요. VASS가 확인음을 울립니다.

예시:
- *"Erika, 지금 몇 시야?"*
- *"Erika, 최신 뉴스 검색해 줘"*
- *"Erika, 내일 오후 2시 회의 알림 설정해 줘"*

### 메모리 모드

GUI 메뉴에서 또는 메인 버튼을 클릭하여:
- **Full** — AI가 메모리 요약을 받습니다
- **Limited** — AI가 최근 기록만 받습니다
- **None** — 기록 컨텍스트 없음

### 음성 명령

명령은 표준 INI 형식으로 `commands.ini`에 구성합니다. 키는 인식할 문구이고 값은 동작입니다:

```ini
[general]
{키워드} 검색 = script:검색
{프로그램} 열기 = start {프로그램}
최신 뉴스 = script:뉴스
지금 몇 시야 = script:시간

[system]
시스템 종료 = shutdown /s /t 60
화면 잠금 = rundll32.exe user32.dll,LockWorkStation
```

- `{키워드}`, `{프로그램}` — 음성에서 캡처된 변수
- `script:스크립트이름` — `scripts/스크립트이름.vass` 실행
- 대체 접두사: `vasscript:`

패턴에 변수가 있으면 해당 값이 `$param1`, `$param2` 등으로 스크립트에 전달됩니다.

### VASScript 스크립트 만들기

GUI 메뉴에서 스크립트 편집기를 열거나 다음을 실행하세요:
```bash
python scripts_editor.py
```

모든 스크립트는 `.vass` 확장자로 `scripts/` 폴더에 저장됩니다.

전체 언어 참조는 `VASCRIPT_REFERENCE.md` 파일을 참조하세요.

### 이벤트 및 알림

이벤트는 `events.json` 파일을 통해 관리됩니다. 음성 알림이 1시간 전에(구성 가능) 발행됩니다.

스케줄(자동 절차)은 `schedule.json`에 있으며 TTS 알림과 함께 명령 실행을 트리거합니다.

---

## GUI 인터페이스

- **메인 버튼** — 클릭하여 상태 변경(listening/paused). 마우스 휠로 볼륨 조절. 드래그하여 창 이동.
- **볼륨 바** (녹색, 상단) — 현재 TTS 볼륨 표시
- **다중 상태 바** — 컨텍스트에 따라 메모리 사용량, 볼륨 또는 스크립트 진행률 표시
- **자동 페이드** — 비활성 상태이고 전체 화면일 때 창이 반투명해집니다

### 단축키

| 키 | 동작 |
|-------|--------|
| `Ctrl+S` | 저장 (편집기에서) |
| 버튼 클릭 | 상태 변경 |
| 버튼 위에서 휠 | 볼륨 조절 |
| 오른쪽 클릭 | 컨텍스트 메뉴 |
| 스크립트의 "읽기" 버튼 | TTS로 스크립트 읽기 |

---

## 문제 해결

### VASS가 시작되지 않음
- Python 3.13+ 확인: `python --version`
- `.venv`가 존재하고 종속성이 포함되어 있는지 확인
- `debug.log`에서 오류 확인

### 마이크가 작동하지 않음
- 마이크가 연결되어 있고 다른 앱에서 사용 중이 아닌지 확인
- 마이크에 대한 시스템 권한 확인
- Windows의 경우: 설정 → 개인정보 → 마이크

### AI가 응답하지 않음
- AI 서버가 `http://127.0.0.1:8080/v1`에서 실행 중인지 확인
- `settings.ini`의 `[ai] url` 확인
- llama.cpp를 사용하는 경우 모델이 `models/` 폴더에 있는지 확인

### OCR이 화면의 텍스트를 인식하지 못함
- 화면의 글꼴 크기나 대비를 높이세요
- EasyOCR은 큰 글꼴과 높은 대비에서 가장 잘 작동합니다
- OCR 언어는 구성된 로케일에 자동으로 적응합니다

---

## 중요 파일

| 파일 | 설명 |
|------|-------------|
| `settings.ini` | 기본 구성 |
| `commands.ini` | 사용자 정의 음성 명령 |
| `scripts/*.vass` | 나의 VASScript 스크립트 |
| `events.json` | 나의 이벤트 및 알림 |
| `schedule.json` | 자동 절차 |
| `memory.json` | 대화 기록 |
| `debug.log` | 디버그 로그 |
| `vass.log` | 애플리케이션 로그 |
