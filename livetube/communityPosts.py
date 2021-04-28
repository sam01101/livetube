from dataclasses import dataclass
from typing import Optional, Union


@dataclass
class Post:
    post_id: str
    author: "Post.Author"
    created_since: str
    likes: str
    content: str
    attach: Optional["Post.Attachment"]
    members_only: bool

    @dataclass
    class Author:
        name: str
        avatar: str
        channel_link: str

    @dataclass
    class Attachment:
        # video, image, poll
        attach_type: str
        attach: Union["Post.Attachment.Video", "Post.Attachment.Image", "Post.Attachment.Poll"]

        @dataclass
        class Video:
            video_id: str
            title: str
            length: str
            thumbnail: str
            views: str
            uploader: str
            uploaded_since: str

            def to_json(self):
                return {
                    "video_id": self.video_id,
                    "title": self.title,
                    "length": self.length,
                    "thumbnail": self.thumbnail,
                    "view_count": self.views,  # Valid or Unknown
                    "author": self.uploader,
                    "create_time": self.uploaded_since
                }

        @dataclass
        class Image:
            is_multi: bool
            images: list

            def to_json(self):
                return {
                    "is_list": self.is_multi,
                    "links": self.images
                }

        @dataclass
        class Poll:
            votes: str
            choices: list

            def to_json(self):
                return {
                    "vote_count": self.votes,
                    "choices": self.choices
                }

    def to_json(self):
        attach = {}
        if self.attach:
            attach['type'] = self.attach.attach_type
            attach['data'] = self.attach.attach.to_json()
        return {
            "type": "post",
            "post_id": self.post_id,
            "author": {
                "name": self.author.name,
                "channel": self.author.channel_link,
                "thumbnail": self.author.avatar
            },
            "text": self.content,
            "create_time": self.created_since,
            "likes": self.likes,
            "attach": attach,
            "member": self.members_only
        }


@dataclass
class SharedPost(Post):
    shared_post: Post

    def __init__(self, post_id: str, author: "Post.Author", created_since: str, post: Post,
                 text="", is_member=False):
        super().__init__(post_id, author, created_since, "", text, None, is_member)
        self.shared_post = post

    def to_json(self):
        return {
            "type": "shared_post",
            "author": {
                "name": self.author.name,
                "channel": self.author.channel_link,
                "thumbnail": self.author.avatar
            },
            "text": self.content,
            "create_time": self.created_since,
            "post": self.shared_post.to_json(),
            "member": self.members_only
        }
