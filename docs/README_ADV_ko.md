# VASS — 고급 문서

## 전체 아키텍처

VASS는 파일 큐, Qt 신호 및 직접 호출을 통해 통신하는 여러 독립 구성 요소로 구성된 모듈식 애플리케이션입니다.

```
┌─────────────────────────────────────────────────┐
│                    vass.py                       │
│              메인 오케스트레이터                   │
│  - 구성 요소 초기화                               │
│  - 청취/쓰기 루프                                │
│  - AI 폴백 관리                                  │
│  - 스크립트 실행                                  │
│  - 파일 큐 감시                                  │
└──────┬──────┬──────┬──────┬──────┬──────────────┘
       │      │      │      │      │
       ▼      ▼      ▼      ▼      ▼
  ┌────────┐┌─────┐┌─────┐┌────┐┌──────────┐
  │  gui.py││TTS  ││STT  ││이벤││mcp_server│
  │  PySide││엔진 ││Whisp││알림││  15 도구 │
  └────────┘└─────┘└─────┘└────┘└──────────┘
```

### 주요 구성 요소

| 구성 요소 | 파일 | 책임 |
|-----------|------|---------------|
| 오케스트레이터 | `vass.py` (1313줄) | 초기화, 메인 루프, AI, 스크립트, 메모리 |
| GUI | `gui.py` (832줄) | PySide6 창, 바, 페이드, 하위 창 |
| TTS | `tts_engine.py` (138줄) | Kokoro TTS, 오디오 재생, 볼륨 |
| STT | `voice_recognition.py` (133줄) | faster-whisper, 웨이크워드 감지 |
| 인터프리터 | `script_engine.py` (761줄) | VASScript 파서, 평가기, 26개 함수 |
| 이벤트 | `event_reminder.py` (280줄) | 이벤트/스케줄 모니터, TTS 알림 |
| 명령 | `command_executor.py` (184줄) | 퍼지 패턴 매칭, 변수 추출 |
| MCP 서버 | `mcp_server/` | FastMCP 서버, 15개 도구, IP 기반 ACL |
| OCR | `script_engine.py:_preprocess_screen` | 전처리 포함 EasyOCR |
| 유휴 | `idle_tracker.py` (67줄) | 크로스 플랫폼 유휴 감지 |
| 리소스 | `resource_monitor.py` (52줄) | AI 요청 전 CPU/RAM/GPU/VRAM 게이트 |
| 로그 | `log_utils.py` (13줄) | 로그 파일 로테이션 |

---

## 오디오 파이프라인

```
마이크 ──► sounddevice (콜백) ──► 오디오 큐 ──► Whisper (전사)
                                                   │
                    ┌──────────────────────────────┤
                    ▼                              ▼
         "Erika" 감지?                    전체 전사
                    │                              │
                    ▼                              ▼
              확인음                      commands.ini 일치?
                    │                        │            │
                    ▼                        ▼            ▼
             명령 대기                     명령 발견    일치 없음
                    │                        │            │
                    ▼                        ▼            ▼
             전사                         액션 실행    AI 폴백
                    │
                    ▼
            Kokoro TTS ──► 스피커
```

### 오디오 구성 요소 세부 정보

- **입력**: 16000 Hz 모노 콜백이 있는 `sounddevice.InputStream`
- **VAD**: 무음 필터링용 webrtcvad
- **웨이크워드**: Whisper tiny 모델, 전사에서 "erika" 검색
- **전사**: 웨이크워드 확인 후 Whisper medium 모델 (구성 가능)
- **TTS**: Kokoro `KPipeline(lang_code='i')`, 음성 `if_sara`, UUID 파일명으로 WAV 생성
- **재생**: 동기화용 `_tts_done` 이벤트가 있는 `sounddevice.play()`

---

## VASScript — 스크립팅 언어

VASScript는 데스크톱 자동화를 위한 미니멀리스트 스크립팅 언어입니다. 줄 단위 실행, 산술 연산자 없음, 모든 것은 문자열입니다.

### 사용 가능한 함수 (총 26개)

