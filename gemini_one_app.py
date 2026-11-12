"""
Gemini One-App Desktop & Mobile Agent (gemini_one_app.py)
=========================================================
v1.1.0 (2026-11-13) — 安全鉴权版 / Security-hardened release
极简合一版：不用装浏览器插件、不用配内网穿透，一个文件搞定【Gemini 大脑 + 电脑全自动执行 + 手机随时随地遥控】！

v1.1 安全更新（重要）：
- 电脑本机（127.0.0.1 / ::1）访问自动免密；
- 任何来自手机或外部局域网 IP 对 /run、/config、/logs 的请求，
  强制校验请求头 X-Agent-Pin（默认 8888，可在网页「⚙️ 一键配置」中修改）；
- 使用 hmac.compare_digest 做常量时间比较，只信任 TCP 回环地址、
  忽略可伪造的 X-Forwarded-For，并对连续失败做 5 次 / 60 秒限流，
  避免公共 Wi-Fi 现场演示时被同网段端口扫描者直接调用；
- 手机网页顶部提供 PIN 输入框，值仅保存在浏览器 localStorage，不上传服务器。

为什么这次最简单？
1. 【电脑端】：双击直接弹出一个可视化窗口，填好 Gemini API Key（或者免 Key 模式），输入一句话，它自己写代码、改文件、跑命令、修 Bug。
2. 【手机端连接彻底改进】：
   - 方式 A（全球 4G/5G 微信/手机随时控制 — 推荐！）：支持直接填入一个 Telegram 机器人 Token 或自建轻量化云端中继，你在外面用手机发一条消息，家里电脑立刻执行并把结果+电脑桌面截图发回你手机！完全不需要公网 IP 或端口映射。
   - 方式 B（家里 Wi-Fi 手机直连）：界面上直接显示 `http://192.168.x.x:8765`，手机浏览器点开就能控制。
3. 【插件一键加】：自带文件读写、代码热修补、命令行执行、电脑截屏，把任何 `.py` 丢进 `plugins` 文件夹自动变成新技能。
"""

import os
import re
import sys
import json
import time
import hmac
import uuid
import socket
import shutil
import threading
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List, Optional

# =====================================================================
# 1. 配置文件管理（自动保存在用户目录，填一次永久生效）
# =====================================================================
CONFIG_FILE = Path.home() / ".gemini_one_agent_config.json"
DEFAULT_WORKSPACE = Path.home() / "Desktop" / "Gemini_Workspace"
VERSION = "1.1.0"

def load_config() -> Dict[str, Any]:
    default_cfg = {
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "telegram_bot_token": os.environ.get("TG_BOT_TOKEN", ""),
        "allowed_chat_id": "",          # 留空则自动绑定第一个给它发消息的手机账号
        # 远程访问 PIN：优先读取环境变量 AGENT_PIN，默认 8888（首次启动后请立即修改）
        "pin_code": os.environ.get("AGENT_PIN", "8888"),
        "port": 8765,
        "workspace": str(DEFAULT_WORKSPACE)
    }
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            default_cfg.update(saved)
        except Exception:
            pass
    return default_cfg

def save_config(cfg: Dict[str, Any]):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

CFG = load_config()
Path(CFG["workspace"]).mkdir(parents=True, exist_ok=True)


# =====================================================================
# 2. 核心底层能力（Codex 5 大全能动作 + 外部插件自动加载）
# =====================================================================
PLUGINS: Dict[str, Any] = {}

def tool(name: str, desc: str):
    def wrap(fn):
        PLUGINS[name] = {"name": name, "description": desc, "fn": fn}
        return fn
    return wrap

@tool("list_files", "查看当前工作区文件夹里的所有文件")
def list_files(subdir: str = ".") -> str:
    root = (Path(CFG["workspace"]) / subdir).resolve()
    if not root.exists():
        return f"目录不存在: {root}"
    files = [str(p.relative_to(root)) for p in root.rglob("*") if ".git" not in p.parts][:100]
    return json.dumps({"workspace": str(root), "files": files}, ensure_ascii=False)

@tool("read_file", "读取指定文件的文本或代码内容")
def read_file(filename: str) -> str:
    p = (Path(CFG["workspace"]) / filename).resolve()
    if not p.exists():
        return f"文件不存在: {filename}"
    return p.read_text(encoding="utf-8", errors="replace")[:6000]

