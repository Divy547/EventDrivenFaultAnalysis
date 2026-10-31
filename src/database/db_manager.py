"""SQLite Database Manager for telemetry, faults, and knowledge persistence.

Features thread-safe connection handling, WAL mode, transaction safety,
indexing for fast time-series queries, and fault lifecycle tracking.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from config import settings
from src.models.telemetry import FaultEvent, MotorTelemetry


class DatabaseManager:
    """Thread-safe SQLite manager for IoT telemetry and diagnosis state."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or settings.db.path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.init_schema()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a contextual connection with WAL mode and row factory."""
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=15.0
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Create database tables and performance indices if not present."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Telemetry readings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    temperature REAL NOT NULL,
                    vibration REAL NOT NULL,
                    current REAL NOT NULL,
                    voltage REAL NOT NULL,
                    rpm REAL NOT NULL,
                    acoustic_db REAL NOT NULL,
                    pressure_bar REAL,
                    power_factor REAL,
                    state TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_device_time ON telemetry (device_id, timestamp);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry (timestamp);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_state ON telemetry (state);")

            # 2. Fault events table with deduplication and tracking fields
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fault_events (
                    fault_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    fault_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    threshold_value REAL NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    occurrence_count INTEGER DEFAULT 1,
                    first_detected TEXT NOT NULL,
                    last_detected TEXT NOT NULL,
                    resolved_at TEXT
                );
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_faults_device_status ON fault_events (device_id, status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_faults_last_detected ON fault_events (last_detected);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_faults_severity ON fault_events (severity);")

            # 3. Knowledge base documents / manual chunks
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_name TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(doc_name, chunk_index)
                );
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_kb_doc_name ON knowledge_documents (doc_name);")

            # 4. Maintenance and action logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS maintenance_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    fault_id TEXT,
                    action_taken TEXT NOT NULL,
                    technician TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    notes TEXT,
                    FOREIGN KEY(fault_id) REFERENCES fault_events(fault_id)
                );
            """)

    # --- Telemetry Ingestion & Querying ---

    def insert_telemetry(self, reading: MotorTelemetry) -> int:
        """Insert a validated telemetry record into the database."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO telemetry (
                    device_id, timestamp, temperature, vibration,
                    current, voltage, rpm, acoustic_db, pressure_bar,
                    power_factor, state, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                reading.device_id,
                reading.timestamp.isoformat(),
                reading.temperature,
                reading.vibration,
                reading.current,
                reading.voltage,
                reading.rpm,
                reading.acoustic_db,
                reading.pressure_bar,
                reading.power_factor,
                reading.state,
                reading.to_json_str()
            ))
            return cursor.lastrowid

    def get_recent_telemetry(
        self,
        device_id: str | None = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Retrieve recent telemetry records ordered by timestamp descending."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            if device_id:
                cursor.execute("""
                    SELECT * FROM telemetry
                    WHERE device_id = ?
                    ORDER BY id DESC LIMIT ?
                """, (device_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM telemetry
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_telemetry_stats(self, device_id: str | None = None) -> dict[str, Any]:
        """Aggregate telemetry metrics (min, max, avg)."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            where_clause = "WHERE device_id = ?" if device_id else ""
            params = (device_id,) if device_id else ()
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total_count,
                    AVG(temperature) as avg_temp,
                    MAX(temperature) as max_temp,
                    AVG(vibration) as avg_vibration,
                    MAX(vibration) as max_vibration,
                    AVG(current) as avg_current,
                    MAX(current) as max_current
                FROM telemetry {where_clause}
            """, params)
            row = cursor.fetchone()
            return dict(row) if row else {}

    # --- Fault Event Persistence & Deduplication ---

    def insert_or_update_fault(self, fault: FaultEvent) -> bool:
        """Insert a new fault event or update an existing active fault with deduplication."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            # Check if fault_id exists
            cursor.execute("SELECT fault_id, occurrence_count FROM fault_events WHERE fault_id = ?", (fault.fault_id,))
            existing = cursor.fetchone()

            if existing:
                cursor.execute("""
                    UPDATE fault_events
                    SET metric_value = ?,
                        threshold_value = ?,
                        message = ?,
                        occurrence_count = occurrence_count + 1,
                        last_detected = ?,
                        status = 'ACTIVE'
                    WHERE fault_id = ?
                """, (
                    fault.metric_value,
                    fault.threshold_value,
                    fault.message,
                    fault.last_detected.isoformat(),
                    fault.fault_id
                ))
                return False  # Updated existing
            else:
                cursor.execute("""
                    INSERT INTO fault_events (
                        fault_id, device_id, timestamp, fault_type,
                        severity, metric_name, metric_value, threshold_value,
                        message, status, occurrence_count, first_detected,
                        last_detected, resolved_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fault.fault_id,
                    fault.device_id,
                    fault.timestamp.isoformat(),
                    fault.fault_type,
                    fault.severity,
                    fault.metric_name,
                    fault.metric_value,
                    fault.threshold_value,
                    fault.message,
                    fault.status,
                    fault.occurrence_count,
                    fault.first_detected.isoformat(),
                    fault.last_detected.isoformat(),
                    fault.resolved_at.isoformat() if fault.resolved_at else None
                ))
                return True  # Created new

    def get_active_faults(self, device_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieve all currently ACTIVE or ACKNOWLEDGED faults."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            if device_id:
                cursor.execute("""
                    SELECT * FROM fault_events
                    WHERE device_id = ? AND status IN ('ACTIVE', 'ACKNOWLEDGED')
                    ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 ELSE 2 END, last_detected DESC
                """, (device_id,))
            else:
                cursor.execute("""
                    SELECT * FROM fault_events
                    WHERE status IN ('ACTIVE', 'ACKNOWLEDGED')
                    ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 ELSE 2 END, last_detected DESC
                """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_fault_history(
        self,
        device_id: str | None = None,
        status: str | None = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Retrieve historical fault records with optional filters."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM fault_events WHERE 1=1"
            params: list[Any] = []
            if device_id:
                query += " AND device_id = ?"
                params.append(device_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY last_detected DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def resolve_fault(self, fault_id: str, technician_note: str | None = None) -> bool:
        """Mark a fault as RESOLVED with resolution timestamp."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                UPDATE fault_events
                SET status = 'RESOLVED',
                    resolved_at = ?
                WHERE fault_id = ?
            """, (now_iso, fault_id))
            updated = cursor.rowcount > 0
            if updated and technician_note:
                cursor.execute("SELECT device_id FROM fault_events WHERE fault_id = ?", (fault_id,))
                row = cursor.fetchone()
                device_id = row["device_id"] if row else "UNKNOWN"
                cursor.execute("""
                    INSERT INTO maintenance_logs (device_id, fault_id, action_taken, technician, timestamp, notes)
                    VALUES (?, ?, 'Manual Resolution', 'Operator', ?, ?)
                """, (device_id, fault_id, now_iso, technician_note))
            return updated

    def acknowledge_fault(self, fault_id: str) -> bool:
        """Acknowledge an active fault."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE fault_events
                SET status = 'ACKNOWLEDGED'
                WHERE fault_id = ? AND status = 'ACTIVE'
            """, (fault_id,))
            return cursor.rowcount > 0

    # --- Knowledge Documents Persistence ---

    def store_document_chunks(self, doc_name: str, chunks: list[dict[str, Any]]) -> int:
        """Store extracted and chunked knowledge base text."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            # Clear previous chunks for same doc to avoid duplication on re-upload
            cursor.execute("DELETE FROM knowledge_documents WHERE doc_name = ?", (doc_name,))
            now_iso = datetime.now(timezone.utc).isoformat()
            count = 0
            for i, chunk in enumerate(chunks):
                content = chunk.get("content", "")
                meta_json = json.dumps(chunk.get("metadata", {}))
                cursor.execute("""
                    INSERT INTO knowledge_documents (doc_name, chunk_index, content, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (doc_name, i, content, meta_json, now_iso))
                count += 1
            return count

    def get_all_document_chunks(self) -> list[dict[str, Any]]:
        """Retrieve all knowledge document chunks."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, doc_name, chunk_index, content, metadata_json, created_at
                FROM knowledge_documents
                ORDER BY doc_name, chunk_index ASC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def list_indexed_documents(self) -> list[dict[str, Any]]:
        """List summary of indexed documents with chunk counts."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT doc_name, COUNT(*) as chunk_count, MIN(created_at) as indexed_at
                FROM knowledge_documents
                GROUP BY doc_name
                ORDER BY indexed_at DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    # --- Maintenance Logs ---

    def add_maintenance_log(
        self,
        device_id: str,
        action: str,
        technician: str = "Technician",
        notes: str = "",
        fault_id: str | None = None
    ) -> int:
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                INSERT INTO maintenance_logs (device_id, fault_id, action_taken, technician, timestamp, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (device_id, fault_id, action, technician, now_iso, notes))
            return cursor.lastrowid

    def get_maintenance_logs(self, device_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            if device_id:
                cursor.execute("""
                    SELECT * FROM maintenance_logs
                    WHERE device_id = ?
                    ORDER BY id DESC LIMIT ?
                """, (device_id, limit))
            else:
                cursor.execute("SELECT * FROM maintenance_logs ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # --- Utility / Reset ---

    def clear_all_data(self) -> None:
        """Purge all telemetry and fault records (useful for resets and tests)."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM telemetry;")
            cursor.execute("DELETE FROM fault_events;")
            cursor.execute("DELETE FROM maintenance_logs;")
