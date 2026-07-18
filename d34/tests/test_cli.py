import sys

import assistant


def test_goal_is_optional_for_interactive_mode(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["assistant.py", "example_project"])
    args = assistant.parse_args()
    assert args.goal == []


def test_one_shot_goal_is_still_supported(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["assistant.py", "example_project", "Найди", "PaymentAPI"],
    )
    args = assistant.parse_args()
    assert args.goal == ["Найди", "PaymentAPI"]