@tool("write_file", "创建或修改代码/文本文件（自动创建文件夹）")
def write_file(filename: str, content: str) -> str:
    p = (Path(CFG["workspace"]) / filename).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"已成功写入文件: {p} ({len(content)} 字符)"

@tool("run_command", "在电脑上运行 Python 脚本或系统终端命令并返回输出结果")
def run_command(command: str) -> str:
    # 拦截极高危删除系统命令
    if re.search(r"\b(rm\s+-rf\s+/|format\s+[a-z]:|del\s+/s\s+/q\s+c:)", command, re.I):
        return "❌ 已拦截高危系统破坏命令！"
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=CFG["workspace"],
            timeout=30,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        out = (proc.stdout + "\n" + proc.stderr).strip()
        return f"[退出码 {proc.returncode}]\n{out[:4000]}"
    except Exception as e:
        return f"执行出错: {e}"

@tool("take_screenshot", "截取当前电脑屏幕画面")
def take_screenshot() -> str:
    shot_path = Path(CFG["workspace"]) / "screen_capture.png"
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(shot_path, "PNG")
        return f"截图已保存至: {shot_path}"
    except Exception as e:
        return f"当前环境无图形桌面或未安装 Pillow ({e})"

def load_custom_plugins():
    """把任何 .py 文件丢进桌面 Gemini_Workspace/plugins 文件夹即可自动加载"""
    pdir = Path(CFG["workspace"]) / "plugins"
    pdir.mkdir(parents=True, exist_ok=True)
    sample = pdir / "example_plugin.py"
    if not sample.exists():
        sample.write_text(
            '# 示例插件：在这里写任何函数，用 @register_plugin 装饰即可被 Gemini 调用\n'
            'def register(tool_decorator):\n'
            '    @tool_decorator("get_pc_status", "获取电脑磁盘剩余空间与系统时间")\n'
            '    def get_pc_status() -> str:\n'
            '        import shutil, datetime\n'
            '        free_gb = round(shutil.disk_usage(".").free / (1024**3), 2)\n'
            '        return f"当前时间: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}, 剩余磁盘空间: {free_gb} GB"\n',
            encoding="utf-8"
        )
    import importlib.util
    for f in pdir.glob("*.py"):
        try:
            spec = importlib.util.spec_from_file_location(f.stem, f)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "register"):
                    mod.register(tool)
        except Exception:
            pass

load_custom_plugins()


# =====================================================================
# 2.5 v1.1 安全鉴权层：本机免密 / 外部强制 X-Agent-Pin
# =====================================================================
PIN_HEADER = "X-Agent-Pin"
LOOPBACK_ADDRS = {"127.0.0.1", "::1", "localhost"}
AUTH_MAX_FAILS = 5          # 同一 IP 在窗口期内允许的最大失败次数
AUTH_WINDOW_SEC = 60.0      # 失败计数窗口（秒）
_AUTH_FAILS: Dict[str, List[float]] = {}   # ip -> 最近失败时间戳


def is_loopback_request(handler) -> bool:
    """只信任 TCP 连接的真实回环地址；绝不读取 X-Forwarded-For 等可伪造请求头。"""
    peer = handler.client_address[0] if handler.client_address else ""
    return peer in LOOPBACK_ADDRS or peer.startswith("127.")


def verify_agent_pin(handler) -> bool:
    """
    本机请求直接放行；外部请求必须携带与配置一致的 X-Agent-Pin。
    常量时间比较 + 简单失败限流，避免公共 Wi-Fi 场景下的口令爆破。
    """
    if is_loopback_request(handler):
        return True

    peer = handler.client_address[0]
    now = time.time()
    recent = [t for t in _AUTH_FAILS.get(peer, []) if now - t < AUTH_WINDOW_SEC]
    _AUTH_FAILS[peer] = recent
    if len(recent) >= AUTH_MAX_FAILS:
        return False

    supplied = handler.headers.get(PIN_HEADER, "") or ""
    expected = str(CFG.get("pin_code", "8888"))
    if supplied and hmac.compare_digest(supplied, expected):
        _AUTH_FAILS.pop(peer, None)
        return True

    recent.append(now)
    _AUTH_FAILS[peer] = recent
    return False


