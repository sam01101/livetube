"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 10:18
    文件:    utils.py
    文件描述: Functions that publicly use
"""
import asyncio
import json
import logging
import re
from hashlib import sha1
from time import time
from typing import Union
from urllib.parse import unquote

import aiohttp

from .util.exceptions import NetworkError

logger = logging.getLogger("livetube")

redirect_regex = re.compile(r"https://www\.youtube\.com/redirect\?[\w+_&=]+&q=(.+)")
number_table = {"K": 1000, "M": 1000000, "B": 1000000000}
time_map = {
    "seconds": "秒",
    "minutes": "分钟",
    "hours": "小时",
    "days": "天",
    "years": "年",
}


def get_text(item: dict) -> str:
    # exception = runs
    if item.get("simpleText") is not None:
        return item['simpleText']
    ret = ""
    for cmd in item['runs']:  # type: dict
        if url_ep := cmd.get("navigationEndpoint", {}).get("urlEndpoint"):
            if url := redirect_regex.match(url_ep['url']):
                ret += unquote(url.group(1))
            else:
                ret += url_ep['url']
        else:
            ret += cmd['text']
    return ret


def string_to_int(readable: str) -> int:
    """Transform a human-readable text to number"""
    for num_text, num in number_table.items():
        if readable.find(num_text) != -1:
            return int(float(readable[:-1]) * num)
    return int(readable)


def string_escape(s, encoding='utf-8') -> str:
    return (s.encode('latin1')  # To bytes, required by 'unicode-escape'
            .decode('unicode-escape')  # Perform the actual octal-escaping decode
            .encode('latin1')  # 1:1 mapping back to bytes
            .decode(encoding))  # Decode original encoding


def calculate_SNAPPISH(cookie: dict, header: dict) -> dict:
    """
    Algorithm: SHA1(Timestamp + " " + SAPISID + " " + Origin)
    Header: Authorization: SAPISIDHASH timestamp_<SAPISIDHASH>
    """
    if not cookie or len(cookie) == 1:
        return header
    timestamp = str(int(time()))
    s_api_id = cookie['SAPISID']
    Origin = header['X-Origin']
    raw = " ".join([timestamp, s_api_id, Origin])
    _hash = sha1(raw.encode()).hexdigest()
    new_header = header.copy()
    new_header["Authorization"] = f"SAPISIDHASH {timestamp}_{_hash}"
    return new_header


# wrapper in wrapper (LOL)
class http_request:
    def __init__(self, client: "aiohttp.TCPConnector", method="GET",
                 url="", header: dict = None, cookie: dict = None,
                 data: bytes = None, json_data: Union[dict, list] = None,
                 max_retries=3, raise_error=True, **kwargs):
        if cookie is None:
            cookie = {}
        if header is None:
            header = {}
        self.pool = client
        self.method = method

        self.url = url
        self.cookie = cookie
        self.header = header

        self.data = data
        self.json = json_data
        self.extra = kwargs

        self.resp = None
        self.max_retries = max_retries
        self.raise_error = raise_error

    async def __aenter__(self):
        for _ in range(self.max_retries):
            # noinspection PyBroadException
            try:
                cookie_jar = aiohttp.CookieJar(quote_cookie=False)
                cookie_jar.update_cookies(cookies=self.cookie)
                async with aiohttp.ClientSession(connector=self.pool, connector_owner=False,
                                                 cookie_jar=cookie_jar) as client:
                    response = await client.request(self.method, self.url,
                                                    data=self.data, json=self.json,
                                                    headers=self.header,
                                                    **self.extra)
                    if response.status > 399 and self.raise_error:
                        try:
                            r: dict = await response.json()
                            response.close()
                            if error := r.get("error"):
                                status, msg = error['status'], error['message']
                                if status == "PERMISSION_DENIED" and msg == "The request is missing a valid API key.":
                                    # Update API key
                                    return False
                                logger.debug(f"Network error: {status} {msg}")
                        except json.JSONDecodeError:
                            logger.debug(f"Network error: {await response.text()}")
                        finally:
                            raise NetworkError
                    self.resp = response
                    return response
            except Exception as e:
                logger.debug(f"Critical network error: {e}")
                await asyncio.sleep(3)
                continue
        raise NetworkError("Max retries reached")

    async def __aexit__(self, _, __, ___):
        if self.resp:
            self.resp.close()
