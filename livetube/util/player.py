"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 12:57
    文件:    player.py
    文件描述: 
"""
import json
import re

from .exceptions import HTMLParseError, RegexMatchError
from .parser import parse_for_object


def get_ytplayer_resp(scripts: list) -> dict:
    """Get the YouTube player response data from the watch html js.

    Extract the ``ytplayer_config``, which is json data embedded within the
    watch html and serves as the primary source of obtaining the stream
    manifest data.

    :param str scripts:
        The html script content of the watch page.
    :rtype: str
    :returns:
        Substring of the html containing the encoded manifest data.
    """
    config_patterns = [
        r"ytInitialPlayerResponse\s*=\s*"
    ]
    for script in scripts:
        for pattern in config_patterns:
            # Try each pattern consecutively if they don't find a match
            try:
                return parse_for_object(script, pattern)
            except HTMLParseError:
                continue

    raise RegexMatchError(
        caller="get_ytplayer_resp",
        pattern="config_patterns, setconfig_patterns"
    )


def get_ytplayer_setconfig(scripts: list) -> dict:
    """Get the YouTube player configuration data from the watch html.

    Extract the ``ytplayer_config``, which is json data embedded within the
    watch html and serves as the primary source of obtaining the stream
    manifest data.

    :param str scripts:
        The html script contents of the watch page.
    :rtype: str
    :returns:
        Substring of the html containing the encoded manifest data.
    """
    setconfig_patterns = [
        r'ytcfg\.set\(({.+?})\);.+setMessage',
        r"yt\.setConfig\(.*['\"]PLAYER_CONFIG['\"]:\s*"
    ]
    for script in scripts:
        for pattern in setconfig_patterns:
            # Try each pattern consecutively if they don't find a match
            try:
                regex = re.compile(pattern)
                result = regex.search(script)
                if not result:
                    continue
                return json.loads(result.group(1))
            except (HTMLParseError, json.JSONDecodeError):
                continue

    raise RegexMatchError(
        caller="get_ytplayer_setconfig",
        pattern="config_patterns, setconfig_patterns"
    )
