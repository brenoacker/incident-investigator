from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from incident_investigation_harness.notifications import (
    NotificationDelivery,
    NotificationDeliveryResult,
)


class ProviderFaultProfile(BaseModel):
    """Deterministic failures to inject into one provider scenario."""

    model_config = ConfigDict(frozen=True)

    rate_limit_attempts: int = Field(default=0, ge=0)


class ProviderAttempt(BaseModel):
    """Read-only record of one request received by the local provider."""

    model_config = ConfigDict(frozen=True)

    order: int = Field(gt=0)
    recipient_email: str
    status_code: int
    result: NotificationDeliveryResult


class LocalNotificationProvider:
    """Local notification dependency used by the worker."""

    def __init__(self) -> None:
        self.deliveries: list[str] = []
        self._attempts: list[ProviderAttempt] = []
        self._fault_profile = ProviderFaultProfile()

    @property
    def attempts(self) -> tuple[ProviderAttempt, ...]:
        """Return the attempts observed in the current scenario."""
        return tuple(self._attempts)

    def configure_fault_profile(self, profile: ProviderFaultProfile) -> None:
        """Start a scenario with the supplied deterministic fault profile."""
        self._fault_profile = profile
        self._attempts.clear()
        self.deliveries.clear()

    def reset(self) -> None:
        """Restore normal responses and discard the current scenario state."""
        self._fault_profile = ProviderFaultProfile()
        self._attempts.clear()
        self.deliveries.clear()

    def deliver(self, recipient_email: str) -> NotificationDelivery:
        self.deliveries.append(recipient_email)
        order = len(self._attempts) + 1
        if order <= self._fault_profile.rate_limit_attempts:
            delivery = NotificationDelivery(
                result=NotificationDeliveryResult.RATE_LIMITED,
                status_code=429,
            )
        else:
            delivery = NotificationDelivery(
                result=NotificationDeliveryResult.ACCEPTED,
                status_code=202,
            )
        self._attempts.append(
            ProviderAttempt(
                order=order,
                recipient_email=recipient_email,
                status_code=delivery.status_code,
                result=delivery.result,
            )
        )
        return delivery
