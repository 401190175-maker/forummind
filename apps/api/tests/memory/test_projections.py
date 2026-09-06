"""Memory Projection 层测试（tasks.md Task 9）。"""
import time

from app.memory.projections import (
    build_evidence_graph,
    build_memory_views,
    build_timeline,
    build_version_tree,
)
from app.memory.timeline import MemoryEntry


def _entry(
    kind: str,
    *,
    version: int = 1,
    supersedes: str | None = None,
    created_at: float = 0.0,
    object_key: str | None = None,
    payload: dict | None = None,
) -> MemoryEntry:
    return MemoryEntry(
        id=f"mem-{kind}-{version}",
        kind=kind,
        payload=payload or {},
        version=version,
        supersedes=supersedes,
        created_at=created_at,
        object_key=object_key,
    )


def _sample_entries() -> list[MemoryEntry]:
    """两组 Claim 版本链 + 一条 Decision，created_at 乱序。"""
    return [
        _entry("Claim", version=1, created_at=3.0, object_key="agent-ms-1",
               payload={"statement": "初始观点 A"}),
        _entry("Claim", version=2, supersedes="mem-Claim-1", created_at=5.0,
               object_key="agent-ms-1", payload={"statement": "修订观点 A"}),
        _entry("Claim", version=1, created_at=1.0, object_key="agent-ms-2",
               payload={"statement": "初始观点 B"}),
        _entry("Decision", version=1, created_at=2.0,
               payload={"option": "returned", "reason": "证据不足"}),
    ]


def test_build_timeline_sorted_by_created_at() -> None:
    entries = _sample_entries()
    timeline = build_timeline(entries)
    created_ats = [item["created_at"] for item in timeline]
    assert created_ats == sorted(created_ats)
    assert [item["id"] for item in timeline] == [
        "mem-Claim-1",
        "mem-Decision-1",
        "mem-Claim-1",
        "mem-Claim-2",
    ]


def test_build_timeline_fields() -> None:
    item = build_timeline(_sample_entries())[0]
    assert set(item) == {
        "id", "kind", "object_key", "version", "supersedes",
        "created_at", "summary", "data_space",
    }
    assert item["summary"] == "初始观点 B"  # created_at=1.0 的 Claim(agent-ms-2)


def test_build_version_tree_keeps_version_fields() -> None:
    tree = build_version_tree(_sample_entries())
    for node in tree:
        assert set(node) == {
            "id", "kind", "object_key", "version", "supersedes", "summary",
        }
    claim_nodes = [n for n in tree if n["kind"] == "Claim"]
    assert len(claim_nodes) == 3
    # 同一对象按 version 递增排列
    ms1 = [n for n in claim_nodes if n["object_key"] == "agent-ms-1"]
    assert [n["version"] for n in ms1] == [1, 2]
    assert ms1[1]["supersedes"] == "mem-Claim-1"


def test_build_evidence_graph_nodes_and_supersedes_edges() -> None:
    graph = build_evidence_graph(_sample_entries())
    assert set(graph) == {"nodes", "edges"}
    assert len(graph["nodes"]) == 4
    assert all(
        {"id", "kind", "object_key", "version", "summary"} <= set(node)
        for node in graph["nodes"]
    )
    assert all(
        {"source", "target", "relation"} <= set(edge) for edge in graph["edges"]
    )
    supersedes_edges = [
        e for e in graph["edges"] if e["relation"] == "supersedes"
    ]
    assert len(supersedes_edges) == 1
    assert supersedes_edges[0] == {
        "source": "mem-Claim-2", "target": "mem-Claim-1", "relation": "supersedes",
    }


def test_build_evidence_graph_without_supersedes_has_empty_edges() -> None:
    entries = [_entry("Claim", version=1, created_at=1.0)]
    graph = build_evidence_graph(entries)
    assert graph["edges"] == []
    assert len(graph["nodes"]) == 1


def test_payload_missing_fields_uses_fallback_summary() -> None:
    entries = [
        _entry("Claim", version=1, created_at=1.0, payload={}),
        _entry("Claim", version=1, created_at=2.0, payload={"weird": 42}),
        _entry("Claim", version=1, created_at=3.0, payload={"statement": 123}),
    ]
    timeline = build_timeline(entries)
    assert all(item["summary"] == "（无摘要）" for item in timeline)
    tree = build_version_tree(entries)
    assert all(node["summary"] == "（无摘要）" for node in tree)
    graph = build_evidence_graph(entries)
    assert len(graph["nodes"]) == 3


