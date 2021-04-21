"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2021/04/21 18:00
    文件:    cache.py
    文件描述: Cached data for reuse
"""
from dataclasses import dataclass
from typing import Union, Any, Optional, Dict

import aiohttp

yt_root_url = "https://www.youtube.com"
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


def get_yt_client_info():
    return {
        "hl": "en_US",
        "clientName": yt_internal_api.client_name,
        "clientVersion": yt_internal_api.client_version,
        "browserName": yt_internal_api.client_browser_name,
        "browserVersion": yt_internal_api.client_browser_version
    }


@dataclass
class InternalAPI:
    key: str = ""
    version = "v1"
    client_version = "2.20770101.00.00"
    client_name = "WEB"
    client_browser_name = "Chrome"
    client_browser_version = "90.0.4430.72"
    yt_client_name = "1"
    yt_client_version = "2.20770101.00.00"
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

    def update_html(self, script: dict):
        """Update data from html's js"""
        client = script['INNERTUBE_CONTEXT']['client']
        self.update({
            "key": script['INNERTUBE_API_KEY'],
            "version": script['INNERTUBE_API_VERSION'],
            "client_name": script['INNERTUBE_CLIENT_NAME'],
            "client_version": script['INNERTUBE_CLIENT_VERSION'],
            "client_browser_name": client['browserName'],
            "client_browser_version": client['browserVersion'],
            "yt_client_name": script['INNERTUBE_CONTEXT_CLIENT_NAME'],
            "yt_client_version": script['INNERTUBE_CONTEXT_CLIENT_VERSION']
        })


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

    def __getitem__(self, item):
        return self.cache.get(item)


yt_internal_api = InternalAPI()
js_cache_v2 = JSCache()
