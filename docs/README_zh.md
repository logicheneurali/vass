# VASS — 智能语音助手

## 什么是 VASS

VASS 是一个适用于 Windows、macOS 和 Linux 的语音助手。它响应语音命令，运行脚本，管理事件和提醒，并通过 OpenAI 兼容 API 与本地或远程 AI 交互。

**默认唤醒词：** "Erika"

**主要特性：**
- 通过 Whisper (faster-whisper) 进行语音识别
- 通过 Kokoro TTS 进行自然语音合成
- 本地或远程 AI（llama.cpp、OpenAI、任何兼容服务器）
- 用于桌面自动化的 VASScript 脚本
- 事件和提醒管理
- 带有 15 个工具的 MCP 服务器，用于 AI 编排
- 对话历史
- 支持 9 种语言（意大利语、英语、德语、法语、西班牙语、葡萄牙语、日语、韩语、中文）

---

## 要求

- **Python 3.13** 或更高版本
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

说"**Erika**"，然后说出您的命令。VASS 会发出确认提示音。

示例：
- *"Erika"（等待哔声），然后 *"现在几点了？"*
- *"Erika"（等待哔声），然后 *"帮我搜索最新新闻"*
- *"Erika"（等待哔声），然后 *"提醒我明天下午 2 点的会议"*

### 记忆模式

从 GUI 菜单或通过点击主按钮：
- **Full** — AI 接收记忆摘要
- **Limited** — AI 仅接收最近的历史记录
- **None** — 无历史上下文

### 语音命令

命令在 `commands.ini` 中以标准 INI 格式配置。键是要识别的短语，值是操作：

```ini
[general]
搜索{关键词} = script:搜索
打开{程序} = start {程序}
最新新闻 = script:新闻
现在几点 = script:时间

[system]
关闭系统 = shutdown /s /t 60
锁定屏幕 = rundll32.exe user32.dll,LockWorkStation
```

- `{关键词}`、`{程序}` — 从语音中捕获的变量
- `script:脚本名` — 运行 `scripts/脚本名.vass`
- 备用前缀：`vasscript:`

如果模式包含变量，其值将作为 `$param1`、`$param2` 等传递给脚本。

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
