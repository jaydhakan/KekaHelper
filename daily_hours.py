import ctypes
import datetime
import subprocess
import time
from datetime import datetime, timedelta
from json import loads
from sys import platform

import scrapy
from scrapy import Request
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from util import auth_token_helpers


class KekaSpider(scrapy.Spider):
    name = 'keka_spider'
    datetime_format = '%Y-%m-%dT%H:%M:%S'
    datetime_format_12_hour = '"%I:%M:%S %p"'
    total_office_time = timedelta(hours=8, minutes=30)
    partial_office_time = timedelta(hours=7, minutes=00)

    def start_requests(self):
        url = (
            "https://kevit.keka.com/k/attendance/api/mytime/attendance/summary"
        )
        authorization_token = auth_token_helpers.read_auth_token_from_file()
        print(authorization_token)
        headers = {
            'authorization': f'{authorization_token}'
        }
        yield Request(url=url, headers=headers, callback=self.parse_daily_hours)

    @staticmethod
    def __notification(title, message):
        if platform == 'linux':
            subprocess.run(['notify-send', title, message])

        elif platform == 'win32':
            ctypes.windll.user32.MessageBoxW(0, message, title, 1)
        time.sleep(1)

    @staticmethod
    def convert_str_to_datetime(time_str: str):
        try:
            timestamp_obj = datetime.strptime(
                time_str, '%Y-%m-%dT%H:%M:%S'
            )
        except Exception as error:
            print(error)
            timestamp_obj = datetime.strptime(
                time_str[:-8], '%Y-%m-%dT%H:%M:%S'
            )
        return timestamp_obj

    @staticmethod
    def is_half_day(last_entry: dict):
        last_entry.get('isFirstHalfLeave', False)
        return (
            last_entry.get('isFirstHalfLeave', False) or
            last_entry.get('isSecondHalfLeave', False)
        )

    def parse_daily_hours(self, response):
        try:
            if response.status == 200:
                data = loads(response.text)

                if data.get('data'):
                    last_entry = data['data'][-1]
                    break_time = (
                        last_entry.get('breakDurationInHHMM', None).split(':')
                    )

                    if self.is_half_day(last_entry):
                        self.total_office_time = timedelta(hours=4, minutes=15)
                        self.partial_office_time = timedelta(
                            hours=2, minutes=45
                        )

                    break_hour = int(break_time[0])
                    break_minute = int(break_time[1])
                    break_time = timedelta(
                        hours=break_hour,
                        minutes=break_minute
                    )
                    first_log = self.convert_str_to_datetime(
                        last_entry.get('originalTimeEntries')[0][
                            'actualTimestamp']
                    )
                    time_spent = (
                        datetime.now() - first_log - break_time
                    )

                    # region Manual Calculation of TIME SPENT
                    # logs = []
                    # for entry in last_entry.get('originalTimeEntries', []):
                    #     actual_timestamp = entry.get('actualTimestamp', None)
                    #     if actual_timestamp is not None:
                    #         logs.append(actual_timestamp)
                    #
                    # # logs.pop()
                    # print(logs)
                    # time_spent = timedelta(hours=0, minutes=0)
                    # if len(logs) == 1:
                    #     time_spent += (
                    #         datetime.now() -
                    #         datetime.strptime(logs[0], self.datetime_format)
                    #     )
                    #
                    # else:
                    #     i = 0
                    #     while i < len(logs):
                    #         if i == len(logs) - 1:
                    #             time_spent += (
                    #                 datetime.now() -
                    #                 datetime.strptime(
                    #                     logs[-1],
                    #                     self.datetime_format
                    #                 )
                    #             )
                    #             break
                    #
                    #         time_spent += (
                    #             datetime.strptime(
                    #                 logs[i + 1],
                    #                 self.datetime_format
                    #             ) -
                    #             datetime.strptime(logs[i],
                    #             self.datetime_format)
                    #         )
                    #         i += 2
                    # endregion

                    print(f'Time spent till now:: {time_spent}')
                    total_time_leave = ((datetime.now() + (
                        self.total_office_time - time_spent))
                    ).strftime(self.datetime_format_12_hour)

                    partial_time_leave = ((datetime.now() + (
                        self.partial_office_time - time_spent))
                    ).strftime(self.datetime_format_12_hour)

                    current_time = (datetime.now().time()).strftime(
                        self.datetime_format_12_hour
                    )
                    notification_title = (
                        f'Office Time Reminder. Time ~ {current_time}'
                    )
                    notification_message = (
                        f'You can close at {total_time_leave}'
                        f' or {partial_time_leave}.'
                    )

                    print(f'Logout time {total_time_leave}')
                    return self.__notification(
                        notification_title, notification_message
                    )

                return self.__notification(
                    'Request failed', f'Failed to get data'
                )

            return self.__notification(
                'Request failed', f'Status code {response.status}'
            )
        except Exception as err:
            print(err)
            self.__notification(
                f'Error: ', str(err)
            )


if __name__ == '__main__':
    def run_spider_manually(spider):
        process = CrawlerProcess(get_project_settings())
        process.crawl(spider)
        process.start()


    run_spider_manually(KekaSpider)
