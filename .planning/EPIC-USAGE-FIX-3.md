# CR-02 accepted worker usage

Accepted, rejected, and drained native turns now share the token counter calculation. It recognizes input, output, cache creation, and cache read counters. An incomplete receipt charges the greater of the configured reservation and the sum of valid known counters. When the idle event is absent, a completed worker has until its existing stage deadline to report usage before the reservation applies.

The accepted charge is stored with the completed worker receipt and reused on replay. Existing completed receipts retain their recorded charges.

All 66 offline delivery and runner tests passed in the shared checkout. Regressions cover a missing usage payload preventing the next paid stage, missing idle events, partial overrun, cache counters, unknown counters, and accepted result replay. Ruff and diff checks passed.
