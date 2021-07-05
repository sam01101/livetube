"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 10:18
    文件:    __main__.py
    文件描述:
"""

# General
import asyncio
import json
import time

# Parsing
import re
import warnings
from asyncio import AbstractEventLoop
from base64 import b64encode, b64decode
from io import BytesIO
from typing import Optional, Dict, Union, List, BinaryIO
from urllib.parse import parse_qsl, quote, unquote, quote_plus

# Networking
import aiohttp
import yarl

# Models
from livetube.memberShips import Member
from livetube.membership_pb3 import ContinuationCommand, ContinuationCommandEntry
from livetube.studio_pb3 import GoogleVisitorId
from livetube.communityPosts import Post, SharedPost
from livetube.playerResponse import playerResponse
# Utils
from livetube.util import player
from livetube.util.cache import (shared_tcp_pool, js_cache_v2, yt_internal_api, user_agent,
                                 get_yt_client_info, default_header, yt_root_url, studio_root_url)
# Cache for YouTube
from livetube.util.cipher import Cipher
from livetube.util.exceptions import RegexMatchError, NetworkError, HTMLParseError, ExtractError
from livetube.util.js import initial_data, video_info_url, query_selector, dict_search
from livetube.util.parser import ScriptTaker
from livetube.util.player import get_ytplayer_resp
from livetube.util.regex import regex_search
from livetube.utils import (time_map, get_text, string_to_int, http_request, logger,
                            calculate_SNAPPISH, gen_yt_upload_session_id)

"""DO NOT USE "FORMAT IMPORT PACKAGE"""

image_regex = re.compile(r"(yt3\.ggpht\.com/.+?)=.+")


