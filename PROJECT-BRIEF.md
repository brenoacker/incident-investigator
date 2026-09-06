# Incident Investigation Harness for Codex

## Objetivo

Demonstrar AI Engineering de ponta a ponta com um ambiente local e reproduzível no qual o Codex investiga incidentes de um Ticketing SaaS simulado. O sistema produz recomendações auditáveis; não executa mitigação no MVP.

## Problema

Em incidentes, evidências ficam espalhadas entre tickets, logs, traces, métricas, runbooks e código. O harness fornece ao Codex fontes limitadas por privilégio e exige um relatório fundamentado, permitindo avaliar qualidade, segurança e operação de modo repetível.

## Princípios decididos

- Codex é o harness; não construímos um chat agent próprio.
- Todo o ambiente do produto é local, executado por Docker Compose.
- O Codex CLI executa os evals; o aplicativo desktop serve para desenvolvimento e dogfooding.
- Cada execução avaliada usa um workspace isolado do agente; código, evidências e oráculos ficam fora dele e só código/evidências chegam por MCPs read-only.
- O MVP é read-only: diagnostica e recomenda, mas não aplica mudanças nem ações operacionais.
- Evidência operacional é não confiável e não pode alterar instruções ou permissões do agente.
- O relatório só passa se cada afirmação factual relevante tiver Evidence Citations verificáveis.
- O Incident Oracle fica inacessível ao Codex durante a investigação.
- O Quality Gate determinístico é a autoridade do MVP.

## Fluxo de uma investigação

```text
Ticket de incidente
  -> Codex CLI + skill de investigação
  -> incident-mcp | operations-mcp | knowledge-mcp | source-mcp
  -> Investigation Report estruturado, com citations
  -> Quality Gate determinístico contra Incident Oracle
  -> resultados, eventos e métricas no stack de observabilidade local
```

## Sistema sob investigação

O Ticketing SaaS recebe tickets e envia notificações assíncronas. Seus componentes iniciais são:

- `ticket-api`: FastAPI + Pydantic para criar tickets e pedidos de notificação.
- `notification-worker`: worker Python assíncrono que consome a fila.
- PostgreSQL: tickets e estado operacional.
- Redis: fila e backlog.
- `notification-provider`: dependência local que pode devolver `429` de modo controlado.

Um injetor de falhas e gerador de tráfego criam incidentes de forma determinística.

## MVP: primeiro corte vertical

### Cenário principal

Uma dependência de notificações devolve `429`. O worker faz retries sem backoff, limite ou jitter adequados. A pressão amplifica o erro, aumenta a fila e degrada a latência p99.

### Evidence Providers via MCP

- `incident-mcp`: ticket, comentários e linha do tempo.
- `operations-mcp`: logs, métricas e traces; somente leitura.
- `knowledge-mcp`: runbooks e ADRs relevantes.
- `source-mcp`: código, diff e histórico Git.

### Relatório obrigatório

O Investigation Report contém impacto, timeline baseada em evidências, hipóteses, causa mais provável, confiança, mitigação sugerida, lacunas de evidência e Evidence Citations.

### Evals mínimos

1. Retry Storm com evidência suficiente: diagnosticar e recomendar controles de retry.
2. Evidência ambígua: declarar incerteza calibrada e pedir a próxima evidência relevante.
3. Prompt injection no ticket: ignorar a instrução maliciosa e manter a investigação segura.

## Tecnologia do núcleo

- Python com `uv`, Pydantic, `pytest`, `asyncio` e type checking.
- Monorepo modular com um único `pyproject.toml`; API, worker, MCPs, simulador e runner têm módulos e entry points próprios.
- Codex CLI com execução em sandbox de somente leitura, JSONL de eventos e schema de saída para o relatório.
- OpenTelemetry + Collector + Jaeger para traces; Prometheus + Grafana para métricas e dashboards.
- Docker Compose para reproduzir a aplicação, os MCPs, o stack de observabilidade e as fixtures.

Cada Investigation Run recebe `incident_id` e `investigation_run_id`, propagados pelos MCPs, logs, spans e relatório. O adapter que invoca o Codex também os injeta no contexto efetivo da investigação, permitindo consultas MCP delimitadas sem exigir que o investigador descubra UUIDs.

## Crescimento planejado após o MVP

1. Retrieval avançado no `knowledge-mcp`: embeddings, chunking, busca híbrida, reranking e métricas recall@k.
2. Context engineering: memória recuperada, cache de instruções e compaction de investigações longas.
3. Mais cenários: poison message, configuração/cache inválido, índice de retrieval desatualizado e falhas de dependência.
4. Avaliação ampliada: regressão, mutation tests e LLM-as-a-judge somente como métrica complementar.
5. Modo de ação aprovado por humano, com ferramentas separadas, reversíveis e auditadas.
6. UI para abrir incidentes e comparar Investigation Runs, somente quando os fluxos estiverem estáveis.

## O que o projeto prova em entrevistas

MCP e tool use, agentes e skills, retrieval, context engineering, evals determinísticos, guardrails contra prompt injection, observabilidade de agentes, qualidade operacional, resiliência e Python de produção — em vez de uma demonstração isolada de chat com documentos.
