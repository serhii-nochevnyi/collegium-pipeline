# Investigation MCP code review

GSD review performed inline per the no-delegation instruction. Scope: MCP source reader,
claim validation, intake/replay, evidence inspection, cloud wiring and bundle assembly.

Reviewed boundaries: native attempt-only auth, exact connection/URL/tool-schema pins,
controller-only read grants, immutable full responses versus excerpt coverage, age bounds,
per-reference and claim DEV/PROD/SHARED labels, no credential/payload publication, original
configuration digests and signed checkpoint artifacts, and idempotent volatile admission.

Resolved during review: reject non-string connection names and invalid pointer escapes
before network, recheck grant/URL metadata after in-flight reads, preserve a capture interval
rather than an ambiguous start-only timestamp, and distinguish selecting a response root
from displaying its entire contents. Existing Git-only claim contracts remain compatible.

Verification:40 focused investigation tests and29 bundle tests pass, including a complete
MCP-backed worker fixture and signed snapshot loss/recovery preserving the exact native
session/turn and raw MCP artifact without recapture. New native installation/service
results must be recorded separately; no live claim is implied by fixtures.
