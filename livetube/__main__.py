"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 10:18
    文件:    __main__.py
    文件描述: 
"""
import asyncio
import json
import re
from asyncio import AbstractEventLoop
from base64 import b64encode, b64decode
from hashlib import sha1
from typing import Optional, Dict, Union
from urllib.parse import parse_qsl, quote, unquote

import aiohttp
import yarl
from time import time

from .playerResponse import playerResponse
from .util.excpetions import RegexMatchError, NetworkError
from .util.js import initial_data, video_info_url, query_selector
from .util.regex import regex_search

memberships_root_url = "https://www.youtube.com/paid_memberships?pbj=1"
mainpage_html = "https://www.youtube.com"
image_regex = re.compile(r"(https://yt3\.ggpht\.com/[A-Za-z0-9\-_]+)=?.+")


def get_text(item: dict) -> str:
    # exection = runs
    if item.get("simpleText"):
        return item.get("simpleText")
    ret = ""
    for cmd in item['runs']:
        ret += cmd['text']
    return ret


def string_escape(s, encoding='utf-8') -> str:
    return (s.encode('latin1')  # To bytes, required by 'unicode-escape'
            .decode('unicode-escape')  # Perform the actual octal-escaping decode
            .encode('latin1')  # 1:1 mapping back to bytes
            .decode(encoding))  # Decode original encoding


class Video:
    def __init__(self,
                 video_id: str,
                 cookie=None,
                 header: Optional[Dict[str, Union[str, bool, int]]] = None,
                 loop: Optional[AbstractEventLoop] = None):
        """
        創造一個Youtube obj

        :param video_id: Video ID, 可以是网址
        :param cookie: Cookie
        :param header: 额外的Header
        """

        # Pre fetch
        if cookie is None:
            cookie = {}
        self.watch_html: Optional[str] = None
        self.age_restricted: Optional[bool] = None

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
        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.cookie = cookie
        cookie_jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False, loop=self.loop)
        cookie_jar.update_cookies(self.cookie)
        self.http: aiohttp.ClientSession = aiohttp.ClientSession(
            headers=self.header, cookie_jar=cookie_jar, loop=self.loop)

        # Raw of video info
        self.vid_info_raw: Optional[str] = None
        self.initial_data: Optional[dict] = None
        self.vid_info: Optional[dict] = None
        self.player_config_args: Optional[dict] = None
        self.player_response: Optional[playerResponse] = None
        self.video_type: Optional[str] = None
        self.isPremiere: Optional[bool] = None

        #  API used to fetch metadata
        self.api_ver: str = "v1"
        self.api_key: Optional[str] = None
        self.api_client_ver: str = "2.20770101.00.00"
        self.api_client_name: str = "WEB"
        self.metadata_endpoint: str = "https://www.youtube.com/youtubei/v1/updated_metadata?key="
        # URL used to fetch heartbeat and player
        self.heartbeat_endpoint: str = "https://www.youtube.com/youtubei/v1/player/heartbeat?alt=json&key="
        self.player_endpoint: str = "https://www.youtube.com/youtubei/v1/player?key="
        """Key for next fetching"""
        self.continue_id: Optional[str] = None

    def update_cookie(self, cookie: dict):
        self.cookie = cookie
        self.http.cookie_jar.clear()
        self.http.cookie_jar.update_cookies(cookie)

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

    def update_actions(self, actions: list):
        for action in actions:  # type: dict
            if info := query_selector(action, "updateViewershipAction/viewCount/videoViewCountRenderer"):
                if viewCount := info.get("viewCount"):
                    self.player_response.videoDetails.liveViewCount = \
                        int(''.join(filter(str.isdigit, get_text(viewCount))))
                if shortViewCount := info.get("extraShortViewCount"):
                    self.player_response.videoDetails.liveShortViewCount = get_text(shortViewCount)
            elif updateToggleButtonTextAction := action.get("updateToggleButtonTextAction"):
                """Like/Dislike button update"""
                buttonId = updateToggleButtonTextAction['buttonId']
                button_type = "shortLikeCount" if buttonId == "TOGGLE_BUTTON_ID_TYPE_LIKE" else "shortDislikeCount"
                setattr(self.player_response.videoDetails, button_type,
                        get_text(updateToggleButtonTextAction['defaultText']))
            elif updateDateTextAction := action.get("updateDateTextAction"):
                pattern = {
                    "seconds": "秒",
                    "minutes": "分钟",
                    "hours": "小时",
                    "days": "天",
                    "years": "年",
                }
                displayText = get_text(updateDateTextAction['dateText'])
                for p, name in pattern.items():
                    try:
                        stream_time = int(regex_search(r"(\d+) " + p, displayText, 1))
                        self.player_response.videoDetails.startedSince = f"{stream_time} {name}前"
                        break
                    except RegexMatchError:
                        continue
            elif updateTitleAction := action.get("updateTitleAction"):
                title: str = get_text(updateTitleAction['title'])
                if self.player_response.videoDetails.title != title:
                    self.player_response.videoDetails.title = title

    async def fetch_metadata(self):
        async with self.http.post(self.metadata_endpoint, data=self.create_metadata_body(),
                                  headers=self.calculate_SNAPPISH()) as response:
            try:
                r: dict = await response.json()
                if r.get("error"):
                    raise NetworkError(f"{r['error']['code']} {r['error']['message']}")
                if not self.continue_id:
                    if continue_id := query_selector(r, "continuation/timedContinuationData/continuation"):
                        self.continue_id = continue_id
            except (json.JSONDecodeError, KeyError) as e:
                raise NetworkError("Malformed JSON error") from e
            if actions := r.get("actions"):
                self.update_actions(actions)

    async def fetch_heartbeat(self):
        # Threat this like a dynamic update list object
        async with self.http.post(self.heartbeat_endpoint, data=self.create_heartbeat_body(),
                                  headers=self.calculate_SNAPPISH()) as response:
            try:
                r: dict = await response.json()
                if r.get("error"):
                    raise NetworkError(f"{r['error']['code']} {r['error']['message']}")
            except (json.JSONDecodeError, KeyError) as e:
                raise NetworkError("Malformed JSON error") from e
            self.player_response.update(r)

    async def fetch_player(self):
        """Get the player"""
        async with self.http.post(self.player_endpoint, data=self.create_metadata_body(True),
                                  headers=self.calculate_SNAPPISH()) as response:
            try:
                r: dict = await response.json()
                if r.get("error"):
                    raise NetworkError(f"{r['error']['code']} {r['error']['message']}")
            except (json.JSONDecodeError, KeyError) as e:
                raise NetworkError("Malformed JSON error") from e
            self.player_response.update(r)

    async def fetch_video_info(self):
        async with self.http.get(yarl.URL(self.vid_info_url, encoded=True),
                                 headers=self.calculate_SNAPPISH()) as response:
            if response.status != 200:
                try:
                    r: dict = await response.json()
                    if r.get("error"):
                        raise NetworkError(f"{r['error']['code']} {r['error']['message']}")
                except json.JSONDecodeError:
                    pass
            self.vid_info_raw = await response.text()
        self.vid_info = dict(parse_qsl(self.vid_info_raw))
        self.api_ver = self.vid_info['innertube_api_version']
        self.api_key = self.vid_info['innertube_api_key']
        self.api_client_ver = self.vid_info['innertube_context_client_version']
        self.player_config_args = self.vid_info
        self.player_response: playerResponse = playerResponse(json.loads(self.vid_info['player_response']))

    def check_video_type(self):
        if self.initial_data:
            pattern = "contents/twoColumnWatchNextResults/results/results/contents/" \
                      "?/videoPrimaryInfoRenderer/badges/0/metadataBadgeRenderer/label"

            if video_type := query_selector(self.initial_data, pattern):  # type: list
                video_tag: str = video_type[0]
                if video_tag in ["Members only", '会员专享']:
                    self.video_type = "Member"
                elif video_tag in ["Unlisted", '不公开列出']:
                    self.video_type = "Unlisted"

    def check_premiere(self):
        date_pattern = "contents/twoColumnWatchNextResults/results/results/contents/" \
                       "?/videoPrimaryInfoRenderer/dateText"
        is_premiere = False
        if self.initial_data:
            is_premiere = query_selector(self.initial_data, date_pattern)
        if self.player_response.playabilityStatus and \
                self.player_response.playabilityStatus.reason.find("Premiere") != -1 or is_premiere:
            if is_premiere:
                if get_text(is_premiere[0]).find("首播") == -1:
                    return
            self.isPremiere = True

    def calculate_SNAPPISH(self):
        """
        Calculate SAPISIDHASH and return header
        Source: https://stackoverflow.com/questions/16907352/reverse-engineering-javascript-behind-google-button
        Algorithm: SHA1(Timestamp + " " + SAPISID + " " + Origin)
        Header: Authorization: SAPISIDHASH timestamp_<SAPISIDHASH>
        """
        if not self.cookie:
            return self.header
        timestamp = str(int(time()))
        SAPISID = self.cookie['SAPISID']
        Origin = self.header['X-Origin']
        raw = " ".join([timestamp, SAPISID, Origin])
        _hash = sha1(bytes(raw, encoding="utf8")).hexdigest()
        new_header = self.header.copy()
        new_header["Authorization"] = f"SAPISIDHASH {timestamp}_{_hash}"
        return new_header

    async def fetch(self):
        """
        Fetch the youtube main page to get initialize data
        """
        async with self.http.get(self.watch_url, headers=self.header) as response:
            if response.status != 200:
                try:
                    r: dict = await response.json()
                    if r.get("error"):
                        raise NetworkError(f"{r['error']['code']} {r['error']['message']}")
                except json.JSONDecodeError:
                    pass
            self.watch_html = await response.text()
        self.vid_info_url = video_info_url(
            self.video_id, self.watch_url
        )
        self.initial_data = initial_data(self.watch_html)
        self.check_video_type()
        await self.fetch_video_info()
        """Fetch metadata and player for first time"""
        self.metadata_endpoint = f"https://www.youtube.com/youtubei/{self.api_ver}/updated_metadata?key={self.api_key}"
        self.heartbeat_endpoint = f"https://www.youtube.com/youtubei/{self.api_ver}/player/heartbeat?alt=json&key={self.api_key}"
        self.player_endpoint = f"https://www.youtube.com/youtubei/{self.api_ver}/player?key={self.api_key}"
        await self.fetch_heartbeat()
        await self.fetch_metadata()
        self.check_premiere()


Youtube = Video


class Community:
    def __init__(self,
                 channel_id: str,
                 cookie=None,
                 header: Optional[Dict[str, Union[str, bool, int]]] = None,
                 loop: Optional[AbstractEventLoop] = None):

        if cookie is None:
            cookie = {}
        self.channel_id = channel_id
        self.community_html: Optional[str] = None
        self.post_url: Optional[str] = "https://www.youtube.com/youtubei/v1/browse?key="
        self.posts: list = []

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
        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.cookie = cookie
        cookie_jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)
        cookie_jar.update_cookies(self.cookie)
        self.http: aiohttp.ClientSession = aiohttp.ClientSession(
            headers=self.header, cookie_jar=cookie_jar, loop=self.loop)

        # Url setup
        self.community_root_url = f"https://www.youtube.com/channel/{self.channel_id}/community"

        # API setup
        self.api_key: Optional[str] = None

    def update_cookie(self, cookie: dict):
        self.cookie = cookie
        self.http.cookie_jar.clear()
        self.http.cookie_jar.update_cookies(cookie)

    def calculate_SNAPPISH(self) -> dict:
        """
        Calculate SAPISIDHASH and return header
        Source: https://stackoverflow.com/questions/16907352/reverse-engineering-javascript-behind-google-button
        Algorithm: SHA1(Timestamp + " " + SAPISID + " " + Origin)
        Header: Authorization: SAPISIDHASH timestamp_<SAPISIDHASH>
        """
        if not self.cookie:
            return self.header
        timestamp = str(int(time()))
        SAPISID = self.cookie['SAPISID']
        Origin = self.header['X-Origin']
        raw = " ".join([timestamp, SAPISID, Origin])
        _hash = sha1(bytes(raw, encoding="utf8")).hexdigest()
        new_header = self.header.copy()
        new_header["Authorization"] = f"SAPISIDHASH {timestamp}_{_hash}"
        return new_header

    def create_body(self) -> str:
        """Create a body use to fetch the API"""
        body = {
            "context": {
                "client": {
                    "hl": "en_US",
                    "isInternal": True,
                    "clientName": "WEB",
                    "clientVersion": "2.19700101.00.00"
                }
            },
            "browseId": self.channel_id,
            "params": quote(b64encode(b"\x12\tcommunity"))
        }
        return json.dumps(body)

    async def parse_posts(self, raw: dict) -> bool:
        raw_datas: list = []
        if tabs := query_selector(raw, "contents/twoColumnBrowseResultsRenderer/tabs"):
            for tab in tabs:  # type: dict
                if query_selector(tab, "tabRenderer/title") == "Community":
                    if query_selector(tab, "tabRenderer/selected"):
                        contents: dict = query_selector(tab,
                                                        "tabRenderer/content/sectionListRenderer/contents/0/itemSectionRenderer/contents")

                        def _create_post(data):
                            def _attach_media(data, raw_data):
                                if data.get("sponsorsOnlyBadge"):
                                    raw_data['type'] = "member"
                                if backstageAttachment := data.get('backstageAttachment'):  # type: dict
                                    if videoRenderer := backstageAttachment.get('videoRenderer'):  # type: dict
                                        thumbnails = videoRenderer['thumbnail']['thumbnails']
                                        raw_data['video'] = {
                                            "video_id": videoRenderer.get('videoId'),
                                            'thumbnail': thumbnails[len(thumbnails) - 1]['url'],
                                            "title": get_text(videoRenderer['title'])
                                        }
                                    if backstageImageRenderer := backstageAttachment.get(
                                            'backstageImageRenderer'):  # type: dict
                                        thumbnails = backstageImageRenderer['image']['thumbnails']
                                        raw_data['image'] = thumbnails[len(thumbnails) - 1]['url']
                                        if image_match := image_regex.match(raw_data['image']):
                                            image_orig_url = image_match.group()
                                            raw_data['image'] = image_orig_url + "=s0"
                                    if pollRenderer := backstageAttachment.get('pollRenderer'):  # type: dict
                                        raw_data['votes'] = []
                                        for choice in pollRenderer['choices']:
                                            raw_data['votes'].append(f"⭕ {get_text(choice['text'])}")
                                return raw_data

                            raw_data = {
                                "id": data['postId'],
                                "author": {
                                    "name": get_text(data['authorText'])
                                },
                                "text": get_text(data['contentText']) if data.get("contentText") else None,
                                "type": "public"
                            }
                            return _attach_media(data, raw_data)

                        for content in contents:
                            data: dict = query_selector(content,
                                                        "backstagePostThreadRenderer/post/backstagePostRenderer")
                            if not data:
                                # sharedPost?
                                data: dict = query_selector(content,
                                                            "backstagePostThreadRenderer/post/sharedPostRenderer")
                                if data:
                                    raw_data = {
                                        "id": data['postId'],
                                        "author": {
                                            "name": get_text(data['displayName'])
                                        },
                                        "sharedPost": _create_post(data['originalPost']['backstagePostRenderer']),
                                        "text": get_text(data['content']) if data.get("content") else None,
                                        "type": "public"
                                    }
                                else:
                                    print("Malformed post content")
                                    continue
                            else:
                                raw_data = _create_post(data)
                            raw_datas.append(raw_data)
                        break
                    else:
                        print("Unexpected: Didn't select community selection")
                        return False
            self.posts = raw_datas
            return True

    async def fetch_post(self) -> bool:
        post_response: Optional[dict] = None
        async with self.http.post(self.post_url,
                                  headers=self.calculate_SNAPPISH(),
                                  data=self.create_body()) as response:
            if response.status != 200:
                print(f"Invaild response status code (Code {response.status})")
                print(await response.text())
                return False
            try:
                post_response = await response.json()
            except json.JSONDecodeError:
                print(f"Malformated post response", post_response)
                return False
        if not post_response:
            print("Cannot get post resposne")
            return False
        return await self.parse_posts(post_response)

    async def fetch(self):
        async with self.http.get(self.community_root_url,
                                 headers=self.calculate_SNAPPISH()) as response:
            self.community_html = await response.text()
        self.api_key = regex_search(r"\"INNERTUBE_API_KEY\":\"([A-Za-z0-9_\-]+)\",", self.community_html, 1)
        self.post_url += self.api_key


class Membership:
    def __init__(self,
                 cookie: dict,
                 header: Optional[Dict[str, Union[str, bool, int]]] = None,
                 loop: Optional[AbstractEventLoop] = None):
        if not loop:
            self.loop = asyncio.get_event_loop()

        self.membership_status_url = "https://www.youtube.com/youtubei/v1/browse?key="
        self.memberships_json: Optional[dict] = None
        self.memberships: list = []

        # json pattern
        self.membership_pattern = "?/response/contents/twoColumnBrowseResultsRenderer/tabs/" \
                                  "?/tabRenderer/content/sectionListRenderer/contents/" \
                                  "?/itemSectionRenderer/contents/" \
                                  "?/cardItemContainerRenderer/baseRenderer/cardItemRenderer/" \
                                  "headingRenderer/cardItemTextWithImageRenderer/" \
                                  "textCollectionRenderer/0/cardItemTextCollectionRenderer"
        self.continuation_pattern = "?/response/contents/twoColumnBrowseResultsRenderer/tabs/" \
                                    "?/tabRenderer/content/sectionListRenderer/contents/" \
                                    "?/itemSectionRenderer/contents/" \
                                    "?/cardItemContainerRenderer/onClickCommand" \
                                    "/continuationCommand/token"
        self.channel_id_pattern = "onResponseReceivedActions/?/appendContinuationItemsAction/continuationItems/" \
                                  "?/itemSectionRenderer/contents/" \
                                  "?/cardItemRenderer/" \
                                  "additionalInfoRenderer/cardItemActionsRenderer/" \
                                  "primaryButtonRenderer/buttonRenderer"

        # Header
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
                          " Chrome/87.0.4280.88 Safari/537.36",
            "X-Origin": "https://www.youtube.com"
        }
        if header:
            self.header.update(header)

        # Client setup
        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop
        if not cookie.get("SAPISID"):
            raise ValueError("SAPISID not found, please check your cookie.")
        self.cookie = cookie
        self.cookie_jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False, loop=self.loop)
        self.cookie_jar.update_cookies(self.cookie)
        self.http: aiohttp.ClientSession = aiohttp.ClientSession(
            headers=self.header, cookie_jar=self.cookie_jar, loop=self.loop)

        # API setup
        self.api_key: Optional[str] = None
        self.__ID_TOKEN__: Optional[str] = None

    def update_cookie(self, cookie: dict):
        if not cookie.get("SAPISID"):
            raise ValueError("SAPISID not found, please check your cookie.")
        self.cookie = cookie
        self.http.cookie_jar.clear()
        self.http.cookie_jar.update_cookies(cookie)

    def calculate_SNAPPISH(self) -> dict:
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
        new_header = self.header.copy()
        new_header["Authorization"] = f"SAPISIDHASH {timestamp}_{_hash}"
        return new_header

    @staticmethod
    def create_query_body(continuation_key: str) -> str:
        return json.dumps({
            "context": {
                "client": {
                    "hl": "en",
                    "gl": "en",
                    "isInternal": True,
                    "clientName": "WEB",
                    "clientVersion": "2.20201220.08.00"
                }
            },
            "continuation": continuation_key
        })

    async def parse_membership_info(self, memberships_raw: list, key_raw: list) -> tuple:
        for data in key_raw.copy():  # type: int, str
            b64_orig = unquote(data).encode('ascii')
            b64_dec_byte = b64decode(b64_orig)
            if b64_dec_byte.find(b"memberships_and_purchases") != -1:
                key_raw.remove(data)
                break

        async def _fetch_status(steps: int, data: dict) -> dict:
            data: list = data["textRenderers"]
            vtuber_name = get_text(data[0]["cardItemTextRenderer"]['text'])
            perk_status = get_text(data[1]["cardItemTextRenderer"]['text'])
            info = {
                "name": vtuber_name,
                "status": perk_status
            }
            async with self.http.post(self.membership_status_url, headers=self.calculate_SNAPPISH(),
                                      data=self.create_query_body(key_raw[steps])) as response:
                membership_status = await response.json()
                status_raw = query_selector(membership_status, self.channel_id_pattern)
                for status in status_raw:
                    test_status = get_text(status['text'])
                    if test_status == "See Perks":  # type: dict
                        navigationEndpoint = status.get("navigationEndpoint")
                        info['expired'] = False
                        info['channel_id']: str = navigationEndpoint['browseEndpoint']['browseId']
                    elif test_status == "Renew":  # type: dict
                        serviceEndpoint = status.get("serviceEndpoint")
                        info['expired'] = True
                        channel_id_raw = b64decode(
                            unquote(serviceEndpoint['ypcGetOffersEndpoint']['params']).encode('ascii'))
                        channel_id_raw = channel_id_raw.decode("utf8")
                        if ((channel_id_start := channel_id_raw.find("UC")) != -1 or
                                (channel_id_start := channel_id_raw.find("HC"))):
                            info['channel_id']: str = channel_id_raw[channel_id_start:24]
                    elif test_status == "Update payment method":
                        serviceEndpoint = status.get("serviceEndpoint")
                        info['paused'] = True
                        channel_id_raw = b64decode(
                            unquote(
                                serviceEndpoint['ypcFixInstrumentEndpoint']['serializedFixFopLoggingParams']).encode(
                                'ascii'))
                        channel_id_raw = channel_id_raw.decode("utf8")
                        if ((channel_id_start := channel_id_raw.find("UC")) != -1 or
                                (channel_id_start := channel_id_raw.find("HC"))):
                            info['channel_id']: str = channel_id_raw[channel_id_start:24]
                    if test_status in ("See Perks", "Renew", "Update payment method"):
                        break
            return info

        return await asyncio.gather(*(_fetch_status(steps, data) for steps, data in enumerate(memberships_raw)))

    async def fetch(self):
        if not self.api_key:
            async with self.http.get(mainpage_html) as response:
                mainpage_url = await response.text()
                self.api_key = regex_search(r"\"INNERTUBE_API_KEY\":\"([A-Za-z0-9_\-]+)\",", mainpage_url, 1)
                self.__ID_TOKEN__ = string_escape(
                    regex_search(r"\"ID_TOKEN\":\"([A-Za-z0-9_\\\-=\/\+]+)\",", mainpage_url, 1))
                self.header.update({
                    "X-YouTube-Client-Name": "1",
                    "X-YouTube-Client-Version": "2.20770101.08.00",
                    "X-Youtube-Identity-Token": self.__ID_TOKEN__
                })
                self.membership_status_url += self.api_key

        async with self.http.get(memberships_root_url, headers=self.header) as response:
            self.memberships_json = await response.json()
        memberships_raw = query_selector(self.memberships_json, self.membership_pattern)
        key_raw = query_selector(self.memberships_json, self.continuation_pattern)
        self.memberships = await self.parse_membership_info(memberships_raw, key_raw)
