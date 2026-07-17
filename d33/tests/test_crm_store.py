import json
from pathlib import Path

import pytest

from crm_store import CRMStore


BASE_DIR = Path(__file__).resolve().parents[1]


def test_ticket_context_contains_linked_user() -> None:
    store = CRMStore(BASE_DIR / "data" / "crm.json")

    context = store.get_ticket_context("tck-101")

    assert context is not None
    assert context["ticket"]["error_code"] == "unauthorized"
    assert context["user"]["id"] == "usr_1001"


def test_invalid_user_reference_is_rejected(tmp_path: Path) -> None:
    crm_file = tmp_path / "crm.json"
    crm_file.write_text(
        json.dumps(
            {
                "users": [],
                "tickets": [{"id": "TCK-1", "user_id": "missing"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="неизвестного пользователя"):
        CRMStore(crm_file)
