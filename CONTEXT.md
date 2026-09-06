# Incident Investigation Harness

A local environment for investigating incidents in a simulated application using Codex as the harness. It exists to make investigation, evidence and human approval reproducible artifacts.

## Language

**Incident Triage**: The process of gathering evidence about an incident, forming a probable cause and proposing a safe next action.
_Avoid_: incident response, debugging

**Ticketing SaaS**: The simulated application that receives tickets and delivers asynchronous notifications to their recipients.
_Avoid_: support system, demo app

**Read-Only Investigation**: The initial mode in which the harness can query evidence and recommend mitigation, but cannot modify systems or execute operational actions.
_Avoid_: auto-remediation, autonomous response

**Investigation Report**: The structured result of triage: impact, evidence-based timeline, hypotheses, probable cause, confidence level, suggested mitigation and evidence gaps.
_Avoid_: chatbot answer, incident summary

**Retry Storm**: An incident in which retries without adequate backoff or limits amplify temporary dependency failures, increasing the Ticketing SaaS queue and latency.
_Avoid_: traffic spike, normal retry

**Incident Oracle**: The private manifest describing reference truth and incident evaluation criteria; it is never accessible during the investigation.
_Avoid_: prompt answer key, public fixture

**Evidence Citation**: A verifiable reference, issued by an MCP, that supports a factual claim in the Investigation Report.
_Avoid_: unsupported claim, inferred source

**Calibrated Uncertainty**: A response that states low confidence, alternative hypotheses and the additional evidence needed when the data does not support a probable cause.
_Avoid_: forced diagnosis, confident guess

**Untrusted Evidence**: Retrieved tickets, comments, logs and documents that may support a hypothesis but have no authority to change instructions or expand the harness's capabilities.
_Avoid_: agent instruction, trusted policy

**Evidence Provider**: A local source with bounded scope and permissions that exposes evidence to the harness through MCP.
_Avoid_: generic tool server, unrestricted integration

**Quality Gate**: The deterministic verdict that approves or rejects an Investigation Report based on the Incident Oracle, schema and verifiability of Evidence Citations.
_Avoid_: subjective review, model-only judge

**Investigation Run**: An identifiable attempt to analyze an incident, including queries to Evidence Providers and the resulting Investigation Report.
_Avoid_: incident, agent session

**Evaluated Run**: An Investigation Run executed by the Codex CLI in a read-only environment and submitted to the Quality Gate.
_Avoid_: interactive debugging, manual demo
