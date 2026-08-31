from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

UTC = timezone.utc
ALLOWED_EXITS = {"fixed_4r", "fixed_5r", "stop_and_1555"}
ALLOWED_EVENTS = {"eligible_session", "missed_signal", "rejected_signal", "data_outage", "manual_deviation"}


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


class PaperJournal:
    """Local, append-only, forward-only paper journal. It has no broker integration."""

    def __init__(self, path: Path = Path("data/paper/paper_journal.sqlite"), now: Callable[[], datetime] | None = None):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.now = now or (lambda: datetime.now(UTC))
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS paper_activation (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    activated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    instrument TEXT NOT NULL CHECK (instrument = 'NQ'),
                    contracts INTEGER NOT NULL CHECK (contracts = 1),
                    entry_rule TEXT NOT NULL,
                    direction_rule TEXT NOT NULL,
                    stop_rule TEXT NOT NULL,
                    exit_method TEXT NOT NULL CHECK (exit_method IN ('fixed_4r','fixed_5r','stop_and_1555')),
                    evidence_label TEXT NOT NULL CHECK (evidence_label = 'Prospective paper'),
                    config_hash TEXT NOT NULL UNIQUE,
                    live_execution INTEGER NOT NULL DEFAULT 0 CHECK (live_execution = 0)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS paper_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_uuid TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL CHECK (event_type IN ('activation','eligible_session','missed_signal','rejected_signal','data_outage','manual_deviation')),
                    session_ts TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_paper_events_session_ts ON paper_events(session_ts)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_paper_events_type_session ON paper_events(event_type, session_ts)")
            connection.execute("""
                CREATE TRIGGER IF NOT EXISTS paper_activation_no_update
                BEFORE UPDATE ON paper_activation BEGIN SELECT RAISE(ABORT, 'paper activation is immutable'); END
            """)
            connection.execute("""
                CREATE TRIGGER IF NOT EXISTS paper_activation_no_delete
                BEFORE DELETE ON paper_activation BEGIN SELECT RAISE(ABORT, 'paper activation cannot be deleted'); END
            """)
            connection.execute("""
                CREATE TRIGGER IF NOT EXISTS paper_events_no_update
                BEFORE UPDATE ON paper_events BEGIN SELECT RAISE(ABORT, 'paper audit log is append-only'); END
            """)
            connection.execute("""
                CREATE TRIGGER IF NOT EXISTS paper_events_no_delete
                BEFORE DELETE ON paper_events BEGIN SELECT RAISE(ABORT, 'paper audit log is append-only'); END
            """)
            connection.execute("PRAGMA optimize")

    @staticmethod
    def _config(activated_at: datetime, exit_method: str) -> dict:
        return {
            "activated_at": activated_at.isoformat(),
            "instrument": "NQ",
            "contracts": 1,
            "entry_rule": "09:35 America/New_York first available one-minute bar open",
            "direction_rule": "completed 09:30-09:34 opening-candle body direction",
            "stop_rule": "opposite extreme of completed opening candle",
            "exit_method": exit_method,
            "evidence_label": "Prospective paper",
            "live_execution": False,
        }

    def activate(self, activated_at: str, exit_method: str) -> dict:
        activation = _aware(activated_at)
        current = self.now().astimezone(UTC)
        if activation <= current:
            raise ValueError("activation must be a future timestamp")
        if exit_method not in ALLOWED_EXITS:
            raise ValueError("exit_method must be fixed_4r, fixed_5r, or stop_and_1555")
        config = self._config(activation, exit_method)
        canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
        config_hash = hashlib.sha256(canonical.encode()).hexdigest()
        created_at = current.isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM paper_activation WHERE id=1").fetchone():
                raise ValueError("paper configuration is already active and immutable")
            connection.execute(
                "INSERT INTO paper_activation (id,activated_at,created_at,instrument,contracts,entry_rule,direction_rule,stop_rule,exit_method,evidence_label,config_hash,live_execution) VALUES (1,?,?,?,?,?,?,?,?,?,?,0)",
                (config["activated_at"], created_at, config["instrument"], config["contracts"], config["entry_rule"], config["direction_rule"], config["stop_rule"], config["exit_method"], config["evidence_label"], config_hash),
            )
            connection.execute(
                "INSERT INTO paper_events (event_uuid,event_type,session_ts,recorded_at,config_hash,payload_json) VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), "activation", config["activated_at"], created_at, config_hash, canonical),
            )
        return self.status()

    def _activation(self, connection: sqlite3.Connection) -> sqlite3.Row | None:
        return connection.execute("SELECT * FROM paper_activation WHERE id=1").fetchone()

    def append(self, event_type: str, session_ts: str, payload: dict) -> dict:
        if event_type not in ALLOWED_EVENTS:
            raise ValueError(f"event_type must be one of {sorted(ALLOWED_EVENTS)}")
        session = _aware(session_ts)
        current = self.now().astimezone(UTC)
        with self._connection() as connection:
            activation = self._activation(connection)
            if activation is None:
                raise ValueError("activate prospective paper mode first")
            activated_at = _aware(activation["activated_at"])
            if current < activated_at:
                raise ValueError("prospective activation time has not arrived")
            if session < activated_at:
                raise ValueError("sessions before activation cannot enter the prospective journal")
            if session > current + timedelta(minutes=5):
                raise ValueError("future sessions cannot be recorded")
            self._validate_payload(event_type, payload)
            recorded_at = current.isoformat()
            event_uuid = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO paper_events (event_uuid,event_type,session_ts,recorded_at,config_hash,payload_json) VALUES (?,?,?,?,?,?)",
                (event_uuid, event_type, session.isoformat(), recorded_at, activation["config_hash"], json.dumps(payload, sort_keys=True, separators=(",", ":"))),
            )
        return {"event_uuid": event_uuid, "event_type": event_type, "session_ts": session.isoformat(), "recorded_at": recorded_at}

    @staticmethod
    def _validate_payload(event_type: str, payload: dict) -> None:
        required = {
            "eligible_session": {"session_date", "intended_entry_ts", "available_market_price", "spread_estimate_points", "simulated_fill", "stop_price", "exit_ts", "exit_price", "net_pnl", "status"},
            "missed_signal": {"session_date", "intended_entry_ts", "reason"},
            "rejected_signal": {"session_date", "intended_entry_ts", "reason"},
            "data_outage": {"session_date", "description"},
            "manual_deviation": {"session_date", "description"},
        }[event_type]
        missing = sorted(required - payload.keys())
        if missing:
            raise ValueError(f"missing payload fields: {', '.join(missing)}")

    def status(self) -> dict:
        with self._connection() as connection:
            activation = self._activation(connection)
            rows = connection.execute("SELECT event_type,payload_json FROM paper_events WHERE event_type != 'activation' ORDER BY id").fetchall()
        counts = {name: 0 for name in ALLOWED_EVENTS}
        paper_net = 0.0
        completed = 0
        for row in rows:
            counts[row["event_type"]] += 1
            if row["event_type"] == "eligible_session":
                payload = json.loads(row["payload_json"])
                paper_net += float(payload.get("net_pnl", 0))
                completed += 1
        config = None
        if activation is not None:
            config = {key: activation[key] for key in ("activated_at", "created_at", "instrument", "contracts", "entry_rule", "direction_rule", "stop_rule", "exit_method", "evidence_label", "config_hash")}
            config["immutable"] = True
            config["live_execution"] = False
        return {
            "status": "active" if activation and self.now().astimezone(UTC) >= _aware(activation["activated_at"]) else "scheduled" if activation else "not_activated",
            "configuration": config,
            "prospective_results": {"evidence_label": "Prospective paper", "completed_sessions": completed, "net_profit": round(paper_net, 2), "event_counts": counts},
            "historical_results_merged": False,
            "broker_connected": False,
        }

    def events(self, limit: int = 500) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute("SELECT id,event_uuid,event_type,session_ts,recorded_at,config_hash,payload_json FROM paper_events ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 2000),)).fetchall()
        return [{**{key: row[key] for key in ("id", "event_uuid", "event_type", "session_ts", "recorded_at", "config_hash")}, "payload": json.loads(row["payload_json"])} for row in rows]
