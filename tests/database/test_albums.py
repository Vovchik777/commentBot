import time


def test_mark_album_processed_once(db_manager):
    assert db_manager.mark_album_processed("jqoiwejqwe") is True


def test_mark_album_processed_twice(db_manager):
    assert db_manager.mark_album_processed("zxcvbnmasd") is True
    assert db_manager.mark_album_processed("zxcvbnmasd") is False


def test_is_album_processed_expired(db_manager, db_cursor):
    media_group_id = "poiuytrewq"
    db_manager.mark_album_processed(media_group_id)
    db_cursor.execute(
        "UPDATE processed_albums SET expires_at = ? WHERE media_group_id = ?",
        (time.time() - 1, media_group_id),
    )
    db_cursor.connection.commit()
    assert db_manager.is_album_processed(media_group_id) is False
