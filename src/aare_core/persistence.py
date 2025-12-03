"""
Optional persistence layer for aare-core verification records.

This module provides an abstract interface for storing verification results,
enabling audit trails and compliance record-keeping.

Usage:
    # With SQLite (included, no extra deps)
    from aare_core.persistence import SQLiteStore
    store = SQLiteStore("verifications.db")

    # Custom backend
    from aare_core.persistence import VerificationStore, VerificationRecord
    class MyStore(VerificationStore):
        def store(self, record: VerificationRecord) -> str: ...
        def retrieve(self, verification_id: str) -> Optional[VerificationRecord]: ...
"""
import hashlib
import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class VerificationRecord:
    """
    Verification result record for persistence.

    Contains all data needed for audit trails and compliance reporting.
    """
    verification_id: str
    ontology_name: str
    timestamp: str
    verified: bool
    violations: List[Dict[str, Any]]
    execution_time_ms: int

    # Optional fields - backends may choose to store or skip
    parsed_data: Optional[Dict[str, Any]] = None
    proof: Optional[Dict[str, Any]] = None
    input_hash: Optional[str] = None

    # Computed fields
    certificate_hash: Optional[str] = field(default=None, init=False)
    violation_count: int = field(default=0, init=False)

    def __post_init__(self):
        self.violation_count = len(self.violations)
        self.certificate_hash = self._compute_certificate_hash()

    def _compute_certificate_hash(self) -> str:
        """Generate SHA256 hash of verification metadata for integrity checking."""
        certificate_data = json.dumps({
            'verification_id': self.verification_id,
            'ontology': self.ontology_name,
            'verified': self.verified,
            'violations': self.violations,
            'timestamp': self.timestamp
        }, sort_keys=True)
        return hashlib.sha256(certificate_data.encode()).hexdigest()

    @classmethod
    def from_verification_result(
        cls,
        verification_id: str,
        ontology_name: str,
        result: Dict[str, Any],
        parsed_data: Optional[Dict[str, Any]] = None,
        llm_output: Optional[str] = None,
        timestamp: Optional[str] = None
    ) -> "VerificationRecord":
        """
        Create a VerificationRecord from SMTVerifier.verify() result.

        Args:
            verification_id: Unique ID for this verification
            ontology_name: Name of ontology used
            result: Result dict from SMTVerifier.verify()
            parsed_data: Optional extracted data from LLMParser
            llm_output: Optional original LLM output (will be hashed, not stored)
            timestamp: Optional ISO timestamp (defaults to now)
        """
        input_hash = None
        if llm_output:
            input_hash = hashlib.sha256(llm_output.encode()).hexdigest()

        return cls(
            verification_id=verification_id,
            ontology_name=ontology_name,
            timestamp=timestamp or datetime.utcnow().isoformat(),
            verified=result['verified'],
            violations=result['violations'],
            execution_time_ms=result['execution_time_ms'],
            parsed_data=parsed_data,
            proof=result.get('proof'),
            input_hash=input_hash
        )


class VerificationStore(ABC):
    """
    Abstract base class for verification record persistence.

    Implement this interface to create custom storage backends
    (PostgreSQL, MongoDB, S3, etc.)
    """

    @abstractmethod
    def store(self, record: VerificationRecord) -> str:
        """
        Store a verification record.

        Args:
            record: The verification record to store

        Returns:
            The certificate_hash for the stored record

        Raises:
            StorageError: If storage fails
        """
        pass

    @abstractmethod
    def retrieve(self, verification_id: str) -> Optional[VerificationRecord]:
        """
        Retrieve a verification record by ID.

        Args:
            verification_id: The unique verification ID

        Returns:
            The VerificationRecord if found, None otherwise
        """
        pass

    def list_recent(self, limit: int = 100) -> List[VerificationRecord]:
        """
        List recent verification records.

        Override in subclasses that support listing.
        Default implementation returns empty list.
        """
        return []

    def close(self):
        """Clean up resources. Override if needed."""
        pass


class StorageError(Exception):
    """Raised when storage operations fail."""
    pass


