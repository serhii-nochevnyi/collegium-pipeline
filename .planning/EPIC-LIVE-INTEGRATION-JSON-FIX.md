# Bounded integration result JSON retry

All3service PRs6/7/8 are actually merged. Combined head5805b160c9bc147ed2e530158b7b7bea9cd0e4b7
has green GitHub Actions quality. The first independent integration validator ran260tests OK,
but returned JSON followed by a prose correction (payload.exit_code260 corrected to0).
The strict parser correctly refused it. Original worker ses_f69fa490ae6d4c749217a02107803d93 /
run_d5f455dfdc294e8fadbf6e0e98f6a1d1 is terminal, drained and charged77996tokens.

Integration jobs now include the existing integration_attempt in future keys (attempt0 keeps
its original identity). A malformed JSON result records its rejection, drains only confirmed
terminal jobs, and checks the stored original prompt, actual runtime, immutable revision,
pinned checkout and actual successful validation commands before a bounded new attempt.
No partial JSON extraction or model prose correction is accepted. The same token reserve,
head, worker binding and CI gates apply; commands with nonzero exit, unknown turns and valid
failed verdicts do not enter this path. Fresh review remains mandatory and independent.

Fixed-service retry-integration reopens only the recorded terminal JSON block, preserves
all ticket/PR/commit evidence and charged usage, then checkpoints a new root attempt. It
is idempotent and starts no worker itself. Subsequent live ticks use the ordinary engine.
Tests exercise full ready recovery, exhausted retry limit and a crash after terminal drain
before document save, without double accounting or replacement of uncertain work.
