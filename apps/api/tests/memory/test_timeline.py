"""科研 Memory 时间线单元测试：锁定只追加/版本链/synthetic 不变式。"""
from app.memory.timeline import MemoryTimeline


def test_append_is_versioned_per_kind():
    t = MemoryTimeline()
    a = t.append("ResearchState", {"summary": "v1"})
    b = t.append("ResearchState", {"summary": "v2"}, supersedes=a.id)
    assert a.version == 1
    assert b.version == 2
    assert b.supersedes == a.id


def test_append_can_version_per_object_key():
    t = MemoryTimeline()
    a1 = t.append("Claim", {"agent_id": "agent-ms-1"}, object_key="agent-ms-1")
    b1 = t.append("Claim", {"agent_id": "agent-ms-2"}, object_key="agent-ms-2")
    a2 = t.append("Claim", {"agent_id": "agent-ms-1"}, object_key="agent-ms-1", supersedes=a1.id)
    assert a1.version == 1
    assert b1.version == 1
    assert a2.version == 2
    assert a2.supersedes == a1.id


def test_append_never_overwrites():
    t = MemoryTimeline()
    t.append("Claim", {"statement": "first"})
    t.append("Claim", {"statement": "second"})
    entries = t.entries()
    assert len(entries) == 2
    assert entries[0].payload["statement"] == "first"
    assert entries[1].payload["statement"] == "second"


def test_all_entries_synthetic():
    t = MemoryTimeline()
    t.append("Evidence", {})
    t.append("Decision", {"option": "approved"})
    assert all(e.data_space == "synthetic" for e in t.entries())


def test_latest_returns_none_on_empty():
    t = MemoryTimeline()
    assert t.latest("Claim") is None
    t.append("Claim", {"statement": "x"})
    assert t.latest("Claim").payload["statement"] == "x"
