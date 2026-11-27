"""Temporary PR-only CI fault injection for the Collegium delivery conveyor."""

EXPECTED = "green"
ACTUAL = "red"


def test_collegium_pipeline_service():
    """The initial PR fails; the fixer changes only ACTUAL to green."""
    assert ACTUAL == EXPECTED
