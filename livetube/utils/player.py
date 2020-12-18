"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 12:57
    文件:    player.py
    文件描述: 
"""
from .excpetions import HTMLParseError, RegexMatchError
from .parser import parse_for_object
from .regex import compile


def get_ytplayer_js(html: str) -> str:
    """Get the YouTube player base JavaScript path.

    :param html
        The html contents of the watch page.
    :rtype: str
    :returns:
        Path to YouTube's base.js file.
    """
    js_url_patterns = [
        r"(/s/player/[\w\d]+/[\w\d_/.]+/base\.js)"
    ]
    for pattern in js_url_patterns:
        regex = compile(pattern)
        function_match = regex.search(html)
        if function_match:
            # print("finished regex search, matched: %s" % pattern)
            yt_player_js = function_match.group(1)
            return yt_player_js

    raise RegexMatchError(
        caller="get_ytplayer_js",
        pattern="js_url_patterns"
    )


def get_ytplayer_config(html: str) -> dict:
    """Get the YouTube player configuration data from the watch html.

    Extract the ``ytplayer_config``, which is json data embedded within the
    watch html and serves as the primary source of obtaining the stream
    manifest data.

    :param str html:
        The html contents of the watch page.
    :rtype: str
    :returns:
        Substring of the html containing the encoded manifest data.
    """
    # print("finding initial function name")
    config_patterns = [
        r"ytplayer\.config\s*=\s*",
        r"ytInitialPlayerResponse\s*=\s*"
    ]
    for pattern in config_patterns:
        # Try each pattern consecutively if they don't find a match
        try:
            return parse_for_object(html, pattern)
        except HTMLParseError:
            continue

    # setConfig() needs to be handled a little differently.
    # We want to parse the entire argument to setConfig()
    #  and use then load that as json to find PLAYER_CONFIG
    #  inside of it.
    setconfig_patterns = [
        r"yt\.setConfig\(.*['\"]PLAYER_CONFIG['\"]:\s*"
    ]
    for pattern in setconfig_patterns:
        # Try each pattern consecutively if they don't find a match
        try:
            return parse_for_object(html, pattern)
        except HTMLParseError:
            continue

    raise RegexMatchError(
        caller="get_ytplayer_config",
        pattern="config_patterns, setconfig_patterns"
    )
