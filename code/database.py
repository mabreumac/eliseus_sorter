"""SQLite persistence for reference face embeddings."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator

import numpy as np

from config import DATABASE_PATH

EMBEDDING_DIM = 128


def _connect(db_path: Path = DATABASE_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_database(db_path: Path = DATABASE_PATH) -> None:
    """Create tables if they do not exist."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reference_faces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                embedding BLOB NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reference_student "
            "ON reference_faces(student_name)"
        )
        conn.commit()


def file_path_exists(file_path: str, db_path: Path = DATABASE_PATH) -> bool:
    """Return True if this file path is already indexed."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM reference_faces WHERE file_path = ? LIMIT 1",
            (file_path,),
        ).fetchone()
    return row is not None


def insert_reference_face(
    student_name: str,
    file_path: str,
    embedding: np.ndarray,
    db_path: Path = DATABASE_PATH,
) -> int:
    """Insert a single reference embedding; returns the new row id."""
    blob = embedding.astype(np.float64).tobytes()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO reference_faces (student_name, file_path, embedding)
            VALUES (?, ?, ?)
            """,
            (student_name, file_path, blob),
        )
        conn.commit()
        return int(cursor.lastrowid)


def iter_reference_embeddings(
    db_path: Path = DATABASE_PATH,
) -> Generator[tuple[str, str, np.ndarray], None, None]:
    """
    Stream reference rows one at a time.

    Yields (student_name, file_path, embedding).
    """
    with _connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT student_name, file_path, embedding FROM reference_faces"
        )
        for row in cursor:
            embedding = np.frombuffer(row["embedding"], dtype=np.float64).copy()
            if embedding.shape[0] != EMBEDDING_DIM:
                raise ValueError(
                    f"Invalid embedding dim {embedding.shape[0]} in {row['file_path']}"
                )
            yield row["student_name"], row["file_path"], embedding


def count_reference_faces(db_path: Path = DATABASE_PATH) -> int:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM reference_faces").fetchone()
    return int(row["n"])


def count_students(db_path: Path = DATABASE_PATH) -> int:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT student_name) AS n FROM reference_faces"
        ).fetchone()
    return int(row["n"])
