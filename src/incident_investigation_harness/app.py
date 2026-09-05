from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from incident_investigation_harness.adapters.postgres import (
    PostgresTicketRepository,
    database_url,
)
from incident_investigation_harness.api.routers.health import router as health_router
from incident_investigation_harness.api.routers.tickets import (
    router as tickets_router,
)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    repository = PostgresTicketRepository(database_url())
    repository.initialize()
    application.state.ticket_repository = repository
    yield


app = FastAPI(title="Incident Investigation Harness", lifespan=lifespan)
app.include_router(health_router)
app.include_router(tickets_router)
