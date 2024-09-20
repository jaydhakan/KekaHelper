import ctypes
import json
import subprocess
from datetime import datetime, timedelta
from sys import platform

import scrapy
from scrapy import Request
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from util import auth_token_helpers


class KekaSpider(scrapy.Spider):
    name = 'keka_spider'
    working_days = 0
    total_office_time = timedelta(hours=8, minutes=30)
    min_office_time = timedelta(hours=8, minutes=20)
    daily_avg = timedelta(hours=0, minutes=0)

    current_month = datetime.now().month
    current_year = datetime.now().year
    from_date = datetime(current_year, current_month, 1).strftime("%Y-%m-%d")
    to_date = datetime.now().date() - timedelta(days=1)

    def start_requests(self):
        url = (
            f'https://kevit.keka.com/k/attendance/api/mytime/attendance'
            f'/lastweekstats?fromDate={self.from_date}&toDate={self.to_date}'
        )
        authorization_token = auth_token_helpers.read_auth_token_from_file()
        print(authorization_token)
        headers = {
            'authorization': f'{authorization_token}'
        }
        yield Request(url=url, headers=headers, callback=self.parse_extra_hours)

    @staticmethod
    def __notification(title, message):
        if platform == 'linux':
            subprocess.run(['notify-send', title, message])

        elif platform == 'win32':
            ctypes.windll.user32.MessageBoxW(0, message, title, 1)

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

    def parse_extra_hours(self, response):
        if response.status == 200:
            data = json.loads(response.text)

            if data.get('data'):
                data = data.get('data')
                mystats = data.get('myStats')
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

                notification_title_min, notification_message_min = (
                    self.calculate_extra_time_and_get_message(
                        self.min_office_time
                    ))

                self.__notification(
                    notification_title_min,
                    notification_message_min
                )
                return self.__notification(
                    notification_title,
                    notification_message
                )

            return self.__notification(
                'Request failed',
                f'Failed to get data'
            )
        return self.__notification(
            'Request failed',
            f'Status code {response.status}'
        )


if __name__ == '__main__':
    def run_spider_manually(spider):
        process = CrawlerProcess(get_project_settings())
        process.crawl(spider)
        process.start()


    run_spider_manually(KekaSpider)
