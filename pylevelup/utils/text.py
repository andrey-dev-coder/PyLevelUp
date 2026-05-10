import re
from html import escape

DASH_MAP = {
    "\u2014": "-",
    "\u2013": "-",
    "\u2212": "-",
}

CODE_HINT_CHARS = "()[]{};=<>"
CODE_KEYWORDS = (
    "def ",
    "class ",
    "import ",
    "from ",
    "lambda",
    "return ",
    "yield ",
    "raise ",
    "async ",
    "await ",
    "print(",
    "len(",
    "range(",
    "list(",
    "dict(",
    "set(",
    "tuple(",
    "str(",
    "int(",
    "True",
    "False",
    "None",
    "self.",
    "*args",
    "**kwargs",
    "SELECT ",
    "INSERT ",
    "UPDATE ",
    "DELETE ",
    "JOIN ",
    "WHERE ",
)

BACKTICK_RE = re.compile(r"`([^`]+)`")
COLON_CODE_RE = re.compile(r"^(.+?:\s+)(.+?)([?.!]?)$", re.DOTALL)


def clean_text(text: str) -> str:
    cleaned = text
    for src, dst in DASH_MAP.items():
        cleaned = cleaned.replace(src, dst)
    return cleaned


def _looks_like_code(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if any(kw in stripped for kw in CODE_KEYWORDS):
        return True
    code_chars = sum(1 for c in stripped if c in CODE_HINT_CHARS)
    if code_chars >= 2:
        return True
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    return False


def _segment_html(text: str) -> str:
    if not text:
        return ""
    match = COLON_CODE_RE.match(text)
    if match:
        prefix, candidate, suffix = match.group(1), match.group(2), match.group(3)
        if _looks_like_code(candidate):
            return f"{escape(prefix)}<code>{escape(candidate)}</code>{escape(suffix)}"
    if _looks_like_code(text):
        return f"<code>{escape(text)}</code>"
    return escape(text)


def render_with_code(raw: str) -> str:
    text = clean_text(raw)
    if "`" in text:
        parts: list[str] = []
        last = 0
        for m in BACKTICK_RE.finditer(text):
            if m.start() > last:
                parts.append(_segment_html(text[last:m.start()]))
            parts.append(f"<code>{escape(m.group(1))}</code>")
            last = m.end()
        if last < len(text):
            parts.append(_segment_html(text[last:]))
        return "".join(parts)
    return _segment_html(text)


def format_question_text(
    question_text: str,
    options: list[str],
    progress_index: int,
    total: int,
) -> str:
    header = f"Вопрос {progress_index + 1} из {total}"
    body = render_with_code(question_text)
    options_lines = "\n".join(
        f"<b>{i + 1}.</b> {render_with_code(option)}" for i, option in enumerate(options)
    )
    return f"<b>{header}</b>\n\n{body}\n\n{options_lines}"
