import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from ingest.encryption import decrypt_file
from ingest.fetch_transactions import DEFAULT_OVERLAP_DAYS, build_arg_parser, fetch, land, main
from ingest.schema import AccountsResponse

requires_age = pytest.mark.skipif(shutil.which("age") is None, reason="age CLI not installed")

FIXTURES = Path(__file__).parent / "fixtures"


# --- fetch: sample vs. live source switch --------------------------------

def test_fetch_from_sample_reads_and_validates_local_json():
    result = fetch("sample", sample_path=FIXTURES / "accounts_response_valid.json")

    assert isinstance(result, AccountsResponse)
    assert len(result.accounts) == 2


def test_fetch_from_live_builds_client_and_delegates_to_fetch_history(monkeypatch):
    mock_client = Mock()
    mock_client_cls = Mock(return_value=mock_client)
    monkeypatch.setattr("ingest.fetch_transactions.SimpleFinClient", mock_client_cls)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 31, tzinfo=timezone.utc)

    fetch(
        "live",
        access_url="https://user:pass@bridge.simplefin.org/simplefin",
        start_date=start,
        end_date=end,
    )

    mock_client_cls.assert_called_once_with(access_url="https://user:pass@bridge.simplefin.org/simplefin")
    mock_client.fetch_history.assert_called_once_with(start, end)


def test_fetch_rejects_unknown_source():
    with pytest.raises(ValueError):
        fetch("bogus")


def test_shipped_sample_dataset_matches_schema():
    result = fetch("sample", sample_path=Path("data/sample/accounts.json"))

    assert len(result.accounts) == 3


# --- land: raw JSON landing -----------------------------------------------

def _sample_response():
    return AccountsResponse.model_validate(
        {
            "accounts": [
                {
                    "id": "ACT-1",
                    "name": "Checking",
                    "currency": "USD",
                    "balance": "100.00",
                    "transactions": [],
                }
            ]
        }
    )


def test_land_writes_json_under_date_dir(tmp_path):
    written = land(_sample_response(), raw_dir=tmp_path, as_of=date(2025, 6, 1))

    assert written == tmp_path / "2025-06-01" / "accounts.json"
    assert written.exists()


def test_land_writes_valid_round_trippable_json(tmp_path):
    response = _sample_response()
    written = land(response, raw_dir=tmp_path, as_of=date(2025, 6, 1))

    assert AccountsResponse.model_validate_json(written.read_text()) == response


def test_land_creates_missing_parent_dirs(tmp_path):
    raw_dir = tmp_path / "nested" / "raw"

    written = land(_sample_response(), raw_dir=raw_dir, as_of=date(2025, 6, 1))

    assert written.exists()


def test_land_defaults_as_of_to_today(tmp_path):
    written = land(_sample_response(), raw_dir=tmp_path)

    assert written.parent.name == date.today().isoformat()


@requires_age
def test_land_encrypts_output_when_recipient_given(tmp_path, make_age_keypair):
    public_key, identity = make_age_keypair()
    response = _sample_response()

    written = land(response, raw_dir=tmp_path, as_of=date(2025, 6, 1), recipient=public_key)

    assert written == tmp_path / "2025-06-01" / "accounts.json.age"
    assert not (tmp_path / "2025-06-01" / "accounts.json").exists()
    decrypted = decrypt_file(written, identity=identity, out_path=tmp_path / "decrypted.json")
    assert AccountsResponse.model_validate_json(decrypted.read_text()) == response


# --- CLI wiring -------------------------------------------------------------

def test_build_arg_parser_defaults_days_to_overlap_window():
    args = build_arg_parser().parse_args(["--source", "sample"])

    assert args.days == DEFAULT_OVERLAP_DAYS


def test_main_lands_sample_data_end_to_end(tmp_path, capsys):
    raw_dir = tmp_path / "raw"

    result = main(
        [
            "--source",
            "sample",
            "--sample-path",
            str(FIXTURES / "accounts_response_valid.json"),
            "--raw-dir",
            str(raw_dir),
        ]
    )

    assert result.exists()
    assert "2 accounts" in capsys.readouterr().out


@requires_age
def test_main_encrypts_landed_data_when_encrypt_for_given(tmp_path, capsys, make_age_keypair):
    public_key, _ = make_age_keypair()
    raw_dir = tmp_path / "raw"

    result = main(
        [
            "--source",
            "sample",
            "--sample-path",
            str(FIXTURES / "accounts_response_valid.json"),
            "--raw-dir",
            str(raw_dir),
            "--encrypt-for",
            public_key,
        ]
    )

    assert result.suffix == ".age"
    assert result.exists()
    capsys.readouterr()
