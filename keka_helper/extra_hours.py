import os
from datetime import datetime, timedelta

import requests

from keka_helper.common_helpers import (
    build_extra_hours_notification,
    get_env_int,
    get_logger,
    notify_user,
    parse_hhmm_text,
)
from keka_helper.util import fetch_keka_response

logger = get_logger(__name__)


def _parse_day_types_env(name: str) -> frozenset[int]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return frozenset({0})
    parsed = set()
    for part in raw.split(","):
        try:
            parsed.add(int(part.strip()))
        except ValueError:
            pass
    return frozenset(parsed) if parsed else frozenset({0})


class KekaExtraHoursCalculator:
    request_timeout_seconds = get_env_int("KEKA_EXTRA_REQUEST_TIMEOUT_SECONDS", 10)
    max_retries = get_env_int("KEKA_EXTRA_RETRY_COUNT", 3)

    def __init__(self) -> None:
        self.working_days = 0
        self.total_office_time = timedelta(hours=8, minutes=30)
        self.daily_avg = timedelta(0)

    @staticmethod
    def check_if_valid_response(response: requests.Response) -> bool:
        try:
            payload = response.json()
        except ValueError:
            return False
        return (
            response.status_code == 200 and
            isinstance(payload.get("data"), dict) and
            isinstance(payload["data"].get("myStats"), dict) and
            "workingDays" in payload["data"]["myStats"] and
            "averageHoursPerDayInHHMM" in payload["data"]["myStats"]
        )

    def fetch_response(self) -> requests.Response:
        now = datetime.now()
        from_date = datetime(now.year, now.month, 1).strftime("%Y-%m-%d")
        to_date = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")
        url = (
            "https://kevit.keka.com/k/attendance/api/mytime/attendance/"
            f"lastweekstats?fromDate={from_date}&toDate={to_date}"
        )
        return fetch_keka_response(
            url=url,
            is_valid_response=self.check_if_valid_response,
            request_timeout_seconds=self.request_timeout_seconds,
            max_retries=self.max_retries,
            context_name="Extra hours API",
        )

    def calculate_extra_time_and_get_message(
        self, office_time: timedelta
    ) -> tuple[str, str]:
        total_effective = self.daily_avg * self.working_days
        total_required = office_time * self.working_days
        return build_extra_hours_notification(
            self.working_days,
            total_effective,
            total_required,
            office_time
        )

    @staticmethod
    def _extract_summary_metrics(
        response: requests.Response
    ) -> tuple[int, timedelta]:
        mystats = response.json()["data"]["myStats"]
        working_days = int(mystats.get("workingDays", 0))
        daily_avg = parse_hhmm_text(mystats.get("averageHoursPerDayInHHMM", "0h 0m"))
        return working_days, daily_avg

    def fetch_your_extra_hours(self) -> None:
        try:
            response = self.fetch_response()
            self.working_days, self.daily_avg = self._extract_summary_metrics(response)
            notification_title, notification_message = (
                self.calculate_extra_time_and_get_message(self.total_office_time)
            )
            notify_user(notification_title, notification_message)
        except Exception as error:
            logger.exception("Failed to calculate extra hours")
            notify_user("ERROR", f"Failed to calculate your extra hours: {error}")


extra_hours_calculator = KekaExtraHoursCalculator()


class KekaExtraHoursCalculatorV2:
    daily_office_time = timedelta(hours=8, minutes=30)
    half_day_office_time = timedelta(hours=4, minutes=15)
    request_timeout_seconds = get_env_int("KEKA_EXTRA_REQUEST_TIMEOUT_SECONDS", 10)
    max_retries = get_env_int("KEKA_EXTRA_RETRY_COUNT", 3)
    counted_day_types = _parse_day_types_env("KEKA_EXTRA_V2_DAY_TYPES")

    @staticmethod
    def check_if_valid_response(response: requests.Response) -> bool:
        try:
            payload = response.json()
        except ValueError:
            return False
        data = payload.get("data")
        return (
            response.status_code == 200 and
            isinstance(data, list) and
            len(data) > 0
        )

    def fetch_response(self) -> requests.Response:
        now = datetime.now()
        from_date = datetime(now.year, now.month, 1).strftime("%Y-%m-%d")
        to_date = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")
        url = (
            "https://kevit.keka.com/k/attendance/api/mytime/attendance/summary"
            f"?fromDate={from_date}&toDate={to_date}"
        )
        return fetch_keka_response(
            url=url,
            is_valid_response=self.check_if_valid_response,
            request_timeout_seconds=self.request_timeout_seconds,
            max_retries=self.max_retries,
            context_name="Extra hours V2 API",
        )

    def _calculate_monthly_stats(self, entries: list) -> tuple[int, timedelta, timedelta]:
        working_days = 0
        total_effective = timedelta(0)
        total_required = timedelta(0)
        for entry in entries:
            if entry.get("dayType") not in self.counted_day_types:
                continue
            effective = parse_hhmm_text(entry.get("effectiveHoursInHHMM", "0h 0m"))
            if effective == timedelta(0):
                continue
            is_half_day = (
                entry.get("isFirstHalfLeave", False) or
                entry.get("isSecondHalfLeave", False)
            )
            working_days += 1
            total_effective += effective
            total_required += self.half_day_office_time if is_half_day else self.daily_office_time
        return working_days, total_effective, total_required

    def _build_notification(
        self, working_days: int, total_effective: timedelta, total_required: timedelta
    ) -> tuple[str, str]:
        return build_extra_hours_notification(
            working_days,
            total_effective,
            total_required,
            self.daily_office_time
        )

    def fetch_your_extra_hours(self) -> None:
        try:
            response = self.fetch_response()
            entries = response.json()["data"]
            working_days, total_effective, total_required = self._calculate_monthly_stats(entries)
            if working_days == 0:
                types_str = ",".join(str(t) for t in sorted(self.counted_day_types))
                notify_user(
                    "Extra Hours V2",
                    f"No dayType={types_str} entries found for this month yet."
                )
                return
            title, message = self._build_notification(working_days, total_effective, total_required)
            notify_user(title, message)
        except Exception as error:
            logger.exception("Failed to calculate extra hours (v2)")
            notify_user("ERROR", f"Failed to calculate your extra hours (v2): {error}")


extra_hours_calculator_v2 = KekaExtraHoursCalculatorV2()
