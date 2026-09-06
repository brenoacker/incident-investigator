# Retry Storm latency scenario

The scenario compares the `notification-processing` operation under two separate controlled executions:

- **Window:** 8 traffic rounds.
- **Traffic:** 2 notification requests published per round.
- **Latency sample:** one deterministic work-unit sample for each processed notification; one unit of processing plus the backlog left after it.
- **Degradation criterion:** Retry Storm is degraded when its p99 is at least 25% higher than the healthy reference p99.

The healthy reference processes two notifications per round. Retry Storm processes one per round while the provider returns `429`, causing immediate retries and a growing backlog. The two scenarios publish independent `LatencyMeasurement` values, and `compare_scenarios` returns a `ScenarioComparison`. The comparison uses samples from each execution and does not require identical execution duration or sample count.
