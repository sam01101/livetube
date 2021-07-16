"""
    livetube - A API for youtube streaming
    Author: Sam
    Created: 2020/12/18 12:59
    File:    regex.py
    Description: 
"""
import re

from livetube.util.exceptions import RegexMatchError


def regex_search(pattern: str, string: str, group: int) -> str:
    """Shortcut method to search a string for a given pattern.

    :param str pattern:
        A regular expression pattern.
    :param str string:
        A target string to search.
    :param int group:
        Index of group to return.
    :rtype:
        str or tuple
    :returns:
        Substring pattern matches or None if not found.
    """
    regex = re.compile(pattern)
    results = regex.search(string)
    if not results:
        raise RegexMatchError(caller="regex_search", pattern=pattern)

    return results.group(group)
