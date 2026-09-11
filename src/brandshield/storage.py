"""SQLite persistence for investigation cases and append-only audit events."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from brandshield.models import (
    AuditEvent,
    CaseStatus,
    InvestigationCase,
)


class CaseNotFoundError(LookupError):
    """Raised when a requested investigation case does not exist."""


class ConcurrentUpdateError(RuntimeError):
    """Raised when a case changed between reading and writing it."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SQLiteCaseRepository:
    """Persist cases locally with transactional state changes and immutable audit rows."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS investigation_cases (
                    case_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    listing_json TEXT NOT NULL,
                    product_json TEXT NOT NULL,
                    assessment_json TEXT NOT NULL,
                    reviewer_name TEXT,
                    reviewer_note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version >= 1)
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    FOREIGN KEY (case_id) REFERENCES investigation_cases(case_id)
                );

                CREATE INDEX IF NOT EXISTS idx_cases_status
                    ON investigation_cases(status);
                CREATE INDEX IF NOT EXISTS idx_audit_case_id
                    ON audit_events(case_id, event_id);

                CREATE TRIGGER IF NOT EXISTS audit_events_no_update
                BEFORE UPDATE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit events are immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
                BEFORE DELETE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit events are immutable');
                END;
                """
            )

    def create_case(
        self,
        case: InvestigationCase,
        *,
        actor: str = "brandshield-system",
    ) -> InvestigationCase:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO investigation_cases (
                    case_id, status, listing_json, product_json, assessment_json,
                    reviewer_name, reviewer_note, created_at, updated_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case.case_id,
                    case.status.value,
                    case.listing.model_dump_json(),
                    case.product.model_dump_json(),
                    case.assessment.model_dump_json(),
                    case.reviewer_name,
                    case.reviewer_note,
                    case.created_at.isoformat(),
                    case.updated_at.isoformat(),
                    case.version,
                ),
            )
            self._insert_event(
                connection,
                case_id=case.case_id,
                event_type="case_created",
                actor=actor,
                details={
                    "status": case.status.value,
                    "risk_score": case.assessment.score,
                    "risk_level": case.assessment.level.value,
                },
            )
        return case

    def new_case_id(self) -> str:
        return f"CASE-{uuid4().hex[:12].upper()}"

    def get_case(self, case_id: str) -> InvestigationCase:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM investigation_cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        if row is None:
            raise CaseNotFoundError(f"Case not found: {case_id}")
        return self._case_from_row(row)

    def list_cases(self, status: CaseStatus | None = None) -> list[InvestigationCase]:
        query = "SELECT * FROM investigation_cases"
        parameters: tuple[str, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            parameters = (status.value,)
        query += " ORDER BY updated_at DESC, case_id DESC"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._case_from_row(row) for row in rows]

    def transition(
        self,
        case_id: str,
        *,
        target_status: CaseStatus,
        actor: str,
        note: str | None,
        event_type: str,
    ) -> InvestigationCase:
        current = self.get_case(case_id)
        now = _utc_now()
        reviewer_name = current.reviewer_name
        reviewer_note = current.reviewer_note
        if target_status in {CaseStatus.APPROVED, CaseStatus.REJECTED}:
            reviewer_name = actor
            reviewer_note = note

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE investigation_cases
                SET status = ?, reviewer_name = ?, reviewer_note = ?,
                    updated_at = ?, version = version + 1
                WHERE case_id = ? AND version = ?
                """,
                (
                    target_status.value,
                    reviewer_name,
                    reviewer_note,
                    now.isoformat(),
                    case_id,
                    current.version,
                ),
            )
            if cursor.rowcount != 1:
                raise ConcurrentUpdateError(
                    f"Case {case_id} was updated by another process; reload and retry."
                )
            self._insert_event(
                connection,
                case_id=case_id,
                event_type=event_type,
                actor=actor,
                details={
                    "from_status": current.status.value,
                    "to_status": target_status.value,
                    "note": note,
                },
            )
        return self.get_case(case_id)

    def append_event(
        self,
        case_id: str,
        *,
        event_type: str,
        actor: str,
        details: dict[str, str | int | float | bool | None],
    ) -> AuditEvent:
        self.get_case(case_id)
        with self._connect() as connection:
            self._insert_event(
                connection,
                case_id=case_id,
                event_type=event_type,
                actor=actor,
                details=details,
            )
        return self.list_events(case_id)[-1]

    def list_events(self, case_id: str) -> list[AuditEvent]:
        self.get_case(case_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, case_id, event_type, actor, details_json, occurred_at
                FROM audit_events
                WHERE case_id = ?
                ORDER BY event_id
                """,
                (case_id,),
            ).fetchall()
        return [
            AuditEvent(
                event_id=row["event_id"],
                case_id=row["case_id"],
                event_type=row["event_type"],
                actor=row["actor"],
                details=json.loads(row["details_json"]),
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
            )
            for row in rows
        ]

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        *,
        case_id: str,
        event_type: str,
        actor: str,
        details: dict[str, str | int | float | bool | None],
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO audit_events (
                case_id, event_type, actor, details_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                case_id,
                event_type,
                actor,
                json.dumps(details, sort_keys=True),
                _utc_now().isoformat(),
            ),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _case_from_row(row: sqlite3.Row) -> InvestigationCase:
        return InvestigationCase(
            case_id=row["case_id"],
            status=CaseStatus(row["status"]),
            listing=json.loads(row["listing_json"]),
            product=json.loads(row["product_json"]),
            assessment=json.loads(row["assessment_json"]),
            reviewer_name=row["reviewer_name"],
            reviewer_note=row["reviewer_note"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            version=row["version"],
        )
