"""LLM fallback: asks the `claude` CLI to answer from the resume."""
import logging
import re
import subprocess
import tempfile

from .. import config
from ..config import PROFILE

logger = logging.getLogger(__name__)

RESUME_TXT = config.resume_path()
LLM_MODEL = config.get("LLM_MODEL")
LLM_TIMEOUT = config.get_int("LLM_TIMEOUT")
DEFAULT_NOTICE_PERIOD = config.get("LLM_DEFAULT_NOTICE_PERIOD")


def llm_answer(question, field_type, options):
    """Ask the claude CLI to answer from resume.txt. Returns '' on failure."""
    try:
        with open(RESUME_TXT, encoding="utf-8") as f:
            resume = f.read()
    except OSError:
        logger.warning("  resume.txt missing; cannot use LLM")
        return ""
    extra = "\n".join(f"{k}: {v}" for k, v in PROFILE.items() if v)
    if options:
        fmt = ("Choose from these options and reply with the option text copied EXACTLY: "
               + " || ".join(options)
               + (". Several may be selected; separate them with ' | '." if field_type == "checkbox" else ". Reply with exactly one."))
    elif field_type == "number":
        fmt = "Reply with a single number only."
    else:
        fmt = "Reply with the short answer text only (one line unless a long answer is clearly required)."
    prompt = (
        "You are filling out a job application's recruiter screening question on behalf of the candidate "
        "below. Use ONLY the resume/profile for facts.\n"
        "Rules: answer in first person as the candidate; no explanations, no quotes, no markdown. "
        "For experience-in-X questions give the years from the resume (0 only if truly unrelated). "
        "For yes/no willingness, availability, relocation, interview, or eligibility questions answer Yes "
        f"(candidate is based in {PROFILE['city']} and is actively job hunting). "
        "If a salary or notice-period value is not in the profile, give a realistic, modest value "
        f"(notice period: {DEFAULT_NOTICE_PERIOD}; expected CTC: a reasonable raise over a typical {PROFILE['designation']} salary in India, in LPA).\n\n"
        f"=== RESUME ===\n{resume}\n=== PROFILE OVERRIDES ===\n{extra}\n\n"
        f"=== QUESTION ===\n{question}\n\n{fmt}\nAnswer:"
    )
    try:
        # run from a temp dir so no project CLAUDE.md/context is loaded
        proc = subprocess.run(
            ["claude", "-p", "--model", LLM_MODEL], input=prompt, capture_output=True,
            text=True, encoding="utf-8", timeout=LLM_TIMEOUT, cwd=tempfile.gettempdir())
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning(f"  LLM call failed: {e}")
        return ""
    ans = (proc.stdout or "").strip().strip('"').strip()
    ans = re.sub(r"^answer\s*:\s*", "", ans, flags=re.I)
    return ans.splitlines()[0].strip() if ans and field_type != "textarea" else ans