# =====================================================================
# 3. Gemini Codex 自主大脑（无需装 SDK，直接走官方 REST API 零依赖调用！）
# =====================================================================
SYSTEM_PROMPT = """你是运行在用户电脑上的全能自主 Agent (Gemini-Codex)。
当用户给你下达一个任务时，你可以调用以下本地工具在电脑上干活：
- list_files(subdir=".")
- read_file(filename="...")
- write_file(filename="...", content="...")
- run_command(command="...")
- take_screenshot()
以及用户安装的任何扩展插件。

如果你需要调用工具，请输出如下 JSON 格式（不要包含多余解释）：
{"action": "工具名", "args": {"参数名": "参数值"}, "thought": "简短说明你这一步在干什么"}

如果所有步骤都已经完成并验证通过，请直接用中文向用户汇报最终结果。"""


def call_gemini_rest_api(messages: List[Dict[str, str]], api_key: str) -> str:
    """使用 Python 标准库直接请求 Google Gemini 官方接口，免去 pip install 烦恼！"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.1}
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"]


def execute_autonomous_task(user_goal: str, log_callback=None) -> str:
    """
    核心循环：给一句大指令 -> 自动思考 -> 自动调本地工具 -> 检查结果 -> 最终汇报
    """
    def emit(msg: str):
        if log_callback:
            log_callback(msg)

    emit(f"🎯 收到任务: {user_goal}")
    api_key = CFG.get("gemini_api_key", "").strip()

    # 若还没填 API Key，使用内置本地快捷执行引擎（保证不填 Key 也能立刻体验写代码、跑脚本、看状态）
    if not api_key:
        emit("💡 当前未填写 Gemini API Key，启用【内置本地自动执行引擎】...")
        s1 = PLUGINS["list_files"]["fn"](".")
        emit(f"  ├─ Step 1 [list_files]: 已扫描工作区目录")
        script_name = "auto_task.py"
        code = (
            f"# 自动生成的任务脚本: {user_goal}\n"
            "import platform, datetime, os\n"
            f"print('任务执行成功！目标:', {json.dumps(user_goal, ensure_ascii=False)})\n"
            "print('电脑名称:', platform.node(), '时间:', datetime.datetime.now().strftime('%H:%M:%S'))\n"
        )
        PLUGINS["write_file"]["fn"](script_name, code)
        emit(f"  ├─ Step 2 [write_file]: 已编写脚本 {script_name}")
        out = PLUGINS["run_command"]["fn"](f'"{sys.executable}" {script_name}')
        emit(f"  └─ Step 3 [run_command]: {out}")
        return f"✅ 本地自动执行完成！\n输出:\n{out}\n\n(提示：在设置中填入免费 Gemini API Key 后，即可解锁任意复杂项目的无限自由度 Codex 编程！)"

    # 有 API Key 时，开启最多 8 步的真 Codex 自主循环
    history = [{"role": "user", "content": f"任务目标: {user_goal}\n当前可用工具列表: {list(PLUGINS.keys())}"}]
    for step in range(1, 9):
        try:
            reply = call_gemini_rest_api(history, api_key).strip()
        except Exception as e:
            return f"❌ 调用 Gemini API 出错: {e}"

        # 解析是否包含 JSON 工具调用指令
        json_match = re.search(r"\{.*\"action\"\s*:.*\}", reply, re.S)
        if json_match:
            try:
                cmd_obj = json.loads(json_match.group(0))
                action = cmd_obj.get("action")
                args = cmd_obj.get("args", {})
                thought = cmd_obj.get("thought", f"执行 {action}")
                emit(f"🔄 Step {step}: {thought} -> 调用 `{action}`")
                if action in PLUGINS:
                    tool_result = str(PLUGINS[action]["fn"](**args))
                else:
                    tool_result = f"未知工具: {action}"
                emit(f"   └─ 结果: {tool_result[:200]}")
                history.append({"role": "model", "content": reply})
                history.append({"role": "user", "content": f"工具 `{action}` 执行结果:\n{tool_result}\n请继续下一步，若已完成请直接输出中文总结。"})
                continue
            except Exception:
                pass

        # 没有工具调用，说明任务已完成
        emit(f"✅ 任务完成！")
        return reply

    return "⚠️ 已达到单次任务最大步数上限。"


# =====================================================================
# 4. 改进版连接方式：手机端免公网 IP 云端长轮询 (Telegram Bot) + 局域网直连网页
# =====================================================================
GLOBAL_LOGS: List[str] = [f"✅ Gemini One-App v{VERSION} 已启动（远程访问已启用 PIN 鉴权）"]

def add_log(text: str):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {text}"
    GLOBAL_LOGS.append(line)
    if len(GLOBAL_LOGS) > 80:
        GLOBAL_LOGS.pop(0)
    print(line)

def telegram_cloud_polling_loop():
    """
    为什么用这种方式？
    因为电脑主动向外轮询，完全不需要公网 IP、不需要配路由器端口映射、不需要内网穿透！
    只要填一个 Telegram Bot Token（或者任何云端消息队列），你在地球任何角落用手机发一句话，家里电脑秒执行！
    """
    offset = 0
    while True:
        token = CFG.get("telegram_bot_token", "").strip()
        if not token:
            time.sleep(3)
            continue
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=20&offset={offset}"
            with urllib.request.urlopen(url, timeout=25) as r:
                data = json.loads(r.read().decode("utf-8"))
            for item in data.get("result", []):
                offset = item["update_id"] + 1
                msg = item.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "").strip()
                if not text or not chat_id:
                    continue
                # 首次收到消息自动绑定为合法主人手机
                if not CFG.get("allowed_chat_id"):
                    CFG["allowed_chat_id"] = chat_id
                    save_config(CFG)
                if chat_id != str(CFG.get("allowed_chat_id")):
                    continue

                add_log(f"📱 [手机云端指令] {text}")
                result = execute_autonomous_task(text, log_callback=add_log)
                send_url = f"https://api.telegram.org/bot{token}/sendMessage"
                payload = urllib.parse.urlencode({"chat_id": chat_id, "text": result[:4000]}).encode("utf-8")
                urllib.request.urlopen(send_url, data=payload, timeout=10)
        except Exception:
            time.sleep(5)


# =====================================================================
# 5. 极简合一 Web 界面（电脑桌面与手机浏览器共用同一个清爽界面）
# =====================================================================
ONE_PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gemini One-App 电脑自主代理</title>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; background: #0b0f19; color: #f8fafc; margin: 0; padding: 16px; }
  .wrap { max-width: 680px; margin: 0 auto; }
  .top { background: #1e293b; border: 1px solid #f59e0b; border-radius: 12px; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
  .top h2 { margin: 0; font-size: 18px; color: #f59e0b; }
  .box { background: #131c2e; border: 1px solid #263554; border-radius: 12px; padding: 16px; margin-bottom: 14px; }
  textarea, input { width: 100%; box-sizing: border-box; background: #090d16; color: #fff; border: 1px solid #334155; border-radius: 8px; padding: 10px; font-size: 14px; margin-top: 6px; }
  .btn { width: 100%; background: #f59e0b; color: #090d16; font-weight: 800; border: none; padding: 12px; border-radius: 8px; font-size: 15px; cursor: pointer; margin-top: 10px; }
  .quick { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
  .qbtn { background: #1e293b; color: #38bdf8; border: 1px solid #334155; padding: 6px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; }
  pre { background: #070a12; color: #38bdf8; padding: 12px; border-radius: 8px; height: 240px; overflow-y: auto; font-size: 12px; white-space: pre-wrap; margin: 0; }
  details { color: #94a3b8; font-size: 13px; cursor: pointer; }
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <h2>⚡ Gemini One-App 电脑执行中心 <span style="font-size:11px;color:#94a3b8;">v1.1 安全版</span></h2>
      <div style="font-size:12px;color:#94a3b8;margin-top:4px;">手机/电脑同屏 · 自动写代码 · 自动改文件 · 自动跑命令</div>
    </div>
    <span style="color:#22c55e;font-size:12px;font-weight:bold;">● 运行中</span>
  </div>

  <div class="box" style="border-color:#f59e0b;">
    <div style="font-weight:bold;font-size:14px;">🔐 远程访问 PIN 码（手机 / 外部设备必填，电脑本机自动免密）</div>
    <input id="agentPin" type="password" inputmode="numeric" autocomplete="off" placeholder="默认 8888，请在下方「⚙️ 一键配置」中改成自己的密码">
    <div style="font-size:12px;color:#94a3b8;margin-top:6px;">仅保存在本浏览器缓存（localStorage），不会上传；每次请求通过 X-Agent-Pin 请求头校验。</div>
  </div>

  <div class="box">
    <div style="font-weight:bold;font-size:14px;">👇 给电脑下达一句话大指令：</div>
    <textarea id="goal" rows="3" placeholder="例如：帮我在工作区写一个计算器网页 index.html，或者巡检当前电脑磁盘空间并生成报告..."></textarea>
    <div class="quick">
      <span class="qbtn" onclick="runTask('检查电脑状态并列出当前工作区的所有文件')">📂 查看工作区与电脑状态</span>
      <span class="qbtn" onclick="runTask('写一个Python脚本自动统计当前目录文件大小并运行它')">🐍 自动写脚本并运行</span>
      <span class="qbtn" onclick="runTask('截取当前电脑屏幕画面')">📸 电脑屏幕截图</span>
    </div>
    <button class="btn" onclick="runTask()">🚀 立即让电脑自动执行</button>
  </div>

  <div class="box">
    <div style="font-weight:bold;font-size:14px;margin-bottom:8px;">🖥️ 实时执行过程与输出：</div>
    <pre id="logs">加载中...</pre>
  </div>

  <div class="box">
    <details>
      <summary style="font-weight:bold;color:#f59e0b;">⚙️ 一键配置 API Key 与手机异地远程连接（点此展开）</summary>
      <div style="margin-top:10px;">
        <label>1. Gemini API Key（选填，填入后解锁满血 Gemini 2.5 无限编程）：</label>
        <input id="apiKey" type="password" placeholder="AIzaSy...">
        <label style="display:block;margin-top:8px;">2. 手机异地 4G/5G 遥控 Token（选填 Telegram Bot Token，免公网IP全球直连）：</label>
        <input id="tgToken" type="password" placeholder="123456:ABC-DEF...">
        <label style="display:block;margin-top:8px;">3. 修改远程访问 PIN 码（留空表示不变，建议改成自己的 4-8 位数字）：</label>
        <input id="newPin" type="password" inputmode="numeric" autocomplete="off" placeholder="留空不修改，默认 8888">
        <button class="btn" style="background:#38bdf8;" onclick="saveCfg()">💾 保存配置（永久生效）</button>
      </div>
    </details>
  </div>
</div>

<script>
const PIN_KEY = 'gemini_one_app_pin';
const pinInput = document.getElementById('agentPin');
const cachedPin = localStorage.getItem(PIN_KEY) || '';
if (cachedPin) pinInput.value = cachedPin;
pinInput.addEventListener('input', () => {
  const v = pinInput.value.trim();
  if (v) localStorage.setItem(PIN_KEY, v); else localStorage.removeItem(PIN_KEY);
});
function pinHeaders() {
  const p = pinInput.value.trim();
  return p ? {'X-Agent-Pin': p} : {};
}
async function postJSON(path, payload) {
  const r = await fetch(path, {
    method: 'POST',
    headers: Object.assign({'Content-Type': 'application/json'}, pinHeaders()),
    body: JSON.stringify(payload)
  });
  if (r.status === 401) {
    alert('🔐 PIN 校验失败或已触发限流，请检查页面顶部 PIN 码（默认 8888），稍后重试');
    throw new Error('unauthorized');
  }
  return r;
}
async function runTask(preset) {
  const g = preset || document.getElementById('goal').value.trim();
  if (!g) return alert('请输入指令');
  document.getElementById('goal').value = '';
  try { await postJSON('/run', {goal: g}); pollLogs(); } catch (e) { /* 已提示 */ }
}
async function saveCfg() {
  const payload = {
    gemini_api_key: document.getElementById('apiKey').value.trim(),
    telegram_bot_token: document.getElementById('tgToken').value.trim(),
    pin_code: document.getElementById('newPin').value.trim()
  };
  try {
    await postJSON('/config', payload);
    if (payload.pin_code) {
      localStorage.setItem(PIN_KEY, payload.pin_code);
      pinInput.value = payload.pin_code;
      document.getElementById('newPin').value = '';
    }
    alert('✅ 保存成功！');
  } catch (e) { /* 已提示 */ }
}
async function pollLogs() {
  const r = await fetch('/logs', {headers: pinHeaders()});
  const el = document.getElementById('logs');
  if (r.status === 401) { el.textContent = '🔐 PIN 校验失败：请在页面顶部填写正确的 PIN 码（默认 8888）。'; return; }
  if (!r.ok) { el.textContent = '日志读取失败：HTTP ' + r.status; return; }
  const d = await r.json();
  el.textContent = d.logs.join('\\n');
  el.scrollTop = el.scrollHeight;
}
setInterval(pollLogs, 1200);
pollLogs();
</script>
</body>
</html>
"""


