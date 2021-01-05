"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 12:56
    文件:    js.py
    文件描述: 
"""
from collections import OrderedDict
from typing import Union, Optional
from urllib.parse import quote, urlencode

from .excpetions import RegexMatchError, HTMLParseError
from .parser import parse_for_object


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
            ("cpn", "PInLukK97Gqrbq8W")
        ]
    )
    return "https://youtube.com/get_video_info?" + urlencode(params)


def query_selector(path_obj: Union[dict, list], pattern: Union[str, list], results=None) -> Union[
    bool, Union[dict, list]]:
    """
    lightwight jq, see gist for why this function exists

    see https://gist.github.com/sam01101/b35da7ffad74849c2d941429c74a2365


    :param results: The total reuslt
    :param path_obj: The path
    :param pattern: The pattern of the path
    :return: The result if the path is executed successfully or False
    """
    if results is None:
        results = []
    pattern_spilt: list = pattern.split("/") if isinstance(pattern, str) else pattern
    """
    About the pattern:
    ? - Any number
    """
    try:
        last_path: Optional[Union[dict, list]] = path_obj
        test_path: Union[dict, list]
        for level, path_name in enumerate(pattern_spilt):  # type: int, str
            if path_name == "?":  # list, test for number
                if not isinstance(last_path, list):
                    return False
                last_path: list
                for test_num in range(len(last_path)):
                    if result := query_selector(last_path[test_num], pattern_spilt[level + 1:], results):
                        if id(results) == id(result):
                            continue
                        if isinstance(result, list):
                            results.append(result[0])
                        else:
                            results.append(result)
                if len(results) > 0:
                    return results
                return False
            elif path_name.isnumeric():  # list, number
                if not isinstance(last_path, list):
                    return False
                last_path = last_path[int(path_name)]
            else:  # dict
                if test_path := last_path.get(path_name):
                    last_path = test_path
                else:
                    return False
        if last_path:
            return last_path
        else:
            return False
    except (IndexError, KeyError):
        return False
