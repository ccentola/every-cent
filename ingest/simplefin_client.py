import base64
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