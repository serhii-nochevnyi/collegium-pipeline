# Terminal verbose-validation correction

Live v19 B validator completed its pinned command (258 tests OK), but Claude Code persisted
40.6KB of output into a sandbox file. The authoritative second tool result exposed only a
2KB preview, omitting COLLEGIUM_CHECKOUT. The controller correctly refused acceptance and
blocked B/C. A's independent validator had the same legacy command and is terminal too.

Capture validation stdout/stderr in a separate temporary log, and return exit code, byte
count and streaming SHA256 in the bounded checkout receipt. Validation argv, candidate,
base, acceptance/config digest, native bindings and CI gates stay identical. This does not
accept a model's claimed test result. A regression actually runs a command producing100KB
and verifies the complete log hash and small receipt. Missing checkout receipts are now
classified as terminal protocol rejection, using the existing bounded retry path.

Explicit fixed-service retry-output observes the two original terminal validators and
checks their original immutable prompts, process proofs, pinned second commands and actual
persisted-output previews. It rejects/accounts each original job, increments one validation
attempt on the SAME candidate, and never replays commit publication or completed planning.
Unfinished/unknown/other failures are refused. The incident marker makes the correction
idempotent and prevents rewinding a later epic. C remains queued until A/B are actually merged.

Inline review: original non-validation checkout bytes preserved; no acceptance/config or
broker pin change; retry cannot replace an unobserved session; old observations and tokens
remain journaled. Partial rejection before snapshot/save is replayable, usage accounting is
deduplicated. All project automations remain paused, no Jira or product pilot.
