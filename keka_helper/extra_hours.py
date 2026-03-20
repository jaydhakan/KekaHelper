from datetime import datetime, timedelta
from calendar import monthrange

import requests

from keka_helper.common_helpers import get_env_int, get_logger, notify_user
from keka_helper.util import fetch_keka_response

logger = get_logger(__name__)


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
    def parse_hhmm_text(value: str) -> timedelta:
        if not value:
            return timedelta(0)
        if ":" in value:
            try:
                hours, minutes = value.split(":", maxsplit=1)
                return timedelta(hours=int(hours), minutes=int(minutes))
            except ValueError:
                logger.warning(f"Invalid HH:MM value for average hours: {value}")
                return timedelta(0)

        hours = 0
        minutes = 0
        for part in value.split():
            if part.endswith("h"):
                hours = int(part[:-1])
            elif part.endswith("m"):
                minutes = int(part[:-1])
        return timedelta(hours=hours, minutes=minutes)

    @staticmethod
    def format_timedelta(value: timedelta) -> str:
        total_minutes = int(value.total_seconds() // 60)
        hours, minutes = divmod(abs(total_minutes), 60)
        return f"{hours}h {minutes}m"

    @staticmethod
    def _remaining_weekdays_in_month(today: datetime) -> int:
        last_day = monthrange(today.year, today.month)[1]
        remaining_days = 0
        for day in range(today.day, last_day + 1):
            current = datetime(today.year, today.month, day)
            if current.weekday() < 5:  # Mon-Fri
                remaining_days += 1
        return remaining_days

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
        remaining_working_days = self._remaining_weekdays_in_month(today)

        if remaining_working_days > 0:
            office_minutes = int(office_time.total_seconds() // 60)
            cumulative_delta_minutes = int(cumulative_delta.total_seconds() // 60)
            required_per_day_minutes = office_minutes - (
                cumulative_delta_minutes // remaining_working_days
            )
            required_per_day_minutes = max(required_per_day_minutes, 7 * 60)
            per_day_text = self._format_minutes_as_timedelta(required_per_day_minutes)
            if cumulative_delta >= timedelta(0):
                daily_message = (
                    "You can leave every day by doing {per_day_text}."
                )
            else:
                daily_message = (
                    f"To reach average, do {per_day_text} "
                    "every remaining working day."
                )
        else:
            daily_message = "No remaining working days in this month."

        if cumulative_delta >= timedelta(0):
            notification_title = (
                f"{self.format_timedelta(cumulative_delta)} extra time available"
            )
            notification_message = (
                f"{daily_message}\n"
                f"Current average: {self.format_timedelta(self.daily_avg)}"
            )
        else:
            time_to_reach_avg = abs(cumulative_delta)
            notification_title = (
                f"{self.format_timedelta(time_to_reach_avg)} "
                "remaining to reach average"
            )
            notification_message = (
                f"{daily_message}\n"
                f"Current average: {self.format_timedelta(self.daily_avg)}"
            )
        return notification_title, notification_message

    def _extract_summary_metrics(
        self, response: requests.Response
    ) -> tuple[int, timedelta]:
        mystats = response.json()["data"]["myStats"]
        working_days = int(mystats.get("workingDays", 0))
        daily_avg = self.parse_hhmm_text(
            mystats.get("averageHoursPerDayInHHMM", "0h 0m")
        )
        return working_days, daily_avg

    def fetch_your_extra_hours(self) -> None:
        try:
            response = self.fetch_response()
            self.working_days, self.daily_avg = self._extract_summary_metrics(
                response
            )
            notification_title, notification_message = (
                self.calculate_extra_time_and_get_message(
                    self.total_office_time
                ))
            notify_user(notification_title, notification_message)
        except Exception as error:
            logger.exception("Failed to calculate extra hours")
            notify_user("ERROR", f"Failed to calculate your extra hours: {error}")


extra_hours_calculator = KekaExtraHoursCalculator()
