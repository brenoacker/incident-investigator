"""Effective capability boundary for a read-only Investigation Run."""

from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from incident_investigation_harness.context import InvestigationContext

AllowedEvidenceProvider = Literal[
    "incident-mcp", "operations-mcp", "knowledge-mcp", "source-mcp"
]
AllowedEvidenceProviders = tuple[AllowedEvidenceProvider, ...]
IsolationProbeOperation = Literal[
    "read-oracle",
    "read-private-data",
    "read-unallowlisted-code",
    "write",
    "administer",
    "inject-failure",
    "quality-gate",
]

ALL_EVIDENCE_PROVIDERS: tuple[AllowedEvidenceProvider, ...] = (
    "incident-mcp",
    "operations-mcp",
    "knowledge-mcp",
    "source-mcp",
)
READ_ONLY_TOOLS = (
    "query",
    "resolve-citation",
)


class IsolationProbeResult(BaseModel):
    """Auditable result of one controlled capability probe."""

    model_config = ConfigDict(frozen=True)

    operation: IsolationProbeOperation
    allowed: bool
    reason: str


class InvestigationEnvironment(BaseModel):
    """The capabilities actually handed to the investigator process."""

    model_config = ConfigDict(frozen=True)

    context: InvestigationContext
    allowed_evidence_providers: tuple[AllowedEvidenceProvider, ...]
    available_tools: tuple[str, ...] = READ_ONLY_TOOLS
    mounted_paths: tuple[str, ...] = ()
    credentials: tuple[str, ...] = ()
    direct_service_access: bool = False
    can_write: bool = False
    can_administer: bool = False
    can_inject_failures: bool = False
    can_evaluate: bool = False
    oracle_access: bool = False
    isolation_probes: tuple[IsolationProbeResult, ...] = ()

    def can_query(self, provider: str) -> bool:
        """Return whether a provider is present in the effective MCP surface."""
        return provider in self.allowed_evidence_providers


class IsolationProbe:
    """Probe only the capability surface; probes never touch protected data."""

    _DENIALS = {
        "read-oracle": "Incident Oracle is evaluator-only",
        "read-private-data": "private data is not mounted or credentialed",
        "read-unallowlisted-code": "code is available only through source-mcp",
        "write": "investigation environment is read-only",
        "administer": "administration tools are not exposed",
        "inject-failure": "scenario controls are outside the investigation",
        "quality-gate": "Quality Gate runs outside the investigation",
    }

    def run(
        self, environment: InvestigationEnvironment
    ) -> tuple[IsolationProbeResult, ...]:
        """Return deterministic, auditable denials for every prohibited operation."""
        del environment
        return tuple(
            IsolationProbeResult(
                operation=cast(IsolationProbeOperation, operation),
                allowed=False,
                reason=reason,
            )
            for operation, reason in self._DENIALS.items()
        )


class InvestigationSandbox:
    """Build and verify the effective read-only environment for an investigator."""

    def __init__(
        self,
        allowed_evidence_providers: AllowedEvidenceProviders = ALL_EVIDENCE_PROVIDERS,
    ) -> None:
        if not allowed_evidence_providers:
            raise ValueError("at least one Evidence Provider must be authorized")
        if len(set(allowed_evidence_providers)) != len(allowed_evidence_providers):
            raise ValueError("Evidence Providers must be unique")
        self._allowed_evidence_providers = allowed_evidence_providers
        self._probe = IsolationProbe()

    def prepare(self, context: InvestigationContext) -> InvestigationEnvironment:
        """Create the effective environment and fail closed if it is unsafe."""
        environment = InvestigationEnvironment(
            context=context,
            allowed_evidence_providers=self._allowed_evidence_providers,
        )
        probes = self.verify(environment)
        return environment.model_copy(update={"isolation_probes": probes})

    def verify(self, environment: InvestigationEnvironment) -> tuple[IsolationProbeResult, ...]:
        """Verify effective capabilities, rather than trusting configuration alone."""
        if environment.mounted_paths or environment.credentials:
            raise ValueError("investigator environment exposes protected mounts or credentials")
        if any(
            (
                environment.direct_service_access,
                environment.can_write,
                environment.can_administer,
                environment.can_inject_failures,
                environment.can_evaluate,
                environment.oracle_access,
            )
        ):
            raise ValueError("investigator environment exposes a prohibited capability")
        if not set(environment.available_tools).issubset(READ_ONLY_TOOLS):
            raise ValueError("investigator environment exposes a non-read-only tool")
        probes = self._probe.run(environment)
        if any(probe.allowed for probe in probes):
            raise ValueError("isolation probe detected an allowed prohibited operation")
        return probes
