"""Rule-based answers built from the candidate profile in .env."""
import re

from ..config import PROFILE, SKILL_YEARS
from .store import norm


def rule_answer(question):
    """Return an answer string from the profile rules, or '' when unknown."""
    q = norm(question)
    p = PROFILE

    def has(*words):
        return any(w in q for w in words)

    if has("first name"):
        return p["first_name"]
    if has("last name", "surname"):
        return p["last_name"]
    if has("full name", "your name") or q in ("name", "name *"):
        return p["full_name"]
    if has("email"):
        return p["email"]
    if has("phone", "mobile", "contact number", "whatsapp"):
        return p["phone"]
    if has("linkedin"):
        return p["linkedin"]
    if has("expected ctc", "expected salary", "expected compensation", "expected package"):
        return p["expected_ctc"]
    if has("current ctc", "current salary", "current compensation", "current package", "present ctc", "fixed ctc"):
        return p["current_ctc"]
    if has("immediate joiner", "join immediately", "immediately available"):
        return p["immediate_joiner"]
    if has("notice period", "how soon", "when can you join", "joining time"):
        return p["notice_period"]
    if has("relocat"):
        return p["relocate"]
    if has("work from office", "wfo", "onsite", "on site", "hybrid"):
        return p["work_from_office"]
    if has("authorized to work", "authorised to work", "work permit", "eligible to work"):
        return p["work_authorized"]
    if has("current company", "current employer", "present company", "current organization", "current organisation"):
        return p["current_company"]
    if has("current designation", "current role", "job title", "designation"):
        return p["designation"]
    if has("highest qualification", "highest education", "degree", "qualification"):
        return p["degree"]
    if has("college", "university", "institute"):
        return p["college"]
    if has("cgpa", "percentage", "gpa"):
        return p["cgpa"]
    if has("current location", "current city", "which city", "where are you", "city are you")             and not has("interview", "available", "willing", "relocate"):
        return p["city"]

    if has("experience", "years", "yrs"):
        # Skill-specific experience: longest matching skill key wins
        skills = [s for s in SKILL_YEARS if re.search(r"(^| )" + re.escape(s) + r"( |$)", q)]
        if skills:
            return SKILL_YEARS[max(skills, key=len)]
        if has("total", "overall", "relevant", "work experience", "professional experience"):
            return p["total_experience"]
    return ""
