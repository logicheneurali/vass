# VASS — 语音助手软件

## 什么是 VASS

VASS 是一个适用于 Windows、macOS 和 Linux 的语音助手。它响应语音命令，运行脚本，管理事件和提醒，并通过 OpenAI 兼容 API 与本地或远程 AI 交互。

**默认唤醒词：** "Erika"

**主要特性：**
- 带自适应噪声底限的 Whisper (faster-whisper) 语音识别
- 带4级回退链的 Kokoro TTS 自然语音合成
- 本地或远程 AI (llama.cpp, OpenAI, 兼容服务器)
- 25+ 内置函数的 VASScript 桌面自动化脚本
- 带 GUI 编辑器的事件和计划管理
- 多语言语音计时器 (5个同时)
- 21个工具的 MCP 服务器用于 AI 编排
- 带自动分类和摘要的永久记忆
- 每条消息带操作的对话历史查看器
- 支持9种语言
- 上下文溢出保护
- 音频设备选择 (输入/输出)
- 多轮工具调用用于复杂 AI 任务

---

## 要求

- **Python 3.13** 或更高版本
- **AI 服务器** (llama.cpp 或 OpenAI 兼容) 已安装并配置在系统上。VASS 可以在配置后自动启动 llama.cpp，但**不会安装 llama.cpp 或下载 AI 模型**：您需要单独获取。
- **互联网连接**（用于下载模型和远程 AI）
- 本地 AI 建议使用 **NVIDIA GPU**（也可使用 CPU 但速度较慢）
- 正常工作的**麦克风**
- Windows 10+、macOS 12+ 或现代 Linux

---

## 安装

### 引导安装

下载或克隆项目，然后进入文件夹并运行脚本：

```bash
cd vass
python install.py
```

> **注意：** 引导安装会设置 VASS，但**不会安装 AI 服务器或模型**。
> 您必须已经运行一个 OpenAI 兼容的服务器（llama.cpp、Ollama、LM Studio、Groq、OpenAI 等）
> 或在 VASS 设置中配置 llama.cpp（可自动启动）。

**注意：** 引导安装程序仍处于实验阶段，可能不适用于所有系统。如遇问题，请使用下面的手动安装。

向导将引导您完成以下操作：
1. 选择语言
2. 检查前置条件（Python 3.13+、pip）
3. 目标文件夹
4. 配置参数（AI URL、模型、唤醒词）
5. 复制文件
6. 创建 Python 虚拟环境 (.venv)
7. 安装 pip 依赖项
8. 创建 settings.ini 文件
9. 创建启动器

### 手动安装

```bash
# 克隆或复制文件到所需文件夹
cd VASS

# 创建虚拟环境
python -m venv .venv

# 激活（Windows）
.venv\Scripts\activate
# 或（macOS/Linux）
source .venv/bin/activate

# 安装依赖项
pip install -r requirements.txt

# 为 Playwright 安装 Chromium（网页搜索）
playwright install chromium

# 创建 settings.ini（从示例 settings.ini 复制）
```

---

## 配置

`settings.ini` 文件包含所有设置。以下是最重要的设置：

| 节 | 参数 | 描述 |
|---------|-----------|-------------|
| `[locale]` | `language` | 语言（it/en/de/fr/es/pt/ja/ko/zh） |
| `[ai]` | `url` | OpenAI 兼容 AI 服务器 URL |
| `[ai]` | `model` | AI 模型名称 |
| `[ai]` | `system_message` | 助手个性 |
| `[ai]` | `memory_tokens` | 最大内存大小 |
| `[wakeword]` | `wakeword` | 唤醒词（默认：erika） |
| `[wakeword]` | `sensitivity` | 检测灵敏度（0-1） |
| `[tts]` | `volume` | TTS 音量（0-1） |

如果在 VASS 运行时修改设置，设置将自动重新加载。

---

## 日常使用

### 启动

双击 `vass.bat`（Windows）或 `vass.sh`/`vass.command`（macOS/Linux）。

或者从终端：
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

### 唤醒词

唤醒词可由用户在 `settings.ini` 文件中 **配置**，可以是任意单词或短语。默认为 "**Erika**"。

当 VASS 检测到唤醒词时，会发出提示音表示已准备好接收命令。请在提示音后说话。

示例：
- *"Erika"*（等待哔声），然后 *"天气怎么样"*
- *"Erika"*（等待哔声），然后 *"读新闻"*
- *"Erika"*（等待哔声），然后 *"人工智能是什么"*
- *"Erika"*（等待哔声），然后 *"把大家早上好翻译成英文"*
- *"Erika"*（等待哔声），然后 *"卡邦尼意面怎么做"*

### 模式：聊天与转录

VASS 可在两种模式下运行，可通过弹出菜单（主按钮右侧的 ≡ 按钮）选择：

- **聊天** `[C]` — 应用程序识别语音命令并执行操作（脚本、系统命令）或与 AI 交互。响应通过 TTS 朗读。
- **转录** `[T]` — VASS 不解译命令，而是忠实地转录用户在唤醒词后（始终在提示音后）所说的内容。文本随后粘贴到活动应用程序中，使 VASS 成为一个文本听写系统。

