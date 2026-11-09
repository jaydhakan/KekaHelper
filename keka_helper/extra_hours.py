from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import requests

from keka_helper.common_helpers import (
    build_extra_hours_notification,
    get_env_int,
    get_logger,
    get_required_office_time,
    has_missing_punch,
    is_full_day_leave,
    notify_user,
    parse_entry_date,
    parse_hhmm_text,
    remaining_working_days_in_month,
)
from keka_helper.config import get_env
from keka_helper.util import fetch_keka_response

logger = get_logger(__name__)


def _parse_day_types_env(name: str) -> frozenset[int]:
    raw = get_env(name, "") or ""
    if not raw.strip():
        return frozenset({0})
    parsed = set()
    for part in raw.split(","):
        try:
            parsed.add(int(part.strip()))
        except ValueError:
            pass
    return frozenset(parsed) if parsed else frozenset({0})


@dataclass
class MonthlyStats:
    working_days: int = 0
    total_effective: timedelta = timedelta(0)
    total_required: timedelta = timedelta(0)
    missing_punch_days: list[date] = field(default_factory=list)


class KekaExtraHoursCalculator:
    daily_office_time = timedelta(hours=8, minutes=30)
    request_timeout_seconds = get_env_int("KEKA_EXTRA_REQUEST_TIMEOUT_SECONDS", 10)
    max_retries = get_env_int("KEKA_EXTRA_RETRY_COUNT", 3)
    counted_day_types = _parse_day_types_env("KEKA_EXTRA_V2_DAY_TYPES")
    summary_url = "https://kevit.keka.com/k/attendance/api/mytime/attendance/summary"
    holidays_url = "https://kevit.keka.com/k/dashboard/api/dashboard/holidays"

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

    @staticmethod
    def _is_valid_holidays_response(response: requests.Response) -> bool:
        try:
            return response.status_code == 200 and isinstance(response.json().get("data"), list)
        except ValueError:
            return False

    def fetch_response(self) -> requests.Response:
        # Keka ignores date query params and always returns the last 30 days
        # (up to today); the current month is filtered in _calculate_monthly_stats.
        return fetch_keka_response(
            url=self.summary_url,
            is_valid_response=self.check_if_valid_response,
            request_timeout_seconds=self.request_timeout_seconds,
            max_retries=self.max_retries,
            context_name="Extra hours API",
        )

    def fetch_holidays(self) -> set[date]:
        """Fixed (non-floater) company holidays. Falls back to none on failure."""
        try:
            response = fetch_keka_response(
                url=self.holidays_url,
                is_valid_response=self._is_valid_holidays_response,
                request_timeout_seconds=self.request_timeout_seconds,
                max_retries=self.max_retries,
                context_name="Holidays API",
            )
            return {
                date.fromisoformat(holiday["date"][:10])
                for holiday in response.json()["data"]
                if holiday.get("date") and not holiday.get("isFloater")
            }
        except Exception:
            logger.warning("Could not fetch holidays; remaining days ignore holidays", exc_info=True)
            return set()

    def _calculate_monthly_stats(self, entries: list, today: date | None = None) -> MonthlyStats:
        today = today or datetime.now().date()
        month_start = today.replace(day=1)
        stats = MonthlyStats()
        for entry in entries:
            attendance_date = parse_entry_date(entry)
            if attendance_date is None or not month_start <= attendance_date < today:
                continue
            if entry.get("dayType") not in self.counted_day_types:
                continue
            if is_full_day_leave(entry):
                continue
            if has_missing_punch(entry):
                stats.missing_punch_days.append(attendance_date)
            effective = parse_hhmm_text(entry.get("effectiveHoursInHHMM", "0h 0m"))
            if effective == timedelta(0):
                continue
            stats.working_days += 1
            stats.total_effective += effective
            stats.total_required += get_required_office_time(entry)
        return stats

    def fetch_your_extra_hours(self) -> None:
        try:
            entries = self.fetch_response().json()["data"]
            stats = self._calculate_monthly_stats(entries)
            if stats.working_days == 0:
                types_str = ",".join(str(t) for t in sorted(self.counted_day_types))
                notify_user(
                    "Extra Hours",
                    f"No worked dayType={types_str} entries found for this month yet."
                )
                return
            remaining_days = remaining_working_days_in_month(
                datetime.now().date(), self.fetch_holidays()
            )
            title, message = build_extra_hours_notification(
                stats.working_days,
                stats.total_effective,
                stats.total_required,
                self.daily_office_time,
                remaining_days,
                stats.missing_punch_days,
            )
            notify_user(title, message)
        except Exception as error:
            logger.exception("Failed to calculate extra hours")
            notify_user("ERROR", f"Failed to calculate your extra hours: {error}")


extra_hours_calculator = KekaExtraHoursCalculator()
