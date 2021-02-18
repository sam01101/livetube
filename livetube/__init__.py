"""
    livetube - A API for youtube streaming
    作者: Sam
    创建日期: 2020/12/18 10:18
    文件:    __init__.py
    文件描述:
    Extra note: All check passed. Not even a warning
"""
__title__ = "livetube"
__author__ = "Sam"

import asyncio

try:
    # noinspection PyUnresolvedReferences
    import uvloop

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ModuleNotFoundError:
    pass

from .__main__ import Video, Community, Membership, Youtube
from .util.excpetions import *