当前模式显示在主按钮上：`[C]` 表示聊天，`[T]` 表示转录。上次使用的模式会在重启时恢复。

### 记忆模式

从 GUI 菜单或通过点击主按钮：
- **Full** — AI 接收记忆摘要
- **Limited** — AI 仅接收最近的历史记录
- **None** — 无历史上下文

### 语音命令

命令在 `commands.ini`（标准 INI 格式）中配置，也可通过 GUI 编辑器（`python commands_editor.py`）编辑。每行是一个 **短语 = 操作** 对：短语是要识别的模式（可包含 `{变量}`），操作是要执行的内容。

```ini
[general]
搜索{关键词} = script:搜索
打开{程序} = start {程序}
在线搜索{escaped_terms} = start firefox "https://duckduckgo.com?q={escaped_terms}"
现在几点 = script:时间

[system]
关闭系统 = shutdown /s /t 60
锁定屏幕 = rundll32.exe user32.dll,LockWorkStation
```

#### 匹配工作原理

1. **模糊识别**：不需要精确匹配。VASS 使用相似度算法（`difflib`）将说出的话语与所有模式进行比较。超过阈值（默认 `0.75`，可在 `settings.ini` 中配置）且得分最高的模式将被激活。

2. **变量 `{名称}`**：捕获该位置说出的词语。示例：说 *"搜索互联网上的猫"*，系统会捕获 `关键词 = "互联网上的猫"`。

3. **转义变量 `{escaped_名称}`**：与普通变量相同，但捕获的文本会进行 URL 编码（空格变为 `%20`）。适用于网页搜索。

4. **AI 回退**：如果没有任何命令超过相似度阈值，该短语将发送给 AI 进行自然语言回复。

#### 操作类型

| 前缀 | 示例 | 行为 |
|------|------|------|
| `script:` | `script:搜索` | 运行 `scripts/搜索.vass`。捕获的变量变为 `$param1`、`$param2` 等 |
| `vasscript:` | `vasscript:事件` | 与 `script:` 相同（替代前缀） |
| URL | `https://...` | 在默认浏览器中打开 |
| 命令 | `shutdown /s` | 直接作为系统命令执行 |

#### 节名称

`[general]` 和 `[system]` 等节名称仅为组织类别，不影响匹配。重要的是**键**（要识别的短语）。

### 创建 VASScript 脚本

从 GUI 菜单打开脚本编辑器或运行：
```bash
python scripts_editor.py
```

所有脚本都放在 `scripts/` 文件夹中，扩展名为 `.vass`。

请参阅 `VASCRIPT_REFERENCE.md` 文件以获取完整的语言参考。

### 事件和提醒

事件通过 `events.json` 文件管理。语音提醒会提前 1 小时发出（可配置）。

计划任务（自动程序）在 `schedule.json` 中，触发命令执行并带有 TTS 通知。

---

## GUI 界面

- **主按钮** — 点击更改状态（listening/paused）。鼠标滚轮调节音量。拖动移动窗口。
- **音量条**（绿色，顶部）— 显示当前 TTS 音量
- **多状态栏** — 根据上下文显示内存使用、音量或脚本进度
- **自动淡出** — 在非活动且全屏时窗口变为半透明

### 快捷键

| 按键 | 操作 |
|-------|--------|
| `Ctrl+S` | 保存（在编辑器中） |
| 按钮点击 | 更改状态 |
| 按钮上的滚轮 | 调节音量 |
| 右键点击 | 上下文菜单 |
| 脚本中的"朗读"按钮 | 使用 TTS 朗读脚本 |

---

## 故障排除

> **重要:** 此应用程序在很大程度上依赖于所使用的 AI 模型。效果不佳或不适合使用 MCP 工具的模型可能会影响功能。

### VASS 无法启动
- 检查 Python 3.13+：`python --version`
- 验证 `.venv` 存在并包含依赖项
- 检查 `debug.log` 中的错误

### 麦克风不工作
- 验证麦克风已连接且未被其他应用占用
- 检查麦克风的系统权限
- 在 Windows 上：设置 → 隐私 → 麦克风

### AI 不响应
- 验证 AI 服务器正在 `http://127.0.0.1:8080/v1` 上运行
- 检查 `settings.ini` 中的 `[ai] url`
- 如果使用 llama.cpp，验证模型是否存在于 `models/` 文件夹中

### OCR 无法识别屏幕上的文字
- 增大屏幕上的字体大小或文本对比度
- EasyOCR 在大字体和高对比度下效果最佳
- OCR 语言会自动适应配置的区域设置

---

## 重要文件

| 文件 | 描述 |
|------|-------------|
| `settings.ini` | 主配置 |
| `commands.ini` | 自定义语音命令 |
| `scripts/*.vass` | 您的 VASScript 脚本 |
| `events.json` | 您的事件和提醒 |
| `schedule.json` | 自动程序 |
| `memory.json` | 对话历史 |
| `debug.log` | 调试日志 |
| `vass.log` | 应用日志 |
