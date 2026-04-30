'''
FundAgent — 基金本子多 Agent Web 应用
  3 个 Agent: 研究背景(bg, kimi-k2.6+联网搜索) / 初稿(draft, deepseek) / 段落修改(revise, deepseek)
'''

# ════════════════════════════════════════════════════════════════
# imports
# ════════════════════════════════════════════════════════════════
import os
import re
import json
import subprocess
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from openai import OpenAI
from dotenv import load_dotenv

# ════════════════════════════════════════════════════════════════
# 手动加载 .env（Windows 下为 GBK 编码，load_dotenv 会乱码）
# ════════════════════════════════════════════════════════════════
import sys
def _load_dotenv_gbk():
    p = Path(__file__).parent / '.env'
    if p.exists():
        with open(p, 'r', encoding='gbk') as f:
            for line in f:
                line = line.strip()
                if line and '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip()

_load_dotenv_gbk()

# ════════════════════════════════════════════════════════════════
# DeepSeek（draft / revise agent 使用）
# ════════════════════════════════════════════════════════════════
API_KEY = os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# ════════════════════════════════════════════════════════════════
# prompts 文件夹
# ════════════════════════════════════════════════════════════════
PROMPT_DIR = Path(__file__).parent / "prompts"

# ════════════════════════════════════════════════════════════════
# 3 个 Agent 定义
#   bg:    研究背景 agent — 用 kimi-k2.6 + $web_search 搜索生成
#   draft: 初稿 agent     — 用 DeepSeek 聊天
#   revise:段落修改 agent  — 用 DeepSeek 聊天 + 解析修改表格
# ════════════════════════════════════════════════════════════════
AGENTS = {
    "bg": {
        "id": "bg",
        "label": "研究背景 Agent",
        "prompt_file": None,
    },
    "draft": {
        "id": "draft",
        "label": "初稿 Agent",
        "prompt_file": "draft.md",
    },
    "revise": {
        "id": "revise",
        "label": "段落修改 Agent",
        "prompt_file": "reviser.md",
    },
}

# ════════════════════════════════════════════════════════════════
# 对话历史（按 agent 隔离，最多保留 5 轮=10 条消息）
# ════════════════════════════════════════════════════════════════
MAX_ROUNDS = 5
histories: dict[str, list[dict]] = {}


def get_history(agent_id: str) -> list[dict]:
    return histories.setdefault(agent_id, [])


def add_to_history(agent_id: str, role: str, content: str):
    h = get_history(agent_id)
    h.append({"role": role, "content": content})
    max_msgs = MAX_ROUNDS * 2
    if len(h) > max_msgs:
        del h[: len(h) - max_msgs]


def reset_history(agent_id: str):
    histories[agent_id] = []


# ════════════════════════════════════════════════════════════════
# 从 prompts 目录加载 system prompt
# ════════════════════════════════════════════════════════════════
def load_system_prompt(agent_id: str) -> str:
    p = AGENTS.get(agent_id)
    if not p:
        return ""
    f = PROMPT_DIR / p["prompt_file"]
    if not p.get("prompt_file") or not f.exists():
        return ""
    return f.read_text(encoding="utf-8")


# ════════════════════════════════════════════════════════════════
# draft / revise 通用的 DeepSeek LLM 调用
#   - 拼接 system prompt → 历史 → 当前输入
# ════════════════════════════════════════════════════════════════
def call_llm(agent_id: str, user_input: str) -> str:
    sys_prompt = load_system_prompt(agent_id)
    messages = [{"role": "system", "content": sys_prompt}]
    messages.extend(get_history(agent_id))
    messages.append({"role": "user", "content": user_input})

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=4096,
    )
    return resp.choices[0].message.content or ""


# ════════════════════════════════════════════════════════════════
# 解析 revise agent 输出的修改说明表格（markdown 格式）
# ════════════════════════════════════════════════════════════════
def parse_changes(reply: str) -> list[dict]:
    changes = []
    section = reply.split("## 修改说明")[-1] if "## 修改说明" in reply else ""
    section = section.split("##")[0]
    rows = re.findall(r"\|(\s*\d+\s*)\|(.*?)\|(.*?)\|(.*?)\|", section, re.DOTALL)
    for row in rows:
        changes.append({
            "original": row[1].strip(),
            "modified": row[2].strip(),
            "reason": row[3].strip(),
        })
    return changes


# ════════════════════════════════════════════════════════════════
# FastAPI 应用
# ════════════════════════════════════════════════════════════════
app = FastAPI(title="FundAgent")
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


class ChatRequest(BaseModel):
    text: str
    agent: str = "revise"


# ════════════════════════════════════════════════════════════════
# GET /  — 返回前端 HTML
# ════════════════════════════════════════════════════════════════
@app.get("/")
async def index():
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


# ════════════════════════════════════════════════════════════════
# GET /agents — 返回 agent 列表和当前模型名
# ════════════════════════════════════════════════════════════════
@app.get("/agents")
async def list_agents():
    return {
        "agents": {
            aid: {"id": aid, "label": info["label"]}
            for aid, info in AGENTS.items()
        },
        "current_model": MODEL,
    }