#### AI 및 TTS
- `ai(prompt)` — AI에 질의하고 텍스트 반환
- `say(text, speed?)` — 음성 합성 (속도: 0.5-1.5)
- `listen(prompt?)` — 음성 녹음, 전사 반환

#### 시스템
- `run(command)` — PowerShell 실행, 출력 반환
- `wait(seconds)` — 실행 일시 중지
- `exit()` — 스크립트 종료
- `getdatetime()` — 현재 날짜/시간 "YYYY-MM-DD HH:MM"

#### 화면 (OCR)
- `screen_search(query)` — 화면에서 텍스트 검색, `$_sx`, `$_sy`, `$_sw`, `$_sh` 설정
- `screen_click(x?, y?)` — 좌표 클릭
- `screen_highlight(x, y, w?, h?, dur?)` — 영역 강조 표시

#### 창 및 키보드
- `setActiveWindow(name)` — 프로세스/제목으로 창 활성화
- `sendText(text)` — 사람과 같은 지연으로 텍스트 입력

#### 이벤트
- `addevent(date, time, duration, description, recur?)` — 이벤트 추가
- `listevents(until_date)` — 이벤트 목록 (JSON)
- `removeevent(name)` — 이벤트 제거 (퍼지 매치)
- `prettyevents(json)` — 이벤트를 읽기 쉬운 텍스트로 형식화

#### 메모리 및 클립보드
- `readinfo(id)` — 정보 파일 읽기
- `writeinfo(text)` — 정보 파일 쓰기, ID 반환
- `clipboardget()` — 클립보드 읽기
- `clipboardset(text)` — 클립보드 쓰기

#### 조건
- `ifcontains(var, substring, if_true, if_false?)` — 부분 문자열 포함 여부
- `ifempty(var, if_empty, if_notempty?)` — 비어 있는지 확인

#### 유틸리티
- `trim(text)` — 공백 제거
- `len(text)` — 문자열 길이
- `contains(text, substring)` — 포함? ("True"/"False")
- `equals(a, b)` — 같음? ("True"/"False")

### 변수

```vascript
$name = "Fabio"            # 할당
$age = "54"                # 모든 것은 문자열
$result = ai("안녕하세요")   # 함수 결과
say("안녕하세요 {$name}님!")  # 문자열 보간
say("당신은 {$age}세입니다")   # 변수도 마찬가지
```

**참고:** VASScript는 `+`를 사용한 연결을 지원하지 않습니다. 문자열에서 `{$var}`를 사용하세요.

### screen_search 전역 변수

`screen_search()`는 첫 번째 일치 항목에 대해 다음 전역 변수를 설정합니다:
- `$_sx`, `$_sy` — 중심 좌표
- `$_sw`, `$_sh` — 너비와 높이

---

## MCP 서버 — 15개 도구

MCP 서버는 `http://localhost:9988`에서 AI가 액세스할 수 있는 15개의 도구를 노출합니다.

### 파일 시스템
- `read_file(path)` — Allowed_root 내 파일 읽기
- `write_file(path, content)` — Allowed_root 내 파일 쓰기

### 웹
- `browse(url)` — 페이지 다운로드 (정적, httpx+BeautifulSoup)
- `websearch(query)` — Playwright를 통해 DuckDuckGo 검색
- `webfetch(url)` — Playwright를 통해 JS 렌더링 페이지 로드

### 계산 및 시간
- `calculate(expression)` — 수학 표현식 평가 (AST, 안전)
- `current_time()` — 현재 날짜/시간
- `disk_space()` — 사용 가능한 디스크 공간

### 실행
- `execute(command)` — 명령 실행 (화이트리스트)
- `script(script_name)` — VASScript 파일 실행
- `interact(code)` — 인라인 VASScript 실행

### 메모리 및 클립보드
- `readinfo(id)` — 정보 파일 읽기
- `writeinfo(text)` — 정보 파일 쓰기
- `clipboardget()` — 클립보드 읽기
- `clipboardset(text)` — 클립보드 쓰기

### 인증

`mcp_server/config/tools.yaml`을 통한 IP 기반 ACL. 각 도구에는 화이트리스트/블랙리스트가 있습니다. 기본값은 거부입니다.

### 스크립트 → VASS 통신