class Video:
    def __init__(self,
                 video_id: str,
                 cookie=None,
                 header: Optional[Dict[str, Union[str, bool, int]]] = None,
                 loop: Optional[AbstractEventLoop] = None):
        """
        Video object

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
            match = re.match(r"([0-9A-Za-z_-]{11})", video_id)
            if not match:
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
        test = query_selector(resp_json, pattern)
        if test:
            video_info = test[0]
            thumbnail = video_info.get("richThumbnail")
            if thumbnail:
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
            info = query_selector(action, "updateViewershipAction/viewCount/videoViewCountRenderer")
            updateToggleButtonTextAction, updateDateTextAction, updateTitleAction = (
                action.get("updateToggleButtonTextAction"), action.get("updateDateTextAction"),
                action.get("updateTitleAction"),
            )
            if info:
                viewCount = info.get("viewCount")
                if viewCount:
                    self.player_response.videoDetails.liveViewCount = int(
                        ''.join(filter(str.isdigit, get_text(viewCount))))
                shortViewCount = info.get("extraShortViewCount")
                if shortViewCount:
                    self.player_response.videoDetails.liveShortViewCount = get_text(shortViewCount)
            elif updateToggleButtonTextAction:
                """Like/Dislike button update"""
                buttonId = updateToggleButtonTextAction['buttonId']
                button_type = "shortLikeCount" if buttonId == "TOGGLE_BUTTON_ID_TYPE_LIKE" else "shortDislikeCount"
                count_text = get_text(updateToggleButtonTextAction['defaultText'])
                if count_text.lower() in ("like", "dislike"):
                    count_text = "?"
                setattr(self.player_response.videoDetails, button_type, count_text)
            elif updateDateTextAction:
                displayText = get_text(updateDateTextAction['dateText'])
                for pattern, name in time_map.items():
                    try:
                        stream_time = regex_search(r"Started streaming on (.+)", displayText, 1)
                        self.player_response.videoDetails.startedSince = stream_time
                        continue
                    except RegexMatchError:
                        pass
                    try:
                        stream_time = int(regex_search(r"(\d+) " + pattern, displayText, 1))
                        text = (f"{stream_time} {name if self.display_chinese else pattern} "
                                f"{'前' if self.display_chinese else 'ago'}")
                        self.player_response.videoDetails.startedSince = text
                        break
                    except RegexMatchError:
                        continue
            elif updateTitleAction:
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
            continue_id = query_selector(resp_json, "continuation/timedContinuationData/continuation")
            if continue_id and continue_id != self._continue_id:
                self._continue_id = continue_id
            update = resp_json.get('responseContext')
            if update:
                self.player_response.responseContext.update(update)
            actions = resp_json.get("actions")
            if actions:
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
            _player = self.player_response
            if _player:
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

        video_type = query_selector(_initial_data, pattern)
        if video_type:
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
        query = query_selector(_initial_data, button_path)
        if query:
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
            channel_id = regex_search(r"(?:v=|\/)(UC[\w-]{21}[AQgw]).*", channel_id, group=1)
        else:
            match = re.match(r"(UC[\w-]{21}[AQgw])", channel_id)
            if not match:
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
        count = dict_search(js_data['header'], "subscriberCountText")
        if count and len(count) > 0:
            subscribers_human_readable = get_text(count).replace(" subscribers", "")
            subscribers = string_to_int(subscribers_human_readable)
            if subscribers != self.subscribers and subscribers > self.subscribers:
                self.subscribers = subscribers

    @staticmethod
    def _get_image_from_elem(elem: dict) -> str:
        images = elem['thumbnails']
        image_url = images[len(images) - 1]['url']
        image_match = image_regex.search(image_url)
        if image_match:
            image_orig_url = image_match.group(1)
            return "https://" + image_orig_url + "=s0"
        return image_url

    def _make_attachment(self, post_id: str, attachment: dict) -> Optional[Post]:
        video_attach = attachment.get("videoRenderer")
        image_attach, images_attach, poll_attach = (
            attachment.get("backstageImageRenderer"), attachment.get("postMultiImageRenderer"),
            attachment.get("pollRenderer")
        )
        if video_attach:
            video_id = video_attach.get("videoId")
            if not video_id:
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
        elif image_attach:
            image = Post.Attachment.Image(False, [self._get_image_from_elem(image_attach['image'])])
            attach = Post.Attachment("image", image)
        elif images_attach:
            images_url = []
            for image_attach in images_attach['images']:
                images_url.append(self._get_image_from_elem(image_attach['backstageImageRenderer']['image']))
            image = Post.Attachment.Image(True, images_url)
            attach = Post.Attachment("image", image)
        elif poll_attach:
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
        attachment = post_data.get('backstageAttachment')
        if attachment:
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
        community_tab = query_selector(json_data, community_enter_point)
        if community_tab:
            community_tab = community_tab[0]
            if not community_tab['selected']:
                self.warn("Expected tab as community.")
                return comm_posts
            contents = query_selector(community_tab, community_content_path)
            if contents:
                if len(contents) == 1 and contents[0].get("messageRenderer"):
                    return comm_posts
            else:
                self.warn("Failed to query post contents")
                return comm_posts
            for post_thread in contents:
                next_page_thread = post_thread.get('continuationItemRenderer')
                if next_page_thread:
                    # TODO Community continue token
                    # next_page_thread['continuationEndpoint']['continuationCommand']['token']
                    continue
                post_thread = post_thread['backstagePostThreadRenderer']['post']
                normal_post = post_thread.get("backstagePostRenderer")
                shared_post = post_thread.get("sharedPostRenderer")
                if normal_post:
                    comm_posts.append(self._make_normal_post(normal_post))
                elif shared_post:
                    post_id = shared_post['postId']
                    author_channel = yt_root_url
                    author_channel += shared_post['endpoint']['commandMetadata']['webCommandMetadata']['url']
                    author = Post.Author(
                        get_text(shared_post['displayName']),
                        self._get_image_from_elem(shared_post['thumbnail']),
                        author_channel
                    )
                    original_post = shared_post['originalPost'].get('backstagePostRenderer')
                    if not original_post:
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
            member_data = query_selector(await response.json(), content_path)
            if member_data:
                return member_data
            else:
                self.error("Failed to query membership status path")
                raise NetworkError

    async def _parse_membership_list(self, membership_list: Union[list, tuple]):
        memberships = []
        item_index = ""  # Memberships | Inactive Memberships
        member_status_path = ("baseRenderer/cardItemRenderer/headingRenderer/cardItemTextWithImageRenderer/"
                              "textCollectionRenderer/?/cardItemTextCollectionRenderer/textRenderers/?/"
                              "cardItemTextRenderer/style:")
        for membership_data in membership_list:  # type: dict
            index_data, member_data = (
                membership_data.get("cardItemRenderer"), membership_data.get('cardItemContainerRenderer')
            )
            if index_data:
                item_index = get_text(
                    index_data['headingRenderer']['cardItemTextCollectionRenderer']['textRenderers'][0]
                    ['cardItemTextRenderer']['text']
                )
            elif member_data:
                if not item_index:
                    self.error("Unknown member type")
                    raise ExtractError
                token = unquote(member_data['onClickCommand']['continuationCommand']['token'])
                entry = (ContinuationCommandEntry.FromString(b64decode(token)))
                details = ContinuationCommand.FromString(b64decode(unquote(entry.entry.details)))
                channel_id = details.entry.details.channelDetails.channelId
                name = query_selector(member_data, member_status_path + "CARD_ITEM_TEXT_STYLE_TITLE_2")
                if name:
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
                    expired_time = query_selector(member_data, member_status_path + "CARD_ITEM_TEXT_STYLE_BODY_2A")
                    if expired_time:
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
        item_selection = query_selector(json_data, items_enter_point)
        if item_selection:
            item_selection = item_selection[0]
            if not item_selection['selected']:
                self.error("Expected page is memberships and purchases")
                raise ExtractError
            items = query_selector(item_selection, items_path)
            if items:
                has_inactive, root_item = False, None
                for root_item in items:
                    root_item = root_item['contents']
                    item_name = get_text(query_selector(root_item, item_name_path))
                    if item_name == "Memberships":
                        return root_item
                    elif item_name == "Inactive Memberships":
                        has_inactive = True
                if has_inactive and root_item:
                    return root_item
                # There's no membership available (Both type)
                self.info("There's no membership available")
                return ()
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
                resp_json = script.get("response")
                if resp_json:
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
        membership_data = await self._parse_item_path(resp_json)
        if membership_data:
            memberships = await self._parse_membership_list(membership_data)
            return memberships
        return []


class Studio:
    def __init__(self, cookie: dict,
                 header: Optional[Dict[str, Union[str, bool, int]]] = None,
                 loop: Optional[AbstractEventLoop] = None):
        """
        Youtube studio object

        :param cookie: Cookie
        :param header: Additional header
        :param loop: Event loop
        :raise ValueError: Cookie doesn't contain SAPISID
        """

        # Header
        self.header = {
            "User-Agent": user_agent,
            "X-Origin": "https://studio.youtube.com",
            "Origin": "https://studio.youtube.com",
            "Referer": "https://studio.youtube.com",
        }
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
        self.upload_cache = {}
        self.session_cache = {}

        # http
        client_id = hash(self.loop)
        if not shared_tcp_pool.get(client_id):
            shared_tcp_pool[client_id] = aiohttp.TCPConnector(loop=self.loop, ttl_dns_cache=60,
                                                              force_close=True, enable_cleanup_closed=True, limit=0)
        self.http = shared_tcp_pool[client_id]

        # endpoint
        self.upload_ep = "https://upload.youtube.com"

    # Logger

    def debug(self, message: str):
        logger.debug(f"[Studio {self.cookie.get('SSID')}] {message}")

    def info(self, message: str):
        logger.info(f"[Studio {self.cookie.get('SSID')}] {message}")

    def warn(self, message: str):
        logger.warning(f"[Studio {self.cookie.get('SSID')}] {message}")

    def error(self, message: str):
        logger.error(f"[Studio {self.cookie.get('SSID')}] {message}")

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

    async def _upload_video(self, file: BytesIO, session_id: str):
        """
        Actual upload function, uploads video chunk to UploadServer

        :param session_id: Upload session id
        """

        last_end_offset = 0
        data = self.upload_cache[session_id]
        header = self.header.copy()
        while True:
            # noinspection PyBroadException
            try:
                chunk = file.read(104857600)
                upload_cmd = []
                if len(chunk) > 0:
                    upload_cmd.append("upload")
                if len(chunk) != 104857600 or not chunk:
                    upload_cmd.append("finalize")
                if not upload_cmd:
                    return True
                header.update({
                    "X-Goog-Upload-File-Name": data['file-name'],
                    "X-Goog-Upload-Offset": str(last_end_offset),
                    "X-Goog-Upload-Command": ", ".join(upload_cmd),
                })
                async with http_request(self.http, "POST", url=data['upload-url'],
                                        header=header, cookie=self.cookie, data=chunk) as response:
                    if response.status == 200:
                        last_end_offset += len(chunk)
                        if response.headers.get("X-Goog-Upload-Status") == "final":
                            # Upload completed
                            return True
            except Exception:
                pass

    async def upload_video(self, file: Union[BytesIO, BinaryIO], file_name: str = ""):
        """
        Uploads video to youtube

        :param file: file stream
        :param file_name: file name
        :param async_upload: Upload all chunk at one time
        :raise RuntimeError: Failed to start upload session
        :return: upload session id, a task that uploading the video
        """

        def get_file_size() -> int:
            file.seek(0, 2)
            size = file.tell()
            file.seek(0, 0)
            return size

        header = self.header.copy()
        header.update({
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-File-Name": file_name,
            "X-Goog-Upload-Header-Content-Length": str(get_file_size()),
            "X-Goog-Upload-Protocol": "resumable"
        })
        upload_session_id = gen_yt_upload_session_id()
        async with http_request(self.http, "POST", url=self.upload_ep + "/upload/studio",
                                header=header, cookie=self.cookie,
                                json_data={"frontendUploadId": upload_session_id}) as response:
            if response.status == 200:
                self.upload_cache[upload_session_id] = {
                    "file-name": file_name,
                    "upload-url": response.headers.get("x-goog-upload-url"),
                    "scotty-resource-id": response.headers.get("x-goog-upload-header-scotty-resource-id")
                }
                task = asyncio.create_task(self._upload_video(file, upload_session_id))
                self.upload_cache[upload_session_id]['task'] = task
                return upload_session_id, task
            else:
                raise RuntimeError("Failed to start upload session")

    async def _get_challenge(self):
        await yt_internal_api.fetch()
        endpoint = studio_root_url + f"/youtubei/{yt_internal_api.version}/att/get"
        endpoint += "?alt=json&key=" + yt_internal_api.key
        header = self.header.copy()
        visitor_id = self.cookie.get("VISITOR_INFO1_LIVE")
        if not visitor_id:
            raise ValueError("VISITOR_INFO1_LIVE is required to get session challenge")
        visitor_proto = GoogleVisitorId(
            visitor_info_live=visitor_id,
            timestamp=int(time.time())
        )
        header['X-Goog-Visitor-Id'] = quote(b64encode(visitor_proto.SerializeToString()))
        async with http_request(self.http, "POST", url=endpoint, header=calculate_SNAPPISH(self.cookie, header),
                                cookie=self.cookie, json_data={
                    "context": {
                        "client": get_yt_client_info()
                    }
                }) as response:
            if response.status == 200:
                js_resp = await response.json()
                return js_resp.get("challenge")

    async def _get_session_token(self, bg_token=""):
        if self.session_cache.get("ts") and time.time() - self.session_cache['ts'] <= 8 * 60 * 60:
            return self.session_cache['token']
        elif not bg_token:
            raise ValueError("botGuard token is required to get session token")
        challenge_data = await self._get_challenge()
        endpoint = studio_root_url + f"/youtubei/{yt_internal_api.version}/att/esr"
        endpoint += "?alt=json&key=" + yt_internal_api.key
        header = self.header.copy()
        visitor_id = self.cookie.get("VISITOR_INFO1_LIVE")
        if not visitor_id:
            raise ValueError("VISITOR_INFO1_LIVE is required to get session id")
        visitor_proto = GoogleVisitorId(
            visitor_info_live=visitor_id,
            timestamp=int(time.time())
        )
        header['X-Goog-Visitor-Id'] = quote(b64encode(visitor_proto.SerializeToString()))
        async with http_request(self.http, "POST", url=endpoint, header=calculate_SNAPPISH(self.cookie, header),
                                cookie=self.cookie, json_data={
                    "context": {
                        "client": get_yt_client_info(studio=True)
                    },
                    "challenge": challenge_data,
                    "botguardResponse": bg_token
                }) as response:
            if response.status == 200:
                js_resp = await response.json()
                if js_resp.get("vint", 1) != 0:
                    self.warn("botGuard token check failed!")
                    return ""
                else:
                    token = js_resp['sessionToken']
                    self.session_cache = {
                        "ts": time.time(),
                        "token": token
                    }
                    return token

    @staticmethod
    def _handle_feedback(data: dict):
        response = {}
        video_id = data.get("videoId")
        if video_id:
            response['video_id'] = video_id
        contents = data.get("contents") or data.get("continuationContents", [None])[0]
        if contents:
            contents = contents.get("uploadFeedbackItemRenderer") or contents.get("uploadFeedbackItemContinuation")
            response['continue_token'] = (contents['continuations'][1]
                ['uploadFeedbackRefreshContinuation'][ 'continuation'])
            id_content = contents.get("id")
            if id_content and not response.get("video_id"):
                response['video_id'] = id_content.get("video_id")
            if contents.get("uploadStatus"):
                response['status'] = contents['uploadStatus']['uploadStatus']
            process_progress = contents.get("processingProgressBar")
            if process_progress:
                process = {'progress': process_progress['fractionCompleted']}
                if process_progress.get("remainingTimeSeconds"):
                    process['remain'] = process_progress['remainingTimeSeconds']
                response['process'] = process
            upload_progress = contents.get("transferProgressBar")
            if upload_progress:
                upload = {'progress': upload_progress['fractionCompleted']}
                if upload_progress.get("remainingTimeSeconds"):
                    upload['remain'] = upload_progress['remainingTimeSeconds']
                response['upload'] = upload
        return response

    async def get_video_progress(self, continue_token: str):
        await yt_internal_api.fetch(studio=True, cookie=self.cookie)
        endpoint = studio_root_url + f"/youtubei/{yt_internal_api.version}/upload/feedback"
        endpoint += f"?alt=json&key=" + yt_internal_api.key
        async with http_request(self.http, "POST", url=endpoint, header=calculate_SNAPPISH(self.cookie, self.header),
                                cookie=self.cookie, json_data={
                    "context": {
                        "client": get_yt_client_info(studio=True)
                    },
                    "continuations": [continue_token]
                }) as response:
            if response.status == 200:
                return self._handle_feedback(await response.json())

    async def create_video(self, upload_session: str, bg_token: str,
                           title="", description="", is_draft: bool = None,
                           privacy="UNLISTED", sponsors_only: bool = None,
                           audio_language="zxx", category=0, allow_comment: bool = None,
                           add_to_playlist_ids: Union[list, tuple] = None,
                           del_from_playlist_ids: Union[list, tuple] = None):
        """
        Create video metadata

        Params:
            - title
            - description
            - privacy (PUBLIC / UNLISTED / PRIVATE)
            - sponsorsOnly (when: privacy = UNLISTED)
            - audioLanguage (zxx = UNAVAILABLE)
            - category (0)
            - addToPlaylist
            - draftState (When true, ignore privacy)
            - allow_comment

        :raise NetworkError: Network error
        :raise ValueError: Failed to get session token
        """
        session_token = await self._get_session_token(bg_token)
        if not session_token:
            raise ValueError("Failed to get session token")
        context = {
            "client": get_yt_client_info(studio=True),
            "request": {
                "sessionInfo": {
                    "token": session_token
                }
            }
        }
        metadata = {
            "context": context,
            "videoReadMask": {},
        }
        if title:
            metadata['title'] = {
                "newTitle": title
            }
        if description:
            metadata['description'] = {
                "newDescription": description
            }
        if privacy:
            if privacy not in ("PUBLIC", "UNLISTED", "PRIVATE"):
                privacy = "UNLISTED"
            metadata['privacy'] = {
                "newPrivacy": privacy
            }
        if privacy == "UNLISTED" and type(sponsors_only) is bool:
            metadata['sponsorsOnly'] = {
                "isSponsorsOnly": sponsors_only
            }
        if audio_language:
            metadata['audioLanguage'] = {
                "newAudioLanguage": audio_language
            }
        if type(category) is int:
            metadata['category'] = {
                "newCategoryId": category
            }
        if type(is_draft) is bool:
            if is_draft:
                if metadata.get("privacy"):
                    metadata['privacy'] = "PRIVATE"
                if metadata.get("sponsorsOnly"):
                    del metadata['sponsorsOnly']
            metadata['draftState'] = {
                "isDraft": is_draft
            }
        if type(allow_comment) is bool:
            metadata['commentOptions'] = {
                "newAllowComments": allow_comment,
                "newCanViewRatings": allow_comment
            }
        if add_to_playlist_ids or del_from_playlist_ids:
            playlist = {}
            if add_to_playlist_ids:
                playlist['addToPlaylistIds'] = add_to_playlist_ids
            if del_from_playlist_ids:
                playlist['deleteFromPlaylistIds'] = del_from_playlist_ids
            if len(playlist):
                metadata['addToPlaylist'] = playlist
        await yt_internal_api.fetch(studio=True, cookie=self.cookie)
        endpoint = studio_root_url + f"/youtubei/{yt_internal_api.version}/upload/createvideo"
        endpoint += "?alt=json&key=" + yt_internal_api.key
        video_id = None
        async with http_request(self.http, "POST", url=endpoint, header=calculate_SNAPPISH(self.cookie, self.header),
                                cookie=self.cookie, json_data={
                    "context": context,
                    "botguardClientResponse": bg_token,
                    "frontendUploadId": upload_session,
                    "resourceId": {
                        "scottyResourceId": {
                            "id": self.upload_cache[upload_session]['scotty-resource-id']
                        }
                    },
                    "initialMetadata": {}
                }) as response:
            if response.status == 200:
                js_resp = await response.json()
                feedback = self._handle_feedback(js_resp)
                video_id = feedback.get("video_id")
                if not video_id:
                    return feedback
        metadata['encryptedVideoId'] = video_id
        endpoint = studio_root_url + f"/youtubei/{yt_internal_api.version}/video_manager/metadata_update"
        endpoint += "?alt=json&key=" + yt_internal_api.key
        async with http_request(self.http, "POST", url=endpoint, header=calculate_SNAPPISH(self.cookie, self.header),
                                cookie=self.cookie, json_data=metadata) as _:
            pass
        return feedback

    async def create_playlist(self, title: str, description="",
                              privacy="UNLSITED", source_playlist_id: str = None,
                              add_to_top: bool = None) -> str:
        """
        Create playlist

        Params:
            - title
            - description
            - privacy (PUBLIC / UNLISTED / PRIVATE)
            - source_playlist_id (Copy playlist)
            - add_to_top
        :return: Created playlist id
        """
        playlist_id = ""
        payload = {
            "context": {
                "client": get_yt_client_info(studio=True)
            },
            "title": title,
        }
        if privacy not in ("PUBLIC", "UNLISTED", "PRIVATE"):
            privacy = "UNLISTED"
        payload['privacyStatus'] = privacy
        if description:
            payload['description'] = description
        if source_playlist_id:
            payload['sourcePlaylistId'] = source_playlist_id
        await yt_internal_api.fetch(studio=True, cookie=self.cookie)
        endpoint = studio_root_url + f"/youtubei/{yt_internal_api.version}/playlist/create"
        endpoint += "?alt=json&key=" + yt_internal_api.key
        async with http_request(self.http, "POST", url=endpoint, header=calculate_SNAPPISH(self.cookie, self.header),
                                cookie=self.cookie, json_data=payload) as response:
            if response.status == 200:
                js_resp = await response.json()
                playlist_id = js_resp['playlistId']
        if playlist_id and type(add_to_top) is bool:
            endpoint = (f"{yt_internal_api.endpoint}/{yt_internal_api.version}/browse/edit_playlist"
                        f"?key={yt_internal_api.key}")
            async with http_request(self.http, "POST", url=endpoint,
                                    header=calculate_SNAPPISH(self.cookie, default_header),
                                    cookie=self.cookie,
                                    json_data={"context": {
                                        "client": get_yt_client_info(studio=True)
                                    },
                                        "actions": [
                                            {
                                                "action": "ACTION_SET_ADD_TO_TOP",
                                                "addToTop": add_to_top
                                            }
                                        ],
                                        "playlistId": playlist_id
                                    }) as response:
                if response.status == 200:
                    js_resp = await response.json()
                    if js_resp['status'] != "STATUS_SUCCEEDED":
                        self.warn("Faield to edit playlist")
        return playlist_id
