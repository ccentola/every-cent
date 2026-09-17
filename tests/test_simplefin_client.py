import base64
import json
from datetime import datetime, timezone
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