from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from incident_investigation_harness.adapters.postgres import (
    PostgresNotificationRequestRepository,
    PostgresTicketRepository,
    database_url,
)
from incident_investigation_harness.adapters.redis import RedisNotificationQueue, redis_url
from incident_investigation_harness.api.routers.health import router as health_router
from incident_investigation_harness.api.routers.tickets import (
    router as tickets_router,
)
from incident_investigation_harness.api.routers.notifications import (
    router as notifications_router,
)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    repository = PostgresTicketRepository(database_url())
    repository.initialize()
    notification_repository = PostgresNotificationRequestRepository(database_url())
    notification_repository.initialize()
    application.state.ticket_repository = repository
    application.state.notification_request_repository = notification_repository
    application.state.notification_queue = RedisNotificationQueue(redis_url())
    yield


app = FastAPI(title="Incident Investigation Harness", lifespan=lifespan)
app.include_router(health_router)
app.include_router(tickets_router)
app.include_router(notifications_router)
