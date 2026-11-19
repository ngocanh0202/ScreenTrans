"""Prompt and reply rules for the remote LLM engines (rules: shared/fixtures/llm/README.md)."""
import json
import re

SYSTEM = ('Bạn dịch lời thoại và chữ trong game từ tiếng Anh sang tiếng Việt. Dịch tự nhiên, đúng giọng nhân vật, '
          'không thêm bớt ý. Giữ nguyên tên riêng. Trả về JSON {"translations": [...]}, mỗi câu đầu vào đúng một bản '
          'dịch, cùng thứ tự.')
CONTEXT_MAX = 10
EXAMPLES_MAX = 5
REPLY_SCHEMA = {
    "type": "object",
    "properties": {"translations": {"type": "array", "items": {"type": "string"}}},
    "required": ["translations"],
    "additionalProperties": False,
}


def build_messages(sentences: list[str], context: list[tuple[str | None, str]], speaker: str | None,
                   glossary: dict[str, str | None], notes: str = "",
                   examples: list[tuple[str, str]] = ()) -> tuple[str, str]:
    """(system, user) for one call translating `sentences`."""
    parts = []
    if notes.strip():
        parts.append("Về game:\n" + notes.strip())
    if glossary:
        parts.append("Thuật ngữ:\n" + "\n".join(f"- {src} (giữ nguyên)" if dst is None else f"- {src} → {dst}"
                                                for src, dst in glossary.items()))
    if examples:
        parts.append("Cách dịch người dùng đã sửa (làm theo giọng này):\n"
                     + "\n".join(f"- {src} → {fixed}" for src, fixed in list(examples)[-EXAMPLES_MAX:]))
    if context:
        parts.append("Câu trước (để hiểu ngữ cảnh, không dịch):\n"
                     + "\n".join(f"- {sp}: {text}" if sp else f"- {text}" for sp, text in context[-CONTEXT_MAX:]))
    if speaker:
        parts.append(f"Người nói: {speaker}")
    parts.append("Dịch các câu sau:\n" + json.dumps(sentences, ensure_ascii=False))
    return SYSTEM, "\n\n".join(parts)


_START = re.compile(r"[\[{]")


def parse_reply(text: str, n: int) -> list[str] | None:
    """The n translations in the model's reply, or None when it cannot be used as is."""
    m = _START.search(text or "")
    if m is None:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(text, m.start())
    except ValueError:
        return None
    items = data.get("translations") if isinstance(data, dict) else data
    if not isinstance(items, list) or len(items) != n:
        return None
    out = [s.strip() for s in items if isinstance(s, str)]
    if len(out) != n or not all(out):
        return None
    return out
