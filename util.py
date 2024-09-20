import asyncio
import ctypes
import subprocess
import sys
from datetime import datetime, timedelta
from json import loads
from sys import platform
from time import sleep

from playwright.async_api import Playwright, async_playwright


class AuthToken:
    ROOT_DIR_PATH = sys.path[0]
    token_file_path = f'{ROOT_DIR_PATH}/token_file.txt'
    time_path = f'{ROOT_DIR_PATH}/last_token_scrap_time.txt'

    @staticmethod
    def __notification(title, message):
        if platform == 'linux':
            subprocess.run(['notify-send', title, message])

        elif platform == 'win32':
            ctypes.windll.user32.MessageBoxW(0, message, title, 1)
        sleep(1)

    async def fetch_auth_token(self, playwright: Playwright):
        self.__notification(
            'Scraping new auth token.', ' This can take up-to 10-15 seconds'
        )
        chromium = playwright.chromium
        chrome_path = f'{self.ROOT_DIR_PATH}/chrome-profile'
        browser = await chromium.launch_persistent_context(
            user_data_dir=chrome_path,
            headless=True
        )
        print('Driver started\n\n')
        page = await browser.new_page()
        url = 'https://kevit.keka.com/#/me/attendance/logs'
        await page.goto(url)
        sleep(2)
        print('Site opened, fetching local storage data\n')
        auth_token = await page.evaluate(
            'JSON.stringify(window.localStorage.getItem("access_token"))'
        )
        auth_token = loads(auth_token)
        if auth_token:
            print(f'Auth token parsed:: {auth_token}\n')
            with open(self.token_file_path, "r+") as token_file:
                self.__notification('Previous Auth Token', token_file.read())
                token_file.seek(0)
                token_file.write(f'Bearer {auth_token}')
                self.__notification('New Auth Token', f'Bearer {auth_token}')
        else:
            self.__notification('Failure', 'Failed to get Auth Token')
            raise Exception('Failed to get Auth Token')
        await browser.close()
        print('\nDriver closed')
        return auth_token

    async def get_auth_token_dynamically(self):
        async with async_playwright() as playwright:
            await self.fetch_auth_token(playwright)

    def check_need_to_scrap_token(self):
        with open(self.time_path, "r+") as token_time_file:
            last_scrap_time = str(token_time_file.readline()).replace('\n', '')
            try:
                last_scrap_time = datetime.strptime(last_scrap_time, "%Y-%m-%d")
            except Exception as error:
                self.__notification(
                    'Error while reading last token scrap time.', str(error)
                )
                last_scrap_time = datetime(year=2024, month=1, day=1)
            if datetime.now() - last_scrap_time > timedelta(hours=23):
                asyncio.run(self.get_auth_token_dynamically())
                token_time_file.seek(0)
                token_time_file.write(str(datetime.now().date()))

    def read_auth_token_from_file(self) -> str:
        self.check_need_to_scrap_token()
        with open(self.token_file_path, "r") as token_file:
            authorization_token = token_file.read()
        return authorization_token


auth_token_helpers = AuthToken()
if __name__ == '__main__':
    auth_token_helpers.check_need_to_scrap_token()