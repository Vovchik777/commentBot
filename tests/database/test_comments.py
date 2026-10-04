from sqlite3 import Row

import pytest

from src.database.models import Comment, CommentTypes


def test_add_comment_success(comments_manager, db_cursor, comment_factory):
    comment = comment_factory()

    assert comments_manager.add_comment(comment) is True


def test_add_comment_duplicate(comments_manager, db_cursor, comment_factory):
    comment = comment_factory()

    assert comments_manager.add_comment(comment) is True
    assert comments_manager.add_comment(comment) is False


def test_delete_comment_success(comments_manager, db_cursor, comment_factory):
    comment = comment_factory()

    comments_manager.add_comment(comment)
    assert comments_manager.delete_comment(comment.group_id, comment.comment_type, 1) == comment

    db_cursor.execute(
        """SELECT id FROM comments WHERE group_id = ? AND comment_type = ? AND comment_text = ?""",
        (
            comment.group_id,
            comment.comment_type,
            comment.comment_text,
        ),
    )
    assert db_cursor.fetchone() is None


def test_delete_comment_not_found(comments_manager, db_cursor, comment_factory):
    comment = comment_factory()
    assert comments_manager.delete_comment(comment.group_id, comment.comment_type, 1) is None


def test_delete_comment_other_group(comments_manager, db_manager, db_cursor, comment_factory):
    comment = comment_factory()

    comments_manager.add_comment(comment)
    assert comments_manager.delete_comment(comment.group_id + 1, comment.comment_type, 1) is None

    db_cursor.execute(
        """SELECT id FROM comments WHERE group_id = ? AND comment_type = ? AND comment_text = ?""",
        (
            comment.group_id,
            comment.comment_type,
            comment.comment_text,
        ),
    )
    assert db_cursor.fetchone() is not None


def test_delete_comment_low_index(comments_manager, db_cursor, comment_factory):
    comment = comment_factory()
    comments_manager.add_comment(comment)
    assert comments_manager.delete_comment(comment.group_id, comment.comment_type, 0) is None


def test_delete_comment_wrong_index(comments_manager, db_cursor, comment_factory):
    comment = comment_factory()
    comments_manager.add_comment(comment)
    assert comments_manager.delete_comment(comment.group_id, comment.comment_type, 3) is None


def test_get_random_comment_returns_one_of_group(comments_manager, comment_factory):
    c2 = comment_factory(comment_text="bbb", tg_group_id=100)
    c3 = comment_factory(comment_text="ccc", tg_group_id=100)
    c1 = comment_factory(comment_text="aaa", tg_group_id=100)
    comments_manager.add_comment(c1)
    comments_manager.add_comment(c2)
    comments_manager.add_comment(c3)

    result = comments_manager.get_random_comment(c1.group_id, CommentTypes.TEXT)

    assert result in (c1, c2, c3)


def test_get_random_comment_isolated_by_group(comments_manager, comment_factory):
    in_group = comment_factory(comment_text="aaa", tg_group_id=100)
    in_other_group = comment_factory(comment_text="bbb", tg_group_id=200)
    comments_manager.add_comment(in_group)
    comments_manager.add_comment(in_other_group)

    for _ in range(20):
        result = comments_manager.get_random_comment(in_group.group_id, CommentTypes.TEXT)
        assert result == in_group


def test_get_random_comment_empty(comments_manager):
    assert comments_manager.get_random_comment(100, CommentTypes.TEXT) is None


def test_get_random_comment_bypass_random_by_one(comments_manager, comment_factory):
    comment = comment_factory()
    comments_manager.add_comment(comment)

    assert comments_manager.get_random_comment(comment.group_id, CommentTypes.TEXT) == comment


def test_get_scheduled_for_today_one_match(comments_manager, comment_factory):
    comment = comment_factory(scheduled_date="1234-12-34", comment_type=CommentTypes.SCHEDULED)
    comments_manager.add_comment(comment)

    res = comments_manager.get_scheduled_for_today(comment.group_id, "1234-12-34")

    assert len(res) == 1
    assert res[0] == comment
    assert isinstance(res[0], Comment) is True


def test_get_scheduled_for_today_multiply_match(comments_manager, comment_factory):
    N = 10
    comments = list()
    for i in range(N):
        comment = comment_factory(scheduled_date="1234-12-34", comment_type=CommentTypes.SCHEDULED, comment_text=f"zhopa bobra {i}")
        comments_manager.add_comment(comment)
        comments.append(comment)

    res = comments_manager.get_scheduled_for_today(comment.group_id, "1234-12-34")

    assert len(res) == N
    assert [c for c in res] == comments


