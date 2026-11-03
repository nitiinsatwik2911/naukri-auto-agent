"""Hermetic test env: set every required .env value before the package is imported
(python-dotenv never overrides variables that are already set)."""
import os
import tempfile

os.environ.update({
    "DATA_DIR": tempfile.mkdtemp(prefix="naukri_test_"),
    "RESUME_FILE": "config/resume.example.txt",
    "SAVED_ANSWER_CUTOFF": "0.95",
    "OPTION_MATCH_CUTOFF": "0.7",
    "LLM_TIMEOUT": "5",
    "LLM_PROVIDER": "claude",
    "LLM_CLAUDE_COMMAND": "claude -p --model haiku",
    "LLM_COPILOT_COMMAND": "copilot -s -p {prompt}",
    "LLM_DEFAULT_NOTICE_PERIOD": "30 days",
    "FULL_NAME": "Test User",
    "FIRSTNAME": "Test",
    "LASTNAME": "User",
    "PROFILE_EMAIL": "test@example.com",
    "PROFILE_PHONE": "9999999999",
    "PROFILE_CITY": "Pune",
    "TOTAL_EXPERIENCE": "5",
    "CURRENT_CTC": "10 LPA",
    "SKILL_YEARS": "python:4,docker:2,c++:3,ci/cd:2",
})
