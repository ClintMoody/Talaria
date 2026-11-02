"""Integration: symlinked skills survive pack -> apply -> verify -> rollback.

Hermes installs an out-of-tree skill as a SYMLINK (``skills/<name> -> /some/repo``) and its
own ``hermes profile export`` preserves symlinks via ``copytree(symlinks=True)``. Talaria
recorded links but wrote no payload member for them and skipped them in pack, so every
linked skill silently vanished from the bundle (42 of them on Clint's install). A link has
no content and no hash, so it travels in the manifest's ``symlinks[]`` section and is
recreated on apply — including the awkward cases: replacing an existing link, a DANGLING
link (whose ``exists()`` is False), and rollback putting the link back.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402

from talaria.engine.apply import ApplyOptions, apply_bundle, rollback_journal  # noqa: E402
from talaria.engine.pack import PackOptions, pack  # noqa: E402
from talaria.engine.scan import scan  # noqa: E402

LINKED = "shared-repo-skill"


def bundle_with_symlinked_skill(tmp_path: Path) -> Path:
    """Pack a fake install that carries a symlinked skill under skills/."""
    inst = build_fake_install(tmp_path / "src", FakeInstallSpec())
    out_of_tree = tmp_path / "out-of-tree-skill"
    (out_of_tree).mkdir(parents=True)
    (out_of_tree / "SKILL.md").write_text(
        "---\nname: " + LINKED + "\ndescription: lives outside HERMES_HOME\n---\n\nBody.\n",
        encoding="utf-8")
    (inst.home / "skills" / LINKED).symlink_to(out_of_tree)
    result = scan(inst.home)
    out = tmp_path / "link.hermespack"
    return pack(result, out, PackOptions()).bundle_path


class TestSymlinkedSkills:
    def test_scan_records_link_target(self, tmp_path):
        inst = build_fake_install(tmp_path / "s", FakeInstallSpec())
        (tmp_path / "target").mkdir()
        (inst.home / "skills" / LINKED).symlink_to(tmp_path / "target")
        result = scan(inst.home)
        links = [f for a in result.artifacts for f in a.files
                 if f.is_symlink and f.home_rel.endswith(LINKED)]
        assert links, "the symlinked skill was not recorded at all"
        assert links[0].link_target, "the link's target was not captured"

    def test_manifest_carries_the_link(self, tmp_path):
        bundle = bundle_with_symlinked_skill(tmp_path)
        import zipfile
        with zipfile.ZipFile(bundle) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        rels = {s["root_rel"] for s in manifest.get("symlinks", [])}
        assert f"skills/{LINKED}" in rels, rels
        entry = next(s for s in manifest["symlinks"] if s["root_rel"] == f"skills/{LINKED}")
        assert entry["target"].endswith("out-of-tree-skill")

    def test_apply_recreates_the_link(self, tmp_path):
        bundle = bundle_with_symlinked_skill(tmp_path)
        target = tmp_path / "target-home"
        outcome = apply_bundle(bundle, target, ApplyOptions(consent_executable=True))
        assert outcome.status == "committed", outcome
        link = target / "skills" / LINKED
        assert link.is_symlink(), "the skill link was not recreated"
        assert link.readlink().as_posix().endswith("out-of-tree-skill")

    def test_apply_replaces_a_different_existing_link(self, tmp_path):
        bundle = bundle_with_symlinked_skill(tmp_path)
        target = tmp_path / "target-home"
        (target / "skills").mkdir(parents=True)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (target / "skills" / LINKED).symlink_to(elsewhere)
        outcome = apply_bundle(bundle, target, ApplyOptions(consent_executable=True))
        assert outcome.status == "committed", outcome
        assert (target / "skills" / LINKED).readlink().as_posix().endswith(
            "out-of-tree-skill")

    def test_verify_accepts_a_dangling_link(self, tmp_path):
        # The out-of-tree repo does not exist on the target machine yet: the link is
        # dangling there by design, and that must not fail verification. Verified against
        # apply's link check rather than exists(), which is False for a dangling link.
        inst = build_fake_install(tmp_path / "src2", FakeInstallSpec())
        link = inst.home / "skills" / LINKED
        link.symlink_to(tmp_path / "does-not-exist-yet")
        assert not link.exists(), "precondition: the link must dangle"
        bundle = pack(scan(inst.home), tmp_path / "dangling.hermespack",
                      PackOptions()).bundle_path
        target = tmp_path / "target-home"
        outcome = apply_bundle(bundle, target, ApplyOptions(consent_executable=True))
        assert outcome.status == "committed", outcome
        landed = target / "skills" / LINKED
        assert landed.is_symlink() and not landed.exists()

    def test_rollback_removes_a_link_it_created(self, tmp_path):
        bundle = bundle_with_symlinked_skill(tmp_path)
        target = tmp_path / "target-home"
        outcome = apply_bundle(bundle, target, ApplyOptions(consent_executable=True))
        assert outcome.status == "committed", outcome
        journal = Path(outcome.journal_path)
        rollback_journal(journal, target)
        assert not (target / "skills" / LINKED).is_symlink()

    def test_rollback_restores_a_pre_existing_link(self, tmp_path):
        bundle = bundle_with_symlinked_skill(tmp_path)
        target = tmp_path / "target-home"
        (target / "skills").mkdir(parents=True)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        original = target / "skills" / LINKED
        original.symlink_to(elsewhere)
        outcome = apply_bundle(bundle, target, ApplyOptions(consent_executable=True))
        assert outcome.status == "committed", outcome
        assert original.readlink() != elsewhere  # replaced by the bundle's link
        rollback_journal(Path(outcome.journal_path), target)
        assert original.is_symlink()
        assert original.readlink() == elsewhere, "the original link was not restored"
