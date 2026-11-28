# CR-05 rejected worker usage

The worker journal records rejected checkout usage in the same transaction as the failed child transition. This includes a timed-out turn with verified terminal identity. Rejection and drain use the same usage calculation and count each native child once. Accounting includes input, output, cache creation, and cache read tokens. Incomplete or invalid counters charge at least the configured ticket reservation and preserve any larger observed total.

Delivery applies the ledger before admitting another worker, after catching a checkout rejection, and after terminal drain. The persisted `unaccepted_tokens` field records the amount already applied. Documents with the earlier `drained_tokens` field use that value as their starting point.

The offline delivery suite ran in the shared checkout. It covered a rejected planning turn above the ticket ceiling, interruption after the child transaction, replay without duplicate usage, duplicate ledger sources, missing or malformed counters, and drain after malformed worker output.