class SQLiteStore(VerificationStore):
    """
    SQLite-based verification store.

    Good for single-node deployments, development, and testing.
    Thread-safe with connection pooling per thread.

    Usage:
        store = SQLiteStore("verifications.db")
        store.store(record)
        record = store.retrieve("abc-123")
        store.close()
    """

    def __init__(self, db_path: str = "verifications.db"):
        """
        Initialize SQLite store.

        Args:
            db_path: Path to SQLite database file. Use ":memory:" for in-memory.
        """
        self.db_path = db_path
        self._local = threading.local()
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_schema(self):
        """Create tables if they don't exist."""
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verifications (
                verification_id TEXT PRIMARY KEY,
                ontology_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                verified INTEGER NOT NULL,
                violation_count INTEGER NOT NULL,
                violations TEXT NOT NULL,
                execution_time_ms INTEGER NOT NULL,
                parsed_data TEXT,
                proof TEXT,
                input_hash TEXT,
                certificate_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON verifications(timestamp DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ontology
            ON verifications(ontology_name)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_verified
            ON verifications(verified)
        """)
        conn.commit()

    def store(self, record: VerificationRecord) -> str:
        """Store verification record in SQLite."""
        try:
            conn = self._get_connection()
            conn.execute("""
                INSERT OR REPLACE INTO verifications (
                    verification_id, ontology_name, timestamp, verified,
                    violation_count, violations, execution_time_ms,
                    parsed_data, proof, input_hash, certificate_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.verification_id,
                record.ontology_name,
                record.timestamp,
                1 if record.verified else 0,
                record.violation_count,
                json.dumps(record.violations),
                record.execution_time_ms,
                json.dumps(record.parsed_data) if record.parsed_data else None,
                json.dumps(record.proof) if record.proof else None,
                record.input_hash,
                record.certificate_hash
            ))
            conn.commit()
            return record.certificate_hash
        except sqlite3.Error as e:
            raise StorageError(f"Failed to store verification: {e}") from e

    def retrieve(self, verification_id: str) -> Optional[VerificationRecord]:
        """Retrieve verification record by ID."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM verifications WHERE verification_id = ?",
            (verification_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def list_recent(self, limit: int = 100) -> List[VerificationRecord]:
        """List recent verification records, newest first."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM verifications ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        return [self._row_to_record(row) for row in cursor.fetchall()]

    def query_by_ontology(
        self,
        ontology_name: str,
        limit: int = 100
    ) -> List[VerificationRecord]:
        """Query records by ontology name."""
        conn = self._get_connection()
        cursor = conn.execute(
            """SELECT * FROM verifications
               WHERE ontology_name = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (ontology_name, limit)
        )
        return [self._row_to_record(row) for row in cursor.fetchall()]

    def query_failures(self, limit: int = 100) -> List[VerificationRecord]:
        """Query only failed verifications."""
        conn = self._get_connection()
        cursor = conn.execute(
            """SELECT * FROM verifications
               WHERE verified = 0
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,)
        )
        return [self._row_to_record(row) for row in cursor.fetchall()]

    def _row_to_record(self, row: sqlite3.Row) -> VerificationRecord:
        """Convert database row to VerificationRecord."""
        record = VerificationRecord(
            verification_id=row['verification_id'],
            ontology_name=row['ontology_name'],
            timestamp=row['timestamp'],
            verified=bool(row['verified']),
            violations=json.loads(row['violations']),
            execution_time_ms=row['execution_time_ms'],
            parsed_data=json.loads(row['parsed_data']) if row['parsed_data'] else None,
            proof=json.loads(row['proof']) if row['proof'] else None,
            input_hash=row['input_hash']
        )
        return record

    def close(self):
        """Close the database connection."""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


class InMemoryStore(VerificationStore):
    """
    In-memory verification store for testing and development.

    Data is lost when the process exits. Thread-safe.
    """

    def __init__(self):
        self._records: Dict[str, VerificationRecord] = {}
        self._lock = threading.Lock()

    def store(self, record: VerificationRecord) -> str:
        with self._lock:
            self._records[record.verification_id] = record
        return record.certificate_hash

    def retrieve(self, verification_id: str) -> Optional[VerificationRecord]:
        return self._records.get(verification_id)

    def list_recent(self, limit: int = 100) -> List[VerificationRecord]:
        with self._lock:
            sorted_records = sorted(
                self._records.values(),
                key=lambda r: r.timestamp,
                reverse=True
            )
            return sorted_records[:limit]

    def clear(self):
        """Clear all records (useful for testing)."""
        with self._lock:
            self._records.clear()
