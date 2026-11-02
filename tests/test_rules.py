from naukri_agent.answers.rules import rule_answer


def test_profile_fields():
    assert rule_answer("What is your email?") == "test@example.com"
    assert rule_answer("First name") == "Test"
    assert rule_answer("Current CTC") == "10 LPA"


def test_skill_years_longest_key_wins():
    assert rule_answer("Years of experience in Python?") == "4"
    assert rule_answer("Experience with Docker") == "2"
    assert rule_answer("How many years of experience in C++?") == "3"


def test_total_experience_fallback():
    assert rule_answer("What is your total experience?") == "5"


def test_unknown_question_returns_empty():
    assert rule_answer("Favourite colour?") == ""
