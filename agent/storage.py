import json
import sqlite3
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
