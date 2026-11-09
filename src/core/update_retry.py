"""Bounded retries for temporary network failures; never retry verification errors."""
import time
from urllib.error import HTTPError, URLError


def retry_network(operation, progress, sleep=time.sleep):
    for attempt in range(3):
        try:
            return operation()
        except (HTTPError, URLError, TimeoutError, ConnectionError) as error:
            if isinstance(error, HTTPError) and error.code not in {408, 429, 500, 502, 503, 504}:
                raise
            if attempt == 2:
                raise RuntimeError("Сервер обновлений временно недоступен. Повторите позже. " + str(error)) from error
            progress(f"Временный сбой сети. Повторная попытка {attempt + 2} из 3…")
            sleep(2 ** (attempt + 1))
