"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 12:56
    文件:    js.py
    文件描述: 
"""
from collections import OrderedDict
from urllib.parse import quote, urlencode

from .excpetions import RegexMatchError, HTMLParseError
from .parser import parse_for_object
from .player import get_ytplayer_js, get_ytplayer_config


def js_url(html: str) -> str:
    """Get the base JavaScript url.

    Construct the base JavaScript url, which contains the decipher
    "transforms".

    :param str html:
        The html contents of the watch page.
    """
    try:
        base_js = get_ytplayer_config(html)['assets']['js']
    except (KeyError, RegexMatchError):
        base_js = get_ytplayer_js(html)
    return "https://youtube.com" + base_js


def initial_data(watch_html: str) -> dict:
    """Extract the ytInitialData json from the watch_html page.

    This mostly contains metadata necessary for rendering the page on-load,
    such as video information, copyright notices, etc.

    :param: watch_html: Html of the watch page
    :return:
    """
    patterns = [
        r"window\[['\"]ytInitialData['\"]]\s*=\s*",
        r"ytInitialData\s*=\s*"
    ]
    for pattern in patterns:
        try:
            return parse_for_object(watch_html, pattern)
        except HTMLParseError:
            pass

    raise RegexMatchError(caller='initial_data', pattern='initial_data_pattern')


def video_info_url(video_id: str, watch_url: str) -> str:
    """Construct the video_info url.

    :param str video_id:
        A YouTube video identifier.
    :param str watch_url:
        A YouTube watch url.
    :rtype: str
    :returns:
        :samp:`https://youtube.com/get_video_info` with necessary GET
        parameters.
    """
    params = OrderedDict(
        [
            ("video_id", video_id),
            ("eurl", quote(watch_url)),
            ("hl", "en_US"),
            ("cpn", "PInLukK97Gqrbq8W"),
        ]
    )
    return "https://youtube.com/get_video_info?" + urlencode(params)
