import json
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from fabric_data_agent_client import (
    DEFAULT_TIMEOUT,
    FabricDataAgentClient,
    format_fabric_error,
    is_fabric_access_error,
    is_retryable_fabric_error,
)
from auth_service import (
    FABRIC_TOKEN_MODE,
    clear_fabric_token_caches,
    get_auth_status,
    get_authenticated_session,
    login_with_access_token,
    login_with_auth_code,
    logout,
)
from chat_history_db import (
    get_chat_history,
    init_db,
    purge_expired_chat_history,
    save_chat_history,
)
from agent_suggestions import (
    clear_suggestion_cache,
    generate_agent_suggestions,
    generate_followup_suggestions,
)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TENANT_ID = os.getenv("TENANT_ID", "aa8801bcb-7990-408e-ab0c-e73eccd70288")
AGENTS_FILE = Path(__file__).parent / "agents.json"

_clients: dict[str, FabricDataAgentClient] = {}
_session_threads: dict[str, str] = {}
_agents_cache: list[dict] | None = None


def reset_runtime_state() -> None:
    """Drop in-memory Fabric clients and thread maps when the signed-in user changes."""
    global _agents_cache
    _agents_cache = None
    _clients.clear()
    _session_threads.clear()
    clear_suggestion_cache()
    clear_fabric_token_caches()


