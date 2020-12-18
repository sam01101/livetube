"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 15:57
    文件:    playerResponse.py
    文件描述: 
"""
from enum import Enum
from typing import Optional, Dict

from .util.excpetions import MembersOnly, RecordingUnavailable, VideoUnavailable, LiveStreamOffline, VideoPrivate


class responseContext:
    def __init__(self, data: dict):
        self.serviceTrackingParams: list = data.get('serviceTrackingParams')
        FEEDBACK: list = self.serviceTrackingParams[0]['params']
        self.is_viewed_live: bool = FEEDBACK[0]['value']
        self.logged_in: bool = FEEDBACK[1]['value']


class playabilityStatus:
    def __init__(self, data: dict):
        self.status: str = data.get("status", "UNPLAYABLE")
        self.reason: str = data.get("reason", "")
        self.playableInEmbed: bool = data.get('playableInEmbed', False)
        if liveStreamability := data.get('liveStreamability'):
            if liveStreamabilityRenderer := liveStreamability.get("liveStreamabilityRenderer"):
                self.pollDelayMs: int = liveStreamabilityRenderer.get("pollDelayMs", 5000)
                if offlineSlate := liveStreamabilityRenderer.get("offlineSlate"):
                    self.isCountDown = offlineSlate['liveStreamOfflineSlateRenderer'].get("canShowCountdown", False)
                    self.scheduled_start_time: int = int(
                        offlineSlate['liveStreamOfflineSlateRenderer']['scheduledStartTime'])


class streamingData:
    def __init__(self, data: dict):
        if data.get('expiresInSeconds'):
            self.expiresInSeconds: int = data.get('expiresInSeconds')
            adaptiveFormats: list = data.get("adaptiveFormats", [])
            self.audios: Dict[str, dict] = {}
            self.videos: Dict[str, dict] = {}
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
            self.hlsManifestUrl: str = data.get('hlsManifestUrl')


class latencyType(Enum):
    MDE_STREAM_OPTIMIZATIONS_RENDERER_LATENCY_NORMAL = "NORMAL"
    MDE_STREAM_OPTIMIZATIONS_RENDERER_LATENCY_LOW = "LOW"
    MDE_STREAM_OPTIMIZATIONS_RENDERER_LATENCY_ULTRA_LOW = "ULTRALOW"
    NORMAL = "NORMAL"
    LOW = "LOW"
    ULTRALOW = "ULTRALOW"


class videoDetails:
    def __init__(self, data: dict):
        self.video_id: str = data.get('videoId')
        self.channel_id: str = data.get('channelId')
        self.channel_name: str = data.get('author')
        self.title: str = data.get("title", "")
        self.lengthSeconds: int = data.get("lengthSeconds", -1)
        self.isLive: bool = data.get('isLive', False)
        self.keywords: list = data.get('keywords', [])
        self.shortDescription: str = data.get('shortDescription', "")
        self.isLiveDvrEnabled: bool = data.get('isLiveDvrEnabled', False)
        thumbnails: list = data.get('thumbnail', {}).get("thumbnails", [])
        self.thumbnail: str = thumbnails[len(thumbnails) - 1]['url']
        # View count info
        self.viewCount: int = int(data.get('viewCount'))
        self.liveViewCount: Optional[int] = None
        self.liveShortViewCount: Optional[str] = None
        self.startedSince: Optional[str] = None
        # Like/Dislike
        self.shortLikeCount: Optional[str] = None
        self.shortDislikeCount: Optional[str] = None
        self.private: bool = data.get('isPrivate', False)
        self.isLowLatencyLiveStream: bool = data.get('isLowLatencyLiveStream', False)
        if self.isLowLatencyLiveStream:
            types = {
                "NORMAL": "普通(~7s+)",
                "LOW": "低延迟(~4-6s) [不支持 4K]",
                "ULTRALOW": "超低延迟(~1-3s) [不支持字幕, 1440p 和 4K]"
            }
            self.latencyClass: latencyType = latencyType[data.get('latencyClass')]
            self.latencyText: str = types.get(self.latencyClass.value, "无法显示")


class playerResponse:
    def __init__(self, player_response: dict):
        self.responseContext = responseContext(player_response.get('responseContext'))
        self.playabilityStatus = playabilityStatus(player_response.get('playabilityStatus'))
        allUnavalible = player_response.get('videoDetails') and player_response.get('streamData')
        if player_response.get('videoDetails'):
            self.videoDetails = videoDetails(player_response.get('videoDetails'))
        if player_response.get('streamingData'):
            self.streamData = streamingData(player_response.get('streamingData'))
        elif allUnavalible:
            status, reason = self.playabilityStatus.status, self.playabilityStatus.reason
            if status == 'UNPLAYABLE':
                if reason == (
                        'Join this channel to get access to members-only content '
                        'like this video, and other exclusive perks.'
                ):
                    raise MembersOnly
                elif reason == 'This live stream recording is not available.':
                    raise RecordingUnavailable
                else:
                    # if reason == 'Video unavailable':
                    #     if extract.is_region_blocked(self.watch_html):
                    #         raise VideoRegionBlocked(video_id=self.video_id)
                    raise VideoUnavailable
            elif status == 'LOGIN_REQUIRED':
                if reason == (
                        'This is a private video. '
                        'Please sign in to verify that you may see it.'
                ):
                    raise VideoPrivate
                raise VideoUnavailable
            elif status == 'LIVE_STREAM_OFFLINE':
                if 'monent' not in reason:
                    pass
                else:
                    raise LiveStreamOffline

    def update(self, update_items: dict):
        if update_items.get('playabilityStatus'):
            self.playabilityStatus.__dict__.update(update_items.get('playabilityStatus'))
        if update_items.get('responseContext'):
            self.responseContext.__dict__.update(update_items.get('responseContext'))
        if update_items.get('streamingData'):
            self.streamData.__dict__.update(update_items.get('streamingData'))