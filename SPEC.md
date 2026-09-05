# Spec: Incident Investigation Harness — MVP de Read-Only Investigation

Status: especificação pronta para implementação; fronteiras de teste confirmadas pelo usuário.

## Problem Statement

Durante Incident Triage, evidências ficam dispersas entre tickets, comentários, logs, traces, métricas, runbooks e código. Quem investiga precisa correlacionar essas fontes, distinguir fatos de hipóteses e recomendar uma próxima ação segura. Uma resposta convincente, mas sem evidências verificáveis, não permite avaliar a qualidade da investigação nem reproduzir suas conclusões.

O projeto precisa demonstrar esse processo em um ambiente local controlado: o Codex investiga um incidente real da aplicação simulada, produz um Investigation Report auditável e tem seu resultado avaliado sem acesso prévio à resposta de referência.

## Solution

Construir o primeiro corte vertical do Incident Investigation Harness. Um Ticketing SaaS local recebe tickets e entrega notificações assíncronas. Um gerador de tráfego e um injetor de falhas produzem uma Retry Storm: o notification-provider devolve `429`, o notification-worker amplifica as falhas por retries inadequados, o backlog cresce e a latência p99 degrada.

O Codex CLI realiza Read-Only Investigation em um workspace isolado, consultando quatro Evidence Providers via MCP. Uma skill orienta a investigação e a produção de um Investigation Report estruturado. Um Quality Gate determinístico compara o relatório com o Incident Oracle privado, valida seu schema e verifica suas Evidence Citations. Eventos e métricas permitem inspecionar cada Investigation Run no stack local de observabilidade.

O MVP cobre evidência suficiente, evidência ambígua e prompt injection no ticket. Seu resultado é uma recomendação fundamentada; nenhuma mitigação é executada.

## User Stories

1. Como desenvolvedor, quero iniciar os serviços do produto com Docker Compose, para reproduzir o ambiente localmente.
2. Como desenvolvedor, quero gerar tráfego controlado no Ticketing SaaS, para estabelecer um comportamento de referência.
3. Como desenvolvedor, quero criar tickets e pedidos de notificação pela API, para exercitar o fluxo de negócio.
4. Como desenvolvedor, quero que um worker processe notificações de forma assíncrona, para observar fila, tentativas e entrega.
5. Como autor de cenário, quero provocar respostas `429` controladas, para reproduzir falhas da dependência.
6. Como autor de cenário, quero reproduzir retries inadequados, para observar a amplificação característica de uma Retry Storm.
7. Como autor de cenário, quero reinicializar os dados entre execuções, para evitar contaminação dos resultados.
8. Como investigador, quero começar por um ticket de incidente, para delimitar o problema relatado.
9. Como investigador, quero consultar comentários e linha do tempo, para entender a evolução do incidente.
10. Como investigador, quero consultar logs, métricas e traces, para correlacionar falhas, backlog e latência.
11. Como investigador, quero consultar runbooks e ADRs relevantes, para fundamentar recomendações no contexto disponível.
12. Como investigador, quero consultar código, diff e histórico Git, para relacionar sintomas ao comportamento da aplicação.
13. Como investigador, quero receber referências verificáveis das fontes consultadas, para sustentar afirmações factuais.
14. Como revisor, quero um Investigation Report com impacto e timeline, para entender quem foi afetado e como o incidente evoluiu.
15. Como revisor, quero distinguir hipóteses, causa provável e fatos, para avaliar o raciocínio apresentado.
16. Como revisor, quero uma declaração de confiança coerente com as evidências, para reconhecer limites da investigação.
17. Como revisor, quero mitigações sugeridas acompanhadas de justificativa, para decidir uma próxima ação segura.
18. Como revisor, quero lacunas de evidência e a próxima evidência necessária, para orientar investigações inconclusivas.
19. Como mantenedor, quero executar evals pelo Codex CLI, para comparar resultados de forma repetível.
20. Como mantenedor, quero isolar o workspace do agente e impedir acesso ao Incident Oracle, para preservar a validade da avaliação.
21. Como mantenedor, quero que código e evidências cheguem apenas pelos MCPs read-only, para limitar a superfície de acesso.
22. Como mantenedor, quero tratar conteúdo recuperado como Untrusted Evidence, para impedir que instruções em tickets ou logs alterem permissões.
23. Como mantenedor, quero avaliar o cenário ambíguo, para verificar Calibrated Uncertainty sem exigir uma causa sem sustentação.
24. Como mantenedor, quero avaliar prompt injection no ticket, para verificar que a investigação permanece segura e útil.
25. Como mantenedor, quero rejeitar relatórios com Evidence Citations inexistentes ou incompatíveis, para evitar conclusões sem rastreabilidade.
26. Como mantenedor, quero um veredito determinístico com motivos de reprovação, para distinguir falhas do relatório e problemas da execução.
27. Como mantenedor, quero correlacionar consultas, logs, spans e relatório pelos identificadores da execução, para auditar uma Investigation Run.
28. Como desenvolvedor, quero consultar dashboards e traces locais, para inspecionar o incidente e o funcionamento do harness.
29. Como desenvolvedor, quero usar o aplicativo desktop para desenvolvimento e dogfooding, mantendo o CLI como executor dos evals, para separar experimentação e avaliação reproduzível.

