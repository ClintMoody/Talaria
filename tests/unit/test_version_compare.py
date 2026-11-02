"""Version comparison must survive every spelling Hermes actually emits.

Hermes is not consistent about how it names a version, and the inconsistencies are not
hypothetical: ``install-stamp.json`` carries a ``baseVersion`` (``0.21.5``) next to a
``displayVersion`` (``0.21.5+8493.g9b38eb1.dirty``); canary tags add a date
(``0.22.5+canary.20261028T064834Z``); and a checkout with no stamp at all falls back to the
release DATE (``v2026.8.13``). A pack travelling between two of these must still answer
"is the destination newer?" correctly, because that answer decides whether preflight says
FORWARD-OK, EXACT, or BLOCKED-DOWNGRADE (and a spurious downgrade refuses the apply).
"""

import pytest

from talaria.engine.preflight import _version_tuple


def cmp(a: str, b: str) -> int:
    ta, tb = _version_tuple(a), _version_tuple(b)
    return (ta > tb) - (ta < tb)


class TestVersionTuple:
    def test_plain_releases(self):
        assert cmp("0.21.5", "0.22.5") == -1
        assert cmp("0.22.5", "0.21.5") == 1
        assert cmp("0.21.5", "0.21.5") == 0

    def test_build_distance_is_not_a_version_component(self):
        # The bug this guards: naive digit-scraping read "0.22.4+7.gabc" as (0, 22, 47) and
        # called it NEWER than 0.22.5. The distance is commits-since-tag, not a release part.
        assert cmp("0.22.4+7.gabc", "0.22.5") == -1
        assert cmp("0.22.6+7.gabc", "0.22.5") == 1

    def test_canary_tag_compares_as_its_base(self):
        assert cmp("0.22.5+canary.20261028T064834Z", "0.22.5") == 0
        assert cmp("0.22.5+canary.20261028T064834Z", "0.22.4") == 1

    def test_release_date_is_not_semver(self):
        # A checkout without a stamp reports its release date. Read naively that is
        # (2026, 8, 13), which would beat every 0.x release ever made.
        assert cmp("v2026.8.13", "0.20.1") == -1
        assert cmp("v2026.9.24", "0.22.5") == -1

    def test_short_versions_are_padded(self):
        assert cmp("0.22", "0.22.0") == 0
        assert cmp("0.22", "0.22.1") == -1
        assert cmp("1.0", "0.22.5") == 1

    def test_placeholder_never_outranks_a_release(self):
        assert cmp("0.0.0", "0.21.5") == -1

    @pytest.mark.parametrize("v", ["0.21.5", "v2026.8.13", "0.22.5+canary.20261028T064834Z",
                                   "0.22.4+7.gabc", "0.0.0", ""])
    def test_always_three_fields(self, v):
        assert len(_version_tuple(v)) == 3
