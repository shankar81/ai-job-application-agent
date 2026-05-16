"""Persistent human-answer memory.

Answers the user provides during Easy Apply forms are saved to
storage/human_answers.json so future runs can reuse them without
prompting again.
"""

import json
import os
import re
from datetime import datetime

from agentic.tools import read_file, write_file

HUMAN_ANSWERS_PATH = "./storage/human_answers.json"


def _normalize_key(label: str) -> str:
    """Produce a stable, filesystem-safe key from a field label or question."""
    key = re.sub(r"[^\w\s]", "", label.lower())
    return re.sub(r"\s+", "_", key.strip())[:60]


def _load_human_answers() -> dict:
    """Load the persisted human-answer memory from disk. Returns {} if missing."""
    if os.path.exists(HUMAN_ANSWERS_PATH):
        try:
            return json.loads(read_file(HUMAN_ANSWERS_PATH))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_human_answer(field: str, question: str, answer: str) -> None:
    """Persist a new human answer (or update an existing one) to disk.

    Each entry tracks:
    - answer            — most recent authoritative value
    - aliases           — alternate field-name spellings seen
    - question_examples — up to 5 phrasings of the same question
    - field_labels      — distinct field labels this answer was used for
    - updated_on        — ISO timestamp of last update
    - use_count         — how many times the user has provided this answer
    """
    memory = _load_human_answers()
    key = _normalize_key(field)
    now = datetime.now().isoformat(timespec="seconds")

    if key in memory:
        entry = memory[key]
        entry["answer"] = answer
        entry["updated_on"] = now
        entry["use_count"] = entry.get("use_count", 0) + 1
        # Keep at most 5 example phrasings to avoid unbounded growth
        examples: list = entry.setdefault("question_examples", [])
        if question not in examples:
            examples.append(question)
            entry["question_examples"] = examples[-5:]
        labels: list = entry.setdefault("field_labels", [])
        if field not in labels:
            labels.append(field)
    else:
        memory[key] = {
            "answer": answer,
            "aliases": [],
            "question_examples": [question],
            "field_labels": [field],
            "updated_on": now,
            "use_count": 1,
        }

    write_file(HUMAN_ANSWERS_PATH, json.dumps(memory, indent=2))
