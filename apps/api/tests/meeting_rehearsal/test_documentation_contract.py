"""真组会预演文档状态契约测试（tasks.md Task 9）。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
DOCUMENTS = [ROOT / "architecture.md", ROOT / "modules.md", ROOT / "readme.md"]


def test_core_documents_describe_rehearsal_boundary_and_api() -> None:
    required = [
        "真组会预演",
        "POST /group-chats/{group_chat_id}/meeting-rehearsals",
        "GET /meeting-rehearsals/{session_id}",
        "record_scope=rehearsal",
        "persistence=not_persisted",
        "正式 `ResearchState`",
    ]

    for document in DOCUMENTS:
        content = document.read_text(encoding="utf-8")
        for phrase in required:
            assert phrase in content, f"{document.name} 缺少: {phrase}"


def test_core_documents_do_not_claim_rehearsal_is_formal_or_persisted() -> None:
    forbidden = [
        "预演准备包是正式会议纪要",
        "真组会预演已接入 Pi runtime",
        "真组会预演已持久化",
    ]

    for document in DOCUMENTS:
        content = document.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in content, f"{document.name} 出现越界表述: {phrase}"
