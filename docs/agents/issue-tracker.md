# Issue tracker: GitHub

Issues and PRDs for this repository live in GitHub Issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`.
- **Read an issue**: `gh issue view <number> --comments`, including labels.
- **List issues**: `gh issue list` with the appropriate state and label filters.
- **Comment**: `gh issue comment <number> --body "..."`.
- **Add or remove labels**: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`.
- **Close**: `gh issue close <number> --comment "..."`.

Infer the repository from `git remote -v`; inside the clone, the `gh` CLI does this automatically.

When a skill says to publish to the issue tracker, create a GitHub Issue. When it says to find the relevant issue, use `gh issue view <number> --comments`.
