# VASS — 음성 비서 소프트웨어

## VASS란 무엇인가

VASS는 Windows, macOS, Linux용 음성 비서입니다. 음성 명령에 응답하고, 스크립트를 실행하며, 이벤트와 알림을 관리하고, OpenAI 호환 API를 통해 로컬 또는 원격 AI와 상호작용합니다.

**기본 웨이크워드:** "Erika"

**주요 기능:**
- 적응형 노이즈 플로어가 있는 Whisper(faster-whisper) 음성 인식
- 4단계 폴백 체인이 있는 Kokoro TTS 자연 음성 합성
- 로컬 또는 원격 AI(llama.cpp, OpenAI, 호환 서버)
- 25개 이상의 내장 함수가 있는 VASScript 데스크톱 자동화
- GUI 편집기가 있는 이벤트 및 일정 관리
- 다국어 음성 타이머(5개 동시)
- AI 오케스트레이션을 위한 21개 도구의 MCP 서버
- 자동 분류 및 요약이 있는 영구 메모리
- 메시지별 작업이 있는 대화 기록 뷰어
- 9개 언어 지원
- 컨텍스트 오버플로우 보호
- 오디오 장치 선택(입력/출력)
- 복잡한 AI 작업을 위한 멀티턴 도구 호출


---

## 요구 사항

- **Python 3.13** 이상
- **AI 서버** (llama.cpp 또는 OpenAI 호환)가 시스템에 이미 설치 및 구성되어 있어야 합니다. VASS는 설정된 경우 llama.cpp를 자동으로 시작할 수 있지만, **llama.cpp를 설치하거나 AI 모델을 다운로드하지 않습니다**: 별도로 준비해야 합니다.
- **인터넷 연결** (모델 다운로드 및 원격 AI용)
- 로컬 AI용 **NVIDIA GPU 권장** (CPU 가능하지만 느림)
- 작동하는 **마이크**
- Windows 10+, macOS 12+ 또는 최신 Linux

---

## 설치

### 그래픽 설치 (권장)

