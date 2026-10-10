import sqlite3
from datetime import date, timedelta

import pytest

from src.database.repository import DataBaseManager
from src.database.migrations import MIGRATIONS, apply_migrations, Migration
from src.database.models import Comment, CommentTypes
from src.shared.time_utils import get_moscow_date


def test_fresh_db_applies_all_migrations(db_manager, db_cursor):
    db_cursor.execute("SELECT version, name FROM schema_migrations ORDER BY version")
    rows = db_cursor.fetchall()
    assert [r[0] for r in rows] == [m.version for m in MIGRATIONS]
    assert rows[0][1] == "comments_scheduled_unique"


def test_migrations_idempotent(temp_db_path):
    DataBaseManager(temp_db_path)
    DataBaseManager(temp_db_path)

    conn = sqlite3.connect(temp_db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    finally:
        conn.close()
    assert count == len(MIGRATIONS)


def test_comments_has_partial_unique_indexes(db_manager, db_cursor):
    db_cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='comments' AND sql LIKE '%UNIQUE%'"
    )
    indexes = {row[0] for row in db_cursor.fetchall()}
    assert "idx_comments_unique_regular" in indexes
    assert "idx_comments_unique_scheduled" in indexes


def test_migrate_old_schema_preserves_data(temp_db_path):
    today = date.fromisoformat(get_moscow_date())
    first_date = (today + timedelta(days=1)).isoformat()
    second_date = (today + timedelta(days=3)).isoformat()

    with sqlite3.connect(temp_db_path) as conn:
        conn.executescript(
            f"""
            CREATE TABLE comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                comment_type TEXT NOT NULL,
                comment_text TEXT NOT NULL,
                scheduled_date TEXT,
                use_count INTEGER DEFAULT 0,
                UNIQUE(group_id, comment_type, comment_text)
            );
            INSERT INTO comments (group_id, comment_type, comment_text, scheduled_date, use_count)
            VALUES (-100, 'scheduled', 'alvldvvla', '{first_date}', 0);
            INSERT INTO comments (group_id, comment_type, comment_text, scheduled_date, use_count)
            VALUES (-100, 'scheduled', 'zhopa', '{second_date}', 0);
            INSERT INTO comments (group_id, comment_type, comment_text, scheduled_date, use_count)
            VALUES (-100, 'text', 'kruto', NULL, 0);
            """
        )

    DataBaseManager(temp_db_path)

    conn = sqlite3.connect(temp_db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT comment_text, comment_type, scheduled_date FROM comments ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    assert [(r["comment_text"], r["comment_type"], r["scheduled_date"]) for r in rows] == [
        ("alvldvvla", "scheduled", first_date),
        ("zhopa", "scheduled", second_date),
        ("kruto", "text", None),
    ]


def test_same_scheduled_text_two_dates(comments_manager):
    first = Comment(-100, CommentTypes.SCHEDULED, "zhopa", "2026-10-11")
    second = Comment(-100, CommentTypes.SCHEDULED, "zhopa", "2026-10-12")

    assert comments_manager.add_comment(first) is True
    assert comments_manager.add_comment(second) is True

    for day in ("2026-10-11", "2026-10-12"):
        assert [c.comment_text for c in comments_manager.get_scheduled_for_today(-100, day)] == ["zhopa"]


def test_same_scheduled_text_same_date_duplicate(comments_manager):
    first = Comment(-100, CommentTypes.SCHEDULED, "zhopa", "2026-10-11")
    duplicate = Comment(-100, CommentTypes.SCHEDULED, "zhopa", "2026-10-11")

    assert comments_manager.add_comment(first) is True
    assert comments_manager.add_comment(duplicate) is False


def test_text_dedup_unchanged(comments_manager):
    first = Comment(-100, CommentTypes.TEXT, "kruto")
    duplicate = Comment(-100, CommentTypes.TEXT, "kruto")

    assert comments_manager.add_comment(first) is True
    assert comments_manager.add_comment(duplicate) is False


def test_failed_migration_rolls_back(temp_db_path):
    conn = sqlite3.connect(temp_db_path)
    try:
        conn.execute("CREATE TABLE invoice (id INTEGER);")
        conn.commit()

        def boom(c):
            c.execute("CREATE TABLE boom_table (id INTEGER);")
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            apply_migrations(conn, [Migration(99, "boom", boom)])

        leftover = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='boom_table'"
        ).fetchone()
        assert leftover is None
        applied = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert applied == 0
    finally:
        conn.close()