from typing import cast

from fastapi import Request

from incident_investigation_harness.notifications import (
    NotificationQueue,
    NotificationRequestRepository,
)
from incident_investigation_harness.tickets import TicketRepository


def get_ticket_repository(request: Request) -> TicketRepository:
    repository = getattr(request.app.state, "ticket_repository", None)
    if repository is None:
        raise RuntimeError("ticket repository has not been initialized")
    return cast(TicketRepository, repository)


def get_notification_request_repository(request: Request) -> NotificationRequestRepository:
    repository = getattr(request.app.state, "notification_request_repository", None)
    if repository is None:
        raise RuntimeError("notification request repository has not been initialized")
    return cast(NotificationRequestRepository, repository)


def get_notification_queue(request: Request) -> NotificationQueue:
    queue = getattr(request.app.state, "notification_queue", None)
    if queue is None:
        raise RuntimeError("notification queue has not been initialized")
    return cast(NotificationQueue, queue)
