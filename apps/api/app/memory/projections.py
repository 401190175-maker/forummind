"""Memory Projection 层：把 raw MemoryEntry 投影为时间轴、版本树与证据图谱。

设计（design.md §2.5、§4.3、§6.6）：

- `build_timeline`：按 `created_at` 排序，回答“什么时候发生了什么”。
- `build_version_tree`：保留 `id` / `kind` / `object_key` / `version` / `supersedes`，
  回答“某个对象如何被 supersede 或分支”。
- `build_evidence_graph`：第一版生成对象节点与 `supersedes` 边，
  Claim/Evidence 等关系在 payload 稳定后再扩展。
- payload 缺少预期字段时使用 fallback summary，不抛异常。

边界约定：

- 只读投影，不修改 raw entries，不改动 `MemoryTimeline` 追加逻辑。
- 纯标准库，不依赖 FastAPI / 数据库 / 网络。
"""

from __future__ import annotations

from typing import Any

from app.memory.timeline import MemoryEntry

# payload 中优先作为摘要的字段（按顺序取第一个非空字符串）。
_SUMMARY_FIELDS = ("statement", "summary", "content", "mechanism_draft", "option")


def _payload_of(entry: MemoryEntry) -> dict[str, Any]:
    """返回 entry payload；非 dict 时回退空 dict，保证投影不抛异常。"""
    if isinstance(entry.payload, dict):
        return entry.payload
    return {}


def _summary(entry: MemoryEntry) -> str:
    """从 payload 提取可读摘要；缺失或类型不对时使用 fallback，不抛异常。"""
    payload = _payload_of(entry)
    for key in _SUMMARY_FIELDS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "（无摘要）"


def build_timeline(entries: list[MemoryEntry]) -> list[dict[str, Any]]:
    """时间轴：按 `created_at` 升序（同刻按 id 稳定排序），只读投影。"""
    ordered = sorted(entries, key=lambda e: (e.created_at, e.id))
    return [
        {
            "id": entry.id,
            "kind": entry.kind,
            "object_key": entry.object_key,
            "version": entry.version,
            "supersedes": entry.supersedes,
            "created_at": entry.created_at,
            "summary": _summary(entry),
            "data_space": entry.data_space,
        }
        for entry in ordered
    ]


def build_version_tree(entries: list[MemoryEntry]) -> list[dict[str, Any]]:
    """版本树：按对象（object_key 优先，缺省按 kind）与版本号分组排序。"""
    nodes = [
        {
            "id": entry.id,
            "kind": entry.kind,
            "object_key": entry.object_key,
            "version": entry.version,
            "supersedes": entry.supersedes,
            "summary": _summary(entry),
        }
        for entry in entries
    ]
    nodes.sort(key=lambda n: ((n["object_key"] or n["kind"]), n["version"]))
    return nodes


def _add_edge(
    edges: list[dict[str, str]],
    seen: set[tuple[str, str, str]],
    node_ids: set[str],
    source: Any,
    target: Any,
    relation: str,
) -> None:
    """仅在端点存在时追加去重边，坏引用静默跳过。"""
    if not isinstance(source, str) or source not in node_ids:
        return
    if not isinstance(target, str) or target not in node_ids:
        return
    key = (source, target, relation)
    if key in seen:
        return
    edges.append({"source": source, "target": target, "relation": relation})
    seen.add(key)


def build_evidence_graph(entries: list[MemoryEntry]) -> dict[str, list[dict[str, Any]]]:
    """证据图谱：对象节点、版本边和实验相关语义边（只读派生）。"""
    nodes = [
        {
            "id": entry.id,
            "kind": entry.kind,
            "object_key": entry.object_key,
            "version": entry.version,
            "summary": _summary(entry),
        }
        for entry in entries
    ]
    node_ids = {node["id"] for node in nodes if isinstance(node["id"], str)}
    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        _add_edge(edges, seen, node_ids, entry.id, entry.supersedes, "supersedes")
        payload = _payload_of(entry)
        if entry.kind == "ExperimentPlan":
            claim_refs = payload.get("claim_refs")
            if isinstance(claim_refs, list):
                for claim_ref in claim_refs:
                    _add_edge(edges, seen, node_ids, entry.id, claim_ref, "tests")
        elif entry.kind == "ExperimentResult":
            _add_edge(edges, seen, node_ids, entry.id, payload.get("plan_ref"), "tests")
        elif entry.kind == "HypothesisUpdate":
            result_ref = payload.get("result_ref")
            claim_ref = payload.get("claim_ref")
            _add_edge(edges, seen, node_ids, result_ref, entry.id, "result_updates")
            status = payload.get("status")
            if status == "supported":
                _add_edge(edges, seen, node_ids, entry.id, claim_ref, "supports")
            elif status == "inconclusive":
                _add_edge(edges, seen, node_ids, entry.id, claim_ref, "inconclusive_for")
    return {"nodes": nodes, "edges": edges}


def build_memory_views(entries: list[MemoryEntry]) -> dict[str, Any]:
    """组合三视图（design §4.3 `MemoryViews` 形状），供 RunSnapshot 附加。"""
    return {
        "timeline": build_timeline(entries),
        "version_tree": build_version_tree(entries),
        "evidence_graph": build_evidence_graph(entries),
    }
