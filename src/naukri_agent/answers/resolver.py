"""Answer priority: saved answers -> profile rules -> LLM."""
import difflib

from .. import config
from .llm import llm_answer
from .rules import rule_answer
from .store import norm

SAVED_ANSWER_CUTOFF = config.get_float("SAVED_ANSWER_CUTOFF")


def find_answer(question, saved, field_type="text", options=None):
    """Return (answer, source). source is 'saved' | 'rule' | 'llm'; answer '' when none."""
    q = norm(question)
    if q in saved:
        return saved[q], "saved"
    close = difflib.get_close_matches(q, list(saved), n=1, cutoff=SAVED_ANSWER_CUTOFF)
    if close:
        return saved[close[0]], "saved"
    ans = rule_answer(question)
    if ans:
        return ans, "rule"
    ans = llm_answer(question, field_type, options)
    return ans, "llm" if ans else ""
