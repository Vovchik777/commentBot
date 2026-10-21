import textwrap

def split_text(text: str, max_size: int = 4096) -> list[str]:
    return textwrap.wrap(
        text, 
        width=max_size, 
        expand_tabs=False, 
        replace_whitespace=False,
        drop_whitespace=False
    )