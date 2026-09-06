"""Thread-safe SQLite connection and transaction management."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock, local
from typing import Iterator


_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_test_results (
    test_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    runtime TEXT NOT NULL,
    result_json TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS agent_test_results_agent_time
    ON agent_test_results(agent_id, created_at, test_id);

CREATE TABLE IF NOT EXISTS group_chats (
    group_chat_id TEXT PRIMARY KEY,
    data_space TEXT NOT NULL DEFAULT 'synthetic',
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    group_chat_id TEXT NOT NULL,
    sender_type TEXT NOT NULL,
    sender_id TEXT,
    content TEXT NOT NULL,
    mention_json TEXT,
    task_id TEXT,
    attachment_ids_json TEXT NOT NULL DEFAULT '[]',
    message_kind TEXT NOT NULL DEFAULT 'text',
    payload_json TEXT NOT NULL DEFAULT '{}',
    reply_to_message_id TEXT,
    data_space TEXT NOT NULL DEFAULT 'synthetic',
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS messages_group_chat_created
    ON messages(group_chat_id, created_at, message_id);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
    USING fts5(message_id UNINDEXED, group_chat_id UNINDEXED, content);

CREATE TABLE IF NOT EXISTS clarifications (
    clarification_id TEXT PRIMARY KEY,
    group_chat_id TEXT NOT NULL,
    mention_json TEXT NOT NULL,
    clarifier_agent_id TEXT NOT NULL,
    initial_intent TEXT NOT NULL,
    turns_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    question_id TEXT,
    question TEXT,
    question_number INTEGER NOT NULL,
    max_questions INTEGER NOT NULL DEFAULT 7,
    dataset_refs_json TEXT NOT NULL DEFAULT '[]',
    error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS clarifications_group_chat_created
    ON clarifications(group_chat_id, created_at, clarification_id);

CREATE TABLE IF NOT EXISTS formal_tasks (
    clarification_id TEXT PRIMARY KEY,
    group_chat_id TEXT NOT NULL,
    context_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS formal_tasks_group_chat
    ON formal_tasks(group_chat_id, created_at, clarification_id);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    group_chat_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    content TEXT NOT NULL,
    data_space TEXT NOT NULL DEFAULT 'synthetic',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS artifacts_run_agent
    ON artifacts(run_id, agent_id, created_at, artifact_id);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    group_chat_id TEXT NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    mode TEXT NOT NULL,
    phase TEXT NOT NULL,
    cycle INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS runs_group_chat
    ON runs(group_chat_id, created_at);

CREATE TABLE IF NOT EXISTS meeting_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp REAL NOT NULL,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT 'live',
    phase TEXT NOT NULL DEFAULT 'meeting',
    sequence INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS meeting_events_run_time
    ON meeting_events(run_id, timestamp, event_id);

CREATE TABLE IF NOT EXISTS meeting_schedules (
    group_chat_id TEXT PRIMARY KEY,
    next_meeting_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    run_id TEXT,
    error TEXT NOT NULL DEFAULT '',
    triggered_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS meeting_schedules_due
    ON meeting_schedules(status, next_meeting_at, group_chat_id);

CREATE TABLE IF NOT EXISTS runtime_sessions (
    session_id TEXT PRIMARY KEY,
    group_chat_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    session_scope TEXT NOT NULL,
    session_file TEXT,
    status TEXT NOT NULL,
    last_cursor INTEGER NOT NULL DEFAULT 0,
    data_space TEXT NOT NULL DEFAULT 'synthetic',
    task_id TEXT NOT NULL DEFAULT '',
    document_scope_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS runtime_sessions_run_agent
    ON runtime_sessions(run_id, agent_id, updated_at);

CREATE TABLE IF NOT EXISTS runtime_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    group_chat_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    event_type TEXT NOT NULL,
    cursor INTEGER NOT NULL,
    invocation_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    data_space TEXT NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    document_scope_json TEXT NOT NULL DEFAULT '[]',
    timestamp REAL NOT NULL,
    UNIQUE(run_id, session_id, cursor)
);

CREATE INDEX IF NOT EXISTS runtime_events_run_cursor
    ON runtime_events(run_id, cursor, event_id);

CREATE TABLE IF NOT EXISTS runtime_cursors (
    run_id TEXT PRIMARY KEY,
    cursor INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    group_chat_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    data_space TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(group_chat_id, sha256)
);

CREATE INDEX IF NOT EXISTS documents_group_created
    ON documents(group_chat_id, created_at, document_id);

CREATE TABLE IF NOT EXISTS research_tasks (
    task_id TEXT PRIMARY KEY,
    group_chat_id TEXT NOT NULL,
    title TEXT NOT NULL,
    question TEXT NOT NULL,
    source_clarification_id TEXT,
    data_space TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS research_tasks_group_created
    ON research_tasks(group_chat_id, created_at, task_id);

CREATE TABLE IF NOT EXISTS task_documents (
    task_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY(task_id, document_id)
);

CREATE INDEX IF NOT EXISTS task_documents_document
    ON task_documents(document_id, task_id);

CREATE TABLE IF NOT EXISTS research_task_dataset_refs (
    task_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_version INTEGER NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY(task_id, dataset_id, dataset_version),
    UNIQUE(task_id, position)
);

CREATE INDEX IF NOT EXISTS research_task_dataset_refs_dataset
    ON research_task_dataset_refs(dataset_id, dataset_version, task_id);

CREATE TABLE IF NOT EXISTS document_chunks (
    document_id TEXT NOT NULL,
    chunk_id TEXT PRIMARY KEY,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    page_or_location TEXT NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS document_chunks_document_order
    ON document_chunks(document_id, chunk_index, chunk_id);

CREATE TABLE IF NOT EXISTS document_index_jobs (
    document_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    error_code TEXT NOT NULL DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 0,
    started_at REAL,
    finished_at REAL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS document_index_jobs_status
    ON document_index_jobs(status, updated_at, document_id);

CREATE TABLE IF NOT EXISTS candidate_claims (
    candidate_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    group_chat_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    claim TEXT NOT NULL,
    reasoning_summary TEXT NOT NULL,
    uncertainty TEXT NOT NULL,
    next_action TEXT NOT NULL,
    data_space TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS candidate_claims_run
    ON candidate_claims(run_id, created_at, candidate_id);

CREATE TABLE IF NOT EXISTS candidate_evidence_refs (
    candidate_id TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    position INTEGER NOT NULL,
    document_id TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'pending',
    PRIMARY KEY(candidate_id, evidence_ref)
);

CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id TEXT PRIMARY KEY,
    source_ref TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    source_data_space TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    applicability_boundary TEXT NOT NULL,
    locator TEXT NOT NULL,
    extraction_summary TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_source_links (
    evidence_id TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    position INTEGER NOT NULL,
    locator_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(evidence_id, source_ref)
);

CREATE INDEX IF NOT EXISTS evidence_source_links_ref
    ON evidence_source_links(source_ref, evidence_id);

CREATE TABLE IF NOT EXISTS candidate_evidence_links (
    candidate_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY(candidate_id, source_ref)
);

CREATE INDEX IF NOT EXISTS candidate_evidence_links_evidence
    ON candidate_evidence_links(evidence_id, candidate_id);

CREATE TABLE IF NOT EXISTS claim_approvals (
    candidate_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS formal_claims (
    claim_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    group_chat_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    claim TEXT NOT NULL,
    data_space TEXT NOT NULL,
    evidence_status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS formal_claims_run
    ON formal_claims(run_id, created_at, claim_id);

CREATE TABLE IF NOT EXISTS formal_claim_evidence_links (
    claim_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY(claim_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS research_state_versions (
    state_id TEXT PRIMARY KEY,
    group_chat_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    previous_state_id TEXT,
    formal_claim_id TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(group_chat_id, version)
);

CREATE INDEX IF NOT EXISTS research_state_versions_group
    ON research_state_versions(group_chat_id, version);

CREATE TABLE IF NOT EXISTS group_research_state_heads (
    group_chat_id TEXT PRIMARY KEY,
    state_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS experiment_datasets (
    dataset_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    group_chat_id TEXT NOT NULL DEFAULT '',
    source_document_id TEXT NOT NULL,
    sample_schema_json TEXT NOT NULL,
    units_json TEXT NOT NULL,
    conditions_json TEXT NOT NULL,
    rows_json TEXT NOT NULL,
    data_space TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(dataset_id, version)
);

CREATE INDEX IF NOT EXISTS experiment_datasets_group
    ON experiment_datasets(group_chat_id, created_at, dataset_id, version);

CREATE TABLE IF NOT EXISTS experiment_analysis (
    analysis_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    dataset_version INTEGER NOT NULL,
    operation TEXT NOT NULL,
    column_name TEXT NOT NULL,
    result_json TEXT NOT NULL,
    input_refs_json TEXT NOT NULL,
    output_refs_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    data_space TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS experiment_analysis_dataset
    ON experiment_analysis(dataset_id, dataset_version, created_at, analysis_id);

CREATE TABLE IF NOT EXISTS experiment_source_files (
    source_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    dataset_version INTEGER NOT NULL,
    group_chat_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS experiment_source_files_dataset
    ON experiment_source_files(group_chat_id, dataset_id, dataset_version, created_at);

CREATE TABLE IF NOT EXISTS tool_call_audits (
    record_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    group_chat_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    record_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS tool_call_audits_run_agent
    ON tool_call_audits(run_id, agent_id, status, created_at, record_id);

CREATE TABLE IF NOT EXISTS literature_leads (
    source_ref TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    doi TEXT,
    url TEXT NOT NULL,
    provider TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    lead_json TEXT NOT NULL,
    retrieved_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS literature_leads_identity
    ON literature_leads(doi, url, provider, retrieved_at);

CREATE TABLE IF NOT EXISTS artifact_versions (
    artifact_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    group_chat_id TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    artifact_type TEXT NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'ready',
    data_space TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(artifact_id, version)
);

CREATE INDEX IF NOT EXISTS artifact_versions_group
    ON artifact_versions(group_chat_id, created_at, artifact_id, version);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    tenant_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS memberships (
    user_id TEXT NOT NULL,
    group_chat_id TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY(user_id, group_chat_id)
);

CREATE INDEX IF NOT EXISTS memberships_group
    ON memberships(group_chat_id, user_id);
"""


