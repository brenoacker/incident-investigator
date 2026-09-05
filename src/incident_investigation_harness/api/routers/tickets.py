from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from incident_investigation_harness.api.dependencies import get_ticket_repository
from incident_investigation_harness.tickets import (
    Ticket,
    TicketCreate,
    TicketNotFound,
    TicketRepository,
    create_ticket,
    find_ticket,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", status_code=201, response_model=Ticket)
def post_ticket(
    ticket: TicketCreate,
    repository: TicketRepository = Depends(get_ticket_repository),
) -> Ticket:
    return create_ticket(repository, ticket)


@router.get("/{ticket_id}", status_code=200, response_model=Ticket)
def get_ticket(
    ticket_id: UUID,
    repository: TicketRepository = Depends(get_ticket_repository),
) -> Ticket:
    try:
        return find_ticket(repository, ticket_id)
    except TicketNotFound as error:
        raise HTTPException(status_code=404, detail="ticket not found") from error
