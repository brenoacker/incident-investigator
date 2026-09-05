from typing import cast

from fastapi import Request

from incident_investigation_harness.tickets import TicketRepository


def get_ticket_repository(request: Request) -> TicketRepository:
    repository = getattr(request.app.state, "ticket_repository", None)
    if repository is None:
        raise RuntimeError("ticket repository has not been initialized")
    return cast(TicketRepository, repository)
