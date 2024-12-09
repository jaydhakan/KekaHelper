import asyncio
import ctypes
import subprocess
import sys
from json import loads
from os.path import exists
from sys import platform
from time import sleep

import urllib3
from playwright.async_api import Playwright, async_playwright


class AuthToken:
    ROOT_DIR_PATH = sys.path[0]
    token_file_path = f'{ROOT_DIR_PATH}/token_file.txt'

    @staticmethod
    def __notification(title, message):
        if platform == 'linux':
            subprocess.run(['notify-send', title, message])

        elif platform == 'win32':
            ctypes.windll.user32.MessageBoxW(0, message, title, 1)
        sleep(1)

    async def fetch_auth_token(self, playwright: Playwright):
        if not self.check_internet():
            self.__notification('Failed!!', 'No internet connection!!')
            exit()
        self.__notification(
            'Scraping new auth token.', ' This can take up-to 10-15 seconds'
        )
        chromium = playwright.chromium
        chrome_path = f'{self.ROOT_DIR_PATH}/chrome-profile'
        browser = await chromium.launch_persistent_context(
            user_data_dir=chrome_path,
            headless=True
        )
        try:
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
                print(f'Successfully scraped auth token::\n{auth_token}\n')
                if not exists(self.token_file_path):
                    with open(self.token_file_path, "w") as token_file:
                        token_file.write(f'Bearer {auth_token}')
                else:
                    with open(self.token_file_path, "r+") as token_file:
                        token_file.seek(0)
                        token_file.write(f'Bearer {auth_token}')
            else:
                self.__notification('Failure', 'Failed to get Auth Token')
                raise Exception('Failed to get Auth Token')
            await browser.close()
            print('\nDriver closed\n\n')
            return auth_token
        finally:
            await browser.close()
            print('\nDriver closed\n\n')
            return None

    async def get_auth_token_dynamically(self):
        async with async_playwright() as playwright:
            await self.fetch_auth_token(playwright)

    def read_auth_token_from_file(
        self, fetch_new_api_token: bool = False
    ) -> str:
        if fetch_new_api_token:
            asyncio.run(self.get_auth_token_dynamically())
        with open(self.token_file_path, "r+") as token_file:
            authorization_token = token_file.read()
        return authorization_token

    @staticmethod
    def check_internet():
        internet_alive = False
        for i in range(3):
            try:
                http = urllib3.PoolManager()
                _ = http.request('GET', 'https://www.google.com')
                internet_alive = True
                break
            except Exception:
                print(f'No internet connection!!')

        return internet_alive


auth_token_helpers = AuthToken()
if __name__ == '__main__':
    auth_token_helpers.read_auth_token_from_file(fetch_new_api_token=True)
