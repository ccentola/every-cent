import json
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from ingest.schema import AccountsResponse

FIXTURES = Path(__file__).parent / "fixtures"

def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())

def test_parses_valid_response_into_expected_shape():
    raw = load_fixture("accounts_response_valid.json")

    parsed = AccountsResponse.model_validate(raw)

    assert len(parsed.accounts) == 2
    checking = next(a for a in parsed.accounts if a.id == "ACT-0001")
    assert checking.name == "Everyday Checking"
    assert len(checking.transactions) == 4


def test_amount_is_parsed_as_decimal_not_float():
    # Money must never be a float — SimpleFIN sends amounts as strings
    # specifically to avoid floating point rounding issues.
    raw = load_fixture("accounts_response_valid.json")

    parsed = AccountsResponse.model_validate(raw)

    txn = parsed.accounts[0].transactions[0]
    assert isinstance(txn.amount, Decimal)
    assert txn.amount == Decimal("-12.50")

def test_posted_epoch_is_parsed_as_utc_datetime():
    raw = load_fixture("accounts_response_valid.json")

    parsed = AccountsResponse.model_validate(raw)

    txn = parsed.accounts[0].transactions[0]
    assert isinstance(txn.posted, datetime)
    assert txn.posted.tzinfo == timezone.utc


def test_missing_required_transaction_field_raises_validation_error():
    raw = load_fixture("accounts_response_missing_field.json")

    with pytest.raises(ValidationError):
        AccountsResponse.model_validate(raw)