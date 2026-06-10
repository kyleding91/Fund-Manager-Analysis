"""Test helper: run with NO membership roster, regardless of the repo's.

The repo ships config/roster.yaml (the sticky universe), which switches
curation.screen_predicate into roster mode. Offline tests build tiny synthetic
databases whose CIKs aren't on the real roster, so they must run in the
pre-roster fallback (per-quarter mechanical screen). Mix this in, or call
no_roster()/restore_roster() from setUp/tearDown.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import curation, roster                                 # noqa: E402

_ORIG = roster.ROSTER_PATH


def no_roster() -> None:
    roster.ROSTER_PATH = Path(tempfile.mkdtemp()) / "absent_roster.yaml"
    roster.reload()
    curation.reload()


def restore_roster() -> None:
    roster.ROSTER_PATH = _ORIG
    roster.reload()
    curation.reload()


class RosterlessMixin:
    """unittest mixin: disables the roster for the duration of each test."""

    def setUp(self):  # noqa: N802
        no_roster()
        super().setUp()

    def tearDown(self):  # noqa: N802
        restore_roster()
        super().tearDown()
