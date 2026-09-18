import argparse
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ingest.schema import AccountsResponse
from ingest.simplefin_client import SimpleFinClient

DEFAULT_OVERLAP_DAYS = 5  # FR3: re-pull the last few days daily to catch late-posting transactions


def fetch(
    source: str, *, access_url=None, sample_path=None, start_date=None, end_date=None
) -> AccountsResponse:
    if source == "sample":
        return AccountsResponse.model_validate_json(Path(sample_path).read_text())
    if source == "live":
        client = SimpleFinClient(access_url=access_url)
        return client.fetch_history(start_date, end_date)
    raise ValueError(f"unknown source: {source!r}")


def land(response: AccountsResponse, raw_dir: Path, as_of: date | None = None) -> Path:
    out_dir = Path(raw_dir) / (as_of or date.today()).isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "accounts.json"
    out_path.write_text(response.model_dump_json())
    return out_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch and land SimpleFIN account data")
    parser.add_argument(
        "--source",
        choices=["sample", "live"],
        default=os.environ.get("INGEST_SOURCE", "live"),
    )
    parser.add_argument("--sample-path", type=Path, default=Path("data/sample/accounts.json"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_OVERLAP_DAYS,
        help="days of history to re-pull for the daily incremental overlap window",
    )
    return parser


def main(argv=None) -> Path:
    args = build_arg_parser().parse_args(argv)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=args.days)

    response = fetch(
        args.source,
        access_url=os.environ.get("SIMPLEFIN_ACCESS_URL"),
        sample_path=args.sample_path,
        start_date=start_date,
        end_date=end_date,
    )
    path = land(response, args.raw_dir)
    print(f"Landed {len(response.accounts)} accounts to {path}")
    return path


if __name__ == "__main__":
    main()
