import sqlite3
import time
from typing import Callable, List


class Migration:
    def __init__(self, version: int, name: str, fn: Callable[[sqlite3.Connection], None]):
        self.version = version
        self.name = name
        self.fn = fn


def _exec_script(conn: sqlite3.Connection, script: str) -> None:
    for statement in (part.strip() for part in script.split(";")):
        if statement:
            conn.execute(statement)


def migrate_comments_scheduled_unique(conn: sqlite3.Connection) -> None:
    _exec_script(
        conn,
        """
        CREATE TABLE comments_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            comment_type TEXT NOT NULL,
            comment_text TEXT NOT NULL,
            scheduled_date TEXT,
            use_count INTEGER DEFAULT 0
        );

        INSERT INTO comments_new (id, group_id, comment_type, comment_text, scheduled_date, use_count)
        SELECT id, group_id, comment_type, comment_text, scheduled_date, use_count FROM comments;

        DROP TABLE comments;
        ALTER TABLE comments_new RENAME TO comments;

        CREATE UNIQUE INDEX idx_comments_unique_regular
            ON comments(group_id, comment_type, comment_text)
            WHERE comment_type IN ('text','photo');
        CREATE UNIQUE INDEX idx_comments_unique_scheduled
            ON comments(group_id, comment_text, scheduled_date)
            WHERE comment_type = 'scheduled';

        CREATE INDEX idx_comments_lookup ON comments(group_id, comment_type);
        CREATE INDEX idx_comments_scheduled ON comments(group_id, scheduled_date);
        """,
    )


def migrate_empty_usernames_to_null(conn: sqlite3.Connection) -> None:
    _exec_script(
        conn,
        """
        UPDATE users
        SET username = NULL
        WHERE username = ''
        """,
    )


MIGRATIONS: List[Migration] = [
    Migration(1, "comments_scheduled_unique", migrate_comments_scheduled_unique),
    Migration(2, "empty_usernames_to_null", migrate_empty_usernames_to_null),
]


def apply_migrations(conn: sqlite3.Connection, migrations: List[Migration] = MIGRATIONS) -> None:

    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at REAL NOT NULL
);"""
    )
    conn.commit()

    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}

    prev_isolation = conn.isolation_level
    conn.isolation_level = None
    try:
        for migration in migrations:
            if migration.version in applied:
                continue
            conn.execute("BEGIN IMMEDIATE;")
            try:
                migration.fn(conn)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (migration.version, migration.name, time.time()),
                )
                conn.execute("COMMIT;")
            except Exception:
                conn.execute("ROLLBACK;")
                raise
    finally:
        conn.isolation_level = prev_isolation
