## Antes de implementar

1. Leia `CONTEXT.md` para conhecer a linguagem ubíqua e o modelo do domínio.
2. Leia o ticket no GitHub com `gh issue view <number> --comments`, incluindo bloqueios e critérios de aceite.
3. Leia os ADRs em `docs/adr/` que afetem a área modificada.
4. Consulte o código e os testes existentes antes de escolher o seam da mudança.
5. Transforme cada critério de aceite relevante em uma verificação observável.

## Fontes de verdade

- `CONTEXT.md`: linguagem ubíqua e modelo do domínio.
- `docs/adr/`: decisões arquiteturais vigentes.
- `docs/agents/domain.md`: como consumir documentação de domínio.
- `docs/agents/issue-tracker.md`: comandos e convenções do GitHub Issues.
- `docs/agents/triage-labels.md`: vocabulário e estados de triagem.

Se uma proposta contradisser um ADR ou um termo de `CONTEXT.md`, sinalize o conflito antes de implementar.

## Fluxo de implementação

1. Identifique o módulo, a interface e o seam que serão alterados.
2. Escreva ou ajuste testes na interface pública relevante.
3. Implemente a menor mudança que satisfaz o ticket.
4. Execute testes, type checking, linting e build quando estiverem configurados.
5. Compare a implementação novamente com todos os critérios do ticket.
6. Preserve alterações não relacionadas e nunca descarte trabalho existente sem autorização.

## Regra de verificação

Toda funcionalidade implementada deve ter testes que exercitem seu comportamento observável na interface pública relevante.

1. Escreva ou atualize os testes junto com a implementação.
2. Execute a suíte completa após cada mudança de código.
3. Execute também type checking, linting e build quando estiverem configurados.
4. Se qualquer verificação falhar, diagnostique a causa, corrija o código ou teste e execute novamente todas as verificações afetadas.
5. Só declare a implementação pronta quando as verificações executadas passarem; testes ignorados ou não executados não contam como aprovação.

## Ciclo de code review

Depois de implementar e verificar o codigo, execute a skill `code-review` do Matt Pocock contra o ticket, o diff e os padroes do repositorio.

1. Registre cada finding da revisao, incluindo gaps de especificacao, riscos e testes ausentes.
2. Implemente todos os findings acionaveis antes do handoff ou da PR.
3. Execute novamente os testes e as verificacoes estaticas depois de cada correcao.
4. Repita o `code-review` sobre o novo diff ate nao haver mais findings acionaveis.
5. So declare o trabalho pronto quando testes, verificacoes e revisao estiverem sem gaps pendentes.

`code-review` complementa os testes: testes demonstram comportamento executado; a revisao verifica cobertura contra especificacao, padroes e riscos que os testes podem nao detectar.

## Skills relevantes

- `implement`: executar um ticket ou especificação de ponta a ponta.
- `tdd`: desenvolver features com o ciclo red-green-refactor.
- `codebase-design`: desenhar interfaces, ports, adapters e seams.
- `diagnosing-bugs`: reproduzir e corrigir falhas ou regressões.
- `code-review`: revisar a implementação contra padrões e especificação.
- `domain-modeling`: alterar linguagem, contexto ou decisões de domínio.
- `writing-for-agents`: modificar `AGENTS.md` ou outra instrução para agentes.

## Repository conventions

### Issue tracker

Issues deste repositório são rastreadas no GitHub. Veja `docs/agents/issue-tracker.md`.

### Triage labels

Usa `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human` e `wontfix`. Veja `docs/agents/triage-labels.md`.

### Domain docs

Repositório single-context: `CONTEXT.md` na raiz e ADRs em `docs/adr/`. Veja `docs/agents/domain.md`.
