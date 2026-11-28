# Runtime and Jira identity review fixes

CR10: a nonempty runtime pin now requires the archive; packed mode never adds source
mirrors to sys.path. Bounded hash/ZIP/CRC validation remains, with isolated tests for
missing/corrupt archive and conflicting source modules. Empty pin retains source mode.

CR11: Task and Jira adapter share canonical ASCII positive decimal immutable issue IDs.
Whitespace, leading zeros, keys and malformed source values are refused. Display keys
remain graph labels; Jira full/lossless view and pagination behavior remain unchanged.

The GSD Sol/low fixer reported20 focused offline tests, Ruff/format/syntax/diff checks.
No commits, remote APIs or bundle builds were performed by the fixer. Parent subsequently
ran the entire integrated suite and regenerated the bundle.
