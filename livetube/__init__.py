"""
    livetube - A API for youtube streaming
    Author: Sam
    Created: 2020/12/18 10:18
    File:    __init__.py
"""
__title__ = "livetube"
__author__ = "Sam"

import asyncio

try:
    import uvloop  # noqa

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ModuleNotFoundError:
    pass

from livetube.__main__ import Video, Membership, Community, Studio
from livetube.util.exceptions import *

__all__ = [
    # Objects
    "Video", "Membership", "Community", "Studio",
    # Base error
    "LivetubeError", "ExtractError",
    # Errors
    "NetworkError", "HTMLParseError", "RegexMatchError", "LiveStreamOffline",
    "VideoUnavailable", "PaymentRequired", "VideoPrivate", "RecordingUnavailable",
    "MembersOnly", "LoginRequired", "AccountBanned", "VideoRegionBlocked"
]
