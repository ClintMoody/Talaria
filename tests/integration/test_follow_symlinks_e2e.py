"""Integration: --follow-symlinks makes linked skills real files on the target machine.

The default behaviour recreates the link, which is exact but only works where the target
path exists. Following copies the content in at the link's own path, so the skill loads on
a machine that does not have the repo. These tests exercise the whole lifecycle against
the fake-install fixture, including applying TWICE (a re-run over an existing followed
directory) and a target machine that already has a DANGLING link where the content goes.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402

from talaria.engine.apply import ApplyOptions, apply_bundle  # noqa: E402
from talaria.engine.pack import PackOptions, pack  # noqa: E402
from talaria.engine.scan import scan  # noqa: E402

LINKED = "shared-repo-skill"


def _spec_install_with_link(tmp_path: Path) -> Path:
    """A fake install whose skills/<LINKED> is a symlink to a repo outside HERMES_HOME."""
    inst = build_fake_install(tmp_path / "src", FakeInstallSpec())
    repo = tmp_path / "out-of-tree-skill"
    (repo / "rules").mkdir(parents=True)
    (repo / "SKILL.md").write_text(
        f"---\nname: {LINKED}\ndescription: lives outside HERMES_HOME\n---\n\nBody.\n",
        encoding="utf-8")
    (repo / "rules" / "extra.md").write_text("rule text\n", encoding="utf-8")
    (inst.home / "skills" / LINKED).symlink_to(repo)
    return inst.home


def _pack(tmp_path: Path, home: Path, follow: bool) -> Path:
    out = tmp_path / ("follow.hermespack" if follow else "links.hermespack")
    return pack(scan(home), out, PackOptions(follow_symlinks=follow)).bundle_path


def _manifest(bundle: Path) -> dict:
    with zipfile.ZipFile(bundle) as zf:
        return json.loads(zf.read("manifest.json"))


class TestFollowSymlinksIntegration:
    def test_followed_bundle_carries_content_not_a_link(self, tmp_path):
        home = _spec_install_with_link(tmp_path)
        bundle = _pack(tmp_path, home, follow=True)
        m = _manifest(bundle)

        assert f"skills/{LINKED}" in (m.get("followed_symlinks") or [])
        # No link record for the followed path: apply would otherwise recreate the link
        # over the copied content.
        assert f"skills/{LINKED}" not in {s["root_rel"] for s in m.get("symlinks", [])}

        with zipfile.ZipFile(bundle) as zf:
            names = zf.namelist()
        assert f"payload/home/skills/{LINKED}/SKILL.md" in names
        assert f"payload/home/skills/{LINKED}/rules/extra.md" in names

    def test_apply_creates_a_real_directory_with_content(self, tmp_path):
        home = _spec_install_with_link(tmp_path)
        bundle = _pack(tmp_path, home, follow=True)
        target = tmp_path / "target-home"
        outcome = apply_bundle(bundle, target, ApplyOptions(consent_executable=True))
        assert outcome.status == "committed", outcome

        skill = target / "skills" / LINKED
        assert not skill.is_symlink(), "followed content came back as a symlink"
        assert skill.is_dir()
        assert (skill / "SKILL.md").is_file()
        assert (skill / "rules" / "extra.md").read_text(encoding="utf-8") == "rule text\n"

    def test_applying_twice_is_idempotent(self, tmp_path):
        home = _spec_install_with_link(tmp_path)
        bundle = _pack(tmp_path, home, follow=True)
        target = tmp_path / "target-home"
        first = apply_bundle(bundle, target, ApplyOptions(consent_executable=True,
                                                          conflict_policy="overwrite"))
        assert first.status == "committed", first
        second = apply_bundle(bundle, target, ApplyOptions(consent_executable=True,
                                                           conflict_policy="overwrite"))
        assert second.status == "committed", second
        skill = target / "skills" / LINKED
        assert skill.is_dir() and not skill.is_symlink()
        assert (skill / "SKILL.md").is_file()

    def test_dangling_link_on_target_is_replaced_by_real_content(self, tmp_path):
        # The realistic move: the target machine has the skill installed as a link to a
        # repo path that does NOT exist there. Following must replace it with content,
        # not fail on mkdir and not keep the dead link.
        home = _spec_install_with_link(tmp_path)
        bundle = _pack(tmp_path, home, follow=True)
        target = tmp_path / "target-home"
        (target / "skills").mkdir(parents=True)
        dead = target / "skills" / LINKED
        dead.symlink_to(tmp_path / "path-that-does-not-exist")
        assert not dead.exists() and dead.is_symlink()

        outcome = apply_bundle(bundle, target, ApplyOptions(consent_executable=True,
                                                            conflict_policy="overwrite"))
        assert outcome.status == "committed", outcome
        assert dead.is_dir() and not dead.is_symlink()
        assert (dead / "SKILL.md").is_file()

    def test_default_still_records_the_link(self, tmp_path):
        # Following is opt-in: without the flag the old, exact behaviour must be intact.
        home = _spec_install_with_link(tmp_path)
        m = _manifest(_pack(tmp_path, home, follow=False))
        assert not (m.get("followed_symlinks") or [])
        assert f"skills/{LINKED}" in {s["root_rel"] for s in m.get("symlinks", [])}
