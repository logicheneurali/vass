# VASS — 语音助手软件

## 什么是 VASS

VASS 是一款面向 Windows、macOS 和 Linux 的语音助手。它能够响应语音命令、运行脚本、管理事件和提醒、阅读和回复邮件，并通过兼容 OpenAI 的 API 与本地或远程 AI 交互。它同时托管一个 MCP 服务器，让 AI 能够直接访问文件、浏览器、日历、邮件、新闻和系统工具。

**默认唤醒词：**"Erika"（可配置）

**当前版本：**0.8.7

**主要特性：**
- 通过 Whisper（faster-whisper）进行语音识别，支持 Silero VAD 和自适应噪声底限
- 通过 Kokoro TTS 进行自然语音合成，带有多级降级回退链
- 本地或远程 AI（llama.cpp、OpenAI 及任何兼容服务器），可选 llama.cpp 自动启动
- 用于桌面自动化的 VASScript 脚本，内置 70 多个函数
- 事件与日程管理，带编辑器界面（提醒、自动化流程）
- 多语言倒计时器（语音触发，最多 5 个同时运行）
- 用于 AI 编排的 MCP 服务器，提供 50 多个工具（浏览器、邮件、新闻、日历、地点、文件、系统）
- 永久记忆，支持自动分类、摘要和用户画像注入
- 集成邮件客户端：Gmail、IMAP、POP3，支持队列、联系人和 AI 代发邮件
- 插件系统：通过本地 TCP 套接字运行内部和外部插件
- 通知中心，支持按事件类型路由
- 对话历史查看器，支持逐条消息操作
- 支持 9 种语言
- 上下文溢出保护（截断或 AI 摘要）
- 音频设备选择（输入/输出）
- 多轮工具调用，用于复杂 AI 任务
- 3 源天气系统，含 20 万城市地理定位数据库
- 时间偏移语音命令（"5 分钟后关机"）
- GUI 中实时显示 MCP 工具活动指示器
- 启发式上下文压缩，支持多语言停用词
- 精确的 Token 计数（tiktoken）
- 脚本执行沙箱，带 SHA-256 授权和审计日志
- 敏感在线工具的安全门（同意确认、速率限制、审计日志）
- 可选的操作系统自启动

---

## 系统要求

- **Python 3.13** 或更高版本
- **AI 服务器**（llama.cpp 或兼容 OpenAI 的服务器）已安装并配置在系统上。VASS 可以在配置后自动启动 llama.cpp，但**不会安装 llama.cpp，也不会下载 AI 模型**：您必须自行获取它们。
- **互联网连接**（用于下载 TTS/STT 模型和连接远程 AI）
- **推荐使用 NVIDIA GPU** 运行本地 AI（CPU 可用但速度较慢）
- **可正常工作的麦克风**
- Windows 10+、macOS 12+ 或较新的 Linux 系统

---

## 安装

### 图形化安装（推荐）

