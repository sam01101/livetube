from dataclasses import dataclass
from typing import Optional


@dataclass
class Member:
    name: str
    channel_id: str
    expired: bool
    expire_time: Optional[str]