def test_get_scheduled_for_today_other_date(comments_manager, comment_factory):
    comment1 = comment_factory(scheduled_date="1234-12-34", comment_type=CommentTypes.SCHEDULED)
    comment2 = comment_factory(scheduled_date="9999-99-99", comment_type=CommentTypes.SCHEDULED)

    comments_manager.add_comment(comment1)
    comments_manager.add_comment(comment2)

    res = comments_manager.get_scheduled_for_today(comment1.group_id, "1234-12-34")

    assert len(res) == 1
    assert res[0] == comment1
    assert isinstance(res[0], Comment) is True


def test_get_scheduled_for_today_other_group(comments_manager, comment_factory):
    comment1 = comment_factory(scheduled_date="1234-12-34", comment_type=CommentTypes.SCHEDULED)
    comment2 = comment_factory(tg_group_id=comment1.group_id + 1, scheduled_date="1234-12-34", comment_type=CommentTypes.SCHEDULED)

    comments_manager.add_comment(comment1)
    comments_manager.add_comment(comment2)

    res = comments_manager.get_scheduled_for_today(comment1.group_id, "1234-12-34")

    assert len(res) == 1
    assert res[0] == comment1
    assert isinstance(res[0], Comment) is True


def test_get_scheduled_for_today_other_type(comments_manager, comment_factory):
    comment1 = comment_factory(scheduled_date="1234-12-34", comment_type=CommentTypes.SCHEDULED)
    comment2 = comment_factory(tg_group_id=comment1.group_id + 1, comment_type=CommentTypes.TEXT)

    comments_manager.add_comment(comment1)
    comments_manager.add_comment(comment2)

    res = comments_manager.get_scheduled_for_today(comment1.group_id, "1234-12-34")

    assert len(res) == 1
    assert res[0] == comment1
    assert isinstance(res[0], Comment) is True
    assert res[0].comment_type == CommentTypes.SCHEDULED


def test_get_scheduled_for_today_null_date(comments_manager, comment_factory, db_cursor):
    comment = comment_factory(scheduled_date=None, comment_type=CommentTypes.SCHEDULED)

    assert comments_manager.add_comment(comment) is False  # провекра через метод

    db_cursor.execute(
        "INSERT INTO comments (group_id, comment_type, comment_text, scheduled_date) VALUES (?, ?, ?, ?)",
        (comment.group_id, CommentTypes.SCHEDULED, "text", None),
    )

    db_cursor.connection.commit()

    res = comments_manager.get_scheduled_for_today(comment.group_id, "1234-12-34")

    assert res == []


def test_get_scheduled_for_today_empty(comments_manager, comment_factory):
    comment = comment_factory(scheduled_date="1234-12-34", comment_type=CommentTypes.SCHEDULED)
    comments_manager.add_comment(comment)

    res = comments_manager.get_scheduled_for_today(comment.group_id, "9999-99-99")

    assert len(res) == 0


def test_get_comments_list_empty(comment_factory, comments_manager, db_manager):
    group_id = 123123
    db_manager.create_group_table(group_id)
    res = comments_manager.get_comments_list(group_id)
    assert res == {"text": [], "photo": [], "scheduled": {}}


def test_get_comments_list_unknown_group(comment_factory, comments_manager, db_manager):
    group_id = 123123
    db_manager.create_group_table(group_id + 1)
    res = comments_manager.get_comments_list(group_id)
    assert res == {"text": [], "photo": [], "scheduled": {}}


def test_get_comments_list_text_only(comment_factory, comments_manager, db_manager):
    group_id = 123123
    comment = comment_factory(tg_group_id=group_id, comment_type=CommentTypes.TEXT)
    comments_manager.add_comment(comment)
    res = comments_manager.get_comments_list(group_id)

    assert res["text"] == [comment]
    assert res["photo"] == []
    assert res["scheduled"] == {}


def test_get_comments_list_photo_only(comment_factory, comments_manager, db_manager):
    group_id = 123123
    comment = comment_factory(tg_group_id=group_id, comment_type=CommentTypes.PHOTO)
    comments_manager.add_comment(comment)
    res = comments_manager.get_comments_list(group_id)

    assert res["text"] == []
    assert res["photo"] == [comment]
    assert res["scheduled"] == {}


def test_get_comments_list_mixed_types(comment_factory, comments_manager, db_manager):
    group_id = 123123

    comment_text = comment_factory(tg_group_id=group_id, comment_type=CommentTypes.TEXT)
    comment_photo = comment_factory(tg_group_id=group_id, comment_type=CommentTypes.PHOTO)
    comment_scheduled = comment_factory(tg_group_id=group_id, comment_type=CommentTypes.SCHEDULED, scheduled_date="1234-12-34")

    for c in (comment_text, comment_photo, comment_scheduled):
        comments_manager.add_comment(c)
    res = comments_manager.get_comments_list(group_id)

    assert res["text"] == [comment_text]
    assert res["photo"] == [comment_photo]
    assert res["scheduled"] == {comment_scheduled.scheduled_date: [comment_scheduled]}


