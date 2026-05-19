import os
from datetime import datetime, timedelta

import requests

from keka_helper.common_helpers import (
    format_timedelta,
    get_env_int,
    get_logger,
    notify_user,
    parse_hhmm_text,
    remaining_weekdays_in_month,
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
        now = datetime.now()
        self.from_date = datetime(now.year, now.month, 1).strftime("%Y-%m-%d")
        self.to_date = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")

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
        url = (
            "https://kevit.keka.com/k/attendance/api/mytime/attendance/"
            f"lastweekstats?fromDate={self.from_date}&toDate={self.to_date}"
        )
        return fetch_keka_response(
            url=url,
            is_valid_response=self.check_if_valid_response,
            request_timeout_seconds=self.request_timeout_seconds,
            max_retries=self.max_retries,
            context_name="Extra hours API",
        )

    @staticmethod
    def _format_minutes_as_timedelta(total_minutes: int) -> str:
        if total_minutes < 0:
            total_minutes = 0
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours}h {minutes}m"

    def calculate_extra_time_and_get_message(
        self, office_time: timedelta
    ) -> tuple[str, str]:
        delta_per_day = self.daily_avg - office_time
        cumulative_delta = delta_per_day * self.working_days
        today = datetime.now()
        remaining_days = remaining_weekdays_in_month(today)

        if remaining_days > 0:
            office_minutes = int(office_time.total_seconds() // 60)
            cumulative_delta_minutes = int(cumulative_delta.total_seconds() // 60)
            required_per_day_minutes = office_minutes - (
                cumulative_delta_minutes // remaining_days
            )
            required_per_day_minutes = max(required_per_day_minutes, 7 * 60)
            per_day_text = self._format_minutes_as_timedelta(required_per_day_minutes)
            if cumulative_delta >= timedelta(0):
                daily_message = f"You can leave every day by doing {per_day_text}."
            else:
                daily_message = (
                    f"To reach average, do {per_day_text} "
                    "every remaining working day."
                )
        else:
            daily_message = "No remaining working days in this month."

        if cumulative_delta >= timedelta(0):
            notification_title = (
                f"{format_timedelta(cumulative_delta)} extra time available"
            )
        else:
            time_to_reach_avg = abs(cumulative_delta)
            notification_title = (
                f"{format_timedelta(time_to_reach_avg)} remaining to reach average"
            )
        notification_message = (
            f"{daily_message}\n"
            f"Current average: {format_timedelta(self.daily_avg)}"
        )
        return notification_title, notification_message

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
    request_timeout_seconds = get_env_int("KEKA_EXTRA_REQUEST_TIMEOUT_SECONDS", 10)
    max_retries = get_env_int("KEKA_EXTRA_RETRY_COUNT", 3)
    counted_day_types = _parse_day_types_env("KEKA_EXTRA_V2_DAY_TYPES")

    def __init__(self) -> None:
        now = datetime.now()
        self.from_date = datetime(now.year, now.month, 1).strftime("%Y-%m-%d")
        self.to_date = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")

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
        url = (
            "https://kevit.keka.com/k/attendance/api/mytime/attendance/summary"
            f"?fromDate={self.from_date}&toDate={self.to_date}"
        )
        return fetch_keka_response(
            url=url,
            is_valid_response=self.check_if_valid_response,
            request_timeout_seconds=self.request_timeout_seconds,
            max_retries=self.max_retries,
            context_name="Extra hours V2 API",
        )

    def _calculate_monthly_stats(self, entries: list) -> tuple[int, timedelta]:
        working_days = 0
        total_effective = timedelta(0)
        for entry in entries:
            if entry.get("dayType") not in self.counted_day_types:
                continue
            effective = parse_hhmm_text(entry.get("effectiveHoursInHHMM", "0h 0m"))
            if effective == timedelta(0):
                continue
            working_days += 1
            total_effective += effective
        return working_days, total_effective

    def _build_notification(
        self, working_days: int, total_effective: timedelta
    ) -> tuple[str, str]:
        required_total = self.daily_office_time * working_days
        delta = total_effective - required_total
        today = datetime.now()
        remaining_days = remaining_weekdays_in_month(today)
        avg = total_effective / working_days if working_days > 0 else timedelta(0)

        if remaining_days > 0:
            office_minutes = int(self.daily_office_time.total_seconds() // 60)
            delta_minutes = int(delta.total_seconds() // 60)
            required_per_day_minutes = office_minutes - round(delta_minutes / remaining_days)
            required_per_day_minutes = max(required_per_day_minutes, 7 * 60)
            h, m = divmod(required_per_day_minutes, 60)
            per_day_text = f"{h}h {m}m"
            if delta >= timedelta(0):
                daily_message = f"You can leave every day by doing {per_day_text}."
            else:
                daily_message = f"To reach average, do {per_day_text} every remaining working day."
        else:
            daily_message = "No remaining working days in this month."

        if delta >= timedelta(0):
            title = f"{format_timedelta(delta)} extra time this month"
        else:
            title = f"{format_timedelta(delta)} deficit this month"

        message = (
            f"{daily_message}\n"
            f"Days counted: {working_days} | Avg: {format_timedelta(avg)}"
        )
        return title, message

    def fetch_your_extra_hours(self) -> None:
        try:
            response = self.fetch_response()
            entries = response.json()["data"]
            working_days, total_effective = self._calculate_monthly_stats(entries)
            if working_days == 0:
                types_str = ",".join(str(t) for t in sorted(self.counted_day_types))
                notify_user("Extra Hours V2", f"No dayType={types_str} entries found for this month yet.")
                return
            title, message = self._build_notification(working_days, total_effective)
            notify_user(title, message)
        except Exception as error:
            logger.exception("Failed to calculate extra hours (v2)")
            notify_user("ERROR", f"Failed to calculate your extra hours (v2): {error}")


extra_hours_calculator_v2 = KekaExtraHoursCalculatorV2()
