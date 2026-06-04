# VASS — 高级文档

## 总体架构

VASS 是一个模块化应用程序，由多个独立组件组成，这些组件通过文件队列、Qt 信号和直接调用进行通信。

```
┌─────────────────────────────────────────────────┐
│                    vass.py                       │
│              主编排器                             │
│  - 组件初始化                                     │
│  - 监听/写入循环                                  │
│  - AI 回退管理                                    │
│  - 脚本执行                                       │
│  - 文件队列看门狗                                  │
└──────┬──────┬──────┬──────┬──────┬──────────────┘
       │      │      │      │      │
       ▼      ▼      ▼      ▼      ▼
  ┌────────┐┌─────┐┌─────┐┌────┐┌──────────┐
  │  gui.py││TTS  ││STT  ││事件││mcp_server│
  │  PySide││引擎 ││Whisp││提醒││  15 工具 │
  └────────┘└─────┘└─────┘└────┘└──────────┘
```

### 核心组件

| 组件 | 文件 | 职责 |
|-----------|------|---------------|
| 编排器 | `vass.py`（1313 行） | 初始化、主循环、AI、脚本、内存 |
| GUI | `gui.py`（832 行） | PySide6 窗口、状态栏、淡出、子窗口 |
| TTS | `tts_engine.py`（138 行） | Kokoro TTS、音频播放、音量 |
| STT | `voice_recognition.py`（133 行） | faster-whisper、唤醒词检测 |
| 解释器 | `script_engine.py`（761 行） | VASScript 解析器、求值器、26 个函数 |
| 事件 | `event_reminder.py`（280 行） | 事件/计划监控、TTS 警报 |
| 命令 | `command_executor.py`（184 行） | 模糊模式匹配、变量提取 |
| MCP 服务器 | `mcp_server/` | FastMCP 服务器、15 个工具、基于 IP 的 ACL |
| OCR | `script_engine.py:_preprocess_screen` | 带预处理的 EasyOCR |
| 空闲 | `idle_tracker.py`（67 行） | 跨平台空闲检测 |
| 资源 | `resource_monitor.py`（52 行） | AI 请求前的 CPU/RAM/GPU/VRAM 门控 |
| 日志 | `log_utils.py`（13 行） | 日志文件轮转 |

---

## 音频管道

```
麦克风 ──► sounddevice（回调）──► 音频队列 ──► Whisper（转录）
                                                   │
                    ┌──────────────────────────────┤
                    ▼                              ▼
         检测到 "Erika"？                  完整转录
                    │                              │
                    ▼                              ▼
              确认提示音                    匹配 commands.ini？
                    │                        │            │
                    ▼                        ▼            ▼
             等待命令                      找到命令     无匹配
                    │                        │            │
                    ▼                        ▼            ▼
             转录                         执行操作     AI 回退
                    │
                    ▼
            Kokoro TTS ──► 扬声器
```

### 音频组件详情

- **输入**：`sounddevice.InputStream`，16000 Hz 单声道回调
- **VAD**：webrtcvad 用于过滤静音
- **唤醒词**：Whisper tiny 模型，在转录中搜索 "erika"
- **转录**：唤醒词确认后的 Whisper medium 模型（可配置）
- **TTS**：Kokoro `KPipeline(lang_code='i')`，语音 `if_sara`，通过 UUID 文件名生成 WAV
- **播放**：`sounddevice.play()`，使用 `_tts_done` 事件进行同步

---

## VASScript — 脚本语言

VASScript 是一种用于桌面自动化的极简脚本语言。逐行执行，无算术运算符，一切都是字符串。

### 可用函数（共 26 个）

#### AI 和 TTS
- `ai(prompt)` — 查询 AI，返回文本
- `say(text, speed?)` — 语音合成（速度：0.5-1.5）
- `listen(prompt?)` — 录制语音，返回转录

#### 系统
- `run(command)` — 执行 PowerShell，返回输出
- `wait(seconds)` — 暂停执行
- `exit()` — 终止脚本
- `getdatetime()` — 当前日期/时间 "YYYY-MM-DD HH:MM"

#### 屏幕（OCR）
- `screen_search(query)` — 在屏幕上搜索文本，设置 `$_sx`、`$_sy`、`$_sw`、`$_sh`
- `screen_click(x?, y?)` — 点击坐标
- `screen_highlight(x, y, w?, h?, dur?)` — 高亮区域

#### 窗口和键盘
- `setActiveWindow(name)` — 按进程/标题激活窗口
- `sendText(text)` — 以类人延迟输入文本

#### 事件
- `addevent(date, time, duration, description, recur?)` — 添加事件
- `listevents(until_date)` — 列出事件（JSON）
- `removeevent(name)` — 删除事件（模糊匹配）
- `prettyevents(json)` — 将事件格式化为可读文本

