"""Shared LLM prompt / reply rules (shared/fixtures/llm)."""
import json
from pathlib import Path

import pytest

from app.translate.llm_prompt import REPLY_SCHEMA, build_messages, parse_reply

FIX = Path(__file__).resolve().parents[2] / "shared" / "fixtures" / "llm"


@pytest.mark.parametrize("path", sorted(FIX.glob("prompt_*.json")), ids=lambda p: p.stem)
def test_prompt_fixture(path):
    case = json.loads(path.read_text(encoding="utf-8"))
    i = case["input"]
    context = [(sp, text) for sp, text in i["context"]]
    examples = [(a, b) for a, b in i.get("examples", [])]
    system, user = build_messages(i["sentences"], context, i["speaker"], i["glossary"], i.get("notes", ""), examples)
    assert (system, user) == (case["expected"]["system"], case["expected"]["user"])


@pytest.mark.parametrize("path", sorted(FIX.glob("reply_*.json")), ids=lambda p: p.stem)
def test_reply_fixture(path):
    case = json.loads(path.read_text(encoding="utf-8"))
    assert parse_reply(case["text"], case["n"]) == case["expected"]


def test_reply_schema_asks_for_a_list_of_strings():
    assert REPLY_SCHEMA["properties"]["translations"] == {"type": "array", "items": {"type": "string"}}
    assert REPLY_SCHEMA["additionalProperties"] is False and REPLY_SCHEMA["required"] == ["translations"]