`script` 및 `interact` 도구는 파일 기반 IPC를 사용합니다:
1. 요청을 `scripts/exec_queue.json`에 작성
2. VASS가 큐를 읽음 (1초 폴링)
3. 스크립트 실행
4. 결과를 `scripts/exec_result.json`에 작성
5. MCP 클라이언트가 결과를 읽음

---

## 메모리 시스템

### 구조

```
Allowed_root/
  memory.json          # 인덱스: {"history": [id1, id2], "summary_id": "id3"}
  memory/
    1780394454383.json  # 단일 항목: {"info": "JSON 문자열"}
    1780427888604.json
    archive/
      2026-06/          # 월별 아카이브
```

### 흐름

1. 각 AI 교환 (사용자+어시스턴트)은 `memory/`에 JSON 파일로 저장됩니다
2. `memory.json`은 최근 20개의 ID를 추적합니다
3. 5회 저장 후 참조되지 않은 파일은 `archive/{YYYY-MM}/`로 이동합니다
4. 6개월 이상 된 아카이브는 삭제됩니다
5. 메모리가 `memory_tokens * 4` 바이트를 초과하면 AI 압축이 트리거됩니다:
   - 오래된 메시지가 AI에 의해 요약됩니다
   - 요약이 `summary_id` 항목으로 저장됩니다
   - 원본 파일이 아카이브됩니다

---

## 이벤트 및 스케줄

### events.json
```json
{
  "events": [{
    "date": "2026-06-15",
    "time": "14:30",
    "duration": 60,
    "description": "팀 회의",
    "recur": "7d",
    "notify": "2026-06-15 13:30:00"
  }]
}
```
- `recur`: "1d"=매일, "7d"=매주, "1m"=매월, "2h"=2시간마다
- `notify`: 알림이 전송된 타임스탬프

### schedule.json
```json
{
  "schedules": [{
    "date": "2026-06-05",
    "time": "08:00",
    "duration": 5,
    "description": "백업",
    "recur": "1d",
    "command": "powershell",
    "arguments": "-File backup.ps1"
  }]
}
```
- 이벤트와 유사하지만 명령 실행을 트리거합니다
- 시작 및 종료 시 TTS 알림
- 안전한 패턴에 대한 명령 유효성 검사 (`.exe`, `.bat`, `.ps1`, `.py`, `.cmd`, `.vbs`)

---

## 종속성

### 코어 (13)
| 패키지 | 사용 |
|-----------|-----|
| `sounddevice` | 오디오 입력/출력 |
| `numpy` | 오디오 및 이미지용 배열 |
| `faster-whisper` | STT 음성 인식 |
| `webrtcvad` | 음성 활동 감지 |
| `kokoro` | TTS 음성 합성 |
| `torch` | 딥러닝 (Kokoro, Whisper, EasyOCR) |
| `soundfile` | WAV 파일 쓰기 |
| `openai` | OpenAI 호환 API 클라이언트 |
| `mcp[cli]` | FastMCP MCP 서버 |
| `pynput` | 마우스/키보드 제어 |
| `PySide6` | Qt6 GUI |
| `keyring` | Windows 자격 증명 관리자 |
| `httpx` | AI 및 웹용 HTTP 클라이언트 |

### 웹 및 OCR (6)
| 패키지 | 사용 |
|-----------|-----|
| `beautifulsoup4` | 정적 페이지 HTML 파싱 |
| `lxml` | 빠른 XML/HTML 엔진 |
| `playwright` | JS 페이지용 헤드리스 브라우저 |
| `mss` | 빠른 스크린샷 |
| `easyocr` | 화면 텍스트 인식 |
| `pillow` | 이미지 처리 |

### 유틸리티 (5)
| 패키지 | 사용 |
|-----------|-----|
| `pyyaml` | MCP 서버 구성 |
| `structlog` | MCP 구조화 로깅 |
| `uvicorn` | MCP HTTP 서버 |
| `psutil` | 리소스 모니터링 |
| `misaki` | Kokoro 토큰화 |
| `dateparser` | 자연어 날짜 파싱 |

---

## 내부 구조

### 스레딩 모델