#### 内存和剪贴板
- `readinfo(id)` — 读取信息文件
- `writeinfo(text)` — 写入信息文件，返回 ID
- `clipboardget()` — 读取剪贴板
- `clipboardset(text)` — 写入剪贴板

#### 条件
- `ifcontains(var, substring, if_true, if_false?)` — 包含子字符串
- `ifempty(var, if_empty, if_notempty?)` — 检查是否为空

#### 实用工具
- `trim(text)` — 删除空格
- `len(text)` — 字符串长度
- `contains(text, substring)` — 包含？("True"/"False")
- `equals(a, b)` — 相等？("True"/"False")

### 变量

```vascript
$name = "Fabio"            # 赋值
$age = "54"                # 一切都是字符串
$result = ai("你好")        # 函数结果
say("你好 {$name}！")       # 字符串插值
say("你今年 {$age} 岁")     # 同样适用于变量
```

**注意：** VASScript 不支持使用 `+` 连接。请在字符串中使用 `{$var}`。

### screen_search 全局变量

`screen_search()` 为第一个匹配设置以下全局变量：
- `$_sx`、`$_sy` — 中心坐标
- `$_sw`、`$_sh` — 宽度和高度

---

## MCP 服务器 — 15 个工具

MCP 服务器在 `http://localhost:9988` 上向 AI 暴露 15 个工具。

### 文件系统
- `read_file(path)` — 在 Allowed_root 内读取文件
- `write_file(path, content)` — 在 Allowed_root 内写入文件

### 网页
- `browse(url)` — 下载页面（静态，httpx+BeautifulSoup）
- `websearch(query)` — 通过 Playwright 搜索 DuckDuckGo
- `webfetch(url)` — 通过 Playwright 加载 JS 渲染页面

### 计算和时间
- `calculate(expression)` — 求值数学表达式（AST，安全）
- `current_time()` — 当前日期/时间
- `disk_space()` — 可用磁盘空间

### 执行
- `execute(command)` — 执行命令（白名单）
- `script(script_name)` — 运行 VASScript 文件
- `interact(code)` — 执行内联 VASScript

### 内存和剪贴板
- `readinfo(id)` — 读取信息文件
- `writeinfo(text)` — 写入信息文件
- `clipboardget()` — 读取剪贴板
- `clipboardset(text)` — 写入剪贴板

### 认证

通过 `mcp_server/config/tools.yaml` 实现基于 IP 的 ACL。每个工具有白名单/黑名单。默认为拒绝。

### 脚本 → VASS 通信

`script` 和 `interact` 工具使用基于文件的 IPC：
1. 将请求写入 `scripts/exec_queue.json`
2. VASS 读取队列（1 秒轮询）
3. 执行脚本
4. 将结果写入 `scripts/exec_result.json`
5. MCP 客户端读取结果

---

## 内存系统

### 结构

```
Allowed_root/
  memory.json          # 索引：{"history": [id1, id2], "summary_id": "id3"}
  memory/
    1780394454383.json  # 单条目：{"info": "JSON 字符串"}
    1780427888604.json
    archive/
      2026-06/          # 月度存档
```

### 流程

1. 每次 AI 交换（用户+助手）被保存为 `memory/` 中的 JSON 文件
2. `memory.json` 跟踪最近 20 个 ID
3. 5 次保存后，未引用的文件进入 `archive/{YYYY-MM}/`
4. 超过 6 个月的存档将被删除
5. 当内存超过 `memory_tokens * 4` 字节时，触发 AI 压缩：
   - 旧消息由 AI 摘要
   - 摘要保存为 `summary_id` 条目
   - 原始文件被存档

---

## 事件和计划

### events.json
```json
{
  "events": [{
    "date": "2026-06-15",
    "time": "14:30",
    "duration": 60,
    "description": "团队会议",
    "recur": "7d",
    "notify": "2026-06-15 13:30:00"
  }]
}
```
- `recur`："1d"=每日，"7d"=每周，"1m"=每月，"2h"=每 2 小时
- `notify`：通知发送的时间戳

### schedule.json
```json
{
  "schedules": [{
    "date": "2026-06-05",
    "time": "08:00",
    "duration": 5,
    "description": "备份",
    "recur": "1d",
    "command": "powershell",
    "arguments": "-File backup.ps1"
  }]
}
```
- 类似事件，但触发命令执行
- 开始和结束时 TTS 通知
- 针对安全模式验证命令（`.exe`、`.bat`、`.ps1`、`.py`、`.cmd`、`.vbs`）

---

## 依赖项

### 核心（13）
| 包 | 用途 |
|-----------|-----|
| `sounddevice` | 音频输入/输出 |
| `numpy` | 音频和图像数组 |
| `faster-whisper` | STT 语音识别 |
| `webrtcvad` | 语音活动检测 |
| `kokoro` | TTS 语音合成 |
| `torch` | 深度学习（Kokoro、Whisper、EasyOCR） |
| `soundfile` | WAV 文件写入 |
| `openai` | OpenAI 兼容 API 客户端 |
| `mcp[cli]` | FastMCP MCP 服务器 |
| `pynput` | 鼠标/键盘控制 |
| `PySide6` | Qt6 GUI |
| `keyring` | Windows 凭据管理器 |
| `httpx` | AI 和网页 HTTP 客户端 |

