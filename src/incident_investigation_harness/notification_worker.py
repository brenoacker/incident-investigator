from __future__ import annotations

import asyncio

from incident_investigation_harness.adapters.notification_provider import (
    LocalNotificationProvider,
)
from incident_investigation_harness.adapters.postgres import (
    PostgresNotificationRequestRepository,
    PostgresTicketRepository,
    database_url,
)
from incident_investigation_harness.adapters.redis import RedisNotificationQueue, redis_url
from incident_investigation_harness.notifications import NotificationWorker


async def run_worker() -> None:
    ticket_repository = PostgresTicketRepository(database_url())
    ticket_repository.initialize()
    request_repository = PostgresNotificationRequestRepository(database_url())
    request_repository.initialize()
    queue = RedisNotificationQueue(redis_url())
    provider = LocalNotificationProvider()
    worker = NotificationWorker(request_repository, queue, provider)
    await worker.run_forever()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
