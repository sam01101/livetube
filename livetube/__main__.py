"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 10:18
    文件:    __main__.py
    文件描述: 
"""

# General
import asyncio
import warnings
import json
from asyncio import AbstractEventLoop
# Parsing
import re
from base64 import b64encode, b64decode
from typing import Optional, Dict, Union, List
from urllib.parse import parse_qsl, quote, unquote, quote_plus
from util.player import get_ytplayer_resp
from membership_pb3 import ContinuationCommand, ContinuationCommandEntry
from util.parser import ScriptTaker

# Networking
import aiohttp
import yarl

# Cache for YouTube
from util.cipher import Cipher
from util.cache import shared_tcp_pool, js_cache_v2, yt_internal_api, get_yt_client_info, default_header, yt_root_url

# Models
from .memberShips import Member
from .communityPosts import Post, SharedPost
from .playerResponse import playerResponse

# Utils
from .util import player
from .util.exceptions import RegexMatchError, NetworkError, HTMLParseError, ExtractError
from .util.js import initial_data, video_info_url, query_selector, dict_search
from .util.regex import regex_search
from .utils import time_map, get_text, string_to_int, http_request, logger, calculate_SNAPPISH

image_regex = re.compile(r"(yt3\.ggpht\.com/.+?)=.+")


class Video:
    def __init__(self,
                 video_id: str,
                 cookie=None,
                 header: Optional[Dict[str, Union[str, bool, int]]] = None,
                 loop: Optional[AbstractEventLoop] = None):
        """
        Create a video object

        :param video_id: Video ID, can be url
        :param cookie:   Cookie
        :param header:   Extra header
        """

        # Not impl yet
        self.age_restricted: bool = False

        # Special settings
        # This will only effect updateDateTextAction
        self.display_chinese = False

        # js
        self.js_url: Optional[str] = None

        # Video ID
        if video_id.startswith("http"):
            video_id = regex_search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", video_id, group=1)
        else:
            if not (match := re.match(r"([0-9A-Za-z_-]{11})", video_id)):
                raise ExtractError("Invalid video id")
            else:
                video_id = match.group(1)
        self.video_id = video_id
        self.short_url = f"https://youtu.be/{self.video_id}"
        self.watch_url = f"{yt_root_url}/watch?v={self.video_id}"
        self.vid_info_url: Optional[str] = None

        # Header
        self.header = default_header
        if header:
            self.header.update(header)

        # Client setup
        self._loop = loop or asyncio.get_event_loop()
        if cookie is None:
            cookie = dict()
        cookie.update({"PREF": "hl=en"})
        self.cookie = cookie

        # http
        client_id = hash(self._loop)
        if not shared_tcp_pool.get(client_id):
            shared_tcp_pool[client_id] = aiohttp.TCPConnector(loop=self._loop, ttl_dns_cache=60,
                                                              force_close=True, enable_cleanup_closed=True, limit=0)
        self._pool = shared_tcp_pool[client_id]

        """Raw of video info"""
        self.player_response: Optional[playerResponse] = None
        self.video_type: str = ""
        self.isPremiere: bool = False

        """Key for next data requesting"""
        self._continue_id: str = ""
        self._heartbeat_seq_number: int = 0

    # Logger

    def debug(self, message: str):
        logger.debug(f"[{self.video_id}] {message}")

    def info(self, message: str):
        logger.info(f"[{self.video_id}] {message}")

    def warn(self, message: str):
        logger.warning(f"[{self.video_id}] {message}")

    def error(self, message: str):
        logger.error(f"[{self.video_id}] {message}")

    # ======

    def update_cookie(self, cookie: dict):
        """更新 Cookie"""
        cookie.update({"PREF": "hl=en"})
        self.cookie = cookie

    async def get_anim_thumbnail(self) -> str:
        """
        获取动态缩图

        :raise NetworkError: Problem while getting thumbnail
        :return str: Url of thumbnail
        """
        self.debug("Fetching animation thumbnail link")
        pattern = ("contents/twoColumnSearchResultsRenderer/primaryContents/sectionListRenderer/contents/?/"
                   f"itemSectionRenderer/contents/?/videoRenderer/videoId:{self.video_id}")
        endpoint = f"{yt_internal_api.endpoint}/{yt_internal_api.version}/search?key={yt_internal_api.key}"
        if not yt_internal_api.key:
            # Fallback to html mode
            endpoint = f"{yt_root_url}/results?search_query={quote_plus(self.watch_url)}"
            async with http_request(self._pool, url=endpoint, header=self.header, cookie=self.cookie) as response:
                html_js = ScriptTaker(await response.text()).scripts
                yt_internal_api.update_html(player.get_ytplayer_setconfig(html_js))
                resp_json = initial_data(html_js)
        else:
            async with http_request(self._pool, "POST", url=endpoint, json_data={
                "context": {
                    "client": get_yt_client_info()
                },
                "query": self.watch_url
            }, header=calculate_SNAPPISH(self.cookie, self.header), cookie=self.cookie) as response:
                if response is False:
                    # Fallback
                    yt_internal_api.key = ""
                    return await self.get_anim_thumbnail()
                if response.content_type == "text/html":
                    self.error("Failed to query video search")
                    raise NetworkError
                resp_json = await response.json()
        if test := query_selector(resp_json, pattern):
            video_info = test[0]
            if thumbnail := video_info.get("richThumbnail"):
                return thumbnail['movingThumbnailRenderer']['movingThumbnailDetails']['thumbnails'][0]['url']
            else:
                self.info("No preview animation thumbnail")
                return ""
        else:
            self.error("Failed to locate thumbnail location")
            raise NetworkError

    def _create_metadata_body(self, force_video_id: bool = False) -> dict:
        """Create a metadata body"""
        param_cond = not force_video_id and self._continue_id
        return {
            "context": {
                "client": get_yt_client_info()
            },
            ("continuation" if param_cond else "videoId"): (
                self._continue_id if param_cond else self.video_id
            )
        }

    # metadata update
    def _update_actions(self, actions: list):
        for action in actions:  # type: dict
            if info := query_selector(action, "updateViewershipAction/viewCount/videoViewCountRenderer"):
                if viewCount := info.get("viewCount"):
                    self.player_response.videoDetails.liveViewCount = int(
                        ''.join(filter(str.isdigit, get_text(viewCount))))
                if shortViewCount := info.get("extraShortViewCount"):
                    self.player_response.videoDetails.liveShortViewCount = get_text(shortViewCount)
            elif updateToggleButtonTextAction := action.get("updateToggleButtonTextAction"):
                """Like/Dislike button update"""
                buttonId = updateToggleButtonTextAction['buttonId']
                button_type = "shortLikeCount" if buttonId == "TOGGLE_BUTTON_ID_TYPE_LIKE" else "shortDislikeCount"
                count_text = get_text(updateToggleButtonTextAction['defaultText'])
                if count_text.lower() in ("like", "dislike"):
                    count_text = "?"
                setattr(self.player_response.videoDetails, button_type, count_text)
            elif updateDateTextAction := action.get("updateDateTextAction"):
                displayText = get_text(updateDateTextAction['dateText'])
                if not self.display_chinese:
                    self.player_response.videoDetails.startedSince = displayText
                    continue
                for pattern, name in time_map.items():
                    try:
                        stream_time = int(regex_search(r"(\d+) " + pattern, displayText, 1))
                        self.player_response.videoDetails.startedSince = f"{stream_time} {name}前"
                        break
                    except RegexMatchError:
                        continue
            elif updateTitleAction := action.get("updateTitleAction"):
                title: str = get_text(updateTitleAction['title'])
                if self.player_response.videoDetails.title != title:
                    self.player_response.videoDetails.title = title

    async def fetch_metadata(self):
        """更新直播信息"""
        if not self.player_response:
            return
        self.debug("Fetching metadata")
        endpoint = (f"{yt_internal_api.endpoint}/{yt_internal_api.version}/"
                    f"updated_metadata?key={yt_internal_api.key}")
        async with http_request(self._pool, "POST", endpoint, json_data=self._create_metadata_body(),
                                header=calculate_SNAPPISH(self.cookie, self.header), cookie=self.cookie) as response:
            if response is False:
                # Fallback
                return await self._fetch_html()
            if response.content_type == "text/html":
                self.error("Failed to fetch metadata")
                raise NetworkError
            resp_json: dict = await response.json()
            if ((continue_id := query_selector(resp_json, "continuation/timedContinuationData/continuation"))
                    and continue_id != self._continue_id):
                self._continue_id = continue_id
            if update := resp_json.get('responseContext'):
                self.player_response.responseContext.update(update)
            if actions := resp_json.get("actions"):
                self._update_actions(actions)

    async def fetch_heartbeat(self):
        """更新直播心跳"""
        if not self.player_response:
            return
        # Threat this like a dynamic update list object
        self.debug("Fetching heartbeat")
        endpoint = (f"{yt_internal_api.endpoint}/{yt_internal_api.version}/"
                    f"player/heartbeat?alt=json&key={yt_internal_api.key}")
        async with http_request(self._pool, "POST", endpoint, json_data={
            "context": {
                "client": get_yt_client_info()
            },
            "heartbeatRequestParams": {
                "heartbeatChecks": [
                    "HEARTBEAT_CHECK_TYPE_LIVE_STREAM_STATUS"
                ]
            },
            "sequenceNumber": self._heartbeat_seq_number,
            "videoId": self.video_id
        }, header=calculate_SNAPPISH(self.cookie, self.header), cookie=self.cookie) as response:
            if response is False:
                # Fallback
                return await self._fetch_html()
            if response.content_type == "text/html":
                self.error("Failed to fetch heartbeat")
                raise NetworkError
            self._heartbeat_seq_number += 1
            last_status = self.player_response.playabilityStatus.status
            self.player_response.update(await response.json())
            if (
                    last_status == "OK" and self.player_response.playabilityStatus.status != last_status or
                    last_status != "OK" and self.player_response.playabilityStatus.status == "OK"
            ):
                """Refreshing whole page is better than only player"""
                # await self.fetch_player()
                await self._fetch_json()

    async def fetch_player(self):
        """
        使用 player 刷新视频信息

        :raise NetworkError: 网络错误
        """
        if not self.player_response:
            return
        self.debug("Downloading player")
        endpoint = f"{yt_internal_api.endpoint}/{yt_internal_api.version}/player?key={yt_internal_api.key}"
        async with http_request(self._pool, "POST", endpoint, json_data=self._create_metadata_body(True),
                                header=calculate_SNAPPISH(self.cookie, self.header), cookie=self.cookie) as response:
            if response is False:
                # Fallback
                return await self._fetch_html()
            if response.content_type == "text/html":
                self.error("Failed to download player")
                raise NetworkError
            if _player := self.player_response:
                await self._check_cipher()
                _player.update(await response.json())

    async def _check_cipher(self):
        """Update cipher to prevent being removed by cache"""
        if not self.js_url:
            self.warn("js_url not found")
            return
        elif not js_cache_v2[self.js_url]:
            self.info("Downloading base js")
            async with http_request(self._pool, url=self.js_url, header=self.header) as response:
                if response.status == 200:
                    js_cache_v2[self.js_url] = Cipher(js=await response.text())
                else:
                    raise HTMLParseError("Cipher parse failed")

    async def _fetch_video_info(self):
        """
        Deprecated: Replaced by _fetch_json
        """
        warnings.warn("This method has deprecated since livetube 2.0, "
                      "and scheduled for removal in livetube 3.0.",
                      DeprecationWarning, stacklevel=2)
        self.info("Downloading video info")
        async with http_request(self._pool, url=yarl.URL(self.vid_info_url, encoded=True),
                                header=calculate_SNAPPISH(self.cookie, self.header), cookie=self.cookie) as response:
            if response is False:
                # Fallback
                return await self._fetch_html()
            if response.content_type == "text/html":
                self.error(f"Failed to fetch video info | Wrong Content-Type {response.content_type}")
                raise NetworkError
            vid_info = dict(parse_qsl(await response.text()))
            yt_internal_api.update({
                "key": vid_info['innertube_api_key'],
                "version": vid_info['innertube_api_version'],
                "client_name": vid_info['c'],
                "client_version": vid_info['cver'],
                "client_browser_name": vid_info['cbr'],
                "client_browser_version": vid_info['cbrver']
            })
        resp = json.loads(vid_info['player_response'])
        await self._check_cipher()
        if self.player_response:
            self.player_response.update(resp)
        else:
            self.player_response = playerResponse(resp, self.js_url)

    def _check_video_type(self, _initial_data: dict):
        pattern = ("contents/twoColumnWatchNextResults/results/results/contents/"
                   "?/videoPrimaryInfoRenderer/badges/0/metadataBadgeRenderer/label")

        if video_type := query_selector(_initial_data, pattern):  # type: list
            video_tag: str = video_type[0]
            if video_tag.find("Member") != -1:
                self.video_type = "Member"
            elif video_tag in ("Purchased", "Private", "Unlisted"):
                self.video_type = video_tag
            else:
                # For new unknown tag
                self.warn(f"Unknown video tag {video_tag}")
                self.video_type = video_tag
        elif self.player_response.playabilityStatus.status == "LOGIN_REQUIRED":
            self.video_type = "Private"

    def _check_premiere(self, _initial_data: dict):
        date_pattern = ("contents/twoColumnWatchNextResults/results/results/contents/"
                        "?/videoPrimaryInfoRenderer/dateText")
        is_premiere = False
        if _initial_data:
            is_premiere = query_selector(_initial_data, date_pattern)
        if (self.player_response.playabilityStatus and
                self.player_response.playabilityStatus.reason.find("Premiere") != -1 or is_premiere):
            if is_premiere:
                if get_text(is_premiere[0]).lower().find("premiere") == -1:
                    return
            self.isPremiere = True

    def _add_like_count(self, _initial_data: dict):
        button_path = ("contents/twoColumnWatchNextResults/results/results/contents/?/videoPrimaryInfoRenderer/"
                       "videoActions/menuRenderer/topLevelButtons/?/toggleButtonRenderer")
        if query := query_selector(_initial_data, button_path):
            for raw_data in query:
                buttonId = raw_data['toggleButtonSupportedData']['toggleButtonIdData']['id']
                button_type = "shortLikeCount" if buttonId == "TOGGLE_BUTTON_ID_TYPE_LIKE" else "shortDislikeCount"
                count_text = get_text(raw_data['defaultText'])
                if count_text.lower() in ("like", "dislike"):
                    count_text = "?"
                setattr(self.player_response.videoDetails, button_type, count_text)

    async def _parse_resp_data(self, player_response: dict, _initial_data: dict):
        """Parse response data"""
        await self._check_cipher()
        if self.player_response:
            self.player_response.update(player_response)
        else:
            self.player_response = playerResponse(player_response, self.js_url)
        self._check_video_type(_initial_data)
        self._check_premiere(_initial_data)
        self._add_like_count(_initial_data)

    async def _fetch_json(self):
        # Fetch json type webpage
        endpoint = f"{self.watch_url}&pbj=1"
        async with http_request(self._pool, "POST", url=endpoint,
                                header=self.header, cookie=self.cookie) as response:
            if response.content_type == "text/html":
                self.error(f"Failed to fetch video info")
                raise NetworkError
            json_resp = await response.json()
            player_response, _initial_data = (
                query_selector(json_resp, "?/playerResponse"),
                query_selector(json_resp, "?/response")
            )
            if not player_response or not _initial_data:
                self.error("One of the data failed to query path")
                raise ExtractError
            return player_response[0], _initial_data[0]

    async def _fetch_html(self):
        # Fetch html type webpage
        async with http_request(self._pool, url=self.watch_url,
                                header=self.header, cookie=self.cookie) as response:
            html_js = ScriptTaker(await response.text()).scripts
        self.vid_info_url = video_info_url(self.video_id, self.watch_url)
        player_config_args = player.get_ytplayer_setconfig(html_js)
        yt_internal_api.update_html(player_config_args)
        self.js_url = yt_root_url + player_config_args['PLAYER_JS_URL']
        _initial_data = initial_data(html_js)
        player_response = get_ytplayer_resp(html_js)
        return player_response, _initial_data

    async def fetch(self):
        """
        下载并解析油管视频

        :raises ExtractError: Failed to extract data
        :raises NetworkError: Problem fetching data
        """
        self.info("Downloading webpage")
        player_response, _initial_data = await (self._fetch_json() if self.js_url else self._fetch_html())
        await self._parse_resp_data(player_response, _initial_data)


class Community:
    def __init__(self, channel_id: str, cookie=None,
                 header: Optional[Dict[str, Union[str, bool, int]]] = None,
                 loop: Optional[AbstractEventLoop] = None):
        """Community init"""

        # Channel ID
        if channel_id.startswith("http"):
            channel_id = regex_search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", channel_id, group=1)
        else:
            if not (match := re.match(r"(UC[\w-]{21}[AQgw])", channel_id)):
                raise ExtractError("Invalid channel id")
            else:
                channel_id = match.group(1)
        self.channel_id = channel_id
        self.subscribers: int = -1

        # Header
        self.header = default_header
        if header:
            self.header.update(header)

        # Client setup
        self._loop = loop or asyncio.get_event_loop()
        if cookie is None:
            cookie = dict()
        cookie.update({"PREF": "hl=en"})
        self.cookie = cookie

        # http
        client_id = hash(self._loop)
        if not shared_tcp_pool.get(client_id):
            shared_tcp_pool[client_id] = aiohttp.TCPConnector(loop=self._loop, ttl_dns_cache=60,
                                                              force_close=True, enable_cleanup_closed=True, limit=0)
        self._pool = shared_tcp_pool[client_id]

    # Logger

    def debug(self, message: str):
        logger.debug(f"[{self.channel_id}] {message}")

    def info(self, message: str):
        logger.info(f"[{self.channel_id}] {message}")

    def warn(self, message: str):
        logger.warning(f"[{self.channel_id}] {message}")

    def error(self, message: str):
        logger.error(f"[{self.channel_id}] {message}")

    # ======

    def update_cookie(self, cookie: dict):
        self.cookie = cookie

    def _update_subscriber_count(self, js_data: dict):
        if (count := dict_search(js_data['header'], "subscriberCountText")) and len(count) > 0:
            subscribers_human_readable = get_text(count).replace(" subscribers", "")
            subscribers = string_to_int(subscribers_human_readable)
            if subscribers != self.subscribers and subscribers > self.subscribers:
                self.subscribers = subscribers

    @staticmethod
    def _get_image_from_elem(elem: dict) -> str:
        images = elem['thumbnails']
        image_url = images[len(images) - 1]['url']
        if image_match := image_regex.search(image_url):
            image_orig_url = image_match.group(1)
            return "https://" + image_orig_url + "=s0"
        return image_url

    def _make_attachment(self, post_id: str, attachment: dict) -> Optional[Post]:
        if video_attach := attachment.get("videoRenderer"):
            if not (video_id := video_attach.get("videoId")):
                return
            thumbnail = self._get_image_from_elem(video_attach['thumbnail'])
            views = get_text(video_attach.get("viewCountText", {"simpleText": "Unknown"}))
            if views != "Unknown":
                views = re.match("(.+) views?", views).group(1)
            video = Post.Attachment.Video(
                video_id,
                get_text(video_attach['title']),
                get_text(video_attach['lengthText']),
                thumbnail,
                views,
                get_text(video_attach['ownerText']),
                get_text(video_attach['publishedTimeText'])
            )
            attach = Post.Attachment("video", video)
        elif image_attach := attachment.get("backstageImageRenderer"):
            image = Post.Attachment.Image(False, [self._get_image_from_elem(image_attach['image'])])
            attach = Post.Attachment("image", image)
        elif images_attach := attachment.get("postMultiImageRenderer"):
            images_url = []
            for image_attach in images_attach['images']:
                images_url.append(self._get_image_from_elem(image_attach['backstageImageRenderer']['image']))
            image = Post.Attachment.Image(True, images_url)
            attach = Post.Attachment("image", image)
        elif poll_attach := attachment.get("pollRenderer"):
            choices = []
            for raw_poll in poll_attach['choices']:
                choices.append(get_text(raw_poll['text']))
            poll = Post.Attachment.Poll(
                re.match("(.+) votes?", get_text(poll_attach['totalVotes'])).group(1),
                choices
            )
            attach = Post.Attachment("poll", poll)
        else:
            self.warn(f"Unknown attachment type in post {post_id}")
            attach = None
        return attach

    def _make_normal_post(self, post_data: dict):
        post_id = post_data['postId']
        attach: Optional[Post.Attachment] = None
        author_channel = yt_root_url
        author_channel += post_data['authorEndpoint']['commandMetadata']['webCommandMetadata']['url']
        author = Post.Author(
            get_text(post_data['authorText']),
            "https:" + self._get_image_from_elem(post_data['authorThumbnail']),
            author_channel
        )
        if attachment := post_data.get('backstageAttachment'):
            attach = self._make_attachment(post_id, attachment)
        return Post(
            post_id,
            author,
            get_text(post_data['publishedTimeText']),
            get_text(post_data['voteCount']),
            get_text(post_data['contentText']) if post_data['contentText'] else "",
            attach,
            (post_data.get('sponsorsOnlyBadge') is not None)
        )

    def _parse_posts(self, json_data: dict):
        comm_posts = []
        community_enter_point = "contents/twoColumnBrowseResultsRenderer/tabs/?/tabRenderer/title:Community"
        community_content_path = "content/sectionListRenderer/contents/0/itemSectionRenderer/contents"
        if community_tab := query_selector(json_data, community_enter_point):
            community_tab = community_tab[0]
            if not community_tab['selected']:
                self.warn("Expected tab as community.")
                return comm_posts
            if contents := query_selector(community_tab, community_content_path):
                if len(contents) == 1 and contents[0].get("messageRenderer"):
                    return comm_posts
            else:
                self.warn("Failed to query post contents")
                return comm_posts
            for post_thread in contents:
                if next_page_thread := post_thread.get('continuationItemRenderer'):
                    # TODO Community continue token
                    # next_page_thread['continuationEndpoint']['continuationCommand']['token']
                    continue
                post_thread = post_thread['backstagePostThreadRenderer']['post']
                if normal_post := post_thread.get("backstagePostRenderer"):
                    comm_posts.append(self._make_normal_post(normal_post))
                elif shared_post := post_thread.get("sharedPostRenderer"):
                    post_id = shared_post['postId']
                    author_channel = yt_root_url
                    author_channel += shared_post['endpoint']['commandMetadata']['webCommandMetadata']['url']
                    author = Post.Author(
                        get_text(shared_post['displayName']),
                        self._get_image_from_elem(shared_post['thumbnail']),
                        author_channel
                    )
                    if not (original_post := shared_post['originalPost'].get('backstagePostRenderer')):
                        self.warn(f"Unknown post type in post {post_id}")
                        continue
                    comm_posts.append(SharedPost(
                        post_id,
                        author,
                        re.match("shared (.+)", get_text(shared_post['publishedTimeText'])).group(1),
                        self._make_normal_post(original_post),
                        get_text(shared_post['content']),
                        (shared_post.get('sponsorsOnlyBadge') is not None)
                    ))
            return comm_posts
        else:
            self.info("This channel hasn't enable community post feature")
            return comm_posts

    async def _api_fetch(self):
        endpoint = f"{yt_internal_api.endpoint}/{yt_internal_api.version}/browse?key={yt_internal_api.key}"
        async with http_request(self._pool, "POST", url=endpoint, json_data={
            "context": {
                "client": get_yt_client_info()
            },
            "browseId": self.channel_id,
            "params": quote(b64encode(b"\x12\tcommunity"))
        },
                                header=calculate_SNAPPISH(self.cookie, self.header), cookie=self.cookie) as response:
            if response is False:
                # Fallback
                return await self._html_fetch()
            if response.content_type == "text/html":
                self.error(f"Failed to fetch community posts")
                raise NetworkError
            return await response.json()

    async def _html_fetch(self):
        async with http_request(self._pool, url=f"{yt_root_url}/channel/{self.channel_id}/community",
                                header=self.header, cookie=self.cookie) as response:
            html_js = ScriptTaker(await response.text()).scripts
            yt_internal_api.update_html(player.get_ytplayer_setconfig(html_js))
            resp_json = initial_data(html_js)
            return resp_json

    async def fetch(self) -> List[Post]:
        """
        Fetch community posts

        :raise NetworkError: Fetching problems
        :return: A list of Posts
        """
        # Fallback to html if no api key
        js_data = await (self._api_fetch() if yt_internal_api.key else self._html_fetch())
        self._update_subscriber_count(js_data)
        return self._parse_posts(js_data)


class Membership:
    def __init__(self, cookie: dict,
                 header: Optional[Dict[str, Union[str, bool, int]]] = None,
                 loop: Optional[AbstractEventLoop] = None):
        """
        Membership list init

        :param cookie: Cookie
        :param header: Additional header
        :param loop: Event loop
        :raise ValueError: Cookie doesn't contain SAPISID
        """

        # Header
        self.header = default_header
        if header:
            self.header.update(header)

        # Client setup
        self.loop = loop or asyncio.get_event_loop()
        if cookie is None:
            cookie = dict()
        cookie.update({"PREF": "hl=en"})
        if not cookie.get("SAPISID"):
            raise ValueError("SAPISID not found in cookie")
        self.cookie = cookie

        # http
        client_id = hash(self.loop)
        if not shared_tcp_pool.get(client_id):
            shared_tcp_pool[client_id] = aiohttp.TCPConnector(loop=self.loop, ttl_dns_cache=60,
                                                              force_close=True, enable_cleanup_closed=True, limit=0)
        self.http = shared_tcp_pool[client_id]

        self.endpoint = f"{yt_root_url}/paid_memberships"

    # Logger

    def debug(self, message: str):
        logger.debug(f"[Membership {self.cookie.get('SSID')}] {message}")

    def info(self, message: str):
        logger.info(f"[Membership {self.cookie.get('SSID')}] {message}")

    def warn(self, message: str):
        logger.warning(f"[Membership {self.cookie.get('SSID')}] {message}")

    def error(self, message: str):
        logger.error(f"[Membership {self.cookie.get('SSID')}] {message}")

    # ======

    def update_cookie(self, cookie: dict):
        """
        Update cookie

        :param cookie: Cookie
        :raise ValueError: Cookie doesn't contain SAPISID
        """
        if not cookie.get("SAPISID"):
            raise ValueError("SAPISID not found, please check your cookie.")
        self.cookie = cookie

    async def _api_membership_status(self, continuation: str):
        endpoint = f"{yt_internal_api.endpoint}/{yt_internal_api.version}/browse?key={yt_internal_api.key}"
        content_path = ("onResponseReceivedActions/0/appendContinuationItemsAction/continuationItems/0/"
                        "itemSectionRenderer/contents")
        async with http_request(self.http, "POST", url=endpoint, json_data={
            "context": {
                "client": get_yt_client_info()
            },
            "continuation": continuation
        }, header=calculate_SNAPPISH(self.cookie, self.header), cookie=self.cookie) as response:
            if response.content_type == "text/html":
                self.error(f"Failed to fetch membership status")
                raise NetworkError
            if member_data := query_selector(await response.json(), content_path):
                return member_data
            else:
                self.error("Failed to query membership status path")
                raise NetworkError

    async def _parse_membership_list(self, membership_list: list):
        memberships = []
        item_index = ""  # Memberships | Inactive Memberships
        member_status_path = ("baseRenderer/cardItemRenderer/headingRenderer/cardItemTextWithImageRenderer/"
                              "textCollectionRenderer/?/cardItemTextCollectionRenderer/textRenderers/?/"
                              "cardItemTextRenderer/style:")
        for membership_data in membership_list:  # type: dict
            if index_data := membership_data.get("cardItemRenderer"):
                item_index = get_text(
                    index_data['headingRenderer']['cardItemTextCollectionRenderer']['textRenderers'][0]
                    ['cardItemTextRenderer']['text']
                )
            elif member_data := membership_data.get('cardItemContainerRenderer'):
                if not item_index:
                    self.error("Unknown member type")
                    raise ExtractError
                token = unquote(member_data['onClickCommand']['continuationCommand']['token'])
                entry = (ContinuationCommandEntry.FromString(b64decode(token)))
                details = ContinuationCommand.FromString(b64decode(unquote(entry.entry.details)))
                channel_id = details.entry.details.channelDetails.channelId
                if name := query_selector(member_data, member_status_path + "CARD_ITEM_TEXT_STYLE_TITLE_2"):
                    name = get_text(name[0]['text'])
                elif details.entry.details.channelDetails.channelId == "unlimited-B-music":
                    name = "Youtube Music"
                elif details.entry.details.channelDetails.channelId == "unlimited":
                    name = "Youtube Premium"
                else:
                    name = "Unknown"
                data = {
                    "name": name,
                    "channel_id": channel_id,
                    "expired": item_index == "Inactive Memberships"
                }
                if item_index != "Memberships":
                    # Expire time
                    if expired_time := query_selector(member_data, member_status_path + "CARD_ITEM_TEXT_STYLE_BODY_2A"):
                        expired_time = expired_time[0]['text']['runs'][1]['text']
                        data['expire_time'] = expired_time
                memberships.append(Member(**data))
        return memberships

    async def _parse_item_path(self, json_data: dict):
        """
            Find membership selection

            return empty dict when there's no selection
        """
        items_enter_point = ("contents/twoColumnBrowseResultsRenderer/tabs/?/"
                             "tabRenderer/tabIdentifier:FEmemberships_and_purchases")
        items_path = "content/sectionListRenderer/contents/?/itemSectionRenderer"
        item_name_path = "0/cardItemRenderer/headingRenderer/cardItemTextCollectionRenderer/textRenderers/0/" \
                         "cardItemTextRenderer/text"
        if item_selection := query_selector(json_data, items_enter_point):
            item_selection = item_selection[0]
            if not item_selection['selected']:
                self.error("Expected page is memberships and purchases")
                raise ExtractError
            if items := query_selector(item_selection, items_path):
                for root_item in items:
                    root_item = root_item['contents']
                    item_name = get_text(query_selector(root_item, item_name_path))
                    if item_name == "Memberships":
                        return root_item
                for root_item in items:  # Inactive only
                    root_item = root_item['contents']
                    item_name = get_text(query_selector(root_item, item_name_path))
                    if item_name == "Inactive Memberships":
                        return root_item
                # There's no membership available (Both type)
                self.info("There's no membership available")
                return {}
            else:
                self.error("Failed to query items path")
        else:
            self.error("Cannot query entry point of items")
        raise ExtractError

    async def _json_fetch(self):
        async with http_request(self.http, "POST", url=self.endpoint + "?pbj=1",
                                header=self.header, cookie=self.cookie) as response:
            if response is False:
                # Fallback
                return await self._html_fetch()
            if response.content_type == "text/html":
                self.error(f"Failed to fetch membership list")
                raise NetworkError
            scripts = await response.json()
            for script in scripts:
                if resp_json := script.get("response"):
                    return resp_json

    async def _html_fetch(self):
        async with http_request(self.http, url=self.endpoint,
                                header=self.header, cookie=self.cookie, allow_redirects=False) as response:
            if response.status != 200:
                self.error(f"Failed to fetch membership list")
                raise NetworkError
            html_js = ScriptTaker(await response.text()).scripts
            yt_internal_api.update_html(player.get_ytplayer_setconfig(html_js))
            resp_json = initial_data(html_js)
            return resp_json

    async def fetch(self) -> list:
        """
        Fetch membership infomation

        :raise ExtractError: Cannot extract field(s)
        :raise NetworkError: Fetching problems
        :return: Membership details
        """
        self.info("Downloading webpage")
        resp_json = await (self._json_fetch() if yt_internal_api.key else self._html_fetch())
        if membership_data := await self._parse_item_path(resp_json):
            memberships = await self._parse_membership_list(membership_data)
            return memberships
        return []