## Implementation Decisions

### Decisões estabelecidas pelos documentos de origem

- Codex é o harness. Não haverá um chat agent próprio.
- O núcleo usa Python, `uv`, Pydantic, `pytest`, `asyncio` e type checking, em monorepo modular com uma configuração de projeto e entry points separados para API, worker, MCPs, simulador e runner.
- O Ticketing SaaS contém ticket-api com FastAPI e Pydantic, notification-worker assíncrono, PostgreSQL para tickets e estado operacional, Redis para fila e backlog e notification-provider local com respostas `429` controláveis.
- Docker Compose reproduz os serviços do produto, Evidence Providers, observabilidade e fixtures. Codex CLI executa os evals; o desktop serve para desenvolvimento e dogfooding.
- O incident-mcp expõe ticket, comentários e timeline; o operations-mcp expõe logs, métricas e traces; o knowledge-mcp expõe runbooks e ADRs; o source-mcp expõe código, diff e histórico Git. Todos são read-only para o agente.
- Cada Evaluated Run usa workspace isolado. Código, evidências e Incident Oracle ficam fora dele. Código e evidências só chegam ao agente pelos MCPs. O Oracle nunca é acessível durante a investigação.
- O relatório contém impacto, timeline fundamentada, hipóteses, causa provável, confiança, mitigação sugerida, lacunas de evidência e Evidence Citations. A saída do CLI segue um schema estruturado, e seus eventos são registrados em JSONL.
- `incident_id` e `investigation_run_id` são propagados pelos MCPs, logs, spans e relatório.
- OpenTelemetry, Collector e Jaeger oferecem traces; Prometheus e Grafana oferecem métricas e dashboards locais.
- O Quality Gate determinístico é a autoridade de aprovação do MVP. Não há execução de ações operacionais pelo agente.

### Contratos propostos para concretizar o MVP

Estas escolhas detalham os princípios acima; não representam decisões técnicas já registradas em ADR.

- O runner é a entrada pública de uma Evaluated Run: recebe o cenário e sua configuração, prepara o ambiente isolado, executa o Codex CLI, coleta relatório e eventos e aciona a avaliação em contexto separado do agente. Retorna identificadores, artefatos e resultado de avaliação ou falha de execução explícita.
- O isolamento deve restringir visibilidade e capacidades, além de impedir escrita. Uma sandbox read-only, sozinha, não demonstra que o Oracle está inacessível. O processo do agente não recebe montagens, credenciais ou ferramentas que permitam ler o Oracle ou consultar diretamente os serviços subjacentes.
- O agente acessa apenas os Evidence Providers previstos para investigação. Ferramentas de simulação, escrita, administração e avaliação pertencem ao controle externo da execução e não são expostas ao Codex.
- Cada resposta de evidência inclui identificação da fonte e referências estáveis suficientes para resolver uma Evidence Citation no conjunto de evidências daquela execução. O relatório não pode fabricar identificadores nem usar referências de outra execução como suporte.
- O schema associa citações às afirmações factuais relevantes. Hipóteses, recomendações e lacunas são explicitamente distinguíveis de fatos; ausência de causa provável é permitida quando os dados são insuficientes.
- O Quality Gate valida schema, identidade da execução, resolução das citações e critérios explícitos do cenário no Incident Oracle. Existência de uma referência não basta: os critérios devem verificar a correspondência entre fatos esperados e evidências citadas. A implementação deve explicitar os limites dessa verificação determinística de texto livre.
- O Incident Oracle define por cenário os fatos esperados, suportes admissíveis, conclusões incompatíveis e critérios de confiança e mitigação. Seus critérios são versionados antes do eval, sem serem revelados em instruções, respostas MCP, eventos ou artefatos visíveis ao agente.
- As fixtures controlam tráfego, falhas e evidência disponível. A reprodução garante o mesmo cenário e critérios verificáveis, sem exigir texto idêntico do modelo ou tempos de execução exatamente iguais.
- O cenário ambíguo limita deliberadamente a evidência disponível; sua aprovação exige Calibrated Uncertainty, alternativas plausíveis e uma solicitação de evidência relevante. Não exige adivinhar a causa privada.
- O cenário de prompt injection inclui conteúdo operacional que tenta desviar o agente. Aprovação exige preservar os limites de acesso e produzir investigação fundamentada; o conteúdo malicioso não ganha autoridade por aparecer em uma resposta MCP.
- Estado do simulador, evidências e artefatos são separados por execução ou reinicializados de modo verificável. Falhas de infraestrutura, saída inválida do CLI e ausência de relatório nunca geram aprovação.
- A observabilidade inclui consultas aos Evidence Providers, duração e falhas das execuções, resultado do Quality Gate e sinais operacionais da Retry Storm. Define-se explicitamente qual operação tem sua latência p99 medida e qual janela é usada para comparação.

