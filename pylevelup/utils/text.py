from html import escape

DASH_MAP = {
    "\u2014": "-",
    "\u2013": "-",
    "\u2212": "-",
}


def clean_text(text: str) -> str:
    cleaned = text
    for src, dst in DASH_MAP.items():
        cleaned = cleaned.replace(src, dst)
    return cleaned


def format_question_text(
    question_text: str,
    options: list[str],
    progress_index: int,
    total: int,
) -> str:
    header = f"Вопрос {progress_index + 1} из {total}"
    body = clean_text(question_text)
    options_lines = "\n".join(
        f"<b>{i + 1}.</b> {escape(clean_text(option))}" for i, option in enumerate(options)
    )
    return f"<b>{header}</b>\n\n{escape(body)}\n\n{options_lines}"
