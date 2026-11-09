from datetime import date, datetime, timedelta

import requests

from keka_helper.common_helpers import (
    convert_str_to_datetime,
    format_timedelta,
    get_env_int,
    get_logger,
    get_required_office_time,
    notify_user,
    parse_entry_date,
)
from keka_helper.util import fetch_keka_response

logger = get_logger(__name__)

PUNCH_IN = 0
PUNCH_OUT = 1


class KekaDailyHoursCalculator:
    datetime_format_12_hour = "%I:%M:%S %p"
    total_office_time = timedelta(hours=8, minutes=30)
    partial_office_time = timedelta(hours=6, minutes=55)
    half_day_total_office_time = timedelta(hours=4, minutes=15)
    half_day_partial_office_time = timedelta(hours=2, minutes=45)
    request_timeout_seconds = get_env_int("KEKA_DAILY_REQUEST_TIMEOUT_SECONDS", 10)
    max_retries = get_env_int("KEKA_DAILY_RETRY_COUNT", 3)

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
        url = "https://kevit.keka.com/k/attendance/api/mytime/attendance/summary"
        return fetch_keka_response(
            url=url,
            is_valid_response=self.check_if_valid_response,
            request_timeout_seconds=self.request_timeout_seconds,
            max_retries=self.max_retries,
            context_name="Daily hours API",
        )

    @staticmethod
    def _get_today_entry(entries: list, today: date) -> dict:
        for entry in reversed(entries):
            if parse_entry_date(entry) == today:
                return entry
        raise RuntimeError(f"No attendance entry for today ({today:%d %b %Y}) in Keka response")

    def _get_office_time_targets(self, entry: dict) -> tuple[timedelta, timedelta]:
        """Full/min targets from Keka's shift length; min time scales with the shift."""
        total = get_required_office_time(entry)
        if total <= timedelta(0):
            raise RuntimeError("Today is marked as a full-day leave")
        if total <= self.half_day_total_office_time:
            partial = self.half_day_partial_office_time * (total / self.half_day_total_office_time)
        else:
            partial = self.partial_office_time * (total / self.total_office_time)
        return total, timedelta(minutes=round(partial.total_seconds() / 60))

    @staticmethod
    def _get_punches(entry: dict) -> list[tuple[datetime, int]]:
        raw_entries = entry.get("timeEntries") or entry.get("originalTimeEntries") or []
        punches = [
            (
                convert_str_to_datetime(
                    raw.get("adjustedTimestamp") or raw.get("timestamp") or raw["actualTimestamp"]
                ),
                raw.get("punchStatus"),
            )
            for raw in raw_entries
            if not raw.get("isDeleted")
        ]
        if not punches:
            raise RuntimeError("No time entries found for today")
        return sorted(punches, key=lambda punch: punch[0])

    @staticmethod
    def _calculate_effective_time_spent(
        punches: list[tuple[datetime, int]], now: datetime
    ) -> tuple[timedelta, bool]:
        """Sum of in->out pairs, plus the open session if currently punched in."""
        worked = timedelta(0)
        current_in: datetime | None = None
        for timestamp, status in punches:
            if status == PUNCH_IN and current_in is None:
                current_in = timestamp
            elif status == PUNCH_OUT and current_in is not None:
                worked += timestamp - current_in
                current_in = None
        is_punched_in = current_in is not None
        if is_punched_in:
            worked += max(now - current_in, timedelta(0))
        return worked, is_punched_in

    def _format_leave_time(self, now: datetime, remaining: timedelta) -> str:
        if remaining <= timedelta(0):
            return "Completed"
        return (now + remaining).strftime(self.datetime_format_12_hour)

    @staticmethod
    def _build_notification(
        total_time_leave: str,
        partial_time_leave: str,
        total_remaining: timedelta,
        partial_remaining: timedelta,
        is_punched_in: bool = True,
    ) -> tuple[str, str]:
        if partial_remaining > timedelta(0):
            title = f"{format_timedelta(partial_remaining)} remaining for min time"
        elif total_remaining > timedelta(0):
            title = f"{format_timedelta(total_remaining)} remaining for full time"
        else:
            title = f"Full time completed - {format_timedelta(abs(total_remaining))} extra"

        message = (
            f"Min time: {partial_time_leave}\n"
            f"Full time: {total_time_leave}"
        )
        if not is_punched_in:
            message += "\nYou are punched out - times assume you punch in now"
        return title, message

    def calculate_daily_hours(self) -> None:
        try:
            now = datetime.now()
            entries = self.fetch_response().json()["data"]
            entry = self._get_today_entry(entries, now.date())
            total_office_time, partial_office_time = self._get_office_time_targets(entry)
            time_spent, is_punched_in = self._calculate_effective_time_spent(
                self._get_punches(entry), now
            )

            total_remaining = total_office_time - time_spent
            partial_remaining = partial_office_time - time_spent
            total_time_leave = self._format_leave_time(now, total_remaining)
            partial_time_leave = self._format_leave_time(now, partial_remaining)
            notification_title, notification_message = self._build_notification(
                total_time_leave,
                partial_time_leave,
                total_remaining,
                partial_remaining,
                is_punched_in,
            )

            logger.info(
                f"Computed leave windows spent={format_timedelta(time_spent)} "
                f"total={total_time_leave} partial={partial_time_leave}"
            )
            notify_user(notification_title, notification_message)
        except Exception as err:
            logger.exception("Failed to calculate daily hours")
            notify_user("Error", f"Failed to calculate daily hours: {str(err)}")


daily_hours_calculator = KekaDailyHoursCalculator()
