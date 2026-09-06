## Before implementing

1. Read `CONTEXT.md` to learn the ubiquitous language and domain model.
2. Read the GitHub ticket with `gh issue view <number> --comments`, including blockers and acceptance criteria.
3. Read the ADRs in `docs/adr/` that affect the area being changed.
4. Inspect existing code and tests before choosing the change seam.
5. Turn each relevant acceptance criterion into an observable verification.

## Sources of truth

- `CONTEXT.md`: ubiquitous language and domain model.
- `docs/system-workflow.md`: friendly, high-level view of all system flows, including Evidence Providers via MCP. Read it when changing or adding components, states, integrations, permissions, flow steps, the Investigation Report format, the Quality Gate, or observability; update it in the same change.
- `docs/adr/`: current architectural decisions.
- `docs/agents/domain.md`: how to consume domain documentation.
- `docs/agents/issue-tracker.md`: GitHub Issues commands and conventions.
- `docs/agents/triage-labels.md`: triage vocabulary and states.

If a proposal conflicts with an ADR or a term in `CONTEXT.md`, flag the conflict before implementing.

## Living workflow documentation

Before finalizing any change or addition that affects system behavior, compare it with `docs/system-workflow.md` and update that file if the map, a table, or a Mermaid diagram no longer represents the implemented behavior. Clearly mark what is implemented and what remains planned.

## Implementation workflow

1. Identify the module, interface and seam to change.
2. Write or adjust tests at the relevant public interface.
3. Implement the smallest change that satisfies the ticket.
4. Run tests, type checking, linting and build when configured.
5. Compare the implementation again with every ticket criterion.
6. Preserve unrelated changes and never discard existing work without authorization.

## Verification rule

Every implemented feature must have tests that exercise its observable behavior at the relevant public interface.

1. Write or update tests alongside the implementation.
2. Run the full suite after every code change.
3. Also run type checking, linting and build when configured.
4. If any verification fails, diagnose the cause, fix the code or test, and rerun all affected verifications.
5. Declare the implementation ready only when the executed verifications pass; skipped or unexecuted tests do not count as approval.

## Code review cycle

After implementing and verifying the code, run the Matt Pocock `code-review` skill against the ticket, diff and repository standards.

1. Record every review finding, including specification gaps, risks and missing tests.
2. Implement every actionable finding before handoff or PR.
3. Rerun tests and static checks after each correction.
4. Repeat `code-review` on the new diff until there are no actionable findings.
5. Declare the work ready only when tests, checks and review have no pending gaps.

`code-review` complements tests: tests demonstrate executed behavior; review checks coverage against the specification, standards and risks that tests may miss.

## Relevant skills

- `implement`: execute a ticket or specification end to end.
- `tdd`: develop features with the red-green-refactor cycle.
- `codebase-design`: design interfaces, ports, adapters and seams.
- `diagnosing-bugs`: reproduce and fix failures or regressions.
- `code-review`: review implementation against standards and specification.
- `domain-modeling`: change language, context or domain decisions.
- `writing-for-agents`: modify `AGENTS.md` or another agent instruction.

## Repository conventions

### Issue tracker

Issues in this repository are tracked in GitHub. See `docs/agents/issue-tracker.md`.

### Triage labels

Use `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human` and `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository: `CONTEXT.md` is at the root and ADRs are in `docs/adr/`. See `docs/agents/domain.md`.

### Adapter and Fake naming

- Use `Adapter` as the suffix for a concrete implementation of a port/interface, especially when it integrates real infrastructure.
- Use `Fake` as the suffix for deterministic substitutes used in tests, fixtures or local development.
- Do not use `InMemory` in type or module names; in-memory storage is an implementation detail, while `Adapter` and `Fake` communicate the code's role.
- When an implementation could fit both roles, prefer `Fake` when it exists for tests/fixtures and reserve `Adapter` for the real integration.
