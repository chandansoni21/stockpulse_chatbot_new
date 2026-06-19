import json
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from fabric_data_agent_client import DEFAULT_TIMEOUT, FabricDataAgentClient
from auth_service import get_auth_status, login_interactive, logout, is_session_valid

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TENANT_ID = os.getenv("TENANT_ID", "aca0b239-69e9-4246-87ba-8e07ad0a9249")
AGENTS_FILE = Path(__file__).parent / "agents.json"

_clients: dict[str, FabricDataAgentClient] = {}
_session_threads: dict[str, str] = {}
_agents_cache: list[dict] | None = None


def load_agents() -> list[dict]:
    global _agents_cache
    if _agents_cache is not None:
        return _agents_cache

    if AGENTS_FILE.exists():
        with AGENTS_FILE.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        agents = payload.get("agents", [])
    else:
        agents = [{
            "id": "default",
            "name": "Data Agent",
            "description": "Default Fabric Data Agent",
            "data_agent_url": os.getenv(
                "DATA_AGENT_URL",
                "https://api.fabric.microsoft.com/v1/workspaces/f86b0adb-cc7d-4466-85ea-b94d20e7926a/dataagents/e1534133-1784-4553-946f-7d32857afc5d/aiassistant/openai",
            ),
        }]

    if not agents:
        raise RuntimeError("No agents configured. Add entries to backend/agents.json")

    _agents_cache = agents
    return agents


def get_agent(agent_id: str) -> dict:
    for agent in load_agents():
        if agent["id"] == agent_id:
            return agent
    raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")


def get_client(agent_id: str) -> FabricDataAgentClient:
    if agent_id in _clients:
        return _clients[agent_id]

    agent = get_agent(agent_id)
    _clients[agent_id] = FabricDataAgentClient(
        tenant_id=TENANT_ID,
        data_agent_url=agent["data_agent_url"],
    )
    return _clients[agent_id]


def _thread_key(session_id: Optional[str], agent_id: str) -> str:
    return f"{session_id or 'anonymous'}:{agent_id}"


class ChatRequest(BaseModel):
    question: str
    agent_id: str = "stock-pulse"
    thread_name: Optional[str] = None
    timeout: int = Field(default=DEFAULT_TIMEOUT, ge=30, le=900)
    new_session: bool = False
    include_details: bool = True


class SessionRequest(BaseModel):
    agent_id: str = "stock-pulse"


def _resolve_thread_name(request: ChatRequest, session_id: Optional[str]) -> str:
    key = _thread_key(session_id, request.agent_id)

    if request.new_session:
        thread_name = f"web-session-{uuid.uuid4()}"
        _session_threads[key] = thread_name
        return thread_name

    if request.thread_name:
        _session_threads[key] = request.thread_name
        return request.thread_name

    if key in _session_threads:
        return _session_threads[key]

    thread_name = f"web-session-{uuid.uuid4()}"
    _session_threads[key] = thread_name
    return thread_name


def _format_chat_response(result: dict, agent_id: str) -> dict:
    thread = result.get("thread") or {}
    previews = result.get("sql_data_previews") or []
    flat_preview = []
    for preview in previews:
        if isinstance(preview, list):
            flat_preview.extend(preview)
        elif preview:
            flat_preview.append(str(preview))

    return {
        "answer": result.get("answer"),
        "agent_id": agent_id,
        "reframed_query": result.get("reframed_query"),
        "sql_queries": result.get("sql_queries") or [],
        "data_retrieval_query": result.get("data_retrieval_query"),
        "sql_data_preview": flat_preview[:20],
        "run_status": result.get("run_status"),
        "success": result.get("success", True),
        "thread_name": thread.get("name"),
        "error": result.get("error"),
    }


def require_authenticated():
    if not get_auth_status()["authenticated"]:
        raise HTTPException(status_code=401, detail="Microsoft login required. Please sign in first.")


@app.get("/auth/status")
async def auth_status():
    return get_auth_status()


@app.post("/auth/login")
async def auth_login():
    try:
        return login_interactive()
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Microsoft login failed: {exc}") from exc


@app.post("/auth/logout")
async def auth_logout():
    _clients.clear()
    return logout()


@app.get("/agents")
async def list_agents():
    require_authenticated()
    agents = load_agents()
    return {
        "agents": [
            {
                "id": agent["id"],
                "name": agent["name"],
                "description": agent.get("description", ""),
            }
            for agent in agents
        ]
    }


@app.post("/chat")
async def chat(
    request: ChatRequest,
    x_session_id: Optional[str] = Header(default=None),
):
    require_authenticated()
    get_agent(request.agent_id)
    client = get_client(request.agent_id)
    thread_name = _resolve_thread_name(request, x_session_id)

    if request.include_details:
        result = client.ask_with_details(
            request.question,
            timeout=request.timeout,
            thread_name=thread_name,
            preserve_thread=True,
        )
    else:
        answer = client.ask(
            request.question,
            timeout=request.timeout,
            thread_name=thread_name,
            preserve_thread=True,
        )
        result = {
            "answer": answer,
            "thread": {"name": thread_name},
            "success": not str(answer).startswith("Error:"),
            "run_status": "completed" if not str(answer).startswith("Error:") else "failed",
        }

    return _format_chat_response(result, request.agent_id)


@app.post("/chat/details")
async def chat_details(
    request: ChatRequest,
    x_session_id: Optional[str] = Header(default=None),
):
    require_authenticated()
    get_agent(request.agent_id)
    client = get_client(request.agent_id)
    thread_name = _resolve_thread_name(request, x_session_id)
    return client.get_run_details(
        request.question,
        thread_name=thread_name,
        timeout=request.timeout,
    )


@app.post("/session/new")
async def new_session(
    request: SessionRequest,
    x_session_id: Optional[str] = Header(default=None),
):
    require_authenticated()
    get_agent(request.agent_id)
    thread_name = f"web-session-{uuid.uuid4()}"
    key = _thread_key(x_session_id, request.agent_id)
    _session_threads[key] = thread_name
    agent = get_agent(request.agent_id)
    return {
        "thread_name": thread_name,
        "agent_id": request.agent_id,
        "agent_name": agent["name"],
    }
