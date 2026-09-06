"""Browser-facing runtime event replay and run control endpoints."""
from __future__ import annotations

import json
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api import runs

router = APIRouter(tags=["runs"])


class RuntimeControlRequest(BaseModel):
    action: Literal["pause", "resume", "abort", "retry", "steer", "follow-up"]
    message: str = Field(default="", max_length=12000)
    agent_id: str = Field(default="", max_length=200)


def _state(run_id: str):
    state = runs.run_store.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run 不存在")
    return state


def _sse(event: dict) -> str:
    event_type = str(event.get("type", "event"))
    payload = dict(event)
    if event_type in {"text_delta", "text_completed"}:
        payload["status"] = "candidate"
    return (
        f"id: {event['cursor']}\n"
        f"event: runtime.{event_type}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


@router.get("/runs/{run_id}/events", include_in_schema=False)
def get_runtime_events(run_id: str, after: int = Query(default=0, ge=0)) -> StreamingResponse:
    state = _state(run_id)

    def stream():
        cursor = after
        while True:
            events = runs.run_store.list_runtime_events(run_id, after=cursor)
            if events:
                for event in events:
                    cursor = max(cursor, int(event["cursor"]))
                    yield _sse(event)
                continue

            current = runs.run_store.get(run_id) or state
            if current.status in {
                "awaiting_review", "completed", "failed", "cancelled",
                "terminated", "cycle_exhausted",
            }:
                settled_cursor = cursor + 1
                task_context = getattr(current, "task_context", {}) or {}
                yield _sse({
                    "event_id": f"run-settled:{run_id}:{settled_cursor}",
                    "cursor": settled_cursor, "run_id": run_id,
                    "group_chat_id": current.group_chat_id, "type": "settled",
                    "payload": {"status": current.status},
                    "data_space": task_context.get("data_space", "synthetic"),
                    "task_id": getattr(current, "task_id", ""),
                    "document_scope": list(task_context.get(
                        "allowed_document_ids", task_context.get("document_ids", [])
                    )),
                    "timestamp": time.time(),
                })
                return
            yield ": keep-alive\n\n"
            time.sleep(0.05)

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/control", include_in_schema=False)
def control_run(run_id: str, body: RuntimeControlRequest) -> dict:
    state = _state(run_id)
    if body.action == "pause":
        state.control_state = "pause_requested"
    elif body.action == "resume":
        state.control_state = "running"
    elif body.action == "abort":
        state.control_state = "aborted"
        state.status = "terminated"
        state.phase = "terminated"
        state.error = "Run 已由用户中止"
    elif body.action == "retry":
        if runs.is_multi_agent_task_run(state):
            target_id = body.agent_id.strip() or state.current_agent_id
            if not target_id:
                raise HTTPException(status_code=422, detail="retry 需要 agent_id")
            try:
                runs.retry_live_task_agent(state.run_id, target_id)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        else:
            state.control_state = "retry_requested"
            if state.status in {"failed", "terminated"}:
                state.status = "running"
    else:
        state.control_state = f"{body.action}_requested"
    state.persist()
    return {
        "run_id": state.run_id, "status": state.status,
        "control_state": state.control_state,
    }
