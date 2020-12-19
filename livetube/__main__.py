"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 10:18
    文件:    __main__.py
    文件描述: 
"""
import asyncio
import json
from hashlib import sha1
from time import time
from typing import Optional, Dict, Union
from urllib.parse import parse_qsl

import aiohttp
import yarl

from .playerResponse import playerResponse
from .util.excpetions import RegexMatchError
from .util.js import js_url, initial_data, video_info_url
from .util.regex import regex_search


# noinspection PyDefaultArgument
class Youtube:
    def __init__(self,
                 video_id: str,
                 cookie: dict,
                 header: Optional[Dict[str, Union[str, bool, int]]] = None):
        """
        創造一個Youtube obj

        :param video_id: Video ID, 可以是网址
        :param cookie: Cookie
        :param header: 额外的Header
        """

        # Pre fetch
        self.watch_html: Optional[str] = None
        self.age_restricted: Optional[bool] = None

        # JavaScript
        self.js: Optional[str] = None
        self.js_url: Optional[str] = None

        # Getting video_id
        if video_id.startswith("http"):
            video_id = regex_search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", video_id, group=1)

        self.video_id = video_id
        self.short_url = f"https://youtu.be/{self.video_id}"
        self.watch_url = f"https://youtube.com/watch?v={self.video_id}"
        self.embed_url = f"https://youtube.com/embed/{self.video_id}"
        self.vid_info_url: Optional[str] = None

        # Header
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
                          " Chrome/87.0.4280.88 Safari/537.36",
            "X-Origin": "https://www.youtube.com"
        }
        if header:
            self.header.update(header)

        # Client setup
        # Checking SAPISID from cookie
        if not cookie.get("SAPISID"):
            print("SAPISID not found, please check your cookie.")
            exit(1)
        # Fuck cookie jar, i'm out.
        self.cookie = cookie
        self.cookie_jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)
        self.cookie_jar.update_cookies(self.cookie)
        # self.cookie_header = {"Cookie": " ".join([f"{name}={value};" for name, value in cookie.items()])}
        # self.header.update(self.cookie_header)
        self.http: Optional[aiohttp.ClientSession] = None

        # Raw of video info
        self.vid_info_raw: Optional[str] = None
        self.initial_data: Optional[dict] = None
        self.vid_info: Optional[dict] = None
        self.player_config_args: Optional[dict] = None
        self.player_response: Optional[playerResponse] = None

        #  API used to fetch metadata
        self.api_ver: str = "v1"
        self.api_key: Optional[str] = None
        self.api_client_ver: str = "2.19970101.00.00"
        self.api_client_name: str = "WEB"
        self.metadata_endpoint: str = "https://www.youtube.com/youtubei/v1/updated_metadata?key="
        # URL used to fetch heartbeat and player
        self.heartbeat_endpoint: str = "https://www.youtube.com/youtubei/v1/player/heartbeat?alt=json&key="
        self.player_endpoint: str = "https://www.youtube.com/youtubei/v1/player?key="
        """Key for next fetching"""
        self.continue_id: Optional[str] = None

    def __del__(self):
        loop = asyncio.get_event_loop()
        if loop and not self.http.closed:
            asyncio.ensure_future(self.http.close(), loop=loop)

    def create_metadata_body(self, force_video_id: bool = False) -> str:
        """
        Create a dummy metadata body and dump as json
        :return: json string
        """
        body = {
            "context": {
                "client": {
                    "hl": "en_US",
                    "isInternal": True,
                    "clientName": self.api_client_name,
                    "clientVersion": self.api_client_ver
                }
            }
        }
        if not force_video_id and self.continue_id:
            body["continuation"] = self.continue_id
        else:
            body["videoId"] = self.video_id
        return json.dumps(body)

    def create_heartbeat_body(self) -> str:
        """
        Create a dummy heartbeat body and dump as json
        :return: json string
        """
        body = {
            "context": {
                "client": {
                    "hl": "en_US",
                    "clientName": self.api_client_name,
                    "clientVersion": self.api_client_ver
                }
            },
            "heartbeatRequestParams": {
                "heartbeatChecks": [
                    "HEARTBEAT_CHECK_TYPE_LIVE_STREAM_STATUS"
                ]
            },
            "videoId": self.video_id
        }
        return json.dumps(body)

    def get_exec_text(self, text: list) -> str:
        # exection = runs
        ret = ""
        for cmd in text:
            ret += cmd['text']
        return ret

    def update_actions(self, actions: list):
        for action in actions:  # type: dict
            if updateViewershipAction := action.get("updateViewershipAction"):
                """1,901 watching now"""
                # Btw isLive is inside
                data: dict = updateViewershipAction['viewCount']
                if data:
                    """    ==Structure==
                        viewCount {
                            videoViewCountRenderer {
                                viewCount {
                                    simpleText: str
                                }
                                isLive: bool
                                extraShortViewCount {
                                    accessibility {
                                        accessibilityData {
                                            label: str
                                        }
                                    }
                                    simpleText: str
                                }
                            }
                        }
                    """
                    if info := data.get("videoViewCountRenderer"):
                        if info.get("viewCount"):
                            text = self.get_exec_text(info['viewCount']['runs']) if info['viewCount'].get("runs") else \
                            info['viewCount']['simpleText']
                            self.player_response.videoDetails.liveViewCount = \
                                int(''.join(filter(str.isdigit, text)))
                        if info.get("isLive"):
                            self.player_response.videoDetails.isLive = info['isLive']
                        if info.get("extraShortViewCount"):
                            self.player_response.videoDetails.liveShortViewCount = info['extraShortViewCount'][
                                'simpleText']
            elif updateToggleButtonTextAction := action.get("updateToggleButtonTextAction"):
                """Like/Dislike button update"""
                # Note that the real number won't update tho
                if updateToggleButtonTextAction['buttonId'] == "TOGGLE_BUTTON_ID_TYPE_LIKE":
                    self.player_response.videoDetails.shortLikeCount = updateToggleButtonTextAction['defaultText'][
                        'simpleText']
                elif updateToggleButtonTextAction['buttonId'] == "TOGGLE_BUTTON_ID_TYPE_DISLIKE":
                    self.player_response.videoDetails.shortDislikeCount = updateToggleButtonTextAction['defaultText'][
                        'simpleText']
            elif updateDateTextAction := action.get("updateDateTextAction"):
                """Started streaming 6 hours ago"""
                pattern = {
                    "seconds": "秒",
                    "minutes": "分钟",
                    "hours": "小时",
                    "days": "天",
                    "years": "年",
                }
                displayText = updateDateTextAction['dateText']['simpleText']
                for p, name in pattern.items():
                    try:
                        time: int = int(regex_search(r"\d+" + p, displayText, 1))
                        self.player_response.videoDetails.startedSince = f"{time} {name}前"
                        break
                    except RegexMatchError:
                        continue
            elif updateTitleAction := action.get("updateTitleAction"):
                full_title = ""
                title: dict = updateTitleAction['title']
                if title.get("simpleText"):
                    full_title = title.get("simpleText")
                elif title.get("runs"):
                    for segment in title.get("runs"):  # type: dict
                        if segment != "":
                            full_title += segment.get("text", "")
                if self.player_response.videoDetails.title != full_title:
                    self.player_response.videoDetails.title = full_title

    async def fetch_metadata(self):
        print(time(), "Fetch metadata")
        async with self.http.post(self.metadata_endpoint, data=self.create_metadata_body(),
                                  headers=self.calculate_SNAPPISH()) as response:
            try:
                r: dict = await response.json()
                if not self.continue_id:
                    self.continue_id = r["continuation"]['timedContinuationData']['continuation']
            except (json.JSONDecodeError, KeyError):
                # print("Error: malformed JSON data", r)
                return
            self.update_actions(r['actions'])

    async def fetch_heartbeat(self):
        print(time(), "Fetch heartbeat")
        # Threat this like a dymanic update list object
        async with self.http.post(self.heartbeat_endpoint, data=self.create_heartbeat_body(),
                                  headers=self.calculate_SNAPPISH()) as response:
            try:
                r: dict = await response.json()
            except (json.JSONDecodeError, KeyError):
                # print("Error: malformed JSON data", r)
                return
            self.player_response.update(r)

    async def fetch_player(self):
        """Get the player"""
        async with self.http.post(self.player_endpoint, data=self.create_metadata_body(True),
                                  headers=self.calculate_SNAPPISH()) as response:
            try:
                r: dict = await response.json()
            except (json.JSONDecodeError, KeyError):
                # print("Error: malformed JSON data", r)
                return
            self.player_response.update(r)

    def calculate_SNAPPISH(self):
        """
        Calculate SAPISIDHASH and return header
        Source: https://stackoverflow.com/questions/16907352/reverse-engineering-javascript-behind-google-button
        Algorithm: SHA1(Timestamp + " " + SAPISID + " " + Origin)
        Header: Authorization: SAPISIDHASH timestamp_<SAPISIDHASH>
        """
        timestamp = str(int(time()))
        SAPISID = self.cookie['SAPISID']
        Origin = self.header['X-Origin']
        raw = " ".join([timestamp, SAPISID, Origin])
        _hash = sha1(bytes(raw, encoding="utf8")).hexdigest()
        return {"Authorization": f"SAPISIDHASH {timestamp}_{_hash}"}
        # SAPISIDHASH 1608384358_9c8c91868ac1be1b21a6c62eb769ec04f53d7ffb

    async def fetch(self):
        """
        Fetch the youtube main page to get initialize data
        """
        if self.http is None:
            self.http = aiohttp.ClientSession(headers=self.header, cookie_jar=self.cookie_jar)
        async with self.http.get(self.watch_url, headers=self.header) as response:
            self.watch_html = await response.text()
        self.vid_info_url = video_info_url(
            self.video_id, self.watch_url
        )
        self.js_url = js_url(self.watch_html)
        self.initial_data = initial_data(self.watch_html)
        async with self.http.get(yarl.URL(self.vid_info_url, encoded=True),
                                 headers=self.calculate_SNAPPISH()) as response:
            self.vid_info_raw = await response.text()
        async with self.http.get(self.js_url, headers=self.calculate_SNAPPISH()) as response:
            self.js = await response.text()
        #  Descramble the stream data and build Stream instances.
        self.vid_info = dict(parse_qsl(self.vid_info_raw))
        self.api_ver = self.vid_info['innertube_api_version']
        self.api_key = self.vid_info['innertube_api_key']
        self.api_client_ver = self.vid_info['innertube_context_client_version']
        self.player_config_args = self.vid_info
        self.player_response: playerResponse = playerResponse(json.loads(self.vid_info['player_response']))
        """Fetch metadata and player for first time"""
        self.metadata_endpoint = f"https://www.youtube.com/youtubei/{self.api_ver}/updated_metadata?key={self.api_key}"
        self.heartbeat_endpoint = f"https://www.youtube.com/youtubei/{self.api_ver}/player/heartbeat?alt=json&key={self.api_key}"
        self.player_endpoint = f"https://www.youtube.com/youtubei/{self.api_ver}/player?key={self.api_key}"
        await self.fetch_metadata()
        await self.fetch_heartbeat()