class SQLiteStore:
    """Own one SQLite connection and serialize access to it."""

    def __init__(self, path: str | Path) -> None:
        self.path = path if isinstance(path, str) else Path(path)
        self._connection: sqlite3.Connection | None = None
        self._lock = RLock()
        self._transaction_state = local()

    def initialize(self) -> None:
        """Open the database and create the minimal schema if necessary."""
        with self._lock:
            if self._connection is None:
                if self.path != ":memory:":
                    Path(self.path).parent.mkdir(parents=True, exist_ok=True)
                self._connection = sqlite3.connect(
                    str(self.path), check_same_thread=False
                )
                self._connection.row_factory = sqlite3.Row
            self._connection.executescript(_SCHEMA)
            self._ensure_compat_columns()
            self._connection.commit()

    def _ensure_compat_columns(self) -> None:
        """Add columns introduced after an existing local database was created."""
        assert self._connection is not None
        meeting_columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(meeting_events)")
        }
        meeting_additions = {
            "source": "TEXT NOT NULL DEFAULT 'live'",
            "phase": "TEXT NOT NULL DEFAULT 'meeting'",
            "sequence": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in meeting_additions.items():
            if name not in meeting_columns:
                self._connection.execute(
                    f"ALTER TABLE meeting_events ADD COLUMN {name} {definition}"
                )
        task_columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(research_tasks)")
        }
        if "source_clarification_id" not in task_columns:
            self._connection.execute(
                "ALTER TABLE research_tasks ADD COLUMN source_clarification_id TEXT"
            )
        self._connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS research_tasks_group_clarification
            ON research_tasks(group_chat_id, source_clarification_id)
            WHERE source_clarification_id IS NOT NULL
            """
        )
        clarification_columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(clarifications)")
        }
        if "dataset_refs_json" not in clarification_columns:
            self._connection.execute(
                "ALTER TABLE clarifications ADD COLUMN dataset_refs_json TEXT NOT NULL DEFAULT '[]'"
            )
        message_columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(messages)")
        }
        message_additions = {
            "sender_id": "TEXT",
            "task_id": "TEXT",
            "attachment_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "message_kind": "TEXT NOT NULL DEFAULT 'text'",
            "payload_json": "TEXT NOT NULL DEFAULT '{}'",
            "reply_to_message_id": "TEXT",
        }
        for name, definition in message_additions.items():
            if name not in message_columns:
                self._connection.execute(
                    f"ALTER TABLE messages ADD COLUMN {name} {definition}"
                )
        self._connection.execute(
            """
            INSERT OR IGNORE INTO messages_fts(message_id, group_chat_id, content)
            SELECT message_id, group_chat_id, content FROM messages
            """
        )
        run_columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(runs)")
        }
        if "task_id" not in run_columns:
            self._connection.execute(
                "ALTER TABLE runs ADD COLUMN task_id TEXT NOT NULL DEFAULT ''"
            )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS runs_task ON runs(task_id, created_at)"
        )
        session_columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(runtime_sessions)")
        }
        if "task_id" not in session_columns:
            self._connection.execute(
                "ALTER TABLE runtime_sessions ADD COLUMN task_id TEXT NOT NULL DEFAULT ''"
            )
        if "document_scope_json" not in session_columns:
            self._connection.execute(
                "ALTER TABLE runtime_sessions ADD COLUMN document_scope_json TEXT NOT NULL DEFAULT '[]'"
            )
        event_columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(runtime_events)")
        }
        if "task_id" not in event_columns:
            self._connection.execute(
                "ALTER TABLE runtime_events ADD COLUMN task_id TEXT NOT NULL DEFAULT ''"
            )
        if "document_scope_json" not in event_columns:
            self._connection.execute(
                "ALTER TABLE runtime_events ADD COLUMN document_scope_json TEXT NOT NULL DEFAULT '[]'"
            )

    def connection(self) -> sqlite3.Connection:
        """Return the initialized connection."""
        if self._connection is None:
            self.initialize()
        assert self._connection is not None
        return self._connection

    @property
    def in_transaction(self) -> bool:
        """Whether the current Store transaction owns the connection."""
        return getattr(self._transaction_state, "depth", 0) > 0

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Commit on success and roll back the complete outer transaction."""
        with self._lock:
            connection = self.connection()
            depth = getattr(self._transaction_state, "depth", 0)
            is_outer = depth == 0
            self._transaction_state.depth = depth + 1
            try:
                yield connection
                if is_outer:
                    connection.commit()
            except Exception:
                if is_outer:
                    connection.rollback()
                raise
            finally:
                self._transaction_state.depth = depth

    @contextmanager
    def locked(self) -> Iterator[sqlite3.Connection]:
        """Serialize a read and return the current connection."""
        with self._lock:
            yield self.connection()

    def close(self) -> None:
        """Close the connection; a later access may initialize it again."""
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
