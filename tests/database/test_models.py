import pytest

from src.database.models import Comment, CommentTypes


def test_comment_types():
    assert CommentTypes.from_str("text") is CommentTypes.TEXT
    assert CommentTypes.from_str("photo") is CommentTypes.PHOTO
    assert CommentTypes.from_str("scheduled") is CommentTypes.SCHEDULED

    assert CommentTypes.from_str("TeXt") is CommentTypes.TEXT
    assert CommentTypes.from_str("pHoto") is CommentTypes.PHOTO
    assert CommentTypes.from_str("scHedUled") is CommentTypes.SCHEDULED


def test_comment_types_from_str_unknown():
    assert CommentTypes.from_str("video") is None
    assert CommentTypes.from_str("") is None


def test_comment_types_from_str_not_a_string():
    assert CommentTypes.from_str(None) is None
    assert CommentTypes.from_str(1) is None


def test_comment_accepts_enum():
    comment = Comment(group_id=1, comment_type=CommentTypes.PHOTO, comment_text="text")
    assert comment.comment_type is CommentTypes.PHOTO


def test_comment_coerces_string_to_enum():
    comment = Comment(group_id=1, comment_type="photo", comment_text="text")
    assert comment.comment_type is CommentTypes.PHOTO

    comment = Comment(group_id=1, comment_type="SchEdUled", comment_text="text")
    assert comment.comment_type is CommentTypes.SCHEDULED


def test_comment_rejects_unknown_type():
    with pytest.raises(ValueError):
        Comment(group_id=1, comment_type="video", comment_text="text")

    with pytest.raises(ValueError):
        Comment(group_id=1, comment_type=None, comment_text="text")


def test_comment_type_equals_by_string():
    comment = Comment(group_id=1, comment_type="text", comment_text="text")
    assert comment.comment_type == CommentTypes.TEXT
    assert comment.comment_type == "text"