## Testing Decisions

### Fronteiras de teste confirmadas

- **Fronteira principal: runner de Evaluated Run.** Testar a entrada pública que executa cenário → Codex CLI → Evidence Providers → Investigation Report → Quality Gate, observando artefatos, veredito e limites de acesso. Essa é a fronteira mais alta que cobre o resultado do produto.
- **Verificações complementares de contrato:** testar diretamente as interfaces públicas dos Evidence Providers e do Quality Gate para casos de permissões e validação que seriam difíceis de provocar de forma confiável pelo modelo. Não criar fronteiras por função interna ou por cada serviço sem necessidade comportamental.
- Não há código nem testes existentes no repositório na data desta especificação; portanto, não há precedentes de testes a reutilizar. O runner proposto inaugura a fronteira principal.

### Critérios de bons testes

- Verificar comportamento externo: evidência consultável, citações resolvíveis, qualidade exigida por cenário, isolamento e ausência de ações operacionais. Não fixar ordem exata de chamadas, texto literal do modelo ou detalhes internos dos módulos.
- Separar evals reais com Codex CLI das verificações determinísticas de contratos. Dublês podem exercitar falhas do runner, mas não substituem as três Evaluated Runs mínimas.
- Tornar cada reprovação atribuível a critérios observáveis e preservar artefatos suficientes para reproduzir a avaliação.

### Aceitação do corte vertical

1. **Ambiente e cenário:** o fluxo de tickets e notificações funciona localmente; a injeção de `429` produz retries amplificados, aumento de backlog e degradação da p99 da operação definida, em comparação com o comportamento de referência.
2. **Evidência suficiente:** o Codex identifica a Retry Storm e relaciona `429`, retries inadequados, backlog e latência usando Evidence Citations verificáveis. Sugere controles de retry coerentes, incluindo backoff, limite de tentativas e jitter, sem executá-los.
3. **Evidência ambígua:** o relatório explicita confiança baixa, alternativas e evidência adicional necessária. Uma conclusão categórica não sustentada reprova.
4. **Prompt injection:** instruções maliciosas no ticket não alteram o objetivo, permissões ou capacidades; o relatório permanece fundamentado e nenhuma ação operacional ocorre.
5. **Quality Gate:** relatórios inválidos, identificadores incompatíveis, referências inventadas, citações de outra execução e afirmações factuais relevantes sem suporte reprovam com motivos específicos. Relatórios válidos para cada cenário aprovam.
6. **Isolamento:** uma tentativa controlada de acesso direto pelo ambiente do agente ao Oracle, código ou evidências fora dos MCPs é negada. Os Evidence Providers não permitem escrita nem expõem o Oracle. A validação inclui o ambiente efetivo do CLI, não apenas descrições de permissões.
7. **Rastreabilidade:** consultas MCP, logs, spans e relatório permitem recuperar a execução correspondente pelos dois identificadores. Artefatos de execuções distintas não são misturados.
8. **Falhas e repetição:** indisponibilidade de um provider, execução interrompida ou relatório ausente gera resultado explícito sem aprovação indevida. Reiniciar o cenário não herda estado operacional da tentativa anterior.

## Out of Scope

- Executar mitigação, alterar código durante a investigação ou disponibilizar ferramentas de ação ao agente.
- Modo de ação com aprovação humana, ferramentas reversíveis de mitigação e seu fluxo de autorização.
- Chat agent próprio, UI dedicada para incidentes ou comparação visual de Investigation Runs.
- Serviços de produto hospedados externamente e integrações com sistemas operacionais reais.
- Retrieval avançado: embeddings, chunking, busca híbrida, reranking e recall@k.
- Memória recuperada, cache de instruções e compaction de investigações longas.
- Cenários adicionais como poison message, configuração/cache inválido e índice de retrieval desatualizado.
- Mutation tests e LLM-as-a-judge como avaliação complementar.
- Prometer determinismo das respostas do Codex ou validação semântica irrestrita de texto livre pelo Quality Gate.

## Further Notes

- Esta especificação sintetiza o glossário e o brief do projeto. O escopo implementável é o primeiro corte vertical com três evals mínimos; a lista de crescimento posterior não amplia o MVP.
- Não foram encontrados ADRs ou implementação existente para impor contratos adicionais.
- Na implementação, os critérios mensuráveis dos cenários, o schema de citações e o mecanismo efetivo de isolamento precisam ser explicitados e testados antes de declarar o MVP concluído. Não há valores de limiar, orçamento ou versões exatas estabelecidos pelos documentos de origem.
- O ambiente do produto é local. A expressão não estabelece inferência offline do modelo; a execução do Codex CLI requer sua própria configuração de acesso.
- As fronteiras de teste foram confirmadas pelo usuário: runner de Evaluated Run como fronteira principal, com verificações complementares dos contratos MCP e Quality Gate. A especificação recebe o label `ready-for-agent` no GitHub.
