def test_bot_state_table_not_created(db_manager, db_cursor):
    row = db_cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_state'"
    ).fetchone()

    assert row is None


def test_last_comments_table_created(db_manager, db_cursor):
    row = db_cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='last_comments'"
    ).fetchone()

    assert row is not None
    assert "chat_id INTEGER PRIMARY KEY" in row[0]
    assert "comment_text TEXT NOT NULL" in row[0]


def test_banwords_cache_table_created_with_not_null_expires(db_manager, db_cursor):
    row = db_cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='banwords_cache'"
    ).fetchone()

    assert row is not None
    assert "expires_at REAL NOT NULL" in row[0]


def test_banwords_cache_expire_index_created(db_manager, db_cursor):
    row = db_cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_banwords_cache_expire'"
    ).fetchone()

    assert row is not None


def test_processed_albums_still_created(db_manager, db_cursor):
    row = db_cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='processed_albums'"
    ).fetchone()

    assert row is not None


def test_banwords_table_created_with_unique_on_group_and_pattern(db_manager, db_cursor):
    row = db_cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='banwords'"
    ).fetchone()

    assert row is not None
    assert "UNIQUE(group_id, pattern)" in row[0]
