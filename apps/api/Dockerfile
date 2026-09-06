# syntax=docker/dockerfile:1

# ForumMind API — FastAPI 后端服务镜像。
#
# 构建上下文为 apps/api（Task 13 的 docker-compose 也从同一上下文构建）：
#   docker build -t forummind-api ./apps/api
# 运行：
#   docker run --rm -p 8000:8000 forummind-api
#
# 设计约束（changes/design.md §8.4）：基础镜像固定版本、不复制 .env/缓存/测试产物。

# 固定稳定基础镜像，禁止 latest，保证可复现（pyproject requires-python >=3.11）。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# 安装 uv 并固定为生成 uv.lock 的版本；依赖清单只来自 pyproject.toml / uv.lock，
# 不手工维护第二份依赖列表。
RUN pip install --no-cache-dir "uv==0.11.29"

# 先安装锁定依赖以利用层缓存：--frozen 严格按 uv.lock 安装，
# --no-install-project 不构建项目本身（运行时从 /app 直接导入 app 包）。
# dev 可选依赖（pytest/httpx）不在默认安装范围内，不会进入镜像。
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# 只复制应用代码（.dockerignore 已排除虚拟环境、缓存、测试等）。
COPY app ./app

# API 服务端口。
EXPOSE 8000

# 启动 FastAPI 服务（uvicorn 由 uv sync 装入 .venv）。
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
