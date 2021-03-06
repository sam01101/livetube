"""
    livetube - A API for youtube streaming
    Author: Sam
    Created: 2020/12/18 13:15
    File:    exceptions.py
    Description: 
"""
from re import Pattern
from typing import Union


class LivetubeError(Exception):
    """Base pytube exception that all others inherent.

    This is done to not pollute the built-in exceptions, which *could* result
    in unintended errors being unexpectedly and incorrectly handled within
    implementers code.
    """


class ExtractError(LivetubeError):
    """Data extraction based exception."""


class NetworkError(LivetubeError):
    """Network based exception."""


class HTMLParseError(ExtractError):
    """HTML could not be parsed"""


class RegexMatchError(ExtractError):
    """Regex pattern did not return any matches."""

    def __init__(self, caller: str, pattern: Union[str, Pattern]):
        """
        :param str caller:
            Calling function
        :param str pattern:
            Pattern that failed to match
        """
        super().__init__(f"{caller}: could not find match for {pattern}")
        self.caller = caller
        self.pattern = pattern


class LiveStreamOffline(LivetubeError):
    """Live stream offline."""


class VideoUnavailable(LivetubeError):
    """Video is unavailable."""


class PaymentRequired(LivetubeError):
    """Video needs to pay before able to watch."""


class VideoPrivate(ExtractError):
    """Video is private"""


class RecordingUnavailable(ExtractError):
    pass


class MembersOnly(LivetubeError):
    """Video is members-only.

    YouTube has special videos that are only viewable to users who have
    subscribed to a content creator.
    ref: https://support.google.com/youtube/answer/7544492?hl=en
    """


class LoginRequired(LivetubeError):
    """This video needs to login before parsing"""


class AccountBanned(LivetubeError):
    """The youtube account associated with the video has been banned"""


class VideoRegionBlocked(ExtractError):
    """Reversed"""
