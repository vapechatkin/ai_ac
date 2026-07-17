from assistant import parse_help_question


def test_help_parser_accepts_quotes_and_plain_text() -> None:
    assert parse_help_question('/help "Как устроен сервер?"') == "Как устроен сервер?"
    assert parse_help_question("/help Как устроен сервер?") == "Как устроен сервер?"


def test_help_parser_rejects_other_commands() -> None:
    assert parse_help_question("/branch") is None
    assert parse_help_question("/help") == ""
