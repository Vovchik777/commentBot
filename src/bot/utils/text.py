import textwrap
import html
import re
from typing import Any, Mapping

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

def split_text(text: str, max_size: int = 4096) -> list[str]:
    return textwrap.wrap(
        text, 
        width=max_size, 
        expand_tabs=False, 
        replace_whitespace=False,
        drop_whitespace=False
    )

def fill_placeholders(template: str, values: Mapping[str, Any]) -> str:
    escaped = {k: html.escape(str(v)) for k, v in values.items()}
    return _PLACEHOLDER_RE.sub(lambda m: escaped.get(m.group(1), m.group(0)), template)