- **메인 스레드**: Qt GUI (이벤트 루프)
- **오디오 스레드**: sounddevice 콜백
- **VASS 스레드**: 청취/전사 루프
- **감시 스레드**: `_watch_commands_file`, `_watch_settings_file`, `_watch_script_queue`
- **일시적**: TTS 재생, AI 폴백, 스크립트 실행

### 잠금 메커니즘

- `_trim_lock` — 메모리 작업 보호
- `_script_engine_lock` — 활성 엔진 보호
- `_tts_done` (이벤트) — TTS 완료 동기화
- `state_lock` — 애플리케이션 상태 보호

### 파일 기반 IPC

**exec_queue.json / exec_result.json**:
- MCP 서버가 스크립트 실행 요청을 작성
- VASS가 폴링 (1초), 실행, 결과 작성
- 타임아웃: 파일 스크립트 60초, 인라인 120초

### 파일 감시

VASS는 다음 파일의 변경 사항을 모니터링합니다:
- `settings.ini` — 자동 다시 로드
- `commands.ini` — 자동 다시 로드
- `events.json` / `schedule.json` — 다음 알림 재계산

### 자격 증명 저장소

- Windows: `keyring`을 통한 Windows 자격 증명 관리자
- macOS: 키체인
- Linux: D-Bus Secret Service 또는 파일
- 용도: AI API 키, VASScript 스크립트 권한 (함수별)

### i18n 시스템

- `locales/*.json`: 9개 언어, 각 215개 이상의 키
- 파일 `i18n.py`: `t(key, lang)` 조회
- 참조: `it.json`
- 모든 파일이 자동으로 정렬됨

### 로그 로테이션

- `debug.log`: 최대 500KB → `.1`, `.2`
- `mcp_server/LOG/`: 최대 1MB → `.1`, `.2`
- 도우미: `log_utils.py`

---

## 고급 구성

### [ai]
| 매개변수 | 기본값 | 설명 |
|-----------|---------|-------------|
| `url` | `http://127.0.0.1:8080/v1` | API 엔드포인트 |
| `model` | `Qwen3-8B-Q4_K_M` | 모델 이름 |
| `api_key` | (비어 있음) | API 키 (로컬의 경우 비어 있음) |
| `system_message` | (긴 텍스트) | 시스템 프롬프트 |
| `mcp_server_url` | `http://localhost:9988` | MCP 서버 URL |
| `memory_tokens` | `4000` | 토큰×4바이트 단위의 메모리 제한 |
| `blacklist` | `Amara.org,QTTS` | 쉼표로 구분된 차단 단어 |

### [tts]
| 매개변수 | 기본값 | 설명 |
|-----------|---------|-------------|
| `tts_engine` | `kokoro` | TTS 엔진 |
| `volume` | `0.50` | 볼륨 0-1 |

### [wakeword]
| 매개변수 | 기본값 | 설명 |
|-----------|---------|-------------|
| `wakeword` | `erika` | 웨이크워드 |
| `sensitivity` | `0.01` | 감도 0-1 |

### [resources]
| 매개변수 | 기본값 | 설명 |
|-----------|---------|-------------|
| `cpu_max` | `75` | CPU 임계값 % |
| `ram_max` | `99` | RAM 임계값 % |
| `gpu_max` | `75` | GPU 임계값 % |
| `vram_max` | `99` | VRAM 임계값 % |
| `resource_timeout` | `30` | 대기 타임아웃 초 |

### [llamacpp]
| 매개변수 | 설명 |
|-----------|-------------|
| `llama_server_path` | llama.cpp 실행 파일 경로 |
| `llama_server_arguments` | 명령줄 인수 |

### [events]
| 매개변수 | 기본값 | 설명 |
|-----------|---------|-------------|
| `reminder_advance` | `3600` | 알림 사전 시간 초 (1시간) |

### [gui]
| 매개변수 | 기본값 | 설명 |
|-----------|---------|-------------|
| `x`, `y` | auto | 창 위치 |
| `width`, `height` | `200`, `32` | 창 크기 |
| `font_family` | `Segoe UI` | GUI 글꼴 |
| `font_size` | `10` | 글꼴 크기 |
