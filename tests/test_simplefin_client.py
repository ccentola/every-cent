import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import responses

from ingest.simplefin_client import (
    SimpleFinClient,
    SimpleFinAPIError,
    claim_access_url,
)

FIXTURES = Path(__file__).parent / "fixtures"
ACCESS_URL = "https://demo-user:demo-pass@bridge.simplefin.org/simplefin"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# --- Claiming an access URL from a setup token ------------------------

@responses.activate
def test_claim_access_url_decodes_token_and_posts_to_claim_url():
    claim_url = "https://bridge.simplefin.org/simplefin/claim/DEMO-abc123"
    setup_token = base64.b64encode(claim_url.encode()).decode()
    responses.add(responses.POST, claim_url, body=ACCESS_URL, status=200)

    result = claim_access_url(setup_token)

    assert result == ACCESS_URL
    assert responses.calls[0].request.url == claim_url


@responses.activate
def test_claim_access_url_raises_on_non_200():
    claim_url = "https://bridge.simplefin.org/simplefin/claim/DEMO-bad"
    setup_token = base64.b64encode(claim_url.encode()).decode()
    responses.add(responses.POST, claim_url, body="invalid or expired token", status=403)

    with pytest.raises(SimpleFinAPIError):
        claim_access_url(setup_token)


# --- Fetching accounts --------------------------------------------------

@responses.activate
def test_get_accounts_requests_and_parses_response():
    responses.add(
        responses.GET,
        "https://bridge.simplefin.org/simplefin/accounts",
        json=load_fixture("accounts_response_valid.json"),
        status=200,
    )

    client = SimpleFinClient(access_url=ACCESS_URL)
    result = client.get_accounts()

    assert len(result.accounts) == 2


@responses.activate
def test_get_accounts_uses_basic_auth_from_access_url():
    responses.add(
        responses.GET,
        "https://bridge.simplefin.org/simplefin/accounts",
        json=load_fixture("accounts_response_valid.json"),
        status=200,
    )

    client = SimpleFinClient(access_url=ACCESS_URL)
    client.get_accounts()

    auth_header = responses.calls[0].request.headers["Authorization"]
    assert auth_header.startswith("Basic ")


@responses.activate
def test_get_accounts_passes_date_range_as_query_params():
    responses.add(
        responses.GET,
        "https://bridge.simplefin.org/simplefin/accounts",
        json=load_fixture("accounts_response_valid.json"),
        status=200,
    )
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 31, tzinfo=timezone.utc)

    client = SimpleFinClient(access_url=ACCESS_URL)
    client.get_accounts(start_date=start, end_date=end)

    request_params = responses.calls[0].request.params
    assert request_params["start-date"] == str(int(start.timestamp()))
    assert request_params["end-date"] == str(int(end.timestamp()))


@responses.activate
def test_get_accounts_raises_on_http_error():
    responses.add(
        responses.GET,
        "https://bridge.simplefin.org/simplefin/accounts",
        body="rate limited",
        status=429,
    )

    client = SimpleFinClient(access_url=ACCESS_URL)
    with pytest.raises(SimpleFinAPIError):
        client.get_accounts()


# --- Paging across the 90-day window + merging ---------------------------

@responses.activate
def test_fetch_history_chunks_requests_when_range_exceeds_90_days():
    responses.add(
        responses.GET,
        "https://bridge.simplefin.org/simplefin/accounts",
        json=load_fixture("accounts_response_valid.json"),
        status=200,
    )
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=200)  # exceeds the 90-day window twice over

    client = SimpleFinClient(access_url=ACCESS_URL)
    client.fetch_history(start_date=start, end_date=end)

    # 200 days across a 90-day window should take at least 3 requests
    assert len(responses.calls) >= 3
    for call in responses.calls:
        params = call.request.params
        window_start = int(params["start-date"])
        window_end = int(params["end-date"])
        assert (window_end - window_start) <= 90 * 86400


@responses.activate
def test_fetch_history_merges_transactions_across_pages_without_duplicates():
    responses.add(
        responses.GET,
        "https://bridge.simplefin.org/simplefin/accounts",
        json=load_fixture("accounts_response_valid.json"),
        status=200,
    )
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=200)

    client = SimpleFinClient(access_url=ACCESS_URL)
    merged = client.fetch_history(start_date=start, end_date=end)

    checking = next(a for a in merged.accounts if a.id == "ACT-0001")
    txn_ids = [t.id for t in checking.transactions]
    assert len(txn_ids) == len(set(txn_ids)), "duplicate transaction IDs after merge"


@responses.activate
def test_fetch_history_keeps_latest_version_of_overlapping_transaction():
    # TXN-0004 appears in both fixtures: pending=True in the first pull,
    # pending=False (settled) in the second. The merge must prefer the
    # later-fetched version, since that reflects the transaction's most
    # current state.
    responses.add(
        responses.GET,
        "https://bridge.simplefin.org/simplefin/accounts",
        json=load_fixture("accounts_response_valid.json"),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://bridge.simplefin.org/simplefin/accounts",
        json=load_fixture("accounts_response_overlap.json"),
        status=200,
    )
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=100)

    client = SimpleFinClient(access_url=ACCESS_URL)
    merged = client.fetch_history(start_date=start, end_date=end)

    checking = next(a for a in merged.accounts if a.id == "ACT-0001")
    txn_0004 = next(t for t in checking.transactions if t.id == "TXN-0004")
    assert txn_0004.pending is False


@responses.activate
def test_fetch_history_merges_accounts_present_in_only_one_page():
    # ACT-0002 ("Savings") only appears in the valid fixture, not the
    # overlap fixture. The merge must not drop it just because a later
    # page didn't mention it.
    responses.add(
        responses.GET,
        "https://bridge.simplefin.org/simplefin/accounts",
        json=load_fixture("accounts_response_valid.json"),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://bridge.simplefin.org/simplefin/accounts",
        json=load_fixture("accounts_response_overlap.json"),
        status=200,
    )
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=100)

    client = SimpleFinClient(access_url=ACCESS_URL)
    merged = client.fetch_history(start_date=start, end_date=end)

    account_ids = {a.id for a in merged.accounts}
    assert "ACT-0002" in account_ids


@responses.activate
def test_fetch_history_within_single_90_day_window_makes_one_request():
    # Sanity check: a range that fits within one window shouldn't be
    # split unnecessarily — no point burning extra requests against
    # SimpleFIN's daily rate limit.
    responses.add(
        responses.GET,
        "https://bridge.simplefin.org/simplefin/accounts",
        json=load_fixture("accounts_response_valid.json"),
        status=200,
    )
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=30)

    client = SimpleFinClient(access_url=ACCESS_URL)
    client.fetch_history(start_date=start, end_date=end)

    assert len(responses.calls) == 1