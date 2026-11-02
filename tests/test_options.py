from naukri_agent.answers.options import match_option


def test_exact_and_yes_no():
    assert match_option("Yes", ["Yes", "No"]) == 0
    assert match_option("no", ["Yes", "No"]) == 1


def test_numeric_ranges():
    opts = ["0-2 years", "3-5 years", "6+ years"]
    assert match_option("4", opts) == 1
    assert match_option("8", opts) == 2


def test_no_match():
    assert match_option("banana", ["Yes", "No"]) == -1
