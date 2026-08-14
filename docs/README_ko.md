# VASS — 음성 비서 소프트웨어

## VASS란 무엇인가

VASS는 Windows, macOS, Linux용 음성 비서입니다. 음성 명령에 응답하고, 스크립트를 실행하며, 이벤트와 알림을 관리하고, 이메일을 읽고 답장하며, OpenAI 호환 API를 통해 로컬 또는 원격 AI와 상호작용합니다. 또한 MCP 서버를 호스팅하여 AI가 파일, 브라우저, 캘린더, 이메일, 뉴스, 시스템 도구에 직접 접근할 수 있게 해줍니다.

**기본 웨이크 워드:** "Erika" (변경 가능)

**현재 버전:** 0.8.7

**주요 기능:**
- Silero VAD와 적응형 노이즈 플로어를 갖춘 Whisper(faster-whisper) 기반 음성 인식
- 다단계 폴백 체인을 갖춘 Kokoro TTS 기반 자연스러운 음성 합성
- 로컬 또는 원격 AI(llama.cpp, OpenAI, 모든 호환 서버)와 선택적 llama.cpp 자동 시작 지원
- 70개 이상의 내장 함수를 갖춘 데스크톱 자동화용 VASScript 스크립팅
- 편집기 GUI를 통한 이벤트 및 일정 관리(알림, 자동화 절차)
- 다국어 카운트다운 타이머(음성 활성화, 동시 5개)
- AI 오케스트레이션을 위한 50개 이상의 도구를 갖춘 MCP 서버(브라우저, 메일, 뉴스, 캘린더, 장소, 파일, 시스템)
- 자동 분류, 요약, 사용자 프로필 주입을 갖춘 영구 메모리
- 통합 이메일 클라이언트: 큐, 연락처, AI 발신 이메일을 지원하는 Gmail, IMAP, POP3
- 플러그인 시스템: 로컬 TCP 소켓을 통한 내부 및 외부 플러그인
- 이벤트 유형별 라우팅을 갖춘 알림 센터
- 메시지별 작업을 지원하는 대화 기록 뷰어
- 9개 언어 지원
- 컨텍스트 오버플로 보호(`truncate` 또는 AI 요약)
- 오디오 장치 선택(입력/출력)
- 복잡한 AI 작업을 위한 다중 턴 도구 호출
- 20만 개 도시 지리 위치 데이터베이스를 갖춘 3소스 날씨 시스템
- 시간 지연 음성 명령("5분 후 종료")
- GUI의 실시간 MCP 도구 활동 표시기
- 다국어 불용어 지원을 갖춘 휴리스틱 컨텍스트 압축
- 토큰 정확도 컨텍스트 계산(tiktoken)
- SHA-256 인증 및 감사 로깅을 갖춘 스크립트 실행 샌드박스
- 민감한 온라인 도구를 위한 보안 게이트(동의, 속도 제한, 감사 로그)
- 선택적 OS 자동 시작

---

## 시스템 요구 사항

- **Python 3.13** 이상
- **AI 서버**(llama.cpp 또는 OpenAI 호환)가 시스템에 이미 설치 및 구성되어 있어야 합니다. VASS는 구성된 경우 llama.cpp를 자동 시작할 수 있지만, llama.cpp를 설치하거나 AI 모델을 다운로드하지는 **않습니다**: 별도로 직접 준비해야 합니다.
- **인터넷 연결**(TTS/STT 모델 다운로드 및 원격 AI용)
- 로컬 AI에는 **NVIDIA GPU 권장**(CPU 가능하지만 느림)
- **작동하는 마이크**
- Windows 10+, macOS 12+, 또는 최신 Linux

---

## 설치

### 그래픽 설치(권장)

