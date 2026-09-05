from __future__ import annotations

from incident_investigation_harness.notifications import (
    NotificationDelivery,
    NotificationDeliveryResult,
)


class LocalNotificationProvider:
    """Local notification dependency used by the worker."""

    def __init__(self) -> None:
        self.deliveries: list[str] = []

    def deliver(self, recipient_email: str) -> NotificationDelivery:
        self.deliveries.append(recipient_email)
        return NotificationDelivery(result=NotificationDeliveryResult.ACCEPTED)
