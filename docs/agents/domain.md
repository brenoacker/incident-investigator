# Domain documentation

How engineering skills should consume this repository's domain documentation.

## Before exploring

- Read `CONTEXT.md` at the root.
- If `CONTEXT-MAP.md` exists, use it to locate relevant contexts.
- Read ADRs in `docs/adr/` that affect the area in question.

If one of these files does not exist, continue without calling out its absence. Create the glossary and ADRs only when there is a domain or architectural decision to record.

## Layout

This is a single-context repository:

```text
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

## Vocabulary

Use the terms defined in `CONTEXT.md` in issues, proposals, hypotheses and test names. Do not replace terms with synonyms that the glossary avoids.

If a necessary concept is not in the glossary, treat it as a possible gap to resolve before inventing terminology.

## ADRs

If a proposal conflicts with an existing ADR, explicitly flag the conflict instead of silently replacing it.