[Releases 페이지](https://github.com/logicheneurali/vass/releases)에서 설치 프로그램을 다운로드하여 실행하세요. 마법사가 Python, VASS, llama.cpp, AI 모델을 자동으로 설치합니다.

### 안내 설치

프로젝트를 다운로드 또는 클론한 후 폴더에 들어가서 스크립트를 실행합니다:

```bash
cd vass
python install.py
```

> **참고:** 안내식 설치는 VASS를 설정하지만 **AI 서버나 모델을 설치하지 않습니다**.
> OpenAI 호환 서버가 이미 실행 중이어야 합니다 (llama.cpp, Ollama, LM Studio, Groq, OpenAI 등)
> 또는 VASS 설정에서 llama.cpp를 구성하세요 (자동 시작 가능).

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

웨이크워드는 사용자가 `settings.ini` 파일에서 **설정 가능**하며, 어떤 단어나 짧은 문구든 사용할 수 있습니다. 기본값은 "**Erika**"입니다.

VASS가 웨이크워드를 감지하면 신호음을 울려 명령을 받을 준비가 되었음을 알립니다. 신호음 후에 말하세요.

예시:
- *"Erika"* (신호음 대기), 그다음 *"날씨 어때"*
- *"Erika"* (신호음 대기), 그다음 *"뉴스 읽어줘"*
- *"Erika"* (신호음 대기), 그다음 *"인공지능 뭐야"*
- *"Erika"* (신호음 대기), 그다음 *"여러분 좋은 아침입니다을 영어로 번역해줘"*
- *"Erika"* (신호음 대기), 그다음 *"까르보나라 만드는 법"*

### 모드: 채팅과 필사

VASS는 두 가지 모드로 작동하며, 팝업 메뉴(메인 버튼 오른쪽의 ≡ 버튼)에서 선택할 수 있습니다:

- **채팅** `[C]` — 애플리케이션이 음성 명령을 인식하고 작업(스크립트, 시스템 명령)을 실행하거나 AI와 상호작용합니다. 응답은 TTS로 읽어줍니다.
- **필사** `[T]` — 명령을 해석하는 대신, VASS는 웨이크워드 이후(항상 신호음 후) 사용자가 말한 내용을 충실히 필사합니다. 텍스트는 활성 애플리케이션에 붙여넣어져, VASS를 텍스트 받아쓰기 시스템으로 사용할 수 있습니다.

현재 모드는 메인 버튼에 표시됩니다: 채팅은 `[C]`, 필사는 `[T]`. 마지막으로 사용한 모드는 재시작 시 복원됩니다.

### 메모리 모드

GUI 메뉴에서 또는 메인 버튼을 클릭하여:
- **Full** — AI가 메모리 요약을 받습니다
- **Limited** — AI가 최근 기록만 받습니다
- **None** — 기록 컨텍스트 없음

### 음성 명령

명령은 표준 INI 형식으로 `commands.ini`에 구성하며, GUI 편집기(`python commands_editor.py`)로도 편집할 수 있습니다. 각 줄은 **문구 = 동작** 쌍입니다: 문구는 인식할 패턴(`{변수}` 포함 가능), 동작은 실행할 내용입니다.

```ini
[general]
{키워드} 검색 = script:검색
{프로그램} 열기 = start {프로그램}
온라인 검색 {escaped_terms} = start firefox "https://duckduckgo.com?q={escaped_terms}"
지금 몇 시야 = script:시간

[system]
시스템 종료 = shutdown /s /t 60
화면 잠금 = rundll32.exe user32.dll,LockWorkStation
```

#### 매칭 작동 방식

1. **퍼지 인식**: 정확한 일치가 필요하지 않습니다. VASS는 발화된 문구를 모든 패턴과 유사도 알고리즘(`difflib`)으로 비교합니다. 임계값(기본값 `0.75`, `settings.ini`에서 설정 가능)을 초과하는 가장 높은 점수의 패턴이 활성화됩니다.

2. **변수 `{이름}`**: 해당 위치에서 발화된 단어를 캡처합니다. 예: *"인터넷에서 고양이 검색"*이라고 말하면 시스템은 `키워드 = "인터넷에서 고양이 검색"`을 캡처합니다.

3. **이스케이프 변수 `{escaped_이름}`**: 일반 변수와 동일하지만 캡처된 텍스트가 URL 인코딩됩니다(공백이 `%20`으로 변환). 웹 검색에 유용합니다.

4. **AI 폴백**: 어떤 명령도 유사도 임계값을 초과하지 못하면, 문구가 자연어 응답을 위해 AI로 전송됩니다.

#### 쉼표 대안 (데카르트 곱)

쉼표를 사용하여 각 위치에 여러 대안을 지정할 수 있습니다. **공백**은 위치를 구분하고, **쉼표**는 위치 내 대안을 구분합니다. VASS는 가능한 모든 조합(데카르트 곱)을 생성합니다.

```ini
# 단일 위치: 전치사 대안
click the,on text {text}
```
3개 패턴 생성: `click the text {text}`, `click on text {text}`, `click text {text}`.

```ini
# 두 위치: 각 위치에 고유한 대안
aa,xx bb,cc {var}
```
4개 패턴 생성: `aa bb {var}`, `aa cc {var}`, `xx bb {var}`, `xx cc {var}` (2x2 = 4).

```ini
# 혼합: 고정 단어 + 대안
turn on,off {device}
```
2개 패턴 생성: `turn on {device}`, `turn off {device}` (`on`과 `off` 사이에 공백 없음 → 같은 위치).

음성 문구는 생성된 모든 패턴과 비교됩니다. 최상의 퍼지 매치가 승리합니다.

#### 동작 유형

| 접두사 | 예시 | 동작 |
|--------|------|------|
| `script:` | `script:검색` | `scripts/검색.vass` 실행. 캡처된 변수는 `$param1`, `$param2` 등이 됩니다 |
| `vasscript:` | `vasscript:이벤트` | `script:`와 동일 (대체 접두사) |
| URL | `https://...` | 기본 브라우저에서 열림 |
| 명령어 | `shutdown /s` | 시스템 명령으로 직접 실행 |

#### 섹션 이름

`[general]` 및 `[system]`과 같은 섹션 이름은 단순한 정리용 카테고리일 뿐 매칭에 영향을 주지 않습니다. 중요한 것은 **키**(인식할 문구)입니다.

### VASScript 스크립트 만들기

GUI 메뉴에서 스크립트 편집기를 열거나 다음을 실행하세요:
```bash
python scripts_editor.py
```

모든 스크립트는 `.vass` 확장자로 `scripts/` 폴더에 저장됩니다.

**권한 부여**: 새 스크립트나 수정된 스크립트를 실행하기 전에 VASS가 권한을 요청하는 팝업을 표시합니다. 스크립트는 SHA-256 해시로 검증되며, 권한 부여 후 스크립트 파일이 수정되면 권한이 자동으로 취소되고 다음 실행 시 팝업이 다시 나타납니다. 이를 통해 명시적 동의 없이는 어떤 스크립트도 컴퓨터에서 실행될 수 없습니다.

전체 언어 참조는 [VASCRIPT_REFERENCE.md](../Allowed_root/VASCRIPT_REFERENCE.md) 파일을 참조하세요.

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

> **중요:** 이 애플리케이션은 사용되는 AI 모델에 크게 의존합니다. 비효과적인 모델이나 MCP 도구 사용에 적합하지 않은 모델은 기능을 저하시킬 수 있습니다.

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
