"""Learned answers: application_answers.csv (read/write + question normalisation)."""
import csv
import os
import re
from datetime import datetime

from .. import config

ANSWERS_CSV = config.data_path("application_answers.csv")
CSV_FIELDS = ["question_text", "answer", "field_type", "created_at", "source", "options"]


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#/. -]", " ", (text or "").lower())).strip()


def _read_rows():
    if not os.path.exists(ANSWERS_CSV):
        return []
    with open(ANSWERS_CSV, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write_rows(rows):
    with open(ANSWERS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_saved_answers():
    answers = {}
    for row in _read_rows():
        q, a = norm(row.get("question_text")), (row.get("answer") or "").strip()
        if q and a:
            answers[q] = a
    return answers


def save_answer(question, answer, field_type, source, options=None):
    """Record the answer used for a question (no-op if the question is already saved)."""
    rows = _read_rows()
    key = norm(question)
    if any(norm(r.get("question_text")) == key for r in rows):
        return
    rows.append({
        "question_text": question.strip(), "answer": answer, "field_type": field_type,
        "created_at": datetime.now().isoformat(timespec="seconds"), "source": source,
        "options": " | ".join(options or []),
    })
    _write_rows(rows)
