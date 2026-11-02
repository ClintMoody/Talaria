"""Out-of-tree symlinks are a real portability dependency, not just a link record.

A bundle cannot carry a symlink's target: hardening rejects symlink members, so only the
link record travels. On the source machine the skill works because the target is right
there; on a new machine the link dangles and the skill silently does not load. Hermes'
own ``profile export`` has the same hole. Talaria should at least say so.
"""

from pathlib import Path

from talaria.engine import deps
from talaria.model.artifact import FileEntry


class _FakeIdentity:
    def __init__(self, root: Path):
        self.root = str(root)


class _FakeScan:
    def __init__(self, root: Path, artifacts):
        self.identity = _FakeIdentity(root)
        self.artifacts = artifacts
        self.config = {}
        self.cron_jobs = {}


class _FakeArt:
    def __init__(self, aid, files):
        self.id = aid
        self.profile = None
        self.kind = "skill-dir"
        self.files = files


def _link(home_rel: str, target: str) -> FileEntry:
    fe = FileEntry(home_rel=home_rel, size=0, mode=0o644, mtime=0.0)
    fe.is_symlink = True
    fe.link_target = target
    return fe


def test_out_of_tree_symlink_is_found(tmp_path):
    root = tmp_path / ".hermes"
    (root / "skills").mkdir(parents=True)
    scan = _FakeScan(root, [_FakeArt("skill-dir@/remotion",
                                     [_link("skills/remotion", "/opt/repos/remotion")])])
    found = deps.symlink_dependencies(scan)
    assert len(found) == 1
    assert found[0].dependency.kind == "symlink"
    assert found[0].dependency.detail["in_home"] is False
    assert found[0].dependency.detail["target"] == "/opt/repos/remotion"
    assert found[0].remediation


def test_in_home_symlink_is_not_a_dependency(tmp_path):
    # A link that stays inside HERMES_HOME still survives a bundle, because the target
    # is packed as an ordinary file.
    root = tmp_path / ".hermes"
    (root / "skills" / "real").mkdir(parents=True)
    scan = _FakeScan(root, [_FakeArt("skill-dir@/alias",
                                     [_link("skills/alias", "real")])])
    assert deps.symlink_dependencies(scan) == []


def test_relative_out_of_home_link_resolves_against_link_dir(tmp_path):
    # ../../.agents/skills/x from skills/ lands outside .hermes, on purpose.
    root = tmp_path / ".hermes"
    (root / "skills").mkdir(parents=True)
    scan = _FakeScan(root, [_FakeArt(
        "skill-dir@/firecrawl",
        [_link("skills/firecrawl", "../../.agents/skills/firecrawl")])])
    found = deps.symlink_dependencies(scan)
    assert len(found) == 1
    assert found[0].dependency.detail["absolute"] is False


def test_dangling_out_of_tree_link_is_action_not_ok(tmp_path):
    # The failure mode we care about: a link to a path that does not exist on the target
    # machine must never be reported as 'ok'.
    root = tmp_path / ".hermes"
    (root / "skills").mkdir(parents=True)
    scan = _FakeScan(root, [_FakeArt("skill-dir@/gone",
                                     [_link("skills/gone", "/no/such/path")])])
    findings = deps.symlink_dependencies(scan)
    deps.evaluate_predictive(findings, "linux")
    assert findings[0].verdicts["linux"] == "action"


def test_symlink_to_real_parent_repo_that_exists_here_still_actions(tmp_path):
    # Even when the target exists on THIS machine, a migration to another machine needs
    # the action: existence here proves nothing about there.
    target = tmp_path / "repo"
    target.mkdir()
    root = tmp_path / ".hermes"
    (root / "skills").mkdir(parents=True)
    scan = _FakeScan(root, [_FakeArt("skill-dir@/x",
                                     [_link("skills/x", str(target))])])
    findings = deps.symlink_dependencies(scan)
    deps.evaluate_predictive(findings, "windows")
    assert findings[0].verdicts["windows"] == "action"
