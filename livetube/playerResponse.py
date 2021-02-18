"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 15:57
    文件:    playerResponse.py
    文件描述: 
"""
from enum import Enum
from typing import Optional, Dict

from .util.excpetions import MembersOnly, RecordingUnavailable, VideoUnavailable, LiveStreamOffline, VideoPrivate, \
    RegexMatchError, VideoRegionBlocked, PaymentRequired
from .util.js import query_selector
from .util.regex import regex_search


def extract_string(data: dict):
    if text := data.get("simpleText"):
        return text
    elif flows := data.get("runs"):
        text = ""
        for flow in flows:
            if "<" not in flow['text']:
                text += flow['text']
        return text


class latencyType(Enum):
    MDE_STREAM_OPTIMIZATIONS_RENDERER_LATENCY_NORMAL = "NORMAL"
    MDE_STREAM_OPTIMIZATIONS_RENDERER_LATENCY_LOW = "LOW"
    MDE_STREAM_OPTIMIZATIONS_RENDERER_LATENCY_ULTRA_LOW = "ULTRALOW"
    NORMAL = "NORMAL"
    LOW = "LOW"
    ULTRALOW = "ULTRALOW"


class responseContext:
    serviceTrackingParams: list
    is_viewed_live: bool
    logged_in: bool

    def __init__(self, data: dict):
        FEEDBACK: list
        self.serviceTrackingParams = data.get('serviceTrackingParams')
        if self.serviceTrackingParams:
            FEEDBACK = self.serviceTrackingParams[0]['params']
            self.is_viewed_live = FEEDBACK[0]['value']
            self.logged_in = FEEDBACK[1]['value']


# last_reason

class playabilityStatus:
    status: str
    reason: str
    playableInEmbed: bool
    subreason: Optional[str] = None
    last_reason: Optional[str] = None
    pollDelayMs: int = 5000
    isCountDown = False
    isPremiere: bool = False
    scheduled_start_time: Optional[int] = None

    def __init__(self, data: dict):
        self.status = data.get("status", "UNPLAYABLE")
        self.reason = data.get("reason", "")
        self.playableInEmbed = data.get('playableInEmbed', False)
        if subreason := query_selector(data, "errorScreen/playerErrorMessageRenderer/subreason"):
            self.subreason = extract_string(subreason)
        if poll_ms := query_selector(data, "liveStreamability/liveStreamabilityRenderer/pollDelayMs"):
            self.pollDelayMs = int(poll_ms)
        if livestream_offline := query_selector(data,
                                                "liveStreamability/liveStreamabilityRenderer/offlineSlate/liveStreamOfflineSlateRenderer"):
            self.isCountDown = livestream_offline.get("canShowCountdown", False)
            if scheduled_start_time := livestream_offline.get("scheduledStartTime"):
                self.scheduled_start_time = int(scheduled_start_time)


class streamingData:
    expiresInSeconds: int
    hlsManifestUrl: str
    dashManifestUrl: str
    expireTimestamp: int
    audios: Dict[str, dict]
    videos: Dict[str, dict]

    def __init__(self, data: dict):
        if data.get('expiresInSeconds'):
            self.expiresInSeconds = int(data.get('expiresInSeconds'))
            self.hlsManifestUrl = data.get('hlsManifestUrl')
            self.dashManifestUrl = data.get('dashManifestUrl')
            # Get timestamp of expire time
            if fmt_link := (self.hlsManifestUrl or self.dashManifestUrl):
                try:
                    self.expireTimestamp = int(regex_search(r"/expire/(\d+)/", fmt_link, 1))
                except RegexMatchError:
                    pass
            adaptiveFormats: list = data.get("adaptiveFormats", [])
            self.audios = {}
            self.videos = {}
            for formats in adaptiveFormats:
                if "audio" in formats['mimeType']:
                    self.audios[formats['itag']] = formats
                elif "mp4" in formats['mimeType']:
                    self.videos[formats['itag']] = formats
            # Get best format
            bestBitrate: int = 0
            best: Optional[dict] = None
            for _, formats in self.audios.items():
                if int(formats['bitrate']) > bestBitrate:
                    bestBitrate = int(formats['bitrate'])
                    best = formats
            if best:
                self.audios['best'] = best
            bestW, bestH, bestFPS = 0, 0, 0
            best: Optional[dict] = None
            for _, formats in self.videos.items():
                w, h, fps = int(formats['width']), int(formats['height']), int(formats['fps'])
                if w >= bestW and h >= bestH and fps >= bestFPS:
                    bestW, bestH, bestFPS = w, h, fps
                    best = formats
            if best:
                self.videos['best'] = best


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
    liveViewCount: Optional[int]
    liveShortViewCount: Optional[int]
    startedSince: Optional[str]
    shortLikeCount: Optional[str]
    shortDislikeCount: Optional[str]
    isLowLatencyLiveStream: Optional[bool]
    latencyClass: latencyType
    latencyText: Optional[str]

    def __init__(self, data: Optional[dict] = None, extra_data: Optional[dict] = None):
        # Basic info
        if data:
            self.isLive = data.get("isLive", False)
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
            self.latencyText = types.get(self.latencyClass.value, "无法显示")
        self.title = extra_data['playerMicroformatRenderer']['title']['simpleText'] if extra_data else data['title']
        self.lengthSeconds = int(
            (extra_data['playerMicroformatRenderer'] if extra_data else data).get("lengthSeconds", 0))
        thumbnails = (extra_data['playerMicroformatRenderer'] if extra_data else data)['thumbnail']['thumbnails']
        self.thumbnail = thumbnails[len(thumbnails) - 1]['url']
        # Extra basic info
        if extra_data:
            self.isUnlisted = extra_data['playerMicroformatRenderer'].get('isUnlisted', False)
        # View count info
        self.viewCount = int((extra_data['playerMicroformatRenderer'] if extra_data else data).get('viewCount'), 0)
        self.liveViewCount = None
        self.liveShortViewCount = None
        self.startedSince = None
        # Like/Dislike
        self.shortLikeCount = None
        self.shortDislikeCount = None


class playerResponse:
    responseContext: responseContext
    playabilityStatus: playabilityStatus
    videoDetails: Optional[videoDetails] = None
    streamData: Optional[streamingData] = None

    def __init__(self, player_response: dict):
        self.responseContext = responseContext(player_response.get('responseContext'))
        self.playabilityStatus = playabilityStatus(player_response.get('playabilityStatus'))
        if player_response.get('videoDetails'):
            self.videoDetails = videoDetails(player_response.get('videoDetails'), player_response.get('microformat'))
            self.videoDetails.isLive = self.playabilityStatus.status == "OK" and self.playabilityStatus.reason == ""
        if player_response.get('streamingData'):
            self.streamData = streamingData(player_response.get('streamingData'))

    def raise_for_status(self):
        status, reason, subreason = self.playabilityStatus.status, self.playabilityStatus.reason, self.playabilityStatus.subreason
        if status == 'UNPLAYABLE':
            if reason == (
                    'Join this channel to get access to members-only content '
                    'like this video, and other exclusive perks.'
            ):
                raise MembersOnly
            elif reason == 'This live stream recording is not available.':
                raise RecordingUnavailable
            else:
                if reason == 'Video unavailable':
                    if subreason == 'The uploader has not made this video available in your country.':
                        raise VideoRegionBlocked
                elif reason == 'This video requires payment to watch.':
                    raise PaymentRequired
                raise VideoUnavailable
        elif status == "ERROR":
            if subreason == "This video is private.":
                raise VideoPrivate
            raise VideoUnavailable
        elif status == 'LOGIN_REQUIRED':
            if reason == (
                    'This is a private video. '
                    'Please sign in to verify that you may see it.'
            ):
                raise VideoPrivate
            raise VideoUnavailable
        elif status == 'LIVE_STREAM_OFFLINE':
            if 'moment' not in reason and not self.playabilityStatus.scheduled_start_time:
                raise LiveStreamOffline
        elif status != "OK":
            raise VideoUnavailable

    def update(self, update_items: dict):
        if update_items.get('playabilityStatus'):
            new = playabilityStatus(update_items['playabilityStatus'])
            if self.videoDetails:
                self.videoDetails.isLive = new.status == "OK" and new.reason == ""
            if new.reason != self.playabilityStatus.reason:
                self.playabilityStatus.last_reason = self.playabilityStatus.reason
            self.playabilityStatus.__dict__.update(new.__dict__)
        if update_items.get('responseContext'):
            new = responseContext(update_items['responseContext'])
            self.responseContext.__dict__.update(new.__dict__)
        if update_items.get('streamingData'):
            new = streamingData(update_items['streamingData'])
            if self.streamData:
                self.streamData.__dict__.update(new.__dict__)
            else:
                self.streamData = new
        if update_items.get("microformat"):
            new = videoDetails(None, update_items['microformat'])
            self.videoDetails.__dict__.update(new.__dict__)
