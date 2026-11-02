from naukri_agent.answers import resolver


def test_saved_answer_wins_over_rule():
    ans, src = resolver.find_answer("What is your email?", {"what is your email": "custom@x.com"})
    assert (ans, src) == ("custom@x.com", "saved")


def test_rule_used_when_not_saved():
    assert resolver.find_answer("What is your email?", {}) == ("test@example.com", "rule")


def test_llm_last_resort(monkeypatch):
    monkeypatch.setattr(resolver, "llm_answer", lambda q, t, o: "from llm")
    assert resolver.find_answer("Favourite colour?", {}) == ("from llm", "llm")
    monkeypatch.setattr(resolver, "llm_answer", lambda q, t, o: "")
    assert resolver.find_answer("Favourite colour?", {}) == ("", "")
