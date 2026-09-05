from __future__ import annotations

import os
from typing import cast

import redis

from incident_investigation_harness.notifications import (
    NotificationMessage,
    NotificationQueue,
)


class RedisNotificationQueue(NotificationQueue):
    """Redis List adapter for the notification request queue."""

    def __init__(self, redis_url: str, queue_name: str = "notification_requests") -> None:
        self.client = redis.Redis.from_url(redis_url, decode_responses=True)
        self.queue_name = queue_name

    def publish(self, message: NotificationMessage) -> None:
        self.client.rpush(self.queue_name, message.model_dump_json())

    def pop(self) -> NotificationMessage | None:
        payload = cast(str | None, self.client.lpop(self.queue_name))
        if payload is None:
            return None
        return NotificationMessage.model_validate_json(payload)


def redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://redis:6379/0")
