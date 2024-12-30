import ctypes
import subprocess
from datetime import datetime, timedelta
from sys import platform
from time import sleep

import requests

from util import auth_token_helpers


class KekaExtraHoursCalculator:
    working_days = 0
    total_office_time = timedelta(hours=8, minutes=30)
    daily_avg = timedelta(hours=0, minutes=0)

    current_month = datetime.now().month
    current_year = datetime.now().year
    from_date = datetime(current_year, current_month, 1).strftime("%Y-%m-%d")
    to_date = datetime.now().date() - timedelta(days=1)

    @staticmethod
    def __notification(title, message):
        if platform == 'linux':
            subprocess.run(['notify-send', title, message])

        elif platform == 'win32':
            ctypes.windll.user32.MessageBoxW(0, message, title, 1)
        sleep(1)

    @staticmethod
    def check_if_valid_response(response):
        return (
            response.status_code == 200 and
            'data' in response.json() and
            'myStats' in response.json()['data'] and
            'workingDays' in response.json()['data']['myStats'] and
            'averageHoursPerDayInHHMM' in response.json()['data']['myStats']
        )

    def fetch_response(self, fetch_new_api_token: bool = False):
        try:
            url = (
                f'https://kevit.keka.com/k/attendance/api/mytime/attendance/'
                f'lastweekstats?fromDate={self.from_date}&toDate={self.to_date}'
            )
            authorization_token = auth_token_helpers.read_auth_token_from_file(
                fetch_new_api_token
            )
            print(f'Authorization_token:\n{authorization_token}\n')
            headers = {
                'authorization': f'{authorization_token}'
            }
            response = requests.get(url=url, headers=headers, timeout=10)
            if self.check_if_valid_response(response):
                return response
            else:
                if not auth_token_helpers.check_internet():
                    self.__notification('Failed!!', 'No internet connection!!')
                    exit()
                if not fetch_new_api_token:
                    return self.fetch_response(fetch_new_api_token=True)
                print(
                    f'Failed to get response from Keka API call, '
                    f'response: {response.status_code}, {response.text}'
                )
                self.__notification(
                    'Failed',
                    f'Keka API call failed, '
                    f'response: {response.status_code}, {response.text}'
                )
                exit()
        except Exception as err:
            if not auth_token_helpers.check_internet():
                self.__notification('Failed!!', 'No internet connection!!')
                exit()
            if not fetch_new_api_token:
                return self.fetch_response(fetch_new_api_token=True)
            print(
                f'Unknown ERROR when getting response from Keka API call, '
                f'ERROR: {err}'
            )
            self.__notification(
                'ERROR', f'Keka API call failed, ERROR: {str(err)}'
            )
            exit()

    def calculate_extra_time_and_get_message(self, office_time: timedelta):
        extra_time = self.daily_avg - office_time
        if self.daily_avg < office_time:
            extra_time = office_time - self.daily_avg

        total_seconds = extra_time.total_seconds()
        extra_hours = int(total_seconds // 3600) * self.working_days
        extra_minutes = int((total_seconds % 3600) // 60) * self.working_days

        extra_time = timedelta(hours=extra_hours, minutes=extra_minutes)

        notification_title = 'Extra Time Available'
        notification_message = (
            f'Extra time done till now: {extra_time}'
        )
        if self.daily_avg < office_time:
            notification_title = f'Extra time to make average {office_time}.'
            notification_message = (
                f'Extra time to be done: {extra_time}'
            )
        return notification_title, notification_message

    def fetch_your_extra_hours(self):
        try:
            response = self.fetch_response()
            mystats = response.json()['data']['myStats']
            self.working_days = mystats.get('workingDays')
            daily_avg = mystats.get('averageHoursPerDayInHHMM').split(' ')
            daily_hours = int(daily_avg[0][:-1])

            daily_minutes = 0
            if len(daily_avg) > 1:
                daily_minutes = int(daily_avg[1][:-1])
            self.daily_avg = timedelta(
                hours=daily_hours, minutes=daily_minutes
            )

            notification_title, notification_message = (
                self.calculate_extra_time_and_get_message(
                    self.total_office_time
                ))

            return self.__notification(
                notification_title,
                notification_message
            )
        except Exception as error:
            print(f'Failed to calculate your extra hours, ERROR: {error}')
            self.__notification(
                'ERROR', 'Failed to calculate your extra hours, '
                         f'ERROR: {str(error)}'
            )


extra_hours_calculator = KekaExtraHoursCalculator()

if __name__ == '__main__':
    extra_hours_calculator.fetch_your_extra_hours()