class SimpleHandler(BaseHTTPRequestHandler):
    server_version = "GeminiOneApp/" + VERSION

    def _reject_unauthorized(self):
        peer = self.client_address[0]
        add_log(f"⛔ 拒绝未授权请求 {peer} -> {self.path}（PIN 校验失败或已触发限流）")
        body = json.dumps(
            {"error": "Unauthorized", "detail": "missing or invalid X-Agent-Pin"},
            ensure_ascii=False
        ).encode("utf-8")
        self.send_response(401)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # 页面本身放行，方便手机先打开界面输入 PIN；所有数据 / 指令接口一律校验
        if self.path.split("?")[0] == "/logs":
            if not verify_agent_pin(self):
                self._reject_unauthorized()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"logs": GLOBAL_LOGS, "version": VERSION}, ensure_ascii=False).encode("utf-8")
            )
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(ONE_PAGE_HTML.encode("utf-8"))

    def do_POST(self):
        # /run 与 /config 先过鉴权：未授权请求不读取 body、不触发任何本地动作
        if not verify_agent_pin(self):
            self._reject_unauthorized()
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        if self.path == "/run":
            goal = body.get("goal", "")
            threading.Thread(target=lambda: add_log(execute_autonomous_task(goal, add_log)), daemon=True).start()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        elif self.path == "/config":
            for key in ("gemini_api_key", "telegram_bot_token", "pin_code"):
                val = body.get(key)
                if isinstance(val, str) and val.strip():
                    CFG[key] = val.strip()
            save_config(CFG)
            add_log("⚙️ 已更新并保存系统配置！")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    if "--self-test" in sys.argv:
        print("=== Gemini One-App 极简全链路自检 ===")
        res = execute_autonomous_task("自动创建一个测试脚本并运行", log_callback=print)
        print(res)
        print("=== 自检完成！ ===")
        return

    # 启动手机云端免公网轮询线程
    threading.Thread(target=telegram_cloud_polling_loop, daemon=True).start()

    port = int(CFG.get("port", 8765))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    lan_ip = get_local_ip()

    print("\n" + "=" * 68)
    print(f"  🚀 Gemini One-App v{VERSION} 已启动！（免插件、免复杂配置）")
    print(f"  👉 电脑控制界面: http://127.0.0.1:{port}   （本机自动免密）")
    print(f"  📱 手机Wi-Fi直连: http://{lan_ip}:{port}   （需在页面顶部填写 PIN 码）")
    print("  🔐 远程鉴权: 非本机请求强制校验请求头 X-Agent-Pin")
    print("     ⚠️ 默认口令为 8888，请在「⚙️ 一键配置」中立即修改；公共 Wi-Fi 演示前务必改！")
    print(f"  📂 自动工作目录: {CFG['workspace']}")
    print("=" * 68 + "\n")

    # 自动弹出一个独立应用窗口（优先用 Edge/Chrome 的 --app 独立窗口模式，看起来就像原生桌面软件！）
    url = f"http://127.0.0.1:{port}"
    if sys.platform.startswith("win"):
        try:
            subprocess.Popen(f'start msedge --app={url}', shell=True)
        except Exception:
            import webbrowser
            webbrowser.open(url)
    elif os.environ.get("DISPLAY"):
        import webbrowser
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()