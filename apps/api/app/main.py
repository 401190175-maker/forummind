"""ForumMind API 启动入口。

本模块仅提供启动级能力（根路径、/health、/version 等）并注册
业务 router，不承载业务逻辑；应用启动时初始化 SQLite，业务模块
各自负责数据访问和 Agent/runtime 调用边界。
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import runs as runs_api
from app.api import documents as documents_api
from app.api import research_tasks as research_tasks_api
from app.api import candidates as candidates_api
from app.api import experiments as experiments_api
from app.api.group_chats import router as group_chats_router
from app.api.meeting_rehearsal import router as meeting_rehearsal_router
from app.api.runtime_settings import router as runtime_settings_router
from app.api.runtime_internal import router as runtime_internal_router
from app.api import runtime_internal as runtime_internal_api
from app.api.runtime_events import router as runtime_events_router
from app.agent_runtime.config import runtime_config
from app.agents import service as agents_service
from app.group_chats import creation_service, messages
from app.schemas import HealthResponse, VersionResponse
from app.storage.sqlite_store import SQLiteStore
from app.meeting.scheduler import MeetingScheduler, schedule_service

SERVICE_NAME = "forummind-api"
API_VERSION = "0.1.0"
CORS_ORIGINS_DEFAULT = "http://localhost:3000"
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "forummind.db"
DEFAULT_EXPERIMENT_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "data" / "experiment-sources"


def resolve_db_path() -> Path:
    """Return the configured SQLite path without exposing it through the API."""
    raw_path = os.getenv("FORUMMIND_DB_PATH")
    return Path(raw_path) if raw_path else DEFAULT_DB_PATH


def resolve_experiment_source_root() -> Path:
    """Return the private root used to retain imported experiment sources."""
    raw_path = os.getenv("FORUMMIND_EXPERIMENT_SOURCE_ROOT")
    return Path(raw_path) if raw_path else DEFAULT_EXPERIMENT_SOURCE_ROOT


app_store = SQLiteStore(resolve_db_path())
schedule_service.configure_persistence(app_store)


def trigger_scheduled_run(group_chat_id: str) -> str:
    """Start the same server-owned automatic run used by the UI."""
    response = runs_api.start_run(group_chat_id, runs_api.RunRequest(mode="auto"))
    return str(response["run_id"])


meeting_scheduler = MeetingScheduler(
    schedule_service.repository,  # type: ignore[arg-type]
    trigger=trigger_scheduled_run,
)


def configure_application_persistence() -> None:
    """Initialize and connect all application modules to the shared Store."""
    app_store.initialize()
    agents_service.configure_persistence(app_store)
    creation_service.configure_persistence(app_store)
    messages.configure_persistence(app_store)
    documents_api.configure_persistence(app_store)
    research_tasks_api.configure_persistence(app_store)
    candidates_api.configure_persistence(app_store)
    runs_api.run_store.configure_persistence(app_store)
    runs_api.configure_persistence(app_store)
    runtime_internal_api.configure_persistence(app_store)
    experiments_api.configure_persistence(
        app_store,
        source_root=resolve_experiment_source_root(),
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Own the application Store for normal FastAPI startup and shutdown."""
    configure_application_persistence()
    meeting_scheduler.start()
    try:
        yield
    finally:
        meeting_scheduler.stop()
        runtime_config.clear()
        app_store.close()


def get_environment() -> str:
    """返回当前运行环境，默认 development。"""
    return os.getenv("ENVIRONMENT", "development")


def get_cors_origins() -> list[str]:
    """返回允许跨域访问的来源列表，默认仅本地前端。"""
    raw = os.getenv("CORS_ORIGINS", CORS_ORIGINS_DEFAULT)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


configure_application_persistence()

app = FastAPI(
    title="ForumMind API",
    version=API_VERSION,
    description="ForumMind 后端启动级骨架（不含业务逻辑）。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["*"],
)

# 注册业务 router（POST /group-chats + runs 端点；main.py 不承载业务逻辑）。
app.include_router(group_chats_router)
app.include_router(documents_api.router)
app.include_router(experiments_api.router)
app.include_router(research_tasks_api.router)
app.include_router(candidates_api.router)
app.include_router(runs_api.router)
app.include_router(meeting_rehearsal_router)
app.include_router(runtime_settings_router)
app.include_router(runtime_internal_router)
app.include_router(runtime_events_router)


@app.get("/")
def root() -> dict[str, str]:
    """返回基础服务信息。"""
    return {
        "service": SERVICE_NAME,
        "message": "ForumMind API skeleton is running.",
    }


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """返回 API 存活状态，不检查数据库、LLM 或外部依赖。"""
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        environment=get_environment(),
    )


@app.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    """返回服务版本信息，不暴露密钥或系统路径。"""
    return VersionResponse(
        service=SERVICE_NAME,
        version=API_VERSION,
        environment=get_environment(),
    )
