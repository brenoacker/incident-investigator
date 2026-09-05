from __future__ import annotations

import uuid
from datetime import datetime

from incident_investigation_harness.notifications import (
    NotificationDeliveryResult,
    NotificationMessage,
    NotificationQueue,
    NotificationRequest,
    NotificationRequestCreate,
    NotificationRequestRepository,
    NotificationStatus,
)


class InMemoryNotificationRequestRepository(NotificationRequestRepository):
    """Ephemeral notification state for deterministic local scenario fixtures."""

    def __init__(self) -> None:
        self.requests: dict[uuid.UUID, NotificationRequest] = {}

    def create(self, request: NotificationRequestCreate) -> NotificationRequest:
        created = NotificationRequest(
            id=uuid.uuid4(),
            ticket_id=request.ticket_id,
            recipient_email=request.recipient_email,
            status=NotificationStatus.PENDING,
            created_at=datetime.now().astimezone(),
            investigation_context=request.investigation_context,
        )
        self.requests[created.id] = created
        return created

    def get(self, request_id: uuid.UUID) -> NotificationRequest | None:
        return self.requests.get(request_id)

    def list_by_investigation_run_id(
        self, investigation_run_id: uuid.UUID
    ) -> list[NotificationRequest]:
        return [
            request
            for request in self.requests.values()
            if request.investigation_context.investigation_run_id == investigation_run_id
        ]

    def mark_delivered(
        self,
        request_id: uuid.UUID,
        result: NotificationDeliveryResult,
        delivered_at: datetime,
    ) -> NotificationRequest:
        request = self.requests[request_id].model_copy(
            update={
                "status": NotificationStatus.DELIVERED,
                "delivery_result": result,
                "delivered_at": delivered_at,
            }
        )
        self.requests[request_id] = request
        return request


class InMemoryNotificationQueue(NotificationQueue):
    """Ephemeral FIFO queue for deterministic local scenario fixtures."""

    def __init__(self) -> None:
        self.messages: list[NotificationMessage] = []

    def publish(self, message: NotificationMessage) -> None:
        self.messages.append(message)

    def pop(self) -> NotificationMessage | None:
        return self.messages.pop(0) if self.messages else None

    def depth(self) -> int:
        return len(self.messages)
