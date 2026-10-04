import time

from src.bot.services.comments import CommentsManager


def test_parse_comment_template_replace(comments_manager):
    res = comments_manager.parse_comment_template("vova {{name}}")

    assert "vova" in res
    assert "{{name}}" not in res


def test_parse_comment_template_dont_replace_unknown_key(comments_manager):
    res = comments_manager.parse_comment_template("vova {{unknown}}")

    assert "vova" in res
    assert "{{unknown}}" in res


def test_parse_comment_template_no_templates(comments_manager):
    res = comments_manager.parse_comment_template("vova 777")

    assert "vova" in res
    assert "777" in res


def test_parse_comment_template_multiple_templates(comments_manager):
    result = comments_manager.parse_comment_template("{{name}} iz {{company}}")

    assert "{{name}}" not in result
    assert "{{company}}" not in result
    assert " iz " in result


def test_last_comment_starts_empty(comments_manager):
    assert comments_manager.get_last_comment(100) is None


def test_last_comment_set_and_get(comments_manager):
    comments_manager.set_last_comment(100, "первый")
    assert comments_manager.get_last_comment(100) == "первый"

    comments_manager.set_last_comment(100, "второй")
    assert comments_manager.get_last_comment(100) == "второй"


def test_last_comment_isolated_per_chat(comments_manager):
    comments_manager.set_last_comment(100, "для сто")

    assert comments_manager.get_last_comment(200) is None
    assert comments_manager.get_last_comment(100) == "для сто"


def test_last_comment_survives_restart(db_manager):
    before_restart = CommentsManager(db=db_manager)
    before_restart.set_last_comment(100, "текст")

    after_restart = CommentsManager(db=db_manager)

    assert after_restart.get_last_comment(100) == "текст"


def test_last_comment_read_from_ram_not_db(comments_manager, monkeypatch):
    comments_manager.set_last_comment(100, "текст")

    calls = []
    monkeypatch.setattr(comments_manager.db, "get_last_comment", lambda g: calls.append(g))

    for _ in range(5):
        assert comments_manager.get_last_comment(100) == "текст"

    assert calls == []


def test_banwords_cache_reads_source_once(comments_manager, monkeypatch):
    comments_manager.add_banword(1, "привет", "ответ")

    calls = []
    original = comments_manager.db.get_banwords_list

    def counting(group_id):
        calls.append(group_id)
        return original(group_id)

    monkeypatch.setattr(comments_manager.db, "get_banwords_list", counting)

    for _ in range(5):
        comments_manager.get_valid_banwords(1)

    assert calls == [1]


def test_banwords_cache_survives_restart(db_manager, monkeypatch):
    before_restart = CommentsManager(db=db_manager)
    before_restart.add_banword(1, "привет", "ответ")
    assert len(before_restart.get_valid_banwords(1)) == 1

    after_restart = CommentsManager(db=db_manager)

    calls = []
    original = db_manager.get_banwords_list

    def counting(group_id):
        calls.append(group_id)
        return original(group_id)

    monkeypatch.setattr(db_manager, "get_banwords_list", counting)

    assert [b.pattern for b in after_restart.get_valid_banwords(1)] == ["привет"]
    assert calls == []


def test_expired_ram_falls_back_to_db_cache(comments_manager):
    comments_manager.add_banword(1, "привет", "ответ1")
    assert len(comments_manager.get_valid_banwords(1)) == 1

    expires_at, cached = comments_manager._banwords_ram[1]
    comments_manager._banwords_ram[1] = (time.time() - 1, cached)

    assert len(comments_manager.get_valid_banwords(1)) == 1


def test_expired_db_cache_falls_back_to_source(comments_manager, db_cursor):
    comments_manager.db.add_banword(1, "привет", "ответ1")
    assert len(comments_manager.get_valid_banwords(1)) == 1

    past = time.time() - 1
    db_cursor.execute("UPDATE banwords_cache SET expires_at = ?", (past,))
    db_cursor.connection.commit()
    expires_at, cached = comments_manager._banwords_ram[1]
    comments_manager._banwords_ram[1] = (past, cached)

    comments_manager.db.add_banword(1, "пока", "ответ2")
    assert len(comments_manager.get_valid_banwords(1)) == 2


def test_add_banword_invalidates_both_levels(comments_manager):
    assert comments_manager.get_valid_banwords(1) == []
    assert comments_manager.db.get_banwords_cache(1) is not None

    comments_manager.add_banword(1, "привет", "ответ")

    assert comments_manager.db.get_banwords_cache(1) is None
    assert 1 not in comments_manager._banwords_ram
    assert [b.pattern for b in comments_manager.get_valid_banwords(1)] == ["привет"]


def test_add_banword_rejects_broken_pattern(comments_manager):
    assert comments_manager.add_banword(1, "([", "ответ") is False
    assert comments_manager.db.get_banwords_list(1) == []


def test_add_banword_rejects_duplicate(comments_manager):
    assert comments_manager.add_banword(1, "привет", "ответ") is True
    assert comments_manager.add_banword(1, "привет", "другой") is False
    assert len(comments_manager.db.get_banwords_list(1)) == 1


def test_banwords_cache_isolated_per_group(comments_manager):
    comments_manager.add_banword(1, "привет", "ответ1")
    comments_manager.add_banword(2, "пока", "ответ2")

    assert [b.pattern for b in comments_manager.get_valid_banwords(1)] == ["привет"]
    assert [b.pattern for b in comments_manager.get_valid_banwords(2)] == ["пока"]


def test_get_valid_banwords_skips_broken_pattern(comments_manager):
    comments_manager.db.add_banword(1, "([", "ответ1")
    comments_manager.db.add_banword(1, "привет", "ответ2")

    valid = comments_manager.get_valid_banwords(1)

    assert [b.pattern for b in valid] == ["привет"]
    assert "([" in comments_manager._bad_patterns


def test_broken_pattern_stays_skipped_but_fixed_one_works(comments_manager):
    comments_manager.db.add_banword(1, "([", "ответ1")
    comments_manager.get_valid_banwords(1)

    comments_manager.add_banword(1, "привет", "ответ2")

    assert [b.pattern for b in comments_manager.get_valid_banwords(1)] == ["привет"]
