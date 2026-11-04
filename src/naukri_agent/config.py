"""Single place that reads .env. No defaults live in code: set every value in .env
(see .env.example for the full list and example values)."""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root
load_dotenv(os.path.join(BASE_DIR, ".env"))


def get(name):
    """Return the stripped value of an env variable ('' when unset)."""
    return os.getenv(name, "").strip()


def _required(name):
    value = get(name)
    if not value:
        raise SystemExit(f"{name} is not set in .env (see .env.example)")
    return value


def get_bool(name):
    """True for 1/true/yes/on (any case); anything else, including unset, is False."""
    return get(name).lower() in ("1", "true", "yes", "on")


def get_int(name):
    return int(_required(name))


def get_float(name):
    return float(_required(name))


def data_path(filename):
    """Path of a file inside DATA_DIR (created on first use)."""
    folder = os.path.join(BASE_DIR, get("DATA_DIR"))
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, filename)


def resume_path():
    return os.path.join(BASE_DIR, _required("RESUME_FILE"))


# ---------------------------------------------------------------------------
# Candidate profile and skill years (all values come from .env)
# ---------------------------------------------------------------------------
def _parse_skill_years(raw):
    """Parse 'python:4,docker:2' into {'python': '4', 'docker': '2'}."""
    out = {}
    for part in raw.split(","):
        skill, _, years = part.rpartition(":")
        if skill.strip() and years.strip():
            out[skill.strip().lower()] = years.strip()
    return out


SKILL_YEARS = _parse_skill_years(get("SKILL_YEARS"))


def build_profile():
    return {
        "full_name": get("FULL_NAME"),
        "first_name": get("FIRSTNAME"),
        "last_name": get("LASTNAME"),
        "email": get("PROFILE_EMAIL"),
        "phone": get("PROFILE_PHONE"),
        "city": get("PROFILE_CITY"),
        "linkedin": get("PROFILE_LINKEDIN"),
        "total_experience": get("TOTAL_EXPERIENCE"),
        "current_company": get("PROFILE_COMPANY"),
        "designation": get("PROFILE_DESIGNATION"),
        "degree": get("PROFILE_DEGREE"),
        "branch": get("PROFILE_BRANCH"),
        "college": get("PROFILE_COLLEGE"),
        "cgpa": get("PROFILE_CGPA"),
        # Not on resume -> must come from .env, otherwise unanswered
        "current_ctc": get("CURRENT_CTC"),
        "expected_ctc": get("EXPECTED_CTC"),
        "notice_period": get("NOTICE_PERIOD"),           # e.g. "30 days"
        "immediate_joiner": get("IMMEDIATE_JOINER"),     # yes / no
        "relocate": get("WILLING_TO_RELOCATE"),          # yes / no
        "work_from_office": get("WILLING_TO_WORK_FROM_OFFICE"),
        "work_authorized": get("AUTHORIZED_TO_WORK_IN_INDIA"),
    }


PROFILE = build_profile()
