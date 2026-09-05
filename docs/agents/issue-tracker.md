# Issue tracker: GitHub

Issues e PRDs deste repositório vivem no GitHub Issues. Use a CLI `gh` para todas as operações.

## Convenções

- **Criar issue**: `gh issue create --title "..." --body "..."`.
- **Ler issue**: `gh issue view <number> --comments`, incluindo labels.
- **Listar issues**: `gh issue list` com os filtros de estado e label apropriados.
- **Comentar**: `gh issue comment <number> --body "..."`.
- **Aplicar ou remover labels**: `gh issue edit <number> --add-label "..."` ou `--remove-label "..."`.
- **Fechar**: `gh issue close <number> --comment "..."`.

Infira o repositório a partir de `git remote -v`; dentro do clone, a CLI `gh` faz isso automaticamente.

Quando uma skill disser para publicar no issue tracker, crie uma GitHub Issue. Quando disser para buscar a issue relevante, use `gh issue view <number> --comments`.