从 [Releases 页面](https://github.com/logicheneurali/vass/releases) 下载安装程序并运行。向导会自动安装 Python、VASS、llama.cpp 和 AI 模型——无需手动配置。

### 引导式安装

下载或克隆项目，然后进入文件夹并运行脚本：

```bash
cd vass
python install.py
```

> **注意：**引导式安装只配置 VASS，**不会安装 AI 服务器或模型**。
> 您必须已经有一个正在运行的兼容 OpenAI 的服务器（llama.cpp、Ollama、LM Studio、Groq、OpenAI 等），
> 或者在 VASS 设置中配置 llama.cpp（可以自动启动它）。

**注意：**引导式安装流程仍处于试验阶段，可能无法在所有系统上正常工作。如果遇到问题，请使用下面的手动安装流程。

向导将引导您完成：
1. 语言选择
2. 先决条件检查（Python 3.13+、pip）
3. 目标文件夹
4. 参数配置（AI URL、模型、唤醒词）
5. 文件复制
6. Python 虚拟环境创建（.venv）
7. Pip 依赖安装
8. settings.ini 文件创建
9. 启动器创建

### 手动安装

```bash
# 克隆或复制文件到目标文件夹
cd VASS

# 创建虚拟环境
python -m venv .venv

# 激活（Windows）
.venv\Scripts\activate
# 或（macOS/Linux）
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 为 Playwright 安装 Chromium（网页搜索）
playwright install chromium

# 创建 config/settings.ini（从 config/settings.example.ini 复制）
```

---

## 配置

所有设置都位于 `config/settings.ini` 中（模板为 `config/settings.example.ini`）。以下是最重要的设置：

| 节（Section） | 参数（Parameter） | 描述（Description） |
|---------|-----------|-------------|
| `[locale]` | `language` | 语言（it/en/de/fr/es/pt/ja/ko/zh） |
| `[wakeword]` | `wakeword` | 唤醒词（默认：erika） |
| `[wakeword]` | `sensitivity` | 唤醒词检测灵敏度 |
| `[commands]` | `similarity` | 语音命令模糊匹配阈值（默认 0.6） |
| `[commands]` | `word_learning_enabled` | 随时间学习新口述词汇（true/false） |
| `[ai]` | `url` | 兼容 OpenAI 的 AI 服务器 URL |
| `[ai]` | `model` | AI 模型名称 |
| `[ai]` | `system_message` | 助手人设 |
| `[ai]` | `api_key` | API 密钥（设置后存储在系统密钥环中） |
| `[ai]` | `mcp_server_url` | 随附 MCP 服务器的 URL（默认 `http://localhost:9988`） |
| `[ai]` | `memory_tokens` | 最大记忆容量 |
| `[ai]` | `context_length` | 最大上下文 Token 数（0 = 自动） |
| `[ai]` | `overflow_strategy` | 上下文溢出处理方式：`truncate` 或 `summarize` |
| `[ai]` | `allow_ai_scripts` | 允许 AI 运行 VASScript 脚本（true/false） |
| `[llamacpp]` | `llama_server_path` | llama.cpp 服务器位置 |
| `[llamacpp]` | `llama_autostart` | 随 VASS 自动启动 llama.cpp（true/false） |
| `[resources]` | `cpu_max`、`ram_max`、`gpu_max`、`vram_max` | 控制 AI 操作的资源限制 |
| `[events]` | `reminder_advance` | 事件提醒提前的秒数（默认 3600） |
| `[audio]` | `input_device`、`output_device` | 音频设备选择（-1 = 系统默认） |
| `[audio]` | `input_volume`、`output_volume` | 输入/输出音量级别（0-1） |
| `[audio]` | `app_volume` | 主 TTS 音量（取代旧的 `[tts] volume`） |
| `[google]` | — | Google Calendar / Gmail / Google Home 集成 |
| `[startup]` | `app_autostart` | 登录时自动启动 VASS（true/false） |
| `[debug]` | `debug_enabled` | 将详细日志写入 `log/debug.log`（true/false） |

如果 VASS 运行期间修改了设置，设置会自动重新加载。

---

## 日常使用

### 启动

双击 `vass.bat`（Windows）或 `vass.sh`/`vass.command`（macOS/Linux）。

或者从终端启动：
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

> **注意：**首次启动时，语音识别（Whisper）和语音合成（Kokoro）模型会自动从 HuggingFace 下载。首次启动可能需要几分钟（约 2-4 GB 下载量）。这种情况只会发生一次。

### 唤醒词

唤醒词可由用户在 `config/settings.ini` 文件中**配置**，可以是任意单词或短句。默认值为"**Erika**"。

当 VASS 检测到唤醒词时，会发出提示音以表示已准备好接收命令。请在提示音之后说话。

示例：
- *"Erika"*（等待提示音），然后说 *"今天天气怎么样？"*
- *"Erika"*（等待提示音），然后说 *"读一下最新的新闻"*
- *"Erika"*（等待提示音），然后说 *"什么是人工智能？"*
- *"Erika"*（等待提示音），然后说 *"translate to italian good morning everyone"*
- *"Erika"*（等待提示音），然后说 *"意大利面培根蛋酱的做法"*

### 模式：聊天与听写

VASS 可以在两种模式下运行，可从弹出菜单中选择（主按钮右侧的 ≡ 按钮）：

- **聊天** `[C]` — 应用识别语音命令并执行操作（脚本、系统命令）或与 AI 交互。响应通过 TTS 朗读。
- **听写** `[T]` — 不解释命令，VASS 忠实地转录用户在唤醒词之后（始终在提示音之后）所说的内容。文本随后粘贴到活动应用中，使 VASS 成为一个文字听写系统。

当前模式显示在主按钮上：`[C]` 表示聊天，`[T]` 表示听写。上次使用的模式在重启后恢复。

### 记忆模式

可通过 GUI 菜单或单击主按钮设置：
- **完整** — AI 接收记忆摘要和您的用户画像
- **受限** — AI 仅接收最近的历史记录
- **无** — 不提供任何历史上下文

### 语音命令

命令在 `config/commands.ini` 中配置（标准 INI 格式，`phrase = action`），也可以通过 GUI 编辑器（`python src/commands_editor.py`）编辑。特定语言的文件 `config/commands_{lang}.ini` 会在基础文件之上加载。每一行都是一个 **phrase = action** 对：phrase 是要识别的模式（可以包含 `{variables}`），action 是要执行的操作。

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

#### 匹配机制

1. **模糊识别**：不需要完全匹配。VASS 使用相似度算法（`difflib`）将口述短语与所有模式进行比较。得分最高且超过阈值（默认 `0.6`，可在 `config/settings.ini` 的 `[commands] similarity` 下配置）的模式被激活。

2. **变量 `{name}`**：捕获该位置的口述词汇。例如：说 *"search cats on the internet"* 会捕获 `term = "cats on the internet"`。

3. **转义变量 `{escaped_name}`**：与普通变量相同，但捕获的文本会被 URL 编码（空格变成 `%20`）。适用于网页搜索。

4. **时间偏移命令**：`{duration}` 后缀（例如 *"shutdown in 5 minutes"*）会通过计时器系统在给定时间之后调度命令执行。

5. **词汇学习**：如果启用，VASS 会记录您对单词的发音方式，以随时间提高识别准确度。

6. **AI 回退**：如果没有命令超过相似度阈值，短语会被发送给 AI，以获得自然语言响应。

#### 逗号备选（笛卡尔积）

您可以使用逗号为每个词位置指定多个备选项。**空格**分隔词位置，**逗号**分隔同一位置内的备选项。VASS 会生成所有可能的组合（笛卡尔积）。

```ini
# 单一位置：介词的备选项
click the,on text {text}
```
生成 2 个模式：`click the text {text}`、`click on text {text}`。

```ini
# 两个位置：每个位置有自己的备选项
aa,xx bb,cc {var}
```
生成 4 个模式：`aa bb {var}`、`aa cc {var}`、`xx bb {var}`、`xx cc {var}`（2x2 = 4）。

```ini
# 混合：固定词 + 备选项
turn on,off {device}
```
生成 2 个模式：`turn on {device}`、`turn off {device}`（`on` 和 `off` 之间没有空格 -> 属于同一位置）。

口述短语会与所有生成的模式进行比较。模糊匹配得分最高的模式胜出。

#### 动作类型

| 前缀 | 示例 | 行为 |
|--------|---------|----------|
| `script:` | `script:search` | 运行 `scripts/search.vass`。捕获的变量会成为 `$param1`、`$param2` 等。 |
| `vasscript:` | `vasscript:events` | 与 `script:` 相同（备用前缀） |
| 命令 | `shutdown /s` | 直接作为系统命令执行 |

#### 节名称

`[general]` 和 `[system]` 之类的节名称只是组织分类——不影响匹配。**键**（要识别的短语）才是关键。

### 创建 VASScript 脚本

从 GUI 菜单打开脚本编辑器，或运行：
```bash
python src/scripts_editor.py
```

所有脚本都放在 `scripts/` 文件夹中，扩展名为 `.vass`。

**授权**：在运行新脚本或修改过的脚本之前，VASS 会弹窗请求许可。脚本通过 SHA-256 哈希验证（存储在系统密钥环中）：如果授权后的脚本文件被修改，权限会自动撤销，下次执行时会再次弹出授权窗口。权限可以按函数授予，也可以授予整个脚本。这样可以确保没有您的明确同意，任何脚本都无法在您的机器上运行。

完整的语言参考请参阅 [VASCRIPT_REFERENCE.md](../Allowed_root/VASCRIPT_REFERENCE.md) 文件。

### 事件与提醒

事件通过 `Allowed_root/events.json` 文件管理。语音提醒提前 1 小时发出（可通过 `[events] reminder_advance` 配置）。

日程（自动化流程）位于 `Allowed_root/schedules.json` 中，会触发命令执行并通过 TTS 通知。附加标志：`silent`、`run_on_startup`、`check_already_running`、`wait_for_completion`。

### 插件系统

VASS 暴露一个本地 TCP 服务器（`localhost:8765`），插件通过它与应用通信：TTS、通知、AI 查询、RSS 条目、聊天、声明式 UI 等。**内部插件**（随 VASS 附带的）无法移除；**外部插件**可以在 GUI（插件菜单）中启用、禁用和移除。

附带的内部插件：噪声自动暂停、主动代理、用户画像、RSS 阅读器、全球事件、Telegram 机器人。磁盘上可用的外部插件：图像生成器、新闻发布器、时间线查看器。

完整协议以及如何创建自己的插件，请参阅 [PLUGIN_DEV_zh.md](PLUGIN_DEV_zh.md) 指南（另有 `PLUGIN_DEV_{en,it,de,fr,es,pt,ja,ko}.md` 版本可用）。

### 邮件

在 设置 → 邮件 中配置一个或多个账户（Gmail 通过 OAuth，或 IMAP/POP3 使用纯 SSL/TLS）。收到的邮件会被检测并通知；AI 可以搜索、阅读、回复、转发和发送邮件——但发出的邮件总是先放入**队列**，您必须从发件箱批准并发送。联系人以加密方式存储。

---

## GUI 界面

- **主按钮** — 单击切换状态（监听/暂停）。鼠标滚轮调节音量。拖动可移动窗口。
- **音量条**（绿色，位于顶部）— 显示当前 TTS 音量
- **多状态条** — 根据上下文显示内存使用、音量或脚本/活动进度
- **通知中心**（铃铛）— 按类型分页签，提供消息操作和全部标记为已读
- **工具指示器** — 实时图标，显示 AI 正在使用的 MCP 工具
- **麦克风按钮** — 在聊天模式下直接语音输入
- **插件菜单** — 管理插件、插件设置和插件 UI
- **设置对话框** — 从 GUI 进行完整配置（设置菜单）
- **自动淡出** — 空闲和全屏时窗口变为半透明
- **启动画面** — 启动时的加载进度
- **主题** — 应用和所有编辑器共享主题

### 快捷键

| 键 | 操作 |
|-------|--------|
| `Ctrl+S` | 保存（在编辑器中） |
| 单击按钮 | 切换状态 |
| 按钮上滚轮 | 调节音量 |
| 右键单击 | 上下文菜单 |
| 中键单击按钮 | 退出 |

---

## 故障排除

> **重要提示：**此应用高度依赖所使用的 AI 模型。无效的模型或不适合 MCP 工具使用的模型可能会影响功能。

### VASS 无法启动
- 检查 Python 3.13+：`python --version`
- 确认 `.venv` 存在且包含依赖
- 检查 `log/debug.log`（启用 `[debug] debug_enabled = true`）和 `log/crash.log`

### 麦克风不工作
- 确认麦克风已连接且未被其他应用占用
- 检查系统的麦克风权限
- 在 Windows 上：设置 → 隐私 → 麦克风

### AI 无响应
- 确认 AI 服务器运行在 `http://127.0.0.1:8080/v1`
- 检查 `config/settings.ini` 中的 `[ai] url`
- 如果使用 llama.cpp，请确认模型存在且 `[llamacpp] llama_server_path` 正确
- 检查 `log/llamacpp.log` 中的 llama.cpp 错误

### OCR 无法识别屏幕文本
- 增大屏幕上的字体大小或文本对比度
- EasyOCR 在大字体和高对比度下效果最佳
- OCR 语言会自动适配所配置的区域设置

### AI 无法使用某个工具
- 某些在线工具需要您的同意（安全门）——请检查 InfoPanel 中是否有待处理请求
- 确认 MCP 服务器可通过 `http://localhost:9988` 访问（参见 `[ai] mcp_server_url`）
- 检查 `log/mcp_server.log` 中的 MCP 错误

---

## 重要文件

| 文件 | 描述 |
|------|-------------|
| `config/settings.ini` | 主配置 |
| `config/commands.ini` | 基础语音命令（以及 `commands_{lang}.ini`） |
| `config/notifications.ini` | 按事件类型的通知路由 |
| `scripts/*.vass` | 您的 VASScript 脚本 |
| `Allowed_root/events.json` | 您的事件和提醒 |
| `Allowed_root/schedules.json` | 自动化流程 |
| `Allowed_root/memory.json` | 对话历史和记忆 |
| `Allowed_root/private_profile.json` | 注入 AI 上下文的用户画像 |
| `plugins/` | 内部和外部插件 |
| `log/debug.log` | 详细调试日志（启用时） |
| `log/crash.log` | 崩溃日志 |
| `log/faulthandler.log` | 故障处理程序输出 |
| `log/llamacpp.log` | llama.cpp 服务器日志 |
