# ⚡ Gemini One-App

> **一个文件 = Gemini 大脑 + 电脑全自动执行 + 手机随身遥控。** 免浏览器插件、免内网穿透、零第三方依赖。
>
> **One file = Gemini brain + autonomous desktop execution + mobile remote control.** No browser extension, no port forwarding, zero third-party dependencies.

**v1.1.0 (2026-11-13) — 安全鉴权版 / Security-hardened release**：所有来自手机或外部局域网的请求强制校验 `X-Agent-Pin`，电脑本机自动免密。

[简体中文](#zh) · [English](#en)

---

<a id="zh"></a>

## 简体中文

### 这是什么

`gemini_one_app.py` 是一个单文件 Python 程序。运行后它会：

- 在本机弹出一个独立应用窗口（Windows 优先使用 Edge 的 `--app` 模式），作为可视化控制台；
- 用 **Gemini 2.5 Flash** 当「大脑」，把一句自然语言目标拆成最多 8 步的自主执行循环；
- 通过内置工具直接读写文件、执行终端命令、截取屏幕；
- 同一套界面也能在手机浏览器打开；或者借助 Telegram Bot，在全球任意网络（4G/5G）遥控家里的电脑，**不需要公网 IP、端口映射或内网穿透**；
- **v1.1 起所有远程请求都经 PIN 鉴权**：公共 Wi-Fi 下即使别人扫到端口，也拿不到执行权限。

### 快速开始

```bash
python gemini_one_app.py                 # 启动，自动打开 http://127.0.0.1:8765
python gemini_one_app.py --self-test     # 离线自检：不联网、不需要 API Key
```

要求 Python 3.8+。核心功能**只用标准库**；屏幕截图功能需要可选依赖 `pip install Pillow`。

启动后终端会打印三个地址/路径：电脑控制界面 `http://127.0.0.1:8765`（本机免密）、手机 Wi-Fi 直连地址 `http://<局域网IP>:8765`（**需填 PIN**）、以及工作区目录（默认 `~/Desktop/Gemini_Workspace`）。

### 手机连接的两种方式

| 方式 | 适用场景 | 怎么配 |
| :--- | :--- | :--- |
| **A. Telegram Bot（推荐）** | 户外 4G/5G、全球任意地点 | 用 [@BotFather](https://t.me/BotFather) 创建机器人，把 Token 填进网页的「⚙️ 一键配置」，然后**自己先给它发第一条消息**完成主人绑定 |
| **B. 局域网直连** | 家里 / 办公室同一 Wi-Fi | 手机浏览器打开终端打印的 `http://<局域网IP>:8765`，**在页面顶部填入 PIN 码**（默认 `8888`）后即可使用 |

方式 A 的原理是电脑**主动向外长轮询** `getUpdates`，所以不需要公网 IP、路由器端口映射，也不需要任何穿透服务。执行结果会以消息形式回传到手机。

### 🔐 v1.1 安全鉴权（远程访问必读）

从 v1.1 起，服务虽然仍监听 `0.0.0.0:8765` 以便手机访问，但**不再允许匿名调用**：

| 访问来源 | 行为 |
| :--- | :--- |
| 电脑本机 `127.0.0.1` / `::1` | 自动免密，打开即用 |
| 手机 / 任何外部局域网 IP | `/run`、`/config`、`/logs` 全部要求请求头 `X-Agent-Pin` 与配置中的 PIN 一致，否则返回 **401 Unauthorized** |

实现要点：

- 用 `hmac.compare_digest` 做常量时间比较，避免时序侧信道；
- **只认 TCP 连接的真实回环地址**，忽略 `X-Forwarded-For` 等可伪造请求头，防止伪造来源绕过；
- 同一 IP 在 60 秒内连续失败 5 次会被临时锁定，抑制口令爆破；
- 未授权请求在读取 body 之前就被拒绝，不会触发任何本地动作；
- 手机网页顶部提供 PIN 输入框，值只存在浏览器 `localStorage`，不会上传；每次请求自动带上 `X-Agent-Pin`；
- 在「⚙️ 一键配置」里修改 PIN 后**立即生效**，旧 PIN 马上失效；也可用环境变量 `AGENT_PIN` 预置。

⚠️ **默认 PIN 是 `8888`，第一次启动后请立刻改掉**，尤其是在 DevFest / 会场 / 咖啡厅等公共 Wi-Fi 环境下演示。页面本身（`/`）不校验 PIN，是为了让手机能先打开界面输入 PIN，页面不含任何敏感数据。

### 两种工作模式

- **不填 API Key（内置本地引擎）**：自动演示「扫描工作区 → 写脚本 → 运行脚本」三步流程，离线也能体验。
- **填入 Gemini API Key**：直接调用官方 REST 接口 `gemini-2.5-flash`（无需安装 SDK），模型用 JSON 指令调用本地工具，最多 8 步自主循环，完成后用中文汇报结果。

在页面展开「⚙️ 一键配置」即可保存 Key / Token / PIN，配置写入 `~/.gemini_one_agent_config.json`；也可用环境变量 `GEMINI_API_KEY`、`TG_BOT_TOKEN`、`AGENT_PIN` 预置。

### 内置工具与插件扩展

| 工具 | 作用 |
| :--- | :--- |
| `list_files` | 列出工作区文件（最多 100 个） |
| `read_file` | 读取文本 / 代码（最多 6000 字符） |
| `write_file` | 创建或修改文件，自动建目录 |
| `run_command` | 执行终端命令（超时 30 秒，输出最多 4000 字符） |
| `take_screenshot` | 截取当前屏幕（需要 Pillow） |

把任意 `.py` 文件放进 `~/Desktop/Gemini_Workspace/plugins/`，在其中定义 `register(tool_decorator)` 并用装饰器注册函数，重启后即自动成为新技能。首次运行会在该目录生成 `example_plugin.py` 示例。

### 配置项

配置文件：`~/.gemini_one_agent_config.json`

| 键 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `gemini_api_key` | 环境变量 `GEMINI_API_KEY` 或空 | Gemini API Key，留空则使用本地演示引擎 |
| `telegram_bot_token` | 环境变量 `TG_BOT_TOKEN` 或空 | Telegram 机器人 Token，留空则不启用云端遥控 |
| `allowed_chat_id` | 空 | 首个发消息的会话会**自动绑定**为主人 |
| `pin_code` | `8888`（或环境变量 `AGENT_PIN`） | **v1.1 起强制生效**：非本机请求的 `X-Agent-Pin` 必须与此一致，可在网页设置中修改并立即生效 |
| `port` | `8765` | Web 服务端口 |
| `workspace` | `~/Desktop/Gemini_Workspace` | Agent 的工作目录 |

### ⚠️ 安全须知（务必先读）

这个程序**会在你的电脑上执行任意命令**，请先理解它的信任边界：

1. Web 服务监听 `0.0.0.0:8765` 以便手机访问。**v1.1 已对 `/run`、`/config`、`/logs` 强制校验 PIN**（见上节），匿名请求会被 401 拒绝。但默认口令 `8888` 是公开的，**必须首次启动就修改**；在完全不可信的网络，仍建议把监听改到 `127.0.0.1` 或加反向代理 + HTTPS。
2. `run_command` 以当前用户权限执行 shell 命令，只拦截少数高危删除命令，**不是沙箱**。不要对不可信的指令放行。
3. Telegram Bot 会把**第一个**发消息的人自动绑定为主人，请自己先发第一条消息；不要在公开群聊里使用它。
4. API Key、Bot Token 与 PIN 以明文保存在用户主目录配置文件中，请勿把该配置文件提交到仓库。
5. 不要把 `workspace` 指向含敏感数据的目录；模型可能读取或覆写工作区内的任意文件。
6. 本机回环请求免密，意味着**这台电脑上的任何本地进程**都能调用接口；若本机运行不可信程序，请自行加 CSRF 防护或取消免密策略。

### 项目结构

```text
gemini-one-app/
├── gemini_one_app.py   # 全部功能：配置 / 工具 / Agent 循环 / Telegram 轮询 / PIN 鉴权 / Web UI
├── README.md           # 中英双语说明（本文件）
├── .gitignore
└── LICENSE             # MIT
```

### License

MIT © 2026 zihew806-hue

---

<a id="en"></a>

## English

### What is it

`gemini_one_app.py` is a self-contained, single-file Python program. Once started, it:

- opens a standalone app window on the host machine (Edge `--app` mode on Windows) as a visual console;
- uses **Gemini 2.5 Flash** as the brain, turning one natural-language goal into an autonomous loop of up to 8 steps;
- reads/writes files, runs shell commands, and captures the screen through built-in tools;
- serves the same UI to a phone browser, or lets you control the PC from anywhere over 4G/5G via a Telegram bot — **no public IP, no port forwarding, no tunnel service required**;
- **since v1.1, every remote request is PIN-authenticated**: on public Wi-Fi, someone who merely finds the port still cannot issue commands.

### Quick start

```bash
python gemini_one_app.py                 # start; opens http://127.0.0.1:8765
python gemini_one_app.py --self-test     # offline self-test, no API key needed
```

Requires Python 3.8+. The core uses **only the standard library**; screenshots need the optional `pip install Pillow`.

On startup the terminal prints the desktop URL (`http://127.0.0.1:8765`, no PIN needed locally), the LAN URL for phones (`http://<LAN-IP>:8765`, **PIN required**), and the workspace path (default `~/Desktop/Gemini_Workspace`).

### Two ways to connect a phone

| Mode | Best for | Setup |
| :--- | :--- | :--- |
| **A. Telegram bot (recommended)** | Anywhere on 4G/5G, worldwide | Create a bot with [@BotFather](https://t.me/BotFather), paste its token into the "⚙️ Settings" panel, then **send the first message yourself** to bind as owner |
| **B. Direct LAN access** | Home / office Wi-Fi | Open the LAN URL printed in the terminal, then **enter the PIN (default `8888`) in the field at the top of the page** |

Mode A works because the PC **polls outbound** to Telegram's `getUpdates`; the bot replies with the execution result. No inbound connectivity is needed.

### 🔐 v1.1 authentication (read before remote access)

The server still binds `0.0.0.0:8765` so phones can reach it, but **anonymous calls are no longer accepted**:

| Request origin | Behaviour |
| :--- | :--- |
| Local machine `127.0.0.1` / `::1` | Auto-trusted, no PIN needed |
| Phone / any external LAN IP | `/run`, `/config` and `/logs` all require an `X-Agent-Pin` header matching the configured PIN, otherwise **401 Unauthorized** |

Implementation details:

- `hmac.compare_digest` for constant-time comparison (no timing side channel);
- **only the real TCP loopback address is trusted** — spoofable headers such as `X-Forwarded-For` are ignored, so a forged "local" origin cannot bypass auth;
- 5 failed attempts from one IP within 60 seconds trigger a temporary lockout to slow down brute force;
- unauthorized requests are rejected **before** the body is read, so no local action is triggered;
- the phone UI has a PIN field at the top; the value lives only in the browser's `localStorage` and is never uploaded, and every fetch automatically attaches `X-Agent-Pin`;
- changing the PIN in "⚙️ Settings" takes effect **immediately** (the old PIN stops working); it can also be preset via the `AGENT_PIN` environment variable.

⚠️ **The default PIN is `8888` — change it on first launch**, especially when demoing at DevFest, a conference, or a café with public Wi-Fi. The HTML page itself (`/`) is not PIN-gated so a phone can open the UI and enter the PIN; the page contains no sensitive data.

### Two operating modes

- **No API key (built-in local engine)**: a three-step offline demo — scan workspace, write a script, run it.
- **With a Gemini API key**: calls the official `gemini-2.5-flash` REST endpoint directly (no SDK install), emits JSON tool calls in an autonomous loop of up to 8 steps, then reports back in Chinese.

Keys are saved to `~/.gemini_one_agent_config.json` from the settings panel, or preloaded from `GEMINI_API_KEY` / `TG_BOT_TOKEN` / `AGENT_PIN` environment variables.

### Built-in tools & plugins

| Tool | Purpose |
| :--- | :--- |
| `list_files` | List workspace files (up to 100) |
| `read_file` | Read text / code (up to 6000 chars) |
| `write_file` | Create or overwrite files, creating parent dirs |
| `run_command` | Run a shell command (30 s timeout, 4000-char output cap) |
| `take_screenshot` | Capture the screen (requires Pillow) |

Drop any `.py` file into `~/Desktop/Gemini_Workspace/plugins/` that defines `register(tool_decorator)` and decorates its functions; they become new skills on the next start. An `example_plugin.py` sample is generated on first run.

### Configuration

File: `~/.gemini_one_agent_config.json`

| Key | Default | Meaning |
| :--- | :--- | :--- |
| `gemini_api_key` | env `GEMINI_API_KEY` or empty | Gemini API key; empty enables the local demo engine |
| `telegram_bot_token` | env `TG_BOT_TOKEN` or empty | Telegram bot token; empty disables cloud remote control |
| `allowed_chat_id` | empty | The **first** chat to message the bot is auto-bound as owner |
| `pin_code` | `8888` (or env `AGENT_PIN`) | **Enforced since v1.1**: `X-Agent-Pin` on every non-local request must match; editable in the UI, effective immediately |
| `port` | `8765` | Web server port |
| `workspace` | `~/Desktop/Gemini_Workspace` | Agent working directory |

### ⚠️ Security notes (read first)

This program **executes arbitrary commands on your computer**. Understand its trust boundary:

1. The web server binds `0.0.0.0:8765` so phones can connect. **v1.1 enforces PIN auth on `/run`, `/config` and `/logs`** (see above); anonymous calls get 401. The default PIN `8888` is public, so **change it on first launch**. On fully untrusted networks, still prefer binding to `127.0.0.1` or an authenticating reverse proxy with HTTPS.
2. `run_command` runs shell commands with your user privileges. Only a few destructive delete patterns are blocked; **this is not a sandbox**. Never feed it untrusted instructions.
3. The Telegram bot auto-binds the **first** sender as owner — send the first message yourself, and don't use it in public groups.
4. API keys, bot tokens and the PIN are stored in plaintext in your home directory. Never commit that config file.
5. Don't point `workspace` at directories with sensitive data; the model can read or overwrite any file inside it.
6. Loopback requests are trusted, meaning **any local process on this machine** can call the API. If untrusted software runs locally, add CSRF protection or disable the local bypass.

### Project layout

```text
gemini-one-app/
├── gemini_one_app.py   # everything: config / tools / agent loop / Telegram polling / PIN auth / web UI
├── README.md           # bilingual docs (this file)
├── .gitignore
└── LICENSE             # MIT
```

### License

MIT © 2026 zihew806-hue
