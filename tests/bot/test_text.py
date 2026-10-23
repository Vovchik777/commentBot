from src.bot.utils.text import fill_placeholders, split_text


def test_split_text_short_text_single_chunk():
    assert split_text("привет", 4096) == ["привет"]


def test_split_text_empty_text_returns_no_chunks():
    # Пустая строка не режется на чанки; send_message до _send_long_message её не доводит
    assert split_text("", 4096) == []


def test_split_text_respects_max_size():
    text = "слово " * 20

    chunks = split_text(text, 30)

    assert len(chunks) > 1
    assert all(len(chunk) <= 30 for chunk in chunks)
    assert "".join(chunks) == text


def test_split_text_keeps_line_breaks():
    # replace_whitespace=False + drop_whitespace=False: переносы остаются как есть
    assert split_text("a\nb", 10) == ["a\nb"]


def test_fill_placeholders_substitutes_known_keys():
    assert fill_placeholders("<b>{message}</b>", {"message": "привет"}) == "<b>привет</b>"


def test_fill_placeholders_escapes_html():
    assert fill_placeholders("{message}", {"message": "<i>&</i>"}) == "&lt;i&gt;&amp;&lt;/i&gt;"


def test_fill_placeholders_keeps_unknown_placeholders():
    assert fill_placeholders("{a} {unknown}", {"a": "1"}) == "1 {unknown}"


def test_fill_placeholders_does_not_crash_on_stray_braces():
    # раньше str.format падал: IndexError на "{}", KeyError на "{x}"
    assert fill_placeholders("{} {x}", {}) == "{} {x}"


def test_fill_placeholders_survives_format_syntax():
    # str.format упал бы на "{:,}" (ValueError) и "{0}" (IndexError), regex просто оставляет текст
    assert fill_placeholders("{:,} {0}", {}) == "{:,} {0}"


def test_fill_placeholders_escapes_non_string_values():
    assert fill_placeholders("{n}", {"n": 42}) == "42"


def test_fill_placeholders_substitutes_in_one_pass():
    # подставленное значение не сканируется повторно
    assert fill_placeholders("{a}{b}", {"a": "{b}", "b": "<b>"}) == "{b}&lt;b&gt;"
