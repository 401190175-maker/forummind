"""真组会预演 router 注册测试（tasks.md Task 7）。"""

from app.main import app


def test_main_registers_all_meeting_rehearsal_routes() -> None:
    paths = set(app.openapi()["paths"])

    assert "/group-chats/{group_chat_id}/meeting-rehearsals" in paths
    assert "/meeting-rehearsals/{session_id}" in paths
    assert "/meeting-rehearsals/{session_id}/answers" in paths
    assert "/meeting-rehearsals/{session_id}/preparation-package" in paths


def test_main_keeps_existing_startup_group_chat_and_run_routes() -> None:
    paths = set(app.openapi()["paths"])

    assert {"/", "/health", "/version"}.issubset(paths)
    assert "/group-chats" in paths
    assert "/group-chats/{group_chat_id}/runs" in paths
    assert "/runs/{run_id}" in paths
