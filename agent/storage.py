import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path


class StateConflict(RuntimeError):
    pass


class Store:
    def __init__(self, filename: Path) -> None:
        self.filename = filename
        filename.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS runs "
                "(id TEXT PRIMARY KEY, state TEXT NOT NULL, version INTEGER NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS sessions "
                "(id TEXT PRIMARY KEY, created_at TEXT NOT NULL)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS events "
                "(id TEXT PRIMARY KEY, time TEXT NOT NULL, session_id TEXT NOT NULL, "
                "run_id TEXT NOT NULL, type TEXT NOT NULL, data TEXT NOT NULL)"
            )
            database.execute(
                "CREATE INDEX IF NOT EXISTS events_session ON events(session_id,time)"
            )

    def _connect(self) -> sqlite3.Connection:
        database = sqlite3.connect(self.filename, timeout=5)
        database.execute("PRAGMA journal_mode=WAL")
        return database

    def create(self, state: dict) -> None:
        data = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as database:
            database.execute(
                "INSERT INTO runs(id,state,version) VALUES(?,?,0)",
                (state["id"], data),
            )
        state["_version"] = 0

    def load(self, run_id: str) -> dict:
        with self._connect() as database:
            row = database.execute(
                "SELECT state,version FROM runs WHERE id=?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown run_id: {run_id}")
        state = json.loads(row[0])
        state["_version"] = row[1]
        return state

    def save(self, state: dict) -> None:
        expected = state.get("_version")
        if not isinstance(expected, int):
            raise StateConflict("state version is missing")
        clean = {key: value for key, value in state.items() if key != "_version"}
        data = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as database:
            cursor = database.execute(
                "UPDATE runs SET state=?,version=version+1 WHERE id=? AND version=?",
                (data, state["id"], expected),
            )
            if cursor.rowcount != 1:
                raise StateConflict("run was changed by another process")
        state["_version"] = expected + 1

    def create_session(self, session_id: str | None = None) -> str:
        value = session_id or uuid.uuid4().hex
        with self._connect() as database:
            database.execute(
                "INSERT OR IGNORE INTO sessions(id,created_at) VALUES(?,?)",
                (value, datetime.now().astimezone().isoformat()),
            )
        return value

    def add_event(
        self, session_id: str, run_id: str, event_type: str, data: dict
    ) -> dict:
        event = {
            "id": uuid.uuid4().hex,
            "time": datetime.now().astimezone().isoformat(),
            "session_id": session_id,
            "run_id": run_id,
            "type": event_type,
            "data": data,
        }
        with self._connect() as database:
            database.execute(
                "INSERT INTO events(id,time,session_id,run_id,type,data) "
                "VALUES(?,?,?,?,?,?)",
                (
                    event["id"],
                    event["time"],
                    session_id,
                    run_id,
                    event_type,
                    json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                ),
            )
        return event

    def events(self, session_id: str, run_id: str | None = None) -> list[dict]:
        query = (
            "SELECT id,time,session_id,run_id,type,data FROM events WHERE session_id=?"
        )
        values: tuple[str, ...] = (session_id,)
        if run_id:
            query += " AND run_id=?"
            values = (session_id, run_id)
        query += " ORDER BY time,id"
        with self._connect() as database:
            rows = database.execute(query, values).fetchall()
        return [
            {
                "id": row[0],
                "time": row[1],
                "session_id": row[2],
                "run_id": row[3],
                "type": row[4],
                "data": json.loads(row[5]),
            }
            for row in rows
        ]

    def session_runs(self, session_id: str) -> list[dict]:
        with self._connect() as database:
            rows = database.execute("SELECT state FROM runs ORDER BY rowid").fetchall()
        states = [json.loads(row[0]) for row in rows]
        return [state for state in states if state.get("session_id") == session_id]

    def session_stats(self, session_id: str) -> dict:
        events = self.events(session_id)
        runs = self.session_runs(session_id)
        tools: dict[str, int] = {}
        skills: dict[str, int] = {}
        mcp: dict[str, int] = {}
        for event in events:
            data = event["data"]
            if event["type"] == "tool_call":
                name = str(data.get("name", "unknown"))
                tools[name] = tools.get(name, 0) + 1
            elif event["type"] == "skill_loaded":
                name = str(data.get("name", "unknown"))
                skills[name] = skills.get(name, 0) + 1
            elif event["type"] == "mcp_call":
                name = f"{data.get('server', 'unknown')}/{data.get('name', 'unknown')}"
                mcp[name] = mcp.get(name, 0) + 1
        input_values = [run.get("usage", {}).get("input_tokens") for run in runs]
        output_values = [run.get("usage", {}).get("output_tokens") for run in runs]
        usage_complete = bool(runs) and all(
            run.get("usage", {}).get("complete") is True for run in runs
        )
        return {
            "session_id": session_id,
            "runs": len(runs),
            "events": len(events),
            "input_tokens": sum(input_values) if usage_complete else None,
            "output_tokens": sum(output_values) if usage_complete else None,
            "usage_complete": usage_complete,
            "tools": tools,
            "skills": skills,
            "mcp": mcp,
            "unique_tools": len(tools),
            "unique_skills": len(skills),
        }

    def export_events(self, session_id: str, filename: Path) -> None:
        filename.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(event, ensure_ascii=False, separators=(",", ":"))
            for event in self.events(session_id)
        ]
        filename.write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )
