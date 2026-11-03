"""LLM fallback: asks an AI command-line tool (claude, GitHub Copilot, ...) to answer from the resume.

Providers are configured in .env, so adding one needs no code change:
    LLM_PROVIDER=claude,copilot        # tried in this order; empty or 'none' disables the LLM
    LLM_CLAUDE_COMMAND=claude -p --model haiku
    LLM_COPILOT_COMMAND=copilot -s -p {prompt}
A command containing {prompt} gets the prompt as an argument; otherwise it is sent on stdin.
"""
import logging
import re
import shlex
import shutil
import subprocess
import tempfile

from .. import config
from ..config import PROFILE

logger = logging.getLogger(__name__)

RESUME_TXT = config.resume_path()
LLM_TIMEOUT = config.get_int("LLM_TIMEOUT")
DEFAULT_NOTICE_PERIOD = config.get("LLM_DEFAULT_NOTICE_PERIOD")
PROVIDERS = [p.strip().lower() for p in config.get("LLM_PROVIDER").split(",")
             if p.strip() and p.strip().lower() != "none"]

_unavailable = set()  # providers whose command is missing; not retried during this run

# A prompt passed as a command-line argument may reach a Windows .cmd shim, where newlines
# truncate it and these characters are special. The question text comes from a web page,
# so strip them rather than trust it.
_UNSAFE_ARG_CHARS = re.compile(r'[\r\n"%^&|<>!`]')


def _argument_safe(prompt):
    return re.sub(r"\s+", " ", _UNSAFE_ARG_CHARS.sub(" ", prompt)).strip()


def build_prompt(question, field_type, options, resume):
    extra = "\n".join(f"{k}: {v}" for k, v in PROFILE.items() if v)
    if options:
        fmt = ("Choose from these options and reply with the option text copied EXACTLY: "
               + " || ".join(options)
               + (". Several may be selected; separate them with ' | '." if field_type == "checkbox" else ". Reply with exactly one."))
    elif field_type == "number":
        fmt = "Reply with a single number only."
    else:
        fmt = "Reply with the short answer text only (one line unless a long answer is clearly required)."
    return (
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


def clean_answer(text, field_type):
    ans = (text or "").strip().strip('"').strip()
    ans = re.sub(r"^answer\s*:\s*", "", ans, flags=re.I)
    return ans.splitlines()[0].strip() if ans and field_type != "textarea" else ans


def _ask(provider, prompt):
    """Run one provider's command; returns its stdout, or '' when it is unavailable or fails."""
    command = shlex.split(config.get(f"LLM_{provider.upper()}_COMMAND"))
    if not command:
        logger.warning(f"  LLM '{provider}': LLM_{provider.upper()}_COMMAND is not set in .env; skipping it")
        _unavailable.add(provider)
        return ""
    executable = shutil.which(command[0])
    if executable is None:
        logger.warning(f"  LLM '{provider}': '{command[0]}' is not installed or not on PATH; "
                       f"not using it for the rest of this run")
        _unavailable.add(provider)
        return ""
    as_argument = any("{prompt}" in part for part in command)
    args = [executable] + [part.replace("{prompt}", _argument_safe(prompt)) for part in command[1:]]
    try:
        # run from a temp dir so no project context files are picked up by the tool
        proc = subprocess.run(args, input=None if as_argument else prompt, capture_output=True,
                              text=True, encoding="utf-8", timeout=LLM_TIMEOUT, cwd=tempfile.gettempdir())
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning(f"  LLM '{provider}' call failed: {e}")
        return ""
    if proc.returncode != 0:
        # e.g. not logged in: never use the tool's error text as an answer
        logger.warning(f"  LLM '{provider}' failed (exit {proc.returncode}): "
                       f"{(proc.stderr or proc.stdout or '').strip()[:150]}")
        return ""
    return proc.stdout


def llm_answer(question, field_type, options):
    """Ask the configured LLM providers, in order, to answer from the resume. '' if none can."""
    providers = [p for p in PROVIDERS if p not in _unavailable]
    if not providers:
        return ""
    try:
        with open(RESUME_TXT, encoding="utf-8") as f:
            resume = f.read()
    except OSError:
        logger.warning("  resume file missing; cannot use LLM")
        return ""
    prompt = build_prompt(question, field_type, options, resume)
    for provider in providers:
        answer = clean_answer(_ask(provider, prompt), field_type)
        if answer:
            return answer
    return ""
