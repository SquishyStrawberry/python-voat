#!/usr/bin/env python3
import time
import requests
from collections import namedtuple
from datetime import datetime
from py_voat.exceptions import *
from py_voat.constants import raw_url
from py_voat.helpers import handle_code

# placeholders while I implement actual classes
Message = namedtuple("Message", "title content author id")


class VoatObject(object):
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    @classmethod
    def from_dict(cls, json_data, voat_instance=None):
        return cls(voat=voat_instance, **json_data)


# noinspection PyAttributeOutsideInit
class AuthToken(object):
    """
    Small holder class for Voat's Auth Tokens.
    Built to be able to raise an exception when a token is expired.
    """

    def __init__(self, username, token, token_type, expiry_date):
        if isinstance(expiry_date, str):
            if expiry_date.isdigit():
                expiry_date = int(expiry_date)
        if not isinstance(expiry_date, int):
            raise VoatBadExpiry("Bad expiry date, must be int!")
        self.username = username
        self.expiry_date = expiry_date
        self.gotten_at = time.time()
        self.token_type = token_type
        self.token = token

    @classmethod
    def get_auth(cls, username, password, api_key):
        req = requests.post(raw_url + "/api/token",
                            headers={
                                "Voat-ApiKey": api_key,
                                "Content-Type": "application/x-www-form-urlencoded"
                            },
                            data={
                                "grant_type": "password",
                                "username": username,
                                "password": password
                            })
        if req.ok:
            req_json = req.json()
            return cls(req_json["userName"],
                       req_json["access_token"],
                       req_json["token_type"],
                       req_json["expires_in"])
        else:
            handle_code(req.status_code)

    @property
    def token(self):
        if time.time() >= self.gotten_at + self.expiry_date:
            raise VoatExpiredToken("This token is expired!")
        else:
            return self._token

    @token.setter
    def token(self, val):
        self._token = val

    @property
    def headers(self):
        return {
            "Authorization": "{} {}".format(self.token_type.capitalize(),
                                            self.token)
        }


class Submission(VoatObject):
    """
    Holder class for Voat Submissions.
    Can be either generated by hand, or with Submission.from_dict
    """

    def __init__(self, **kwargs):
        """
        Initializes a Submission instance.
        Args were chosen to be KwArgs as they would otherwise be too long.
        Here is a list of what is used in Submission.from_dict:
            * title: The title of the post, obviously.
            * content: Either the content of the post, or the url it links to.
            * comments: The comments of the post, that are actually fetched later.
            * author: Who posted the post.
            * id: The UNIQUE id of the post.
            * subverse: The subverse in which it was posted
            * karma: How many upvotes the post has.
            * views: How many times the post has been viewed.
            * date: A datetime.datetime instance of when the post was posted.
            * voat: An instance of Voat.
            * is_url: If the post's content is text or a link.
        """
        super().__init__(**kwargs)
        self._comments = None

    @classmethod
    def from_dict(cls, json_data, voat_instance=None):
        date = json_data.get("date") or None
        if date is not None:
            # I need to figure out a way to get the format second.microsecond
            datetime.strptime(date.split(".")[0], "%Y-%m-%dT%H:%M:%S")
        inst = cls(title=json_data.get("title", ""),
                   content=json_data.get("content", ""),
                   comments=None,  # No way to get comments from JSON.
                   author=json_data.get("userName", ""),
                   post_id=json_data.get("id", -1),
                   subverse=json_data.get("subverse", ""),
                   karma=json_data.get("upVotes", -1),
                   views=json_data.get("views", -1),
                   date=date,
                   voat=voat_instance,
                   is_url=bool(json_data.get("url")))
        return inst

    @property
    def comments(self):
        if getattr(self, "_comments", None) is None:
            if getattr(self, "voat", None) is not None:
                self._comments = self.voat.fetch_comments(getattr(self, "post_id", 0),
                                                          getattr(self, "subverse", None))
            else:
                self._comments = []
        return self._comments

    @comments.setter
    def comments(self, val):
        self._comments = val


# noinspection PyAttributeOutsideInit
class Subverse(VoatObject):
    @classmethod
    def from_dict(cls, json_data, voat_instance=None):
        date = json_data.get("creationDate")
        inst = cls(title=json_data.get("title", ""),
                   name=json_data.get("name", ""),
                   nsfw=json_data.get("ratedAdult"),
                   sidebar=json_data.get("sidebar", ""),
                   date=date,
                   voat=voat_instance,
                   subscribers=json_data.get("subscriberCount", -1),
                   description=json_data.get("description", ""), )
        return inst

    @property
    def posts(self):
        if getattr(self, "_posts", None) is None:
            if getattr(self, "voat", None) is not None:
                self._posts = self.voat.get_subverse_posts(self.name)
            else:
                self._posts = []
        return self._posts

    @posts.setter
    def posts(self, val):
        self._posts = val


class Comment(VoatObject):
    @classmethod
    def from_dict(cls, json_data, voat_instance=None):
        date = json_data["date"]
        inst = cls(
            voat=voat_instance,
            comment_id=json_data["id"],
            date=date,
            content=json_data["content"],
            karma=json_data["upVotes"]-json_data["downVotes"],
            subverse=json_data["subverse"],
            author=json_data["userName"],
            parent_id=json_data["parentID"],
            submission_id=json_data["submissionID"]
        )
        return inst


    @property
    def parent(self):
        if getattr(self, "_parent", None) is None:
            if getattr(self, "voat", None) is not None and getattr(self, "parent_id", None) is not None:
                try:
                    self._parent = self.voat.get_comment(self.parent_id)
                except:
                    self._parent = self.__class__()
            else:
                self._parent = self.__class__()
        return self._parent

    @property
    def children(self):
        if getattr(self, "_children", None) is None:
            if getattr(self, "submission_id", None) is not None and getattr(self, "voat", None) is not None:
                comments = self.voat.fetch_comments(self.submission_id, getattr(self, "subverse", None))
                self._children = [i for i in comments if getattr(i, "parent_id", None) == self.comment_id]
            else:
                self._children = []
        return self._children
