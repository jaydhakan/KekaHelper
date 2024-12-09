import ctypes
import subprocess
import time
from datetime import datetime, timedelta
from json import dumps, loads
from os.path import exists
from sys import platform

import requests

from util import auth_token_helpers


class KekaDailyHoursCalculator:
    datetime_format = '%Y-%m-%dT%H:%M:%S'
    datetime_format_12_hour = '"%I:%M:%S %p"'
    total_office_time = timedelta(hours=8, minutes=30)
    partial_office_time = timedelta(hours=6, minutes=55)
    time_spent_file_path = 'time_spent.json'

    @staticmethod
    def __notification(title, message):
        if platform == 'linux':
            subprocess.run(['notify-send', title, message])
        elif platform == 'win32':
            ctypes.windll.user32.MessageBoxW(0, message, title, 1)
        time.sleep(1)

    @staticmethod
    def check_if_valid_response(response):
        return (
            response.status_code == 200 and
            'data' in response.json() and
            'breakDurationInHHMM' in response.json()['data'][-1]
        )

    def fetch_response(self, fetch_new_api_token: bool = False):
        for retry_count in range(1, 4):
            try:
                url = (
                    "https://kevit.keka.com"
                    "/k/attendance/api/mytime/attendance/summary"
                )
                authorization_token = (
                    auth_token_helpers.read_auth_token_from_file(
                        fetch_new_api_token
                    ))
                print(f'Authorization_token:\n{authorization_token}\n')
                headers = {
                    'authorization': f'{authorization_token}'
                }
                response = requests.get(url=url, headers=headers, timeout=10)
                if self.check_if_valid_response(response):
                    return response
                else:

                    if not auth_token_helpers.check_internet():
                        self.__notification(
                            'Failed!!', 'No internet connection!!'
                        )
                        exit()
                    if not fetch_new_api_token and retry_count == 3:
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
            except Exception as err:
                if not auth_token_helpers.check_internet():
                    self.__notification('Failed!!', 'No internet connection!!')
                    exit()
                if not fetch_new_api_token and retry_count == 3:
                    return self.fetch_response(fetch_new_api_token=True)
                print(
                    f'Unknown ERROR when getting response from Keka API call, '
                    f'ERROR: {str(err)}'
                )
                self.__notification(
                    'ERROR', f'Keka API call failed, ERROR: {str(err)}'
                )
        exit()

    def convert_str_to_datetime(self, time_str: str):
        try:
            timestamp_obj = datetime.strptime(
                time_str, '%Y-%m-%dT%H:%M:%S'
            )
        except Exception:
            print(
                f'I guess you are in work from home. ENJOIII!!!!!, '
                'Converting string to datetime with modified format.'
            )
            self.__notification(
                'Work from home',
                'I guess you are in work from home. ENJOIII!!!!!'
            )
            timestamp_obj = datetime.strptime(
                time_str[:-8], '%Y-%m-%dT%H:%M:%S'
            )
        return timestamp_obj

    @staticmethod
    def is_half_day(last_entry: dict):
        return (
            last_entry.get('isFirstHalfLeave', False) or
            last_entry.get('isSecondHalfLeave', False)
        )

    def calculate_daily_hours(self):
        try:
            response = self.fetch_response()
            last_entry = response.json()['data'][-1]
            break_time = last_entry.get('breakDurationInHHMM', '0:0').split(
                ':'
            )

            if self.is_half_day(last_entry):
                self.total_office_time = timedelta(hours=4, minutes=15)
                self.partial_office_time = timedelta(hours=2, minutes=45)

            break_hour = int(break_time[0])
            break_minute = int(break_time[1])
            break_time = timedelta(hours=break_hour, minutes=break_minute)

            first_log = self.convert_str_to_datetime(
                last_entry.get('originalTimeEntries')[0]['actualTimestamp']
            )
            time_spent = datetime.now() - first_log - break_time

            total_time_leave = (
                (datetime.now() + (self.total_office_time - time_spent))
            ).strftime(self.datetime_format_12_hour)

            partial_time_leave = (
                (datetime.now() + (self.partial_office_time - time_spent))
            ).strftime(self.datetime_format_12_hour)

            current_time = (
                (datetime.now().time()).strftime(self.datetime_format_12_hour)
            )
            notification_title = (
                f'Office Time Reminder. Time ~ {current_time}'
            )
            notification_message = (
                f'You can close at {total_time_leave} or {partial_time_leave}.'
            )

            print(f'You can logout on {total_time_leave}')
            return self.__notification(
                notification_title, notification_message
            )
        except Exception as err:
            print(f'ERROR: {str(err)}')
            self.__notification(
                'Error', f'Failed to calculate daily hours: {str(err)}'
            )


daily_hours_calculator = KekaDailyHoursCalculator()

if __name__ == '__main__':
    daily_hours_calculator.calculate_daily_hours()