def test_build_memory_views_shape() -> None:
    views = build_memory_views(_sample_entries())
    assert set(views) == {"timeline", "version_tree", "evidence_graph"}
    assert isinstance(views["timeline"], list)
    assert isinstance(views["version_tree"], list)
    assert set(views["evidence_graph"]) == {"nodes", "edges"}


def test_projections_do_not_mutate_entries() -> None:
    entries = _sample_entries()
    payload_before = [dict(e.payload) for e in entries]
    build_timeline(entries)
    build_version_tree(entries)
    build_evidence_graph(entries)
    assert [dict(e.payload) for e in entries] == payload_before
    assert len(entries) == 4


def test_memory_timeline_append_logic_unchanged() -> None:
    """投影层不改动 MemoryTimeline 追加行为（回归哨兵）。"""
    from app.memory.timeline import MemoryTimeline

    timeline = MemoryTimeline()
    e1 = timeline.append("Claim", {"statement": "A"}, object_key="agent-1")
    e2 = timeline.append("Claim", {"statement": "B"}, object_key="agent-1",
                         supersedes=e1.id)
    assert e2.version == 2
    assert e2.supersedes == e1.id
    assert len(timeline.entries()) == 2
    assert timeline.latest("Claim", object_key="agent-1").id == e2.id


def test_evidence_graph_adds_experiment_semantic_edges_without_duplicates() -> None:
    entries = [
        _entry("Claim", version=1, object_key="agent-ms-1", payload={"statement": "claim"}),
        _entry("Claim", version=2, object_key="agent-ms-2", payload={"statement": "claim 2"}),
        _entry("ExperimentPlan", version=1, payload={
            "claim_refs": ["mem-Claim-1"],
            "candidate_explanations": ["解释 A"],
        }),
        _entry("ExperimentResult", version=1, payload={
            "plan_ref": "mem-ExperimentPlan-1",
            "source": "demo_csv",
        }),
        _entry("HypothesisUpdate", version=1, payload={
            "claim_id": "agent-ms-1",
            "status": "supported",
            "result_ref": "mem-ExperimentResult-1",
            "claim_ref": "mem-Claim-1",
        }),
        _entry("HypothesisUpdate", version=2, payload={
            "claim_id": "agent-ms-2",
            "status": "inconclusive",
            "result_ref": "mem-ExperimentResult-1",
            "claim_ref": "mem-Claim-2",
        }),
        _entry("ResearchState", version=2, supersedes="mem-ResearchState-1", payload={
            "summary": "new",
            "trigger_ref": "mem-ExperimentResult-1",
        }),
        _entry("ResearchState", version=1, payload={"summary": "old"}),
    ]

    graph = build_evidence_graph(entries)
    edges = graph["edges"]
    assert {"source": "mem-ExperimentPlan-1", "target": "mem-Claim-1", "relation": "tests"} in edges
    assert {
        "source": "mem-ExperimentResult-1",
        "target": "mem-HypothesisUpdate-1",
        "relation": "result_updates",
    } in edges
    assert {"source": "mem-HypothesisUpdate-1", "target": "mem-Claim-1", "relation": "supports"} in edges
    assert {
        "source": "mem-HypothesisUpdate-2",
        "target": "mem-Claim-2",
        "relation": "inconclusive_for",
    } in edges
    assert {
        "source": "mem-ResearchState-2",
        "target": "mem-ResearchState-1",
        "relation": "supersedes",
    } in edges
    assert len(edges) == len({(e["source"], e["target"], e["relation"]) for e in edges})
    node_ids = {n["id"] for n in graph["nodes"]}
    assert all(e["source"] in node_ids and e["target"] in node_ids for e in edges)


def test_evidence_graph_skips_bad_experiment_references() -> None:
    entries = [
        _entry("ExperimentPlan", version=1, payload={"claim_refs": ["missing-claim", 42]}),
        _entry("ExperimentResult", version=1, payload={"plan_ref": "missing-plan"}),
        _entry("HypothesisUpdate", version=1, payload={
            "status": "unknown",
            "result_ref": "missing-result",
            "claim_ref": "missing-claim",
        }),
        _entry("Claim", version=1, payload=None),
    ]

    graph = build_evidence_graph(entries)

    assert graph["edges"] == []
