from datetime import datetime, timedelta

import requests

from common_helpers import get_env_int, get_logger, notify_user
from util import fetch_keka_response

logger = get_logger(__name__)


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
            len(data) > 0 and
            isinstance(data[-1], dict) and
            "breakDurationInHHMM" in data[-1]
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

    def convert_str_to_datetime(self, time_str: str) -> datetime:
        normalized = time_str.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo:
                return parsed.astimezone().replace(tzinfo=None)
            return parsed
        except ValueError:
            pass

        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(time_str[:19], fmt)
            except ValueError:
                continue
        raise ValueError(f"Unsupported timestamp format: {time_str}")

    @staticmethod
    def parse_break_duration(value: str) -> timedelta:
        if not value:
            return timedelta(0)
        parts = value.split(":")
        if len(parts) != 2:
            return timedelta(0)
        try:
            return timedelta(hours=int(parts[0]), minutes=int(parts[1]))
        except ValueError:
            logger.warning(f"Invalid break duration format: {value}")
            return timedelta(0)

    @staticmethod
    def is_half_day(last_entry: dict):
        return (
            last_entry.get('isFirstHalfLeave', False) or
            last_entry.get('isSecondHalfLeave', False)
        )

    def _get_office_time_targets(
        self, last_entry: dict
    ) -> tuple[timedelta, timedelta]:
        if self.is_half_day(last_entry):
            return self.half_day_total_office_time, self.half_day_partial_office_time
        return self.total_office_time, self.partial_office_time

    def _get_first_log_time(self, last_entry: dict) -> datetime:
        entries = last_entry.get("originalTimeEntries", [])
        if not entries:
            raise RuntimeError("No time entries found for today")
        return self.convert_str_to_datetime(entries[0]["actualTimestamp"])

    @staticmethod
    def _calculate_effective_time_spent(
        now: datetime, first_log: datetime, break_time: timedelta
    ) -> timedelta:
        time_spent = now - first_log - break_time
        if time_spent < timedelta(0):
            return timedelta(0)
        return time_spent

    def _build_notification(
        self, now: datetime, total_time_leave: str, partial_time_leave: str
    ) -> tuple[str, str]:
        current_time = now.strftime(self.datetime_format_12_hour)
        title = f"Office Time Reminder. Time ~ {current_time}"
        message = f"You can close at {total_time_leave} or {partial_time_leave}."
        return title, message

    def _format_leave_time(self, now: datetime, remaining: timedelta) -> str:
        if remaining <= timedelta(0):
            return "now"
        return (now + remaining).strftime(self.datetime_format_12_hour)

    def calculate_daily_hours(self) -> None:
        try:
            response = self.fetch_response()
            last_entry = response.json()["data"][-1]
            total_office_time, partial_office_time = self._get_office_time_targets(
                last_entry
            )
            break_time = self.parse_break_duration(
                last_entry.get("breakDurationInHHMM", "0:0")
            )
            first_log = self._get_first_log_time(last_entry)
            now = datetime.now()
            time_spent = self._calculate_effective_time_spent(
                now, first_log, break_time
            )

            total_remaining = total_office_time - time_spent
            partial_remaining = partial_office_time - time_spent
            total_time_leave = self._format_leave_time(now, total_remaining)
            partial_time_leave = self._format_leave_time(now, partial_remaining)
            notification_title, notification_message = self._build_notification(
                now, total_time_leave, partial_time_leave
            )

            logger.info(
                f"Computed leave windows total={total_time_leave} "
                f"partial={partial_time_leave}"
            )
            notify_user(notification_title, notification_message)
        except Exception as err:
            logger.exception("Failed to calculate daily hours")
            notify_user("Error", f"Failed to calculate daily hours: {str(err)}")


daily_hours_calculator = KekaDailyHoursCalculator()

if __name__ == '__main__':
    daily_hours_calculator.calculate_daily_hours()
