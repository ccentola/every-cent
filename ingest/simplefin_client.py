import base64
from datetime import timedelta
from urllib.parse import urlparse, urlunparse

import requests

from ingest.schema import AccountsResponse


class SimpleFinAPIError(Exception):
    """Raised when the SimpleFIN API returns an error response."""
    pass


def claim_access_url(setup_token: str) -> str:
    claim_url = base64.b64decode(setup_token).decode()
    response = requests.post(claim_url)
    if response.status_code != 200:
        raise SimpleFinAPIError(
            f"Failed to claim access URL: {response.status_code} {response.text}"
        )
    return response.text


class SimpleFinClient:
    def __init__(self, access_url: str):
        self.access_url = access_url
        parsed = urlparse(access_url)
        self._auth = (parsed.username, parsed.password)
        # Rebuild the URL without the embedded user:pass@ — those get
        # sent separately via the `auth` param instead.
        netloc = parsed.hostname
        if parsed.port:
            netloc += f":{parsed.port}"
        self._base_url = urlunparse(parsed._replace(netloc=netloc))

    def get_accounts(self, start_date=None, end_date=None):
        params = {}
        if start_date is not None:
            params["start-date"] = str(int(start_date.timestamp()))
        if end_date is not None:
            params["end-date"] = str(int(end_date.timestamp()))

        response = requests.get(
            f"{self._base_url}/accounts", auth=self._auth, params=params
        )
        if response.status_code != 200:
            raise SimpleFinAPIError(
                f"SimpleFIN API error: {response.status_code} {response.text}"
            )
        return AccountsResponse.model_validate(response.json())

    def fetch_history(self, start_date, end_date):
        """
        Fetch accounts/transactions across an arbitrary date range,
        chunking into <=90-day windows (SimpleFIN's query limit) and
        merging the results. When a transaction appears in more than
        one window (an overlapping daily re-pull), the version from
        the later-fetched window wins, since it reflects the more
        current state (e.g. pending -> settled).
        """
        window_size = timedelta(days=90)
        accounts_by_id: dict[str, dict] = {}
        all_errors: list[str] = []

        window_start = start_date
        while window_start < end_date:
            window_end = min(window_start + window_size, end_date)
            page = self.get_accounts(start_date=window_start, end_date=window_end)
            all_errors.extend(page.errors)

            for account in page.accounts:
                if account.id not in accounts_by_id:
                    accounts_by_id[account.id] = {
                        "account": account,
                        "transactions": {t.id: t for t in account.transactions},
                    }
                else:
                    entry = accounts_by_id[account.id]
                    entry["account"] = account  # keep the latest account-level fields
                    entry["transactions"].update({t.id: t for t in account.transactions})

            window_start = window_end

        merged_accounts = [
            entry["account"].model_copy(
                update={"transactions": list(entry["transactions"].values())}
            )
            for entry in accounts_by_id.values()
        ]
        return AccountsResponse(errors=all_errors, accounts=merged_accounts)