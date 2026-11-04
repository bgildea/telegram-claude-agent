"""The eval checker itself needs to be right, or a green eval run means nothing."""

import json
from pathlib import Path

from evals.run_evals import check

CASES = json.loads((Path(__file__).parents[1] / "evals" / "cases.json").read_text())


def test_every_case_has_an_id_message_and_at_least_one_check():
    check_keys = {"expect_tools", "forbid_tools", "expect_in_reply", "expect_any_in_reply", "forbid_in_reply"}
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
    for case in CASES:
        assert case["message"]
        assert check_keys & case.keys(), case["id"]


def test_check_passes_and_fails_as_expected():
    case = {"expect_tools": ["calculate"], "forbid_in_reply": ["4242"], "expect_in_reply": ["23,382"]}
    assert check(case, "That comes to 23,382 baht.", ["calculate"]) == []
    failures = check(case, "About 4242.", [])
    assert len(failures) == 3
