from incident_investigation_harness.adapters.notification_provider import (
    LocalNotificationProvider,
    ProviderAttempt,
    ProviderFaultProfile,
)
from incident_investigation_harness.notifications import NotificationDeliveryResult


def test_provider_accepts_delivery_and_records_attempt() -> None:
    provider = LocalNotificationProvider()

    delivery = provider.deliver("oncall@example.com")

    assert delivery.status_code == 202
    assert delivery.result == NotificationDeliveryResult.ACCEPTED
    assert provider.attempts == (
        ProviderAttempt(
            order=1,
            recipient_email="oncall@example.com",
            status_code=202,
            result=NotificationDeliveryResult.ACCEPTED,
        ),
    )


def test_provider_returns_configured_rate_limits_in_order() -> None:
    provider = LocalNotificationProvider()
    provider.configure_fault_profile(ProviderFaultProfile(rate_limit_attempts=2))

    first = provider.deliver("oncall@example.com")
    second = provider.deliver("oncall@example.com")
    third = provider.deliver("oncall@example.com")

    assert [first.status_code, second.status_code, third.status_code] == [429, 429, 202]
    assert [attempt.result for attempt in provider.attempts] == [
        NotificationDeliveryResult.RATE_LIMITED,
        NotificationDeliveryResult.RATE_LIMITED,
        NotificationDeliveryResult.ACCEPTED,
    ]
    assert [attempt.order for attempt in provider.attempts] == [1, 2, 3]


def test_reset_removes_fault_profile_and_previous_attempts() -> None:
    provider = LocalNotificationProvider()
    provider.configure_fault_profile(ProviderFaultProfile(rate_limit_attempts=1))
    provider.deliver("previous@example.com")

    provider.reset()
    delivery = provider.deliver("current@example.com")

    assert delivery.status_code == 202
    assert provider.attempts == (
        ProviderAttempt(
            order=1,
            recipient_email="current@example.com",
            status_code=202,
            result=NotificationDeliveryResult.ACCEPTED,
        ),
    )