[Releases 페이지](https://github.com/logicheneurali/vass/releases)에서 설치 프로그램을 다운로드하여 실행하세요. 마법사가 Python, VASS, llama.cpp, AI 모델을 자동으로 설치합니다 — 수동 설정이 필요 없습니다.

### 안내형 설치

프로젝트를 다운로드하거나 클론한 후 폴더에 들어가 스크립트를 실행하세요:

```bash
cd vass
python install.py
```

> **참고:** 안내형 설치는 VASS를 설정하지만 AI 서버나 모델을 **설치하지 않습니다**.
> 이미 실행 중인 OpenAI 호환 서버(llama.cpp, Ollama, LM Studio, Groq, OpenAI 등)가 있어야 합니다.
> 또는 VASS 설정에서 llama.cpp를 구성할 수 있습니다(자동 시작 가능).

**참고:** 안내형 설치 절차는 아직 실험적이며 모든 시스템에서 작동하지 않을 수 있습니다. 문제가 발생하면 아래의 수동 설치 절차를 사용하세요.

마법사가 다음 단계를 안내합니다:
1. 언어 선택
2. 사전 요구 사항 확인(Python 3.13+, pip)
3. 대상 폴더
4. 파라미터 구성(AI URL, 모델, 웨이크 워드)
5. 파일 복사
6. Python 가상 환경 생성(.venv)
7. Pip 종속성 설치
8. settings.ini 파일 생성
9. 실행기 생성

### 수동 설치

```bash
# Clone or copy files to the desired folder
cd VASS

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate
# or (macOS/Linux)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Chromium for Playwright (web searches)
playwright install chromium

# Create config/settings.ini (copy from config/settings.example.ini)
```

---

## 설정

모든 설정은 `config/settings.ini`에 있습니다(템플릿은 `config/settings.example.ini`). 가장 중요한 설정은 다음과 같습니다:

| 섹션 | 파라미터 | 설명 |
|---------|-----------|-------------|
| `[locale]` | `language` | 언어(it/en/de/fr/es/pt/ja/ko/zh) |
| `[wakeword]` | `wakeword` | 웨이크 워드(기본값: erika) |
| `[wakeword]` | `sensitivity` | 웨이크 워드 감지 민감도 |
| `[commands]` | `similarity` | 음성 명령 퍼지 일치 임계값(기본값 0.6) |
| `[commands]` | `word_learning_enabled` | 시간이 지나면서 새로운 음성 단어 학습(true/false) |
| `[ai]` | `url` | OpenAI 호환 AI 서버 URL |
| `[ai]` | `model` | AI 모델 이름 |
| `[ai]` | `system_message` | 어시스턴트 성격 |
| `[ai]` | `api_key` | API 키(설정 시 시스템 키링에 저장) |
| `[ai]` | `mcp_server_url` | 번들 MCP 서버의 URL(기본값 `http://localhost:9988`) |
| `[ai]` | `memory_tokens` | 최대 메모리 크기 |
| `[ai]` | `context_length` | 최대 컨텍스트 토큰(0 = 자동) |
| `[ai]` | `overflow_strategy` | 컨텍스트 오버플로 처리: `truncate` 또는 `summarize` |
| `[ai]` | `allow_ai_scripts` | AI가 VASScript 스크립트를 실행하도록 허용(true/false) |
| `[llamacpp]` | `llama_server_path` | llama.cpp 서버 위치 |
| `[llamacpp]` | `llama_autostart` | VASS와 함께 llama.cpp 자동 시작(true/false) |
| `[resources]` | `cpu_max`, `ram_max`, `gpu_max`, `vram_max` | AI 작업을 제한하는 리소스 한도 |
| `[events]` | `reminder_advance` | 이벤트 전 알림이 발행되는 초(기본값 3600) |
| `[audio]` | `input_device`, `output_device` | 오디오 장치 선택(-1 = 시스템 기본값) |
| `[audio]` | `input_volume`, `output_volume` | 입력/출력 볼륨 레벨(0-1) |
| `[audio]` | `app_volume` | 마스터 TTS 볼륨(기존 `[tts] volume` 대체) |
| `[google]` | — | Google Calendar / Gmail / Google Home 통합 |
| `[startup]` | `app_autostart` | 로그인 시 VASS 자동 시작(true/false) |
| `[debug]` | `debug_enabled` | `log/debug.log`에 상세 로그 기록(true/false) |

VASS 실행 중 설정이 수정되면 자동으로 다시 로드됩니다.

---

## 일상 사용법

### 시작하기

`vass.bat`(Windows) 또는 `vass.sh`/`vass.command`(macOS/Linux)를 더블클릭하세요.

또는 터미널에서:
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

> **참고:** 첫 실행 시 음성 인식(Whisper)과 음성 합성(Kokoro) 모델이 HuggingFace에서 자동으로 다운로드됩니다. 첫 시작은 몇 분이 걸릴 수 있습니다(~2-4GB 다운로드). 이는 한 번만 발생합니다.

### 웨이크 워드

웨이크 워드는 `config/settings.ini` 파일에서 사용자가 **변경할 수** 있으며 어떤 단어나 짧은 문구도 될 수 있습니다. 기본값은 "**Erika**"입니다.

VASS가 웨이크 워드를 감지하면 명령을 받을 준비가 되었음을 알리는 비프음이 울립니다. 비프음 후에 말하세요.

예시:
- *"Erika"*(비프음 대기), 이어서 *"오늘 날씨는 어때?"*
- *"Erika"*(비프음 대기), 이어서 *"최신 뉴스를 읽어줘"*
- *"Erika"*(비프음 대기), 이어서 *"인공지능이 뭐야?"*
- *"Erika"*(비프음 대기), 이어서 *"모두에게 좋은 아침을 이탈리아어로 번역해줘"*
- *"Erika"*(비프음 대기), 이어서 *"파스타 카르보나라 레시피"*

### 모드: 채팅 및 받아쓰기

VASS는 팝업 메뉴(메인 버튼 오른쪽의 ≡ 버튼)에서 선택할 수 있는 두 가지 모드로 작동합니다:

- **채팅** `[C]` — 앱이 음성 명령을 인식하여 작업(스크립트, 시스템 명령)을 수행하거나 AI와 상호작용합니다. 응답은 TTS로 읽어줍니다.
- **받아쓰기** `[T]` — 명령을 해석하는 대신 VASS가 웨이크 워드(항상 비프음 이후) 후 사용자가 말한 내용을 그대로 받아쓰기합니다. 텍스트는 활성 애플리케이션에 붙여넣어져 VASS가 텍스트 받아쓰기 시스템이 됩니다.

현재 모드는 메인 버튼에 표시됩니다: 채팅은 `[C]`, 받아쓰기는 `[T]`. 마지막으로 사용한 모드는 재시작 시 복원됩니다.

### 메모리 모드

GUI 메뉴 또는 메인 버튼 클릭으로 선택할 수 있습니다:
- **전체** — AI가 메모리 요약과 사용자 프로필을 받습니다
- **제한** — AI가 최근 대화 기록만 받습니다
- **없음** — 과거 컨텍스트 없음

### 음성 명령

명령은 `config/commands.ini`(표준 INI 형식, **phrase = action**)에 구성되며, GUI 편집기(`python src/commands_editor.py`)에서도 편집할 수 있습니다. 언어별 파일 `config/commands_{lang}.ini`는 기본 파일 위에 로드됩니다. 각 줄은 **phrase = action** 쌍입니다: phrase는 인식할 패턴(`{variables}` 포함 가능)이고, action은 실행할 작업입니다.

```ini
[general]
search {term} = script:search
open {program} = start {program}
search online {escaped_terms} = start firefox "https://duckduckgo.com?q={escaped_terms}"
what time is it = script:datetime

[system]
shutdown system = shutdown /s /t 60
lock screen = rundll32.exe user32.dll,LockWorkStation
```

#### 일치 방식

1. **퍼지 인식**: 정확히 일치할 필요는 없습니다. VASS는 유사도 알고리즘(`difflib`)을 사용하여 음성 문구를 모든 패턴과 비교합니다. 임계값(기본 `0.6`, `config/settings.ini`의 `[commands] similarity`에서 설정 가능)을 초과하면서 가장 높은 점수를 얻은 패턴이 활성화됩니다.

2. **변수 `{name}`**: 해당 위치의 음성 단어를 캡처합니다. 예: *"인터넷에서 고양이를 검색해줘"*라고 말하면 `term = "cats on the internet"`이 캡처됩니다.

3. **이스케이프 변수 `{escaped_name}`**: 일반 변수와 동일하지만 캡처된 텍스트가 URL 인코딩됩니다(공백은 `%20`이 됨). 웹 검색에 유용합니다.

4. **시간 지연 명령**: `{duration}` 접미어(예: *"5분 후 종료"*)를 사용하면 타이머 시스템을 통해 지정된 시간 후에 명령이 실행되도록 예약됩니다.

5. **단어 학습**: 활성화되면 VASS가 단어 발음 방식을 기록하여 시간이 지나면서 인식을 개선합니다.

6. **AI 폴백**: 유사도 임계값을 초과하는 명령이 없으면 문구가 자연어 응답을 위해 AI로 전송됩니다.

#### 쉼표 대안(데카르트 곱)

각 단어 위치에 대해 쉼표를 사용하여 여러 대안을 지정할 수 있습니다. **공백**은 단어 위치를 구분하고, **쉼표**는 한 위치 내의 대안을 구분합니다. VASS는 가능한 모든 조합(데카르트 곱)을 생성합니다.

```ini
# Single position: alternatives for the preposition
click the,on text {text}
```
2개의 패턴을 생성합니다: `click the text {text}`, `click on text {text}`.

```ini
# Two positions: each position has its own alternatives
aa,xx bb,cc {var}
```
4개의 패턴을 생성합니다: `aa bb {var}`, `aa cc {var}`, `xx bb {var}`, `xx cc {var}`(2x2 = 4).

```ini
# Mixed: fixed word + alternatives
turn on,off {device}
```
2개의 패턴을 생성합니다: `turn on {device}`, `turn off {device}`(`on`과 `off` 사이에 공백이 없으므로 같은 위치입니다).

음성 문구는 생성된 모든 패턴과 비교됩니다. 가장 좋은 퍼지 일치가 선택됩니다.

#### 동작 유형

| 접두어 | 예시 | 동작 |
|--------|---------|----------|
| `script:` | `script:search` | `scripts/search.vass`를 실행합니다. 캡처된 변수는 `$param1`, `$param2` 등이 됩니다. |
| `vasscript:` | `vasscript:events` | `script:`와 동일합니다(대체 접두어) |
| 명령 | `shutdown /s` | 시스템 명령으로 직접 실행됩니다 |

#### 섹션 이름

`[general]`, `[system]`과 같은 섹션 이름은 단지 조직적인 범주일 뿐이며 일치에 영향을 주지 않습니다. 중요한 것은 **키**(인식할 문구)입니다.

### VASScript 스크립트 만들기

GUI 메뉴에서 스크립트 편집기를 열거나 다음을 실행하세요:
```bash
python src/scripts_editor.py
```

모든 스크립트는 `scripts/` 폴더에 `.vass` 확장자로 저장됩니다.

**인증**: 새 스크립트나 수정된 스크립트를 실행하기 전에 VASS가 권한을 묻는 팝업을 표시합니다. 스크립트는 SHA-256 해시(시스템 키링에 저장)로 검증됩니다: 인증 후 스크립트 파일이 수정되면 권한이 자동으로 취소되고 다음 실행 시 팝업이 다시 나타납니다. 권한은 함수별로 또는 스크립트 전체에 대해 부여할 수 있습니다. 이는 명시적인 동의 없이는 어떤 스크립트도 사용자 컴퓨터에서 실행될 수 없도록 보장합니다.

전체 언어 레퍼런스는 [VASCRIPT_REFERENCE.md](../Allowed_root/VASCRIPT_REFERENCE.md) 파일을 참조하세요.

### 이벤트 및 알림

이벤트는 `Allowed_root/events.json` 파일로 관리됩니다. 음성 알림은 1시간 전에 발행됩니다(`[events] reminder_advance`로 설정 가능).

일정(자동화 절차)은 `Allowed_root/schedules.json`에 있으며 TTS 알림과 함께 명령 실행을 트리거합니다. 추가 플래그: `silent`, `run_on_startup`, `check_already_running`, `wait_for_completion`.

### 플러그인 시스템

VASS는 플러그인이 앱과 통신하는 데 사용하는 로컬 TCP 서버(`localhost:8765`)를 제공합니다: TTS, 알림, AI 쿼리, RSS 항목, 채팅, 선언적 UI 등. **내부 플러그인**(VASS에 번들됨)은 제거할 수 없으며, **외부 플러그인**은 GUI(플러그인 메뉴)에서 활성화, 비활성화, 제거할 수 있습니다.

번들 내부 플러그인: 노이즈 자동 일시정지, 능동형 에이전트, 사용자 프로필, RSS 리더, 세계 이벤트, Telegram 봇. 디스크에 있는 외부 플러그인: 이미지 생성기, 뉴스 발행기, 타임라인 뷰어.

전체 프로토콜과 나만의 플러그인을 만드는 방법은 [PLUGIN_DEV_ko.md](PLUGIN_DEV_ko.md) 가이드를 참조하세요(다른 언어로도 제공: `PLUGIN_DEV_{en,it,de,fr,es,pt,ja,zh}.md`).

### 이메일

설정 → 메일에서 하나 이상의 계정을 구성하세요(OAuth를 통한 Gmail, 또는 일반 SSL/TLS를 사용한 IMAP/POP3). 수신 메시지는 감지되어 알림이 전달됩니다. AI는 이메일을 검색, 읽기, 답장, 전달, 보내기를 할 수 있지만, 보낸 이메일은 항상 **큐**에 넣어지며 보낸편지함에서 승인하고 보내야 합니다. 연락처는 암호화되어 저장됩니다.

---

## GUI 인터페이스

- **메인 버튼** — 클릭하여 상태 변경(듣기/일시정지). 마우스 휠로 볼륨 조절. 드래그하여 창 이동.
- **볼륨 바**(상단, 녹색) — 현재 TTS 볼륨 표시
- **다중 상태 바** — 상황에 따라 메모리 사용량, 볼륨, 스크립트/활동 진행 상황을 표시
- **알림 센터**(벨) — 메시지 작업과 모두 읽음 기능이 있는 유형별 탭
- **도구 표시기** — AI가 사용 중인 MCP 도구를 보여주는 실시간 아이콘
- **마이크 버튼** — 채팅 모드에서 직접 음성 입력
- **플러그인 메뉴** — 플러그인, 플러그인 설정, 플러그인 UI 관리
- **설정 대화상자** — GUI에서 전체 구성(설정 메뉴)
- **자동 페이드** — 유휴 상태 및 전체 화면에서 창이 반투명해집니다
- **스플래시 화면** — 시작 시 로딩 진행률 표시
- **테마** — 앱과 모든 편집기에서 공유되는 테마

### 단축키

| 키 | 동작 |
|-------|--------|
| `Ctrl+S` | 저장(편집기에서) |
| 버튼 클릭 | 상태 변경 |
| 버튼 위 휠 | 볼륨 조절 |
| 우클릭 | 컨텍스트 메뉴 |
| 버튼 중간 클릭 | 종료 |

---

## 문제 해결

> **중요:** 이 애플리케이션은 사용하는 AI 모델에 크게 의존합니다. 효과가 없는 모델이나 MCP 도구 사용에 적합하지 않은 모델은 기능을 손상시킬 수 있습니다.

### VASS가 시작되지 않는 경우
- Python 3.13+ 확인: `python --version`
- `.venv`가 존재하고 종속성을 포함하는지 확인
- `log/debug.log`(`[debug] debug_enabled = true` 활성화) 및 `log/crash.log` 확인

### 마이크가 작동하지 않는 경우
- 마이크가 연결되어 있고 다른 앱에서 사용 중이 아닌지 확인
- 마이크에 대한 시스템 권한 확인
- Windows: 설정 → 개인정보 → 마이크

### AI가 응답하지 않는 경우
- AI 서버가 `http://127.0.0.1:8080/v1`에서 실행 중인지 확인
- `config/settings.ini`의 `[ai] url` 확인
- llama.cpp를 사용하는 경우 모델이 존재하고 `[llamacpp] llama_server_path`가 올바른지 확인
- llama.cpp 오류가 없는지 `log/llamacpp.log` 확인

### OCR이 화면 텍스트를 인식하지 못하는 경우
- 화면의 글꼴 크기 또는 텍스트 대비를 높이세요
- EasyOCR은 큰 글꼴과 높은 대비에서 가장 잘 작동합니다
- OCR 언어는 구성된 로케일에 자동으로 적응합니다

### AI가 도구를 사용할 수 없는 경우
- 일부 온라인 도구는 사용자 동의가 필요합니다(보안 게이트) — 보류 중인 요청이 있는지 InfoPanel을 확인하세요
- MCP 서버가 `http://localhost:9988`에서 접근 가능한지 확인(`[ai] mcp_server_url` 참조)
- MCP 오류가 없는지 `log/mcp_server.log` 확인

---

## 주요 파일

| 파일 | 설명 |
|------|-------------|
| `config/settings.ini` | 기본 설정 |
| `config/commands.ini` | 기본 음성 명령(`commands_{lang}.ini` 포함) |
| `config/notifications.ini` | 이벤트 유형별 알림 라우팅 |
| `scripts/*.vass` | 사용자의 VASScript 스크립트 |
| `Allowed_root/events.json` | 사용자의 이벤트 및 알림 |
| `Allowed_root/schedules.json` | 자동화 절차 |
| `Allowed_root/memory.json` | 대화 기록 및 메모리 |
| `Allowed_root/private_profile.json` | AI 컨텍스트에 주입되는 사용자 프로필 |
| `plugins/` | 내부 및 외부 플러그인 |
| `log/debug.log` | 상세 디버그 로그(활성화 시) |
| `log/crash.log` | 충돌 로그 |
| `log/faulthandler.log` | 폴트 핸들러 출력 |
| `log/llamacpp.log` | llama.cpp 서버 로그 |
