import argparse
from typing import Callable

from keka_helper.daily_hours import daily_hours_calculator
from keka_helper.extra_hours import extra_hours_calculator
from keka_helper.util import auth_token_helpers


def run_daily() -> None:
    daily_hours_calculator.calculate_daily_hours()


def run_extra() -> None:
    extra_hours_calculator.fetch_your_extra_hours()


def run_refresh_token() -> None:
    auth_token_helpers.read_auth_token_from_file(fetch_new_api_token=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Keka helper CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("daily", help="Show daily checkout windows")
    subparsers.add_parser("extra", help="Show monthly extra-hours summary")
    subparsers.add_parser("refresh-token", help="Refresh Keka auth token")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    command_handlers: dict[str, Callable[[], None]] = {
        "daily": run_daily,
        "extra": run_extra,
        "refresh-token": run_refresh_token,
    }
    command_handlers[args.command]()


if __name__ == "__main__":
    main()
