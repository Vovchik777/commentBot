import textwrap
import html
import re
from html.parser import HTMLParser
from typing import Any, Mapping

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

# Теги, которые Telegram понимает в parse_mode="HTML".
_ALLOWED_TAGS = {
    "b",
    "strong",
    "i",
    "em",
    "u",
    "ins",
    "s",
    "strike",
    "del",
    "code",
    "pre",
    "tg-spoiler",
    "blockquote",
    "span",
    "a",
}
_ALLOWED_ENTITIES = {"lt", "gt", "amp", "quot"}
_ALLOWED_HREF_PREFIXES = ("http://", "https://", "tg://")
_LANGUAGE_CLASS_RE = re.compile(r"^language-[A-Za-z0-9_+#-]+$")


class _TelegramHTMLSanitizer(HTMLParser):
    """Ремонт HTML: валидные теги Telegram сохраняет, битые экранирует как текст."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._parts: list[str] = []
        self._stack: list[str] = []

    def _start_tag_text(self, tag: str, attrs) -> str | None:
        rendered_attrs: list[str] = []

        if tag == "a":
            href = dict(attrs).get("href") or ""
            if not href.lower().startswith(_ALLOWED_HREF_PREFIXES):
                return None
            rendered_attrs.append(f'href="{html.escape(href, quote=True)}"')
        elif tag == "span":
            if dict(attrs).get("class") != "tg-spoiler":
                return None
            rendered_attrs.append('class="tg-spoiler"')
        elif tag == "code":
            language = dict(attrs).get("class") or ""
            if _LANGUAGE_CLASS_RE.match(language):
                rendered_attrs.append(f'class="{html.escape(language, quote=True)}"')

        attrs_text = f" {' '.join(rendered_attrs)}" if rendered_attrs else ""
        return f"<{tag}{attrs_text}>"

    def handle_starttag(self, tag: str, attrs) -> None:
        rendered = self._start_tag_text(tag, attrs) if tag in _ALLOWED_TAGS else None
        if rendered is None:
            raw = self.get_starttag_text() or f"<{tag}>"
            self._parts.append(html.escape(raw, quote=False))
            return
        self._parts.append(rendered)
        self._stack.append(tag)

    def handle_startendtag(self, tag: str, attrs) -> None:
        # самозакрывающихся тегов в Telegram нет — показываем как текст
        raw = self.get_starttag_text() or f"<{tag}/>"
        self._parts.append(html.escape(raw, quote=False))

    def handle_endtag(self, tag: str) -> None:
        if tag not in _ALLOWED_TAGS:
            self._parts.append(html.escape(f"</{tag}>", quote=False))
            return
        if tag not in self._stack:
            return  # закрывающий тег без открывающего — выбрасываем
        while self._stack:
            open_tag = self._stack.pop()
            self._parts.append(f"</{open_tag}>")
            if open_tag == tag:
                return

    def handle_data(self, data: str) -> None:
        self._parts.append(html.escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if name in _ALLOWED_ENTITIES:
            self._parts.append(f"&{name};")
        else:
            self._parts.append(f"&amp;{name};")

    def handle_charref(self, name: str) -> None:
        self._parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self._parts.append(html.escape(f"<!--{data}-->", quote=False))

    def handle_decl(self, decl: str) -> None:
        self._parts.append(html.escape(f"<!{decl}>", quote=False))

    def result(self) -> str:
        # незакрытые теги закрываем, чтобы Telegram принял разметку
        while self._stack:
            self._parts.append(f"</{self._stack.pop()}>")
        return "".join(self._parts)


def sanitize_telegram_html(text: str) -> str:
    """Чинит разметку под Telegram: битые теги экранирует, валидные оставляет.

    Идемпотентна: корректный HTML возвращается без изменений.
    """
    parser = _TelegramHTMLSanitizer()
    parser.feed(text)
    parser.close()
    return parser.result()


def split_text(text: str, max_size: int = 4096) -> list[str]:
    return textwrap.wrap(
        text,
        width=max_size,
        expand_tabs=False,
        replace_whitespace=False,
        drop_whitespace=False,
    )


def fill_placeholders(template: str, values: Mapping[str, Any]) -> str:
    escaped = {k: html.escape(str(v)) for k, v in values.items()}
    return _PLACEHOLDER_RE.sub(lambda m: escaped.get(m.group(1), m.group(0)), template)
