# Domain Docs

Como as engineering skills devem consumir a documentação de domínio deste repositório.

## Antes de explorar

- Leia `CONTEXT.md` na raiz.
- Se existir `CONTEXT-MAP.md`, use-o para localizar os contextos relevantes.
- Leia ADRs em `docs/adr/` que afetem a área em questão.

Se um desses arquivos ainda não existir, prossiga sem apontar sua ausência. O glossário e ADRs são criados apenas quando houver uma decisão de domínio ou arquitetura a registrar.

## Layout

Este é um repositório single-context:

```text
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

## Vocabulário

Use os termos definidos em `CONTEXT.md` em issues, propostas, hipóteses e nomes de testes. Não troque termos por sinônimos que o glossário evita.

Se um conceito necessário não estiver no glossário, trate isso como uma possível lacuna a ser resolvida antes de inventar terminologia.

## ADRs

Se uma proposta contradisser um ADR existente, sinalize explicitamente o conflito em vez de substituí-lo silenciosamente.
