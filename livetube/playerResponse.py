"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 15:57
    文件:    playerResponse.py
    文件描述: 
"""
import time
from enum import Enum
from typing import Optional, Dict
from urllib.parse import parse_qsl

from livetube.util.cache import js_cache_v2
from livetube.util.exceptions import *
from livetube.util.js import query_selector
from livetube.util.regex import regex_search
from livetube.utils import get_text

error_reasons = (
    # Passed YoutubeDL check
    (MembersOnly, "member"),
    (RecordingUnavailable, 'This live stream recording is not available.'),
    (VideoRegionBlocked, "Video unavailable", 'The uploader has not made this video available in your country.'),
    (AccountBanned, "Video unavailable", 'This video is no longer available because '
                                         'the YouTube account associated with this video has been terminated.'),
    (VideoPrivate, "", "This video is private."),
    (VideoPrivate, "private video"),
    # Check streamData first
    (LoginRequired, 'Sign in to confirm your age', 'This video may be inappropriate for some users.'),
    (PaymentRequired, 'This video requires payment to watch.'),
)


class latencyType(Enum):
    MDE_STREAM_OPTIMIZATIONS_RENDERER_LATENCY_NORMAL = "NORMAL"
    MDE_STREAM_OPTIMIZATIONS_RENDERER_LATENCY_LOW = "LOW"
    MDE_STREAM_OPTIMIZATIONS_RENDERER_LATENCY_ULTRA_LOW = "ULTRALOW"
    NORMAL = "NORMAL"
    LOW = "LOW"
    ULTRALOW = "ULTRALOW"


class responseContext:
    serviceTrackingParams: list
    is_viewed_live: bool = False
    logged_in: bool = False

    def __init__(self, data: dict):
        self.serviceTrackingParams = data.get('serviceTrackingParams')
        if self.serviceTrackingParams:
            for serviceTrackingParam in self.serviceTrackingParams:
                if serviceTrackingParam.get('service', '') == "GFEEDBACK":
                    for param in serviceTrackingParam['params']:
                        if param['key'] == "logged_in":
                            self.logged_in = param['value'] == "1"
                        elif param['key'] == "is_viewed_live":
                            self.is_viewed_live = param['value'] == "1"

    def update(self, data):
        self.__init__(data)


class playabilityStatus:
    status: str
    reason: str
    playableInEmbed: bool
    subreason: str = ""
    pollDelayMs: int = 5000
    isCountDown = False
    isPremiere = False
    scheduled_start_time: Optional[int] = None

    def __init__(self, data: dict):
        self.status = data.get("status", "UNPLAYABLE")
        self.reason = data.get("reason", "")
        self.playableInEmbed = data.get('playableInEmbed', False)
        sub_reason = query_selector(data, "errorScreen/playerErrorMessageRenderer/subreason")
        if sub_reason:
            self.subreason = get_text(sub_reason)
        poll_ms = query_selector(data, "liveStreamability/liveStreamabilityRenderer/pollDelayMs")
        if poll_ms:
            self.pollDelayMs = int(poll_ms)
        livestream_offline = query_selector(data, "liveStreamability/liveStreamabilityRenderer/offlineSlate"
                                                  "/liveStreamOfflineSlateRenderer")
        if livestream_offline:
            self.isCountDown = livestream_offline.get("canShowCountdown", False)
            scheduled_start_time = livestream_offline.get("scheduledStartTime")
            if scheduled_start_time:
                self.scheduled_start_time = int(scheduled_start_time)

    def update(self, data: dict):
        for key in (
                "status",
                "reason",
                "playableInEmbed",
                "errorScreen",
                "liveStreamability"
        ):
            value = data.get(key)
            if value:
                if key == "errorScreen":
                    sub_reason = query_selector(value, "playerErrorMessageRenderer/subreason")
                    if sub_reason:
                        self.subreason = get_text(sub_reason)
                elif key == "liveStreamability":
                    value = value.get("liveStreamabilityRenderer")
                    if not value:
                        return
                    poll_ms = query_selector(value, "pollDelayMs")
                    if poll_ms:
                        self.pollDelayMs = int(poll_ms)
                    livestream_offline = query_selector(value, "offlineSlate/liveStreamOfflineSlateRenderer")
                    if livestream_offline:
                        update = livestream_offline.get("canShowCountdown") is not None
                        if update:
                            self.isCountDown = update
                        scheduled_start_time = livestream_offline.get("scheduledStartTime")
                        if scheduled_start_time:
                            self.scheduled_start_time = int(scheduled_start_time)
                else:
                    setattr(self, key, value)


class streamingData:
    expiresInSeconds: int
    hlsManifestUrl: str
    dashManifestUrl: str
    expireTimestamp: int
    audios: Dict[str, dict]
    videos: Dict[str, dict]

    def __init__(self, data: dict, js_url: str):
        self.expiresInSeconds = int(data.get('expiresInSeconds'))
        self.hlsManifestUrl = data.get('hlsManifestUrl')
        self.dashManifestUrl = data.get('dashManifestUrl')
        adaptiveFormats: list = data.get("adaptiveFormats", [])
        if adaptiveFormats:
            self.audios = {}
            self.videos = {}
            for formats in adaptiveFormats:
                sig_raw = formats.get('signatureCipher')
                if sig_raw:
                    cipher = js_cache_v2[js_url]
                    if not cipher:
                        raise HTMLParseError("Cipher not found.")
                    sig_data = parse_qsl(sig_raw)
                    sig_key = next(data for key, data in sig_data if key == "s")
                    sig_type = next(data for key, data in sig_data if key == "sp")
                    sig_url = next(data for key, data in sig_data if key == "url")
                    signature = cipher.get_signature(ciphered_signature=sig_key)
                    formats['url'] = f"{sig_url}&{sig_type}={signature}"
                    del formats['signatureCipher']

                if "audio" in formats['mimeType']:
                    self.audios[formats['itag']] = formats
                elif "mp4" in formats['mimeType']:
                    self.videos[formats['itag']] = formats
            # Get best format
            bestBitrate: int = 0
            best: Optional[dict] = None
            for _, formats in self.audios.items():
                if int(formats['bitrate']) > bestBitrate and formats['mimeType'].find("mp4") != -1:
                    bestBitrate = int(formats['bitrate'])
                    best = self.audios[formats['itag']]
            self.audios['best'] = best if best else None
            bestW, bestH, bestFPS = 0, 0, 0
            best: Optional[dict] = None
            for _, formats in self.videos.items():
                w, h, fps = int(formats.get("width", 0)), int(formats.get("height", 0)), int(formats.get("fps", 0))
                if w >= bestW and h >= bestH and fps >= bestFPS:
                    bestW, bestH, bestFPS = w, h, fps
                    best = self.videos[formats['itag']]
            self.videos['best'] = best if best else None
            # Get timestamp of expire time
            try:
                self.expireTimestamp = int(regex_search(r"/expire/(\d+)/", self.videos['best']['url'], 1))
            except (RegexMatchError, KeyError):
                self.expireTimestamp = int(time.time()) + self.expiresInSeconds + 120

    def update(self, data: dict, js_url: str):
        update = data.get("expiresInSeconds")
        if update:
            self.expiresInSeconds = update

        update = data.get("hlsManifestUrl")

        if update:
            self.hlsManifestUrl = update

        update = data.get("dashManifestUrl")

        if update:
            self.dashManifestUrl = update

        update = data.get("adaptiveFormats")

        if update:
            self.audios = {}
            self.videos = {}
            for formats in update:
                sig_raw = formats.get('signatureCipher')
                if sig_raw:
                    cipher = js_cache_v2[js_url]
                    if not cipher:
                        raise HTMLParseError("Cipher not found.")
                    sig_data = parse_qsl(sig_raw)
                    sig_key = next(data for key, data in sig_data if key == "s")
                    sig_type = next(data for key, data in sig_data if key == "sp")
                    sig_url = next(data for key, data in sig_data if key == "url")
                    signature = cipher.get_signature(ciphered_signature=sig_key)
                    formats['url'] = f"{sig_url}&{sig_type}={signature}"
                    del formats['signatureCipher']

                if "audio" in formats['mimeType']:
                    self.audios[formats['itag']] = formats
                elif "mp4" in formats['mimeType']:
                    self.videos[formats['itag']] = formats
            # Get best format
            bestBitrate: int = 0
            best: Optional[dict] = None
            for _, formats in self.audios.items():
                if int(formats['bitrate']) > bestBitrate and formats['mimeType'].find("mp4") != -1:
                    bestBitrate = int(formats['bitrate'])
                    best = self.audios[formats['itag']]
            self.audios['best'] = best if best else None
            bestW, bestH, bestFPS = 0, 0, 0
            best: Optional[dict] = None
            for _, formats in self.videos.items():
                w, h, fps = int(formats.get("width", 0)), int(formats.get("height", 0)), int(formats.get("fps", 0))
                if w >= bestW and h >= bestH and fps >= bestFPS:
                    bestW, bestH, bestFPS = w, h, fps
                    best = self.videos[formats['itag']]
            self.videos['best'] = best if best else None
            # Get timestamp of expire time
            try:
                self.expireTimestamp = int(regex_search(r"/expire/(\d+)/", self.videos['best']['url'], 1))
            except (RegexMatchError, KeyError):
                self.expireTimestamp = int(time.time()) + self.expiresInSeconds + 120


class videoDetails:
    video_id: str
    channel_id: str
    title: str
    lengthSeconds: int
    isLive: bool
    isLiveStream: bool
    keywords: list
    shortDescription: str
    isLiveDvrEnabled: bool
    thumbnail: str
    isUnlisted: bool = False
    viewCount: int
    private: bool
    liveViewCount: Optional[int] = None
    liveShortViewCount: Optional[int] = None
    startedSince: Optional[str] = None
    shortLikeCount: str
    shortDislikeCount: str
    isLowLatencyLiveStream: Optional[bool]
    latencyClass: latencyType
    latencyText: Optional[str]
    broadcastDetails: Optional[dict] = {}

    def __init__(self, data: Optional[dict] = None, extra_data: dict = None):
        # Basic info
        if extra_data is None:
            extra_data = {}
        if data:
            self.isLiveStream = data.get('isLiveContent', False)
            self.video_id = data.get('videoId', "")
            self.channel_id = data.get('channelId', "")
            self.channel_name = data.get('author', "Unknown")
            self.keywords = data.get('keywords', [])
            self.shortDescription = data.get('shortDescription', "")
            self.isLiveDvrEnabled = data.get('isLiveDvrEnabled', False)
            self.private = data.get('isPrivate', False)
            self.isLowLatencyLiveStream = data.get('isLowLatencyLiveStream', False)
            try:
                self.latencyClass = latencyType[data.get('latencyClass')]
            except KeyError:
                self.latencyClass = latencyType.NORMAL
            types = {
                "NORMAL": "普通(~7s+)",
                "LOW": "低延迟(~4-6s) [不支持 4K]",
                "ULTRALOW": "超低延迟(~1-3s) [不支持字幕, 1440p 和 4K]"
            }
            self.latencyText = types.get(str(self.latencyClass.value), "无法显示")
        self.update(extra_data)

    def update(self, extra_data: dict):
        extra_data = extra_data.get("playerMicroformatRenderer", extra_data)
        update = extra_data.get("title")
        if update:
            self.title = get_text(update)
        update = extra_data.get("lengthSeconds")
        if update:
            self.lengthSeconds = int(update)
        update = extra_data.get("thumbnail", {}).get("thumbnails")
        if update:
            self.thumbnail = update[len(update) - 1]['url']
        # Extra basic info
        update = extra_data.get("isUnlisted") is not None
        if update:
            self.isUnlisted = update
        # View count info
        update = extra_data.get("viewCount")
        if update:
            self.viewCount = update
        update = extra_data.get("liveBroadcastDetails")
        if update:
            self.broadcastDetails = update
            self.isLive = self.broadcastDetails['isLiveNow']
            # Format of startTimestamp / endTimestamp : "%Y-%m-%dT%H:%M:%S%z"


class playerResponse:
    js_url: str
    responseContext: responseContext
    playabilityStatus: playabilityStatus
    videoDetails: Optional[videoDetails] = None
    streamData: Optional[streamingData] = None

    def __init__(self, player_response: dict, js_url: str):
        self.js_url = js_url
        self.responseContext = responseContext(player_response.get('responseContext'))
        self.playabilityStatus = playabilityStatus(player_response.get('playabilityStatus'))
        update = player_response.get('videoDetails')
        if update:
            self.videoDetails = videoDetails(update, player_response['microformat'])
        update = player_response.get('streamingData')
        if update:
            self.streamData = streamingData(update, js_url)

    def raise_for_status(self):
        status, reason, sub_reason = (self.playabilityStatus.status, self.playabilityStatus.reason,
                                      self.playabilityStatus.subreason or "")
        # reason (sub-reason) > status
        if self.streamData and status not in ('UNPLAYABLE', "LIVE_STREAM_OFFLINE"):  # Skip if there's available stream
            return
        for error in error_reasons:
            if (
                    len(error) == 2 and reason.lower().find(error[1].lower()) != -1 or  # reason only
                    len(error) == 3 and sub_reason.lower().find(error[2].lower()) != -1 and  # with sub-reason
                    len(error) == 3 and reason != "" and reason.lower().find(error[1].lower()) == -1
            ):
                raise error[0]
        if reason.find("member") != -1:  # Members
            if reason.find("higher") != -1:
                raise MembersOnly(reason)
            else:
                raise MembersOnly
        # status
        if status == 'LIVE_STREAM_OFFLINE':
            if 'moment' not in reason and not self.playabilityStatus.scheduled_start_time:
                raise LiveStreamOffline
        elif status != "OK":
            raise VideoUnavailable

    def update(self, update_items: dict):
        update = update_items.get('playabilityStatus')
        if update:
            self.playabilityStatus.update(update)
        update = update_items.get('responseContext')
        if update:
            self.responseContext.update(update)
        if update_items.get('streamingData'):
            if self.streamData:
                self.streamData.update(update, self.js_url)
            else:
                self.streamData = streamingData(update_items['streamingData'], self.js_url)
            update = update_items.get("microformat")
        if update:
            if self.videoDetails:
                self.videoDetails.update(update)
            else:
                self.videoDetails = videoDetails(update_items.get("videoDetails"), update_items['microformat'])