def load_agents() -> list[dict]:
    global _agents_cache
    if _agents_cache is not None:
        return _agents_cache

    env_data_agent_url = os.getenv("DATA_AGENT_URL", "").strip()

    if AGENTS_FILE.exists():
        with AGENTS_FILE.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        agents = payload.get("agents", [])
        if env_data_agent_url:
            for agent in agents:
                agent["data_agent_url"] = env_data_agent_url
    else:
        agents = [{
            "id": "default",
            "name": "Data Agent",
            "description": "Default Fabric Data Agent",
            "data_agent_url": env_data_agent_url or (
                "https://api.fabric.microsoft.com/v1/workspaces/411f437b-71b5-4416-b399-86a34e5518dc/"
                "dataagents/c8ba6773-005d-42dc-85c6-7cae2a9dc726/aiassistant/openai"
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


def get_client(agent_id: str, user_email: Optional[str] = None) -> FabricDataAgentClient:
    cache_key = f"{(user_email or 'anonymous').strip().lower()}:{agent_id}"
    if cache_key in _clients:
        return _clients[cache_key]

    agent = get_agent(agent_id)
    _clients[cache_key] = FabricDataAgentClient(
        tenant_id=TENANT_ID,
        data_agent_url=agent["data_agent_url"],
    )
    return _clients[cache_key]


def _reset_chat_thread(user_email: Optional[str], session_id: Optional[str], agent_id: str) -> str:
    key = _thread_key(user_email, session_id, agent_id)
    _session_threads.pop(key, None)
    thread_name = f"web-session-{uuid.uuid4()}"
    _session_threads[key] = thread_name
    return thread_name


def _run_chat_question(
    client: FabricDataAgentClient,
    question: str,
    thread_name: str,
    timeout: int,
    include_details: bool,
) -> dict:
    if include_details:
        return client.ask_with_details(
            question,
            timeout=timeout,
            thread_name=thread_name,
            preserve_thread=True,
        )

    answer = client.ask(
        question,
        timeout=timeout,
        thread_name=thread_name,
        preserve_thread=True,
    )
    return {
        "answer": answer,
        "thread": {"name": thread_name},
        "success": not FabricDataAgentClient.is_fabric_access_error(str(answer)),
        "run_status": "completed" if not FabricDataAgentClient.is_fabric_access_error(str(answer)) else "failed",
    }


def _thread_key(user_email: Optional[str], session_id: Optional[str], agent_id: str) -> str:
    return f"{user_email or 'anonymous'}:{session_id or 'anonymous'}:{agent_id}"


class ChatRequest(BaseModel):
    question: str
    agent_id: str = "stock-pulse"
    thread_name: Optional[str] = None
    timeout: int = Field(default=DEFAULT_TIMEOUT, ge=30, le=900)
    new_session: bool = False
    include_details: bool = True


class SessionRequest(BaseModel):
    agent_id: str = "stock-pulse"


class TokenLoginRequest(BaseModel):
    access_token: str
    token_expires_on: Optional[float] = None


class CodeLoginRequest(BaseModel):
    code: str
    redirect_uri: str
    code_verifier: str


class ChatHistorySaveRequest(BaseModel):
    agent_id: str
    messages: list[dict] = Field(default_factory=list)
    backend_session_id: str


class SuggestionExchange(BaseModel):
    question: str = ""
    answer: str = ""


class FollowupSuggestionsRequest(BaseModel):
    exchanges: list[SuggestionExchange] = Field(default_factory=list)
    timeout: int = Field(default=90, ge=30, le=300)


def _require_authenticated_session() -> dict:
    require_authenticated()
    session = get_authenticated_session()
    if not session or not session.get("user_email") or session.get("expires_at") is None:
        raise HTTPException(status_code=401, detail="Microsoft login required. Please sign in first.")
    return session


def _resolve_thread_name(
    request: ChatRequest,
    session_id: Optional[str],
    user_email: Optional[str],
) -> str:
    key = _thread_key(user_email, session_id, request.agent_id)

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


@app.on_event("startup")
async def startup() -> None:
    init_db()
    purge_expired_chat_history()
    print(f"Fabric token mode: {FABRIC_TOKEN_MODE}")


@app.get("/auth/status")
async def auth_status():
    return get_auth_status()


@app.post("/auth/login/code")
async def auth_login_code(request: CodeLoginRequest):
    try:
        reset_runtime_state()
        return login_with_auth_code(request.code, request.redirect_uri, request.code_verifier)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Microsoft login failed: {exc}") from exc


@app.post("/auth/login")
async def auth_login(request: TokenLoginRequest):
    try:
        reset_runtime_state()
        return login_with_access_token(request.access_token, request.token_expires_on)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Microsoft login failed: {exc}") from exc


@app.post("/auth/logout")
async def auth_logout():
    reset_runtime_state()
    return logout()


@app.get("/chat/history")
async def read_chat_history(agent_id: str):
    session = _require_authenticated_session()
    get_agent(agent_id)
    history = get_chat_history(
        session["user_email"],
        agent_id,
    )
    return history


@app.put("/chat/history")
async def write_chat_history(request: ChatHistorySaveRequest):
    session = _require_authenticated_session()
    get_agent(request.agent_id)
    save_chat_history(
        session["user_email"],
        request.agent_id,
        request.messages,
        request.backend_session_id,
    )
    return {"saved": True}


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


@app.get("/agents/{agent_id}/suggestions")
async def agent_suggestions(
    agent_id: str,
    force_refresh: bool = False,
    timeout: int = Query(default=120, ge=30, le=300),
):
    session = _require_authenticated_session()
    agent = get_agent(agent_id)
    client = get_client(agent_id, session["user_email"])
    suggestions = generate_agent_suggestions(
        client,
        agent,
        user_email=session["user_email"],
        timeout=timeout,
        force_refresh=force_refresh,
    )
    return {"agent_id": agent_id, "suggestions": suggestions}


@app.post("/agents/{agent_id}/suggestions/followup")
async def agent_followup_suggestions(agent_id: str, request: FollowupSuggestionsRequest):
    session = _require_authenticated_session()
    agent = get_agent(agent_id)
    client = get_client(agent_id, session["user_email"])
    exchanges = [exchange.model_dump() for exchange in request.exchanges]
    suggestions = generate_followup_suggestions(
        client,
        agent,
        exchanges,
        user_email=session["user_email"],
        timeout=request.timeout,
    )
    return {"agent_id": agent_id, "suggestions": suggestions}


@app.post("/chat")
async def chat(
    request: ChatRequest,
    x_session_id: Optional[str] = Header(default=None),
):
    session = _require_authenticated_session()
    get_agent(request.agent_id)
    client = get_client(request.agent_id, session["user_email"])
    thread_name = _resolve_thread_name(request, x_session_id, session["user_email"])

    result = _run_chat_question(
        client,
        request.question,
        thread_name,
        request.timeout,
        request.include_details,
    )

    answer_text = str(result.get("answer") or "")
    if is_retryable_fabric_error(answer_text):
        retry_thread = _reset_chat_thread(session["user_email"], x_session_id, request.agent_id)
        result = _run_chat_question(
            client,
            request.question,
            retry_thread,
            request.timeout,
            request.include_details,
        )
        answer_text = str(result.get("answer") or "")

    if is_fabric_access_error(answer_text):
        friendly = format_fabric_error(answer_text, session.get("user_email"))
        result["answer"] = friendly
        result["success"] = False
        result["run_status"] = "failed"

    return _format_chat_response(result, request.agent_id)


@app.post("/chat/details")
async def chat_details(
    request: ChatRequest,
    x_session_id: Optional[str] = Header(default=None),
):
    session = _require_authenticated_session()
    get_agent(request.agent_id)
    client = get_client(request.agent_id, session["user_email"])
    thread_name = _resolve_thread_name(request, x_session_id, session["user_email"])
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
    session = _require_authenticated_session()
    get_agent(request.agent_id)
    thread_name = f"web-session-{uuid.uuid4()}"
    key = _thread_key(session["user_email"], x_session_id, request.agent_id)
    _session_threads[key] = thread_name
    agent = get_agent(request.agent_id)
    return {
        "thread_name": thread_name,
        "agent_id": request.agent_id,
        "agent_name": agent["name"],
    }
