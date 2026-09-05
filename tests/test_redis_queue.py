from incident_investigation_harness.adapters.redis import RedisNotificationQueue


class _FakeRedis:
    def llen(self, queue_name: str) -> int:
        assert queue_name == "notifications"
        return 3


def test_redis_queue_reports_backlog_depth(monkeypatch) -> None:
    monkeypatch.setattr(
        "incident_investigation_harness.adapters.redis.redis.Redis.from_url",
        lambda *_args, **_kwargs: _FakeRedis(),
    )

    queue = RedisNotificationQueue("redis://test", queue_name="notifications")

    assert queue.depth() == 3
