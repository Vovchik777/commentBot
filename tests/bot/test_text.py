from src.bot.utils.text import fill_placeholders, sanitize_telegram_html, split_text


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


def test_sanitize_keeps_valid_markup():
    assert sanitize_telegram_html("текст <b>и</b> ещё <i>курсив</i>") == (
        "текст <b>и</b> ещё <i>курсив</i>"
    )


def test_sanitize_escapes_broken_tag_but_keeps_valid_ones():
    # инцидент на проде: <b>по<па</b> — валидный <b> должен отрендериться
    assert sanitize_telegram_html("<b>по<па</b>") == "<b>по&lt;па</b>"


def test_sanitize_closes_unclosed_tags():
    assert sanitize_telegram_html("<b>не закрыт") == "<b>не закрыт</b>"


def test_sanitize_escapes_bare_symbols():
    assert sanitize_telegram_html("a < b & c") == "a &lt; b &amp; c"


def test_sanitize_escapes_unsupported_tags():
    assert sanitize_telegram_html("<div>x</div>") == "&lt;div&gt;x&lt;/div&gt;"


def test_sanitize_fixes_crossed_tags():
    assert sanitize_telegram_html("<b>x<i>y</b>z</i>") == "<b>x<i>y</i></b>z"


def test_sanitize_drops_extra_closing_tags():
    assert sanitize_telegram_html("<b>a</b></b>") == "<b>a</b>"


def test_sanitize_keeps_entities_without_double_escaping():
    assert sanitize_telegram_html("&amp; &lt; &nbsp; &#33;") == "&amp; &lt; &amp;nbsp; &#33;"


def test_sanitize_keeps_safe_links_and_spoilers():
    assert sanitize_telegram_html('<a href="https://example.com">link</a>') == (
        '<a href="https://example.com">link</a>'
    )
    assert sanitize_telegram_html('<span class="tg-spoiler">x</span>') == (
        '<span class="tg-spoiler">x</span>'
    )


def test_sanitize_escapes_unsafe_link():
    assert sanitize_telegram_html('<a href="javascript:alert(1)">bad</a>') == (
        '&lt;a href="javascript:alert(1)"&gt;bad'
    )


def test_sanitize_is_idempotent():
    for text in [
        "<b>по<па</b>",
        "a < b & c",
        "<b>x<i>y</b>z</i>",
        '<a href="https://example.com">link</a>',
        "обычный текст",
    ]:
        once = sanitize_telegram_html(text)
        assert sanitize_telegram_html(once) == once