# ════════════════════════════════════════════════════════════════
# POST /chat — 核心对话接口
#   bg:    kimi-k2.6 + $web_search（Kimi 内置联网搜索工具）
#   draft: call_llm / deepseek
#   revise:call_llm / deepseek + parse_changes
# ════════════════════════════════════════════════════════════════
@app.post("/chat")
async def chat(req: ChatRequest):
    agent_id = req.agent
    if agent_id not in AGENTS:
        return JSONResponse({"detail": f"未知 Agent: {agent_id}"}, status_code=400)
    if not req.text.strip():
        return JSONResponse({"detail": "输入不能为空"}, status_code=400)

    try:

        # ── bg agent ────────────────────────────────────────────
        # 用 kimi-k2.6 + builtin_function.$web_search 实现联网搜索
        # 流程：发送请求 → 若返回 tool_calls → 执行搜索 → 继续对话
        # ─────────────────────────────────────────────────────────
        if agent_id == "bg":
            print(f"[BG] 用户输入: {req.text[:60]}...")

            # 读 search api key (来自 .env, GBK)
            search_key = ""
            env_p = Path(__file__).parent / '.env'
            if env_p.exists():
                with open(env_p, 'r', encoding='gbk') as f:
                    for line in f:
                        if 'SEARCH_API_KEY' in line and '=' in line:
                            search_key = line.split('=', 1)[1].strip()
                            break

            # 加载 background.md 作为 system prompt
            bg_prompt_path = PROMPT_DIR / "background.md"
            sys_prompt = bg_prompt_path.read_text(encoding="utf-8") if bg_prompt_path.exists() else ""

            client = OpenAI(
                api_key=search_key or API_KEY,
                base_url="https://api.moonshot.cn/v1",
            )

            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": req.text}
            ]
            tools = [
                {
                    "type": "builtin_function",
                    "function": {"name": "$web_search"},
                }
            ]

            # tool_calls 循环：模型决定要不要搜索
            finish_reason = None
            while finish_reason is None or finish_reason == "tool_calls":
                print(f"[BG] tool_calls loop...")
                completion = client.chat.completions.create(
                    model="kimi-k2.6",
                    messages=messages,
                    tools=tools,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                choice = completion.choices[0]
                finish_reason = choice.finish_reason

                if finish_reason == "tool_calls":
                    messages.append(choice.message)
                    for tool_call in choice.message.tool_calls:
                        tool_call_name = tool_call.function.name
                        tool_call_args = json.loads(tool_call.function.arguments)
                        if tool_call_name == "$web_search":
                            tool_result = tool_call_args
                        else:
                            tool_result = {"error": f"unknown tool: {tool_call_name}"}
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call_name,
                            "content": json.dumps(tool_result),
                        })

            output = choice.message.content or ""
            add_to_history("bg", "user", req.text)
            add_to_history("bg", "assistant", output)
            print(f"[BG] 完成: {len(output)} chars")

            return {
                "output": output,
                "changes": [],
                "model": "kimi-k2.6",
                "agent": "bg",
            }

        # ── draft / revise agent ────────────────────────────────
        reply = call_llm(agent_id, req.text)
        add_to_history(agent_id, "user", req.text)
        add_to_history(agent_id, "assistant", reply)

        result = {"output": "", "changes": [], "model": MODEL, "agent": agent_id}

        # revise agent 特殊处理：分离正文和修改说明表格
        if agent_id == "revise":
            changes = parse_changes(reply)
            display = (
                reply.split("## 修改说明")[0].strip()
                if "## 修改说明" in reply
                else reply.strip()
            )
            display = (
                display.split("## 修改建议")[0].strip()
                if "## 修改建议" in display
                else display
            )
            result["output"] = display
            result["changes"] = changes
        else:
            result["output"] = reply

        return result

    except Exception as e:
        return JSONResponse({"detail": f"调用 LLM 失败: {str(e)}"}, status_code=500)


# ════════════════════════════════════════════════════════════════
# POST /reset — 清空指定 agent 或全部历史
# ════════════════════════════════════════════════════════════════
@app.post("/reset")
async def reset(agent: str = "all"):
    if agent == "all":
        histories.clear()
    elif agent in AGENTS:
        reset_history(agent)
    return {"ok": True}


# ════════════════════════════════════════════════════════════════
# 入口：自动杀 8000 端口旧进程，启动 uvicorn
# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    import subprocess

    try:
        result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        for line in result.stdout.split('\n'):
            if ':8000' in line and 'LISTENING' in line:
                parts = line.strip().split()
                pid = parts[-1]
                if pid != str(os.getpid()):
                    subprocess.run(['taskkill', '/f', '/pid', pid], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    print(f"[Auto] Killed old process PID={pid} on port 8000")
    except:
        pass

    port = int(os.getenv("PORT", "8000"))
    print(f"FundAgent running at http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info", reload=False, workers=1)
