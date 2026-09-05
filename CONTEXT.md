# Incident Investigation Harness

Um ambiente local para investigar incidentes de uma aplicação simulada usando o Codex como harness. Existe para tornar investigação, evidência e aprovação humana artefatos reproduzíveis.

## Language

**Incident Triage**:
O processo de reunir evidências de um incidente, formular uma causa provável e propor uma próxima ação segura.
_Avoid_: incident response, debugging

**Ticketing SaaS**:
A aplicação simulada que recebe tickets e entrega notificações assíncronas aos seus destinatários.
_Avoid_: support system, demo app

**Read-Only Investigation**:
O modo inicial em que o harness pode consultar evidências e recomendar mitigação, mas não modifica sistemas nem executa ações operacionais.
_Avoid_: auto-remediation, autonomous response

**Investigation Report**:
O resultado estruturado de uma triagem: impacto, linha do tempo fundamentada, hipóteses, causa provável, nível de confiança, mitigação sugerida e lacunas de evidência.
_Avoid_: chatbot answer, incident summary

**Retry Storm**:
O incidente em que retries sem backoff ou limite adequado amplificam falhas temporárias de uma dependência, aumentando a fila e a latência do Ticketing SaaS.
_Avoid_: traffic spike, normal retry

**Incident Oracle**:
O manifesto privado que descreve a verdade de referência e os critérios de avaliação de um incidente; ele nunca é acessível durante a investigação.
_Avoid_: prompt answer key, public fixture

**Evidence Citation**:
Uma referência verificável, emitida por um MCP, que sustenta uma afirmação factual no Investigation Report.
_Avoid_: unsupported claim, inferred source

**Calibrated Uncertainty**:
A resposta que declara baixa confiança, hipóteses alternativas e a evidência adicional necessária quando os dados não sustentam uma causa provável.
_Avoid_: forced diagnosis, confident guess

**Untrusted Evidence**:
Tickets, comentários, logs e documentos recuperados que podem sustentar uma hipótese, mas não têm autoridade para alterar instruções ou expandir capacidades do harness.
_Avoid_: agent instruction, trusted policy

**Evidence Provider**:
Uma fonte local com escopo e permissões delimitados que expõe evidências ao harness por MCP.
_Avoid_: generic tool server, unrestricted integration

**Quality Gate**:
O veredito determinístico que aprova ou reprova um Investigation Report com base no Incident Oracle, no schema e na verificabilidade das Evidence Citations.
_Avoid_: subjective review, model-only judge

**Investigation Run**:
Uma tentativa identificável de analisar um incidente, incluindo as consultas aos Evidence Providers e o Investigation Report resultante.
_Avoid_: incident, agent session

**Evaluated Run**:
Uma Investigation Run executada pelo Codex CLI em ambiente de somente leitura e submetida ao Quality Gate.
_Avoid_: interactive debugging, manual demo