### 网页和 OCR（6）
| 包 | 用途 |
|-----------|-----|
| `beautifulsoup4` | 静态页面 HTML 解析 |
| `lxml` | 快速 XML/HTML 引擎 |
| `playwright` | JS 页面无头浏览器 |
| `mss` | 快速截图 |
| `easyocr` | 屏幕文本识别 |
| `pillow` | 图像处理 |

### 实用工具（5）
| 包 | 用途 |
|-----------|-----|
| `pyyaml` | MCP 服务器配置 |
| `structlog` | MCP 结构化日志 |
| `uvicorn` | MCP HTTP 服务器 |
| `psutil` | 资源监控 |
| `misaki` | Kokoro 分词 |
| `dateparser` | 自然语言日期解析 |

---

## 内部机制

### 线程模型

- **主线程**：Qt GUI（事件循环）
- **音频线程**：sounddevice 回调
- **VASS 线程**：监听/转录循环
- **看门狗线程**：`_watch_commands_file`、`_watch_settings_file`、`_watch_script_queue`
- **临时线程**：TTS 播放、AI 回退、脚本执行

### 锁机制

- `_trim_lock` — 保护内存操作
- `_script_engine_lock` — 保护活动引擎
- `_tts_done`（事件）— 同步 TTS 完成
- `state_lock` — 保护应用程序状态

### 基于文件的 IPC

**exec_queue.json / exec_result.json**：
- MCP 服务器写入脚本执行请求
- VASS 轮询（1 秒），执行，写入结果
- 超时：文件脚本 60 秒，内联脚本 120 秒

### 文件看门狗

VASS 监控以下文件的更改：
- `settings.ini` — 自动重新加载
- `commands.ini` — 自动重新加载
- `events.json` / `schedule.json` — 重新计算下一个警报

### 凭据存储

- Windows：通过 `keyring` 使用 Windows 凭据管理器
- macOS：钥匙串
- Linux：D-Bus Secret Service 或文件
- 用于：AI API 密钥、VASScript 脚本权限（按函数）

### 国际化系统

- `locales/*.json`：9 种语言，每种 215+ 个键
- `i18n.py` 文件：`t(key, lang)` 查找
- 参考：`it.json`
- 所有文件自动对齐

### 日志轮转

- `debug.log`：最大 500 KB → `.1`、`.2`
- `mcp_server/LOG/`：最大 1 MB → `.1`、`.2`
- 辅助工具：`log_utils.py`

---

## 高级配置

### [ai]
| 参数 | 默认值 | 描述 |
|-----------|---------|-------------|
| `url` | `http://127.0.0.1:8080/v1` | API 端点 |
| `model` | `Qwen3-8B-Q4_K_M` | 模型名称 |
| `api_key` | （空） | API 密钥（本地为空） |
| `system_message` | （长文本） | 系统提示 |
| `mcp_server_url` | `http://localhost:9988` | MCP 服务器 URL |
| `memory_tokens` | `4000` | 内存限制（令牌×4 字节） |
| `blacklist` | `Amara.org,QTTS` | 逗号分隔的屏蔽词 |

### [tts]
| 参数 | 默认值 | 描述 |
|-----------|---------|-------------|
| `tts_engine` | `kokoro` | TTS 引擎 |
| `volume` | `0.50` | 音量 0-1 |

### [wakeword]
| 参数 | 默认值 | 描述 |
|-----------|---------|-------------|
| `wakeword` | `erika` | 唤醒词 |
| `sensitivity` | `0.01` | 灵敏度 0-1 |

### [resources]
| 参数 | 默认值 | 描述 |
|-----------|---------|-------------|
| `cpu_max` | `75` | CPU 阈值 % |
| `ram_max` | `99` | RAM 阈值 % |
| `gpu_max` | `75` | GPU 阈值 % |
| `vram_max` | `99` | VRAM 阈值 % |
| `resource_timeout` | `30` | 等待超时秒数 |

### [llamacpp]
| 参数 | 描述 |
|-----------|-------------|
| `llama_server_path` | llama.cpp 可执行文件路径 |
| `llama_server_arguments` | 命令行参数 |

### [events]
| 参数 | 默认值 | 描述 |
|-----------|---------|-------------|
| `reminder_advance` | `3600` | 提醒提前秒数（1 小时） |

### [gui]
| 参数 | 默认值 | 描述 |
|-----------|---------|-------------|
| `x`, `y` | auto | 窗口位置 |
| `width`, `height` | `200`、`32` | 窗口尺寸 |
| `font_family` | `Segoe UI` | GUI 字体 |
| `font_size` | `10` | 字体大小 |
