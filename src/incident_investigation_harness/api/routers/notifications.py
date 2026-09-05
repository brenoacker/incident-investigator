from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from incident_investigation_harness.api.dependencies import (
    get_notification_queue,
    get_notification_request_repository,
    get_ticket_repository,
)
from incident_investigation_harness.notifications import (
    NotificationQueue,
    NotificationRequest,
    NotificationRequestNotFound,
    NotificationRequestRepository,
    find_notification_request,
    request_notification,
)
from incident_investigation_harness.tickets import TicketNotFound, TicketRepository

router = APIRouter(tags=["notifications"])


@router.post(
    "/tickets/{ticket_id}/notifications",
    status_code=201,
    response_model=NotificationRequest,
)
def post_notification_request(
    ticket_id: UUID,
    ticket_repository: TicketRepository = Depends(get_ticket_repository),
    request_repository: NotificationRequestRepository = Depends(
        get_notification_request_repository
    ),
    queue: NotificationQueue = Depends(get_notification_queue),
) -> NotificationRequest:
    try:
        return request_notification(
            ticket_repository, request_repository, queue, ticket_id
        )
    except TicketNotFound as error:
        raise HTTPException(status_code=404, detail="ticket not found") from error


@router.get(
    "/notification-requests/{request_id}",
    status_code=200,
    response_model=NotificationRequest,
)
def get_notification_request(
    request_id: UUID,
    repository: NotificationRequestRepository = Depends(
        get_notification_request_repository
    ),
) -> NotificationRequest:
    try:
        return find_notification_request(repository, request_id)
    except NotificationRequestNotFound as error:
        raise HTTPException(
            status_code=404, detail="notification request not found"
        ) from error


@router.get(
    "/notification-requests", status_code=200, response_model=list[NotificationRequest]
)
def list_notification_requests(
    investigation_run_id: UUID = Query(...),
    repository: NotificationRequestRepository = Depends(
        get_notification_request_repository
    ),
) -> list[NotificationRequest]:
    return repository.list_by_investigation_run_id(investigation_run_id)
