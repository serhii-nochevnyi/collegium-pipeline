# Collegium Delivery Pipeline

Private remote: [serhii-nochevnyi/collegium-pipeline](https://github.com/serhii-nochevnyi/collegium-pipeline). This is the source and service-test repository; no product pilot is selected. Historical readiness profiles/reports still refer to the earlier read-only agents-knowledge connection.

An independent delivery pipeline on Collegium, inspired by Shipyard's delivery and investigation practices.

**Status:** six Collegium workers are bound to the local serial controller. A real five-stage readiness run passed with runtime model/effort evidence and seven sandbox checks. PR brokerage and bounded CI repair are implemented and pass local contract tests; native GitHub-write/CI acceptance remains pending. The pilot task is intentionally deferred.

- [Specification](SPEC.md): behavior, architecture, model policy, quality gates and acceptance criteria.
- [Configuration example](config/pipeline.example.json): proposed pipeline configuration, not Collegium's bundle schema.
- [Implementation plan](docs/IMPLEMENTATION.md): vertical slices and release gates.
- [Platform evidence](docs/PLATFORM-EVIDENCE.md): documented capabilities versus assumptions to verify.
- [Local setup](docs/SETUP.md): installed tools and remaining authentication steps.
- [Prototype commands and limits](docs/PROTOTYPE.md): runnable commands and remaining integration work.
- [Project state](.planning/STATE.md): confirmed choices and outstanding decisions.
- [PR brokerage and repair](docs/DELIVERY.md): resumable delivery command, credentials, quality gates and limits.
- [Native readiness report](reports/readiness.json): actual sessions, stage receipts and filtered model/effort proofs.

First version: Jira epics and tickets; GitHub repositories, branches, pull requests and checks. Both epic and single-ticket delivery use the same ticket engine. Collegium supplies agent execution and integrations; the pipeline supplies durable coordination and quality policy.

The pilot uses `airslate-common/agents-knowledge` in the owner's personal Collegium space, in the dedicated `collegium-pipeline` project. Current development is ticketless; the prototype accepts a text task without creating a Jira issue. Jira remains part of the broader design. This is a separate project from Remote Sessions.

Run `make check` for local validation (73 tests). `make doctor-readiness` performs read-only checks and currently passes. `make self-test` resumes the recorded readiness task; a fresh task ID explicitly starts new model calls. `make doctor` checks the separate delivery profile, which stays disabled. `make doctor-delivery` checks the new broker profile; `make test-delivery` verifies the repair scenarios.
