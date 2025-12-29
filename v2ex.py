import logging
from collections.abc import Iterable
from typing import Any, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field

API_BASE = "https://www.v2ex.com/api/v2"
logger = logging.getLogger(__name__)


class V2exBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Member(V2exBaseModel):
    id: int
    username: Optional[str] = None
    name: Optional[str] = None
    bio: Optional[str] = None
    website: Optional[str] = None
    github: Optional[str] = None
    url: Optional[str] = None
    avatar: Optional[str] = None
    created: Optional[int] = None
    pro: Optional[int] = None


class Node(V2exBaseModel):
    id: int
    url: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    header: Optional[str] = None
    footer: Optional[str] = None
    avatar: Optional[str] = None
    topics: Optional[int] = None
    created: Optional[int] = None
    last_modified: Optional[int] = None


class Topic(V2exBaseModel):
    id: int
    title: Optional[str] = None
    content: Optional[str] = None
    content_rendered: Optional[str] = None
    syntax: Optional[int] = None
    url: Optional[str] = None
    replies: Optional[int] = None
    last_reply_by: Optional[str] = None
    created: Optional[int] = None
    created_at: Optional[int] = None
    last_modified: Optional[int] = None
    last_touched: Optional[int] = None
    member: Optional[Member] = None
    node: Optional[Node] = None
    node_id: Optional[int] = None
    supplements: list[Any] = Field(default_factory=list)


class Reply(V2exBaseModel):
    id: int
    content: Optional[str] = None
    content_rendered: Optional[str] = None
    created: Optional[int] = None
    created_at: Optional[int] = None
    member: Optional[Member] = None


class Pagination(V2exBaseModel):
    per_page: int
    total: int
    pages: int


class ApiResponse(V2exBaseModel):
    success: bool
    message: Optional[str] = None


class TopicResponse(ApiResponse):
    result: Topic


class RepliesResponse(ApiResponse):
    result: list[Reply] = Field(default_factory=list)
    pagination: Optional[Pagination] = None


def _ensure_success(payload: dict[str, Any]) -> None:
    response = ApiResponse.model_validate(payload)
    if not response.success:
        raise RuntimeError(response.message or "V2EX API error")


def _truncate(text: str, max_chars: Optional[int]) -> str:
    if max_chars is None or len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _pick_first(*values: Any, default: str = "") -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return str(value)
    return default


class V2EXClient:
    def __init__(self, token: str, api_base: str = API_BASE) -> None:
        self.token = token
        self.api_base = api_base

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def fetch_topic(self, client: httpx.Client, topic_id: int) -> Topic:
        logger.info("Fetching V2EX topic %s", topic_id)
        response = client.get(
            f"{self.api_base}/topics/{topic_id}",
            headers=self._headers(),
            timeout=20.0,
        )
        logger.info("V2EX topic response status=%s", response.status_code)
        logger.debug("V2EX topic response body=%s", response.text)
        response.raise_for_status()
        payload = response.json()
        _ensure_success(payload)
        return TopicResponse.model_validate(payload).result

    def fetch_replies(
        self,
        client: httpx.Client,
        topic_id: int,
        max_pages: int,
        max_replies: Optional[int],
    ) -> list[Reply]:
        replies: list[Reply] = []
        page = 1
        while page <= max_pages:
            logger.info("Fetching V2EX replies topic=%s page=%s", topic_id, page)
            response = client.get(
                f"{self.api_base}/topics/{topic_id}/replies",
                headers=self._headers(),
                params={"p": page},
                timeout=20.0,
            )
            logger.info("V2EX replies response status=%s page=%s", response.status_code, page)
            logger.debug("V2EX replies response body page=%s body=%s", page, response.text)
            response.raise_for_status()
            payload = response.json()
            _ensure_success(payload)
            reply_response = RepliesResponse.model_validate(payload)
            data = reply_response.result
            if not data:
                break
            replies.extend(data)
            if max_replies is not None and len(replies) >= max_replies:
                replies = replies[:max_replies]
                break
            page += 1
        return replies

    def format_topic(self, topic: Topic, max_chars: Optional[int]) -> str:
        title = _pick_first(topic.title)
        content = _pick_first(topic.content, topic.content_rendered)
        node = _pick_first(
            topic.node.title if topic.node else None,
            topic.node.name if topic.node else None,
            topic.node_id,
        )
        author = _pick_first(
            topic.member.username if topic.member else None,
            topic.member.name if topic.member else None,
            topic.member.id if topic.member else None,
        )
        created = _pick_first(topic.created, topic.created_at)
        return "\n".join(
            [
                f"Title: {title}",
                f"Author: {author}",
                f"Node: {node}",
                f"Created: {created}",
                f"Content:\n{_truncate(content, max_chars)}",
            ]
        ).strip()

    def format_replies(
        self,
        replies: Iterable[Reply],
        max_chars: Optional[int],
    ) -> str:
        lines: list[str] = []
        for idx, reply in enumerate(replies, start=1):
            author = _pick_first(
                reply.member.username if reply.member else None,
                reply.member.name if reply.member else None,
                reply.member.id if reply.member else None,
            )
            created = _pick_first(reply.created, reply.created_at)
            content = _pick_first(reply.content, reply.content_rendered)
            block = "\n".join(
                [
                    f"[{idx}] Author: {author}",
                    f"Created: {created}",
                    f"Content:\n{_truncate(content, max_chars)}",
                ]
            )
            lines.append(block)
        return "\n\n".join(lines).strip()

    def build_bundle(self, topic_id: int, max_pages: int) -> str:
        with httpx.Client() as client:
            topic = self.fetch_topic(client, topic_id)
            replies = self.fetch_replies(
                client,
                topic_id,
                max_pages=max_pages,
                max_replies=None,
            )
        topic_text = self.format_topic(topic, None)
        replies_text = self.format_replies(replies, None)
        return "\n\n".join(
            [
                "文章内容（主题）:",
                topic_text or "N/A",
                "",
                "评论:",
                replies_text or "No replies.",
            ]
        ).strip()
