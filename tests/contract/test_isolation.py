from __future__ import annotations

import uuid

import pytest

from incident_investigation_harness.context import InvestigationContext
from incident_investigation_harness.isolation import (
    InvestigationEnvironment,
    InvestigationSandbox,
)


def test_effective_environment_exposes_only_allowlisted_read_only_providers() -> None:
    context = _context()
    environment = InvestigationSandbox(
        allowed_evidence_providers=("operations-mcp", "source-mcp")
    ).prepare(context)

    assert environment.context == context
    assert environment.allowed_evidence_providers == ("operations-mcp", "source-mcp")
    assert environment.can_query("operations-mcp")
    assert not environment.can_query("incident-mcp")
    assert environment.mounted_paths == ()
    assert environment.credentials == ()
    assert not environment.direct_service_access
    assert not environment.can_write
    assert not environment.can_administer
    assert not environment.can_inject_failures
    assert not environment.can_evaluate
    assert not environment.oracle_access


def test_isolation_probes_audit_denied_oracle_private_code_and_operations() -> None:
    environment = InvestigationSandbox().prepare(_context())

    probes = InvestigationSandbox().verify(environment)

    assert {probe.operation for probe in probes} == {
        "read-oracle",
        "read-private-data",
        "read-unallowlisted-code",
        "write",
        "administer",
        "inject-failure",
        "quality-gate",
    }
    assert all(not probe.allowed for probe in probes)
    assert all(probe.reason for probe in probes)


def test_sandbox_fails_closed_for_an_unsafe_effective_environment() -> None:
    environment = InvestigationEnvironment(
        context=_context(),
        allowed_evidence_providers=("operations-mcp",),
        mounted_paths=("docs/incident-oracle.md",),
    )

    with pytest.raises(ValueError, match="protected mounts"):
        InvestigationSandbox().verify(environment)


def _context() -> InvestigationContext:
    return InvestigationContext(
        incident_id=uuid.uuid4(), investigation_run_id=uuid.uuid4()
    )