def test_get_comments_list_scheduled_single_date(comment_factory, comments_manager, db_manager):
    group_id = 123123
    comment1 = comment_factory(tg_group_id=group_id, comment_type=CommentTypes.SCHEDULED, scheduled_date="1234-12-34")
    comment2 = comment_factory(
        comment_text=comment1.comment_text + "asde", tg_group_id=group_id, comment_type=CommentTypes.SCHEDULED, scheduled_date="1234-12-34"
    )

    comments_manager.add_comment(comment1)
    comments_manager.add_comment(comment2)

    res = comments_manager.get_comments_list(group_id)

    assert res["scheduled"] == {comment1.scheduled_date: [comment1, comment2]}


def test_get_comments_list_scheduled_multiple_dates(comment_factory, comments_manager, db_manager):
    group_id = 123123
    comment1 = comment_factory(tg_group_id=group_id, comment_type=CommentTypes.SCHEDULED, scheduled_date="1234-12-34")
    comment2 = comment_factory(
        comment_text=comment1.comment_text + "asde", tg_group_id=group_id, comment_type=CommentTypes.SCHEDULED, scheduled_date="9999-99-99"
    )

    comments_manager.add_comment(comment1)
    comments_manager.add_comment(comment2)

    res = comments_manager.get_comments_list(group_id)

    assert res["scheduled"] == {
        comment1.scheduled_date: [
            comment1,
        ],
        comment2.scheduled_date: [
            comment2,
        ],
    }


def test_get_comments_list_scheduled_mixed_dates(comment_factory, comments_manager, db_manager):
    group_id = 123123
    comment1 = comment_factory(tg_group_id=group_id, comment_type=CommentTypes.SCHEDULED, scheduled_date="1234-12-34")
    comment2 = comment_factory(
        comment_text=comment1.comment_text + "asde", tg_group_id=group_id, comment_type=CommentTypes.SCHEDULED, scheduled_date="9999-99-99"
    )
    comment3 = comment_factory(
        comment_text=comment2.comment_text + "asde", tg_group_id=group_id, comment_type=CommentTypes.SCHEDULED, scheduled_date="9999-99-99"
    )

    comments_manager.add_comment(comment1)
    comments_manager.add_comment(comment2)
    comments_manager.add_comment(comment3)

    res = comments_manager.get_comments_list(group_id)

    assert res["scheduled"] == {
        comment1.scheduled_date: [
            comment1,
        ],
        comment2.scheduled_date: [comment2, comment3],
    }


def test_get_comments_list_scheduled_null_date(comment_factory, comments_manager, db_manager, db_cursor):
    group_id = 123123
    comment = comment_factory(comment_type=CommentTypes.SCHEDULED, scheduled_date=None)

    db_cursor.execute(
        """
        INSERT OR IGNORE INTO comments
        (group_id, comment_type, comment_text, scheduled_date, use_count)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            comment.group_id,
            comment.comment_type.value,
            comment.comment_text,
            comment.scheduled_date,
            comment.use_count,
        ),
    )

    db_cursor.connection.commit()

    res = comments_manager.get_comments_list(group_id)

    assert res["scheduled"] == {}


def test_get_comments_list_other_group(comment_factory, comments_manager, db_manager):
    group_id = 123123
    comment1 = comment_factory(tg_group_id=group_id)
    comment2 = comment_factory(comment_text=comment1.comment_text + "asde", tg_group_id=group_id + 1)
    comments_manager.add_comment(comment1)
    comments_manager.add_comment(comment2)

    res = comments_manager.get_comments_list(group_id)

    assert res["text"] == [comment1]


def test_get_comments_list_returns_comment_objects(comment_factory, comments_manager, db_manager):
    group_id = 123123
    comment = comment_factory(tg_group_id=group_id, comment_type=CommentTypes.TEXT)
    comments_manager.add_comment(comment)
    res = comments_manager.get_comments_list(group_id)

    assert isinstance(res["text"][0], Comment)
    assert res["text"][0] == comment


def test_row_to_comment_unknown_type_raises(db_manager, db_cursor, user_factory):
    user = user_factory()
    db_manager.add_user(user)
    db_cursor.execute(
        "INSERT INTO comments (group_id, comment_type, comment_text) VALUES (?, ?, ?)",
        (user.tg_group_id, "unknown_type", "text"),
    )
    db_cursor.connection.commit()

    with pytest.raises(ValueError):
        db_manager.get_comments_list(user.tg_group_id)
