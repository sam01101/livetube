"""
    livetube - A API for youtube streaming
    Author: Sam
    Created: 2021/04/21 18:00
    File:    cache.py
    Description: Cached data for reuse
"""
import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Union, Any, Optional, Dict

import aiohttp

from livetube.util import player
from livetube.util.parser import ScriptTaker
from livetube.utils import http_request

yt_root_url = "https://www.youtube.com"
studio_root_url = "https://studio.youtube.com"
user_agent = " ".join([
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "AppleWebKit/537.36 (KHTML, like Gecko)",
    "Chrome/90.0.4430.72",
    "Safari/537.36"
])
default_header = {
    "User-Agent": user_agent,
    "X-Origin": yt_root_url
}

# Shared tcp pool to reduce extra memory usage
shared_tcp_pool: Dict[int, "aiohttp.TCPConnector"] = {}


def get_yt_client_info(studio=False):
    data = {
        "hl": "en_US",
        "browserName": yt_internal_api.client_browser_name,
        "browserVersion": yt_internal_api.client_browser_version,
        "clientName": yt_internal_api.yt_client_name,
        "clientVersion": yt_internal_api.yt_client_version,
    }
    if studio:
        data.update({
            "clientName": yt_internal_api.studio_client_name,
            "clientVersion": yt_internal_api.studio_client_version,
        })
    return data


@dataclass
class InternalAPI:
    key: str = ""
    version = "v1"
    client_version = "2.20770101.00.00"
    client_name = "WEB"
    client_browser_name = "Chrome"
    client_browser_version = "90.0.4430.72"
    yt_client_name = 1
    yt_client_version = "2.20770101.00.00"
    studio_client_name = 62
    studio_client_version = "1.20770101.00.00"
    endpoint = "%s/youtubei" % yt_root_url

    def __getitem__(self, item):
        return getattr(self, item, None)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def update(self, key: Union[str, dict], value: Optional[Any] = None):
        if type(key) == str:
            if self[key] != value:
                self[key] = value
        elif type(key) == dict:
            for k, v in key.items():
                if self[k] != v:
                    self[k] = v

    def update_html(self, script: dict, studio=False):
        """Update data from html's js"""
        client = script['INNERTUBE_CONTEXT']['client']
        self.update({
            "key": script['INNERTUBE_API_KEY'],
            "version": script['INNERTUBE_API_VERSION'],
            "client_name": script['INNERTUBE_CLIENT_NAME'],
            "client_version": script['INNERTUBE_CLIENT_VERSION'],
            "client_browser_name": client.get("browserName", self.client_browser_name),
            "client_browser_version": client.get("browserVersion", self.client_browser_name),
        })
        if studio:
            self.update({
                "studio_client_name": script['INNERTUBE_CLIENT_NAME'],
                "studio_client_version": script['INNERTUBE_CLIENT_VERSION'],
            })
        else:
            self.update({
                "yt_client_name": script['INNERTUBE_CONTEXT_CLIENT_NAME'],
                "yt_client_version": script['INNERTUBE_CONTEXT_CLIENT_VERSION'],
            })

    async def fetch(self, force=False, studio=False, cookie: dict = None):
        """
        Manually fetch all data, when not exist

        :param force: Don't check for data exist
        :param studio: Is fetching in studio dashboard
        :param cookie: Cookie for fetching studio
        :raise NetworkError: Network error
        :raise ValueError: Studio mode but no cookie
        """
        loop = asyncio.get_event_loop()
        client_id = hash(loop)
        pool = shared_tcp_pool.get(client_id)
        if not pool:
            shared_tcp_pool[client_id] = aiohttp.TCPConnector(loop=loop, ttl_dns_cache=60,
                                                              force_close=True, enable_cleanup_closed=True, limit=0)
        if self.key and not studio and not force:
            return
        if studio and not cookie:
            raise ValueError("Cookie required to fetch studio client")
        async with http_request(shared_tcp_pool[client_id],
                                url=studio_root_url if studio else yt_root_url,
                                header=default_header, cookie=cookie if studio else {}) as response:
            self.update_html(player.get_ytplayer_setconfig(ScriptTaker(await response.text()).scripts), studio)


class JSCache:
    def __init__(self):
        self.max_cache = 50
        self.cache = {}

    def __setitem__(self, key, value):
        if not self.cache.get(key):
            if len(self.cache) >= self.max_cache:
                # Drop the oldest item
                try:
                    del self.cache[next(iter(self.cache))]
                except (StopIteration, RuntimeError, KeyError):
                    pass
            self.cache[key] = value

    @lru_cache(maxsize=50)
    def __getitem__(self, item):
        return self.cache.get(item)


yt_internal_api = InternalAPI()
js_cache_v2 = JSCache()
