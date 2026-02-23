import asyncio
from json import loads
from pathlib import Path
from typing import Callable

import requests
from playwright.async_api import async_playwright, Playwright

from common_helpers import get_env_int, get_logger, notify_user

logger = get_logger(__name__)


class AuthToken:
    ROOT_DIR_PATH = Path(__file__).resolve().parent
    token_file_path = ROOT_DIR_PATH / "token_file.txt"
    chrome_profile_path = ROOT_DIR_PATH / "chrome-profile"
    internet_retry_count = get_env_int("KEKA_INTERNET_RETRY_COUNT", 3)
    internet_timeout_seconds = get_env_int("KEKA_INTERNET_TIMEOUT_SECONDS", 5)
    browser_goto_timeout_ms = get_env_int(
        "KEKA_BROWSER_GOTO_TIMEOUT_MS", 20000
    )
    browser_wait_after_goto_ms = get_env_int(
        "KEKA_BROWSER_WAIT_AFTER_GOTO_MS", 3000
    )

    async def fetch_auth_token(self, playwright: Playwright) -> str:
        if not self.is_internet_alive():
            notify_user("Failed", "No internet connection")
            raise ConnectionError("No internet connection")

        chromium = playwright.chromium
        browser = await chromium.launch_persistent_context(
            user_data_dir=str(self.chrome_profile_path),
            headless=True,
        )

        try:
            logger.info("Browser session started for auth token refresh")
            page = await browser.new_page()
            url = "https://kevit.keka.com/#/me/attendance/logs"
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.browser_goto_timeout_ms,
            )
            await page.wait_for_timeout(self.browser_wait_after_goto_ms)

            auth_token = await page.evaluate(
                'JSON.stringify(window.localStorage.getItem("access_token"))'
            )
            auth_token = loads(auth_token)
            if auth_token:
                token_value = f"Bearer {auth_token}"
                self.token_file_path.write_text(token_value, encoding="utf-8")
                logger.info("Auth token refreshed and written to token_file.txt")
                return token_value

            notify_user("Failure", "Failed to get auth token")
            raise RuntimeError("Failed to get auth token from browser storage")
        finally:
            await browser.close()
            logger.info("Browser session closed")

    async def get_auth_token_dynamically(self) -> str:
        async with async_playwright() as playwright:
            return await self.fetch_auth_token(playwright)

    def read_auth_token_from_file(
        self, fetch_new_api_token: bool = False
    ) -> str:
        if fetch_new_api_token or not self.token_file_path.exists():
            asyncio.run(self.get_auth_token_dynamically())

        self.token_file_path.parent.mkdir(parents=True, exist_ok=True)
        authorization_token = self.token_file_path.read_text(
            encoding="utf-8"
        ).strip()
        if not authorization_token:
            raise RuntimeError("Authorization token file is empty")
        if not authorization_token.startswith("Bearer "):
            authorization_token = f"Bearer {authorization_token}"

        return authorization_token

    @staticmethod
    def is_internet_alive() -> bool:
        for retry in range(1, AuthToken.internet_retry_count + 1):
            # noinspection PyBroadException
            try:
                _ = requests.get(
                    "https://www.google.com/generate_204",
                    timeout=AuthToken.internet_timeout_seconds,
                )
                return True
            except Exception:
                logger.warning(
                    f"Internet check failed "
                    f"(attempt {retry}/{AuthToken.internet_retry_count})"
                )
        return False


def fetch_keka_response(
    *,
    url: str,
    is_valid_response: Callable[[requests.Response], bool],
    request_timeout_seconds: int,
    max_retries: int,
    context_name: str,
    refresh_token_on_failure: bool = True,
) -> requests.Response:
    response, error = run_keka_request_attempts(
        url=url,
        is_valid_response=is_valid_response,
        request_timeout_seconds=request_timeout_seconds,
        max_retries=max_retries,
        context_name=context_name,
        fetch_new_api_token=False,
    )
    if response is not None:
        return response

    if refresh_token_on_failure:
        logger.info(f"{context_name}: retrying after auth token refresh")
        response, refresh_error = run_keka_request_attempts(
            url=url,
            is_valid_response=is_valid_response,
            request_timeout_seconds=request_timeout_seconds,
            max_retries=max_retries,
            context_name=context_name,
            fetch_new_api_token=True,
        )
        if response is not None:
            return response
        error = refresh_error

    raise RuntimeError(f"{context_name} failed after retries: {error}")


def run_keka_request_attempts(
    *,
    url: str,
    is_valid_response: Callable[[requests.Response], bool],
    request_timeout_seconds: int,
    max_retries: int,
    context_name: str,
    fetch_new_api_token: bool,
) -> tuple[requests.Response | None, Exception | None]:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            token = auth_token_helpers.read_auth_token_from_file(fetch_new_api_token)
            response = requests.get(
                url=url,
                headers={"authorization": token},
                timeout=request_timeout_seconds,
            )
            if is_valid_response(response):
                return response, None

            last_error = RuntimeError(
                f"status={response.status_code}, body={response.text[:200]}"
            )
            logger.warning(
                f"{context_name} invalid response "
                f"(attempt {attempt}/{max_retries}): {last_error}"
            )
        except requests.RequestException as err:
            last_error = err
            if not auth_token_helpers.is_internet_alive():
                notify_user("Failed", "No internet connection")
                raise ConnectionError("No internet connection") from err
            logger.warning(
                f"{context_name} request failure "
                f"(attempt {attempt}/{max_retries}): {err}"
            )
    return None, last_error


auth_token_helpers = AuthToken()
if __name__ == '__main__':
    auth_token_helpers.read_auth_token_from_file(fetch_new_api_token=True)
