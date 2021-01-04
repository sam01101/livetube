"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 10:18
    文件:    __main__.py
    文件描述: 
"""
import asyncio
import json
from base64 import b64encode, b64decode
from hashlib import sha1
from time import time
from typing import Optional, Dict, Union
from urllib.parse import parse_qsl, quote, unquote

import aiohttp
import yarl

from .playerResponse import playerResponse
from .util.excpetions import RegexMatchError
from .util.js import js_url, initial_data, video_info_url, query_selector
from .util.regex import regex_search

memberships_root_url = "https://www.youtube.com/paid_memberships?pbj=1"
mainpage_html = "https://www.youtube.com"


def get_text(item: dict) -> str:
    # exection = runs
    if item.get("simpleText"):
        return item.get("simpleText")
    ret = ""
    for cmd in item['runs']:
        ret += cmd['text']
    return ret


def string_escape(s, encoding='utf-8'):
    return (s.encode('latin1')  # To bytes, required by 'unicode-escape'
            .decode('unicode-escape')  # Perform the actual octal-escaping decode
            .encode('latin1')  # 1:1 mapping back to bytes
            .decode(encoding))  # Decode original encoding


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
        self.cookie = cookie
        self.cookie_jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)
        self.cookie_jar.update_cookies(self.cookie)
        self.http: Optional[aiohttp.ClientSession] = None

        # Raw of video info
        self.vid_info_raw: Optional[str] = None
        self.initial_data: Optional[dict] = None
        self.vid_info: Optional[dict] = None
        self.player_config_args: Optional[dict] = None
        self.player_response: Optional[playerResponse] = None
        self.video_type: Optional[str] = None

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

    def concat_run_text(self, text: list) -> str:
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
                data: dict = updateViewershipAction.get("viewCount")
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
                            text = self.concat_run_text(info['viewCount']['runs']) if info['viewCount'].get("runs") else \
                                info['viewCount']['simpleText']
                            self.player_response.videoDetails.liveViewCount = \
                                int(''.join(filter(str.isdigit, text)))
                        # if info.get("isLive"):
                        #     self.player_response.videoDetails.isLive = info['isLive']
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
                        time: int = int(regex_search(r"(\d+) " + p, displayText, 1))
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
        async with self.http.post(self.metadata_endpoint, data=self.create_metadata_body(),
                                  headers=self.calculate_SNAPPISH()) as response:
            if response.status != 200:
                return
            try:
                r: dict = await response.json()
                if not self.continue_id:
                    self.continue_id = r["continuation"]['timedContinuationData']['continuation']
            except (json.JSONDecodeError, KeyError):
                # print("Error: malformed JSON data", r)
                return
            if actions := r.get("actions"):
                self.update_actions(actions)

    async def fetch_heartbeat(self):
        # Threat this like a dymanic update list object
        async with self.http.post(self.heartbeat_endpoint, data=self.create_heartbeat_body(),
                                  headers=self.calculate_SNAPPISH()) as response:
            if response.status != 200:
                return
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
            if response.status != 200:
                return
            try:
                r: dict = await response.json()
            except (json.JSONDecodeError, KeyError):
                # print("Error: malformed JSON data", r)
                return
            self.player_response.update(r)

    async def fetch_video_info(self):
        async with self.http.get(yarl.URL(self.vid_info_url, encoded=True),
                                 headers=self.calculate_SNAPPISH()) as response:
            self.vid_info_raw = await response.text()
        # async with self.http.get(self.js_url, headers=self.calculate_SNAPPISH()) as response:
        #     self.js = await response.text()
        #  Descramble the stream data and build Stream instances.
        self.vid_info = dict(parse_qsl(self.vid_info_raw))
        self.api_ver = self.vid_info['innertube_api_version']
        self.api_key = self.vid_info['innertube_api_key']
        self.api_client_ver = self.vid_info['innertube_context_client_version']
        self.player_config_args = self.vid_info
        self.player_response: playerResponse = playerResponse(json.loads(self.vid_info['player_response']))

    def check_video_type(self):
        if self.initial_data:
            contents = self.initial_data.get('contents', {}).get('twoColumnWatchNextResults', {}) \
                .get('results', {}).get('results', {}).get('contents')
            if contents:
                for content in contents:  # type: dict
                    if videoPrimaryInfoRenderer := content.get('videoPrimaryInfoRenderer'):  # type: dict
                        if badges := videoPrimaryInfoRenderer.get('badges'):
                            for badge in badges:  # type: dict
                                if metadataBadgeRenderer := badge.get('metadataBadgeRenderer'):
                                    video_type = metadataBadgeRenderer['label']
                                    if video_type == "Members only" or video_type == '会员专享':
                                        self.video_type = "Member"
                                    elif video_type == "Unlisted" or video_type == '不公开列出':
                                        self.video_type = "Unlisted"
                                    break

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
        self.check_video_type()
        await self.fetch_video_info()
        """Fetch metadata and player for first time"""
        self.metadata_endpoint = f"https://www.youtube.com/youtubei/{self.api_ver}/updated_metadata?key={self.api_key}"
        self.heartbeat_endpoint = f"https://www.youtube.com/youtubei/{self.api_ver}/player/heartbeat?alt=json&key={self.api_key}"
        self.player_endpoint = f"https://www.youtube.com/youtubei/{self.api_ver}/player?key={self.api_key}"
        await self.fetch_heartbeat()
        await self.fetch_metadata()


class Community:
    def __init__(self,
                 channel_id: str,
                 cookie: dict,
                 header: Optional[Dict[str, Union[str, bool, int]]] = None):

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
        if not cookie.get("SAPISID"):
            print("SAPISID not found, please check your cookie.")
            exit(1)
        self.cookie = cookie
        self.cookie_jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)
        self.cookie_jar.update_cookies(self.cookie)
        self.http: Optional[aiohttp.ClientSession] = None

        # Url setup
        self.community_root_url = f"https://www.youtube.com/channel/{self.channel_id}/community"

        # API setup
        self.api_key: Optional[str] = None

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
        return {"Authorization": f"SAPISIDHASH {timestamp}_{_hash}"}

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
        tabs = raw.get("contents", {}).get('twoColumnBrowseResultsRenderer', {}).get("tabs")
        raw_datas: list = []
        if tabs:
            for tab in tabs:  # type: dict
                if tab.get("tabRenderer", {}).get("title") == "Community":
                    if tab['tabRenderer']['selected']:
                        contents: dict = \
                            tab['tabRenderer']['content']['sectionListRenderer']['contents'][0]['itemSectionRenderer'][
                                'contents']
                        for content in contents:
                            data: dict = content['backstagePostThreadRenderer']['post']['backstagePostRenderer']
                            raw_data = {
                                "id": data['postId'],
                                "author": {
                                    "name": get_text(data['authorText'])
                                },
                                "text": get_text(data['contentText']) if data.get("contentText") else None,
                                "type": "public"
                            }
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
                                if pollRenderer := backstageAttachment.get('pollRenderer'):  # type: dict
                                    raw_data['votes'] = []
                                    for choice in pollRenderer['choices']:
                                        raw_data['votes'].append(f"⭕ {get_text(choice['text'])}")
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
        if self.http is None:
            self.http = aiohttp.ClientSession(headers=self.header, cookie_jar=self.cookie_jar)
        async with self.http.get(self.community_root_url,
                                 headers=self.calculate_SNAPPISH()) as response:
            self.community_html = await response.text()
        self.api_key = regex_search(r"\"INNERTUBE_API_KEY\":\"([A-Za-z0-9_\-]+)\",", self.community_html, 1)
        self.post_url += self.api_key


class Membership:
    def __init__(self,
                 cookie: dict,
                 header: Optional[Dict[str, Union[str, bool, int]]] = None):

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
        if not cookie.get("SAPISID"):
            print("SAPISID not found, please check your cookie.")
            exit(1)
        self.cookie = cookie
        self.cookie_jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)
        self.cookie_jar.update_cookies(self.cookie)
        self.http: Optional[aiohttp.ClientSession] = None

        # API setup
        self.api_key: Optional[str] = None
        self.__ID_TOKEN__: Optional[str] = None

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
        return {"Authorization": f"SAPISIDHASH {timestamp}_{_hash}"}

    def create_query_body(self, continuation_key: str) -> str:
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

    async def parse_membership_info(self, memberships_raw: list, key_raw: list) -> list:
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
                        info['channel_id']: str = channel_id_raw \
                            .replace(b"\n\x1c\x08\x03\x12\x18", b"") \
                            .replace(b"\x18\x032\x15R\x13FEmembership_detail", b"") \
                            .decode("utf8")
                    if test_status == "See Perks" or test_status == "Renew":
                        break
            return info

        return await asyncio.gather(*(_fetch_status(steps, data) for steps, data in enumerate(memberships_raw)))

    async def fetch(self):
        if not self.http:
            self.http = aiohttp.ClientSession(headers=self.header, cookie_jar=self.cookie_jar)
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
