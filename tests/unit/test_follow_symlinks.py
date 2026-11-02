"""--follow-symlinks copies link TARGET content in, so linked skills survive a move.

The default records only the target STRING. A bundle cannot carry a symlink member
(hardening rejects them), so on a machine where the target path does not exist the link
lands dangling and the skill never loads: 37 of 42 on a real install. Following writes the
target's bytes at the link's own path instead.
"""

import os
from pathlib import Path

from talaria.engine.pack import PackOptions, _Plan, _follow_one


class _Log:
    def emit(self, *a, **k):
        pass


class _FakeArt:
    def __init__(self, aid="skill-dir@/firecrawl"):
        self.id = aid
        self.profile = None
        self.kind = "skill-dir"


class _Fe:
    def __init__(self, home_rel, target, size=0, mode=0o644, mtime=0.0):
        self.home_rel = home_rel
        self.is_symlink = True
        self.link_target = target
        self.size = size
        self.mode = mode
        self.mtime = mtime


def _plan():
    return _Plan()


def _make_repo(tmp_path, files=("SKILL.md", "rules/a.md")):
    repo = tmp_path / "elsewhere" / "skill"
    for f in files:
        p = repo / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"content of {f}\n")
    return repo


def test_followed_dir_copies_content_not_the_link(tmp_path):
    root = tmp_path / ".hermes"
    (root / "skills").mkdir(parents=True)
    repo = _make_repo(tmp_path)
    plan = _plan()
    ok = _follow_one(plan, root, _FakeArt(), _Fe("skills/firecrawl", str(repo)),
                     "skills/firecrawl", 64 * 1024 * 1024)
    assert ok is True
    # Real files, rooted at the LINK's path, not the repo's.
    rels = sorted(e.root_rel for e in plan.entries)
    assert rels == ["skills/firecrawl/SKILL.md", "skills/firecrawl/rules/a.md"]
    assert plan.followed == ["skills/firecrawl"]
    for e in plan.entries:
        assert e.member == "payload/home/" + e.root_rel
        assert e.source.is_file()


def test_followed_file_link(tmp_path):
    root = tmp_path / ".hermes"
    (root / "skills").mkdir(parents=True)
    real = tmp_path / "real.md"
    real.write_text("hello\n")
    plan = _plan()
    ok = _follow_one(plan, root, _FakeArt(), _Fe("skills/alias.md", str(real)),
                     "skills/alias.md", 1024 * 1024)
    assert ok is True
    assert [e.root_rel for e in plan.entries] == ["skills/alias.md"]
    assert plan.entries[0].source == real


def test_dangling_link_is_left_as_a_link_record(tmp_path):
    # Nothing to copy: following must not claim success, or the link would vanish.
    root = tmp_path / ".hermes"
    (root / "skills").mkdir(parents=True)
    plan = _plan()
    ok = _follow_one(plan, root, _FakeArt(),
                     _Fe("skills/gone", str(tmp_path / "no-such-repo")),
                     "skills/gone", 64 * 1024 * 1024)
    assert ok is False
    assert plan.entries == []


def test_relative_link_resolves_against_the_link_directory(tmp_path):
    # The common case on a real install: skills/firecrawl -> ../../.agents/skills/firecrawl
    root = tmp_path / "home" / ".hermes"
    (root / "skills").mkdir(parents=True)
    repo = tmp_path / "home" / ".agents" / "skills" / "firecrawl"
    repo.mkdir(parents=True)
    (repo / "SKILL.md").write_text("x\n")
    plan = _plan()
    ok = _follow_one(plan, root, _FakeArt(), _Fe("skills/firecrawl", "../../.agents/skills/firecrawl"),
                     "skills/firecrawl", 64 * 1024 * 1024)
    assert ok is True
    assert [e.root_rel for e in plan.entries] == ["skills/firecrawl/SKILL.md"]


def test_size_cap_keeps_the_link_record(tmp_path):
    root = tmp_path / ".hermes"
    (root / "skills").mkdir(parents=True)
    repo = _make_repo(tmp_path, files=("big.bin",))
    (repo / "big.bin").write_bytes(b"x" * 5000)
    plan = _plan()
    ok = _follow_one(plan, root, _FakeArt(), _Fe("skills/big", str(repo)),
                     "skills/big", 1024)          # cap well under the target size
    assert ok is False
    assert plan.entries == []


def test_symlink_cycle_is_walked_once(tmp_path):
    root = tmp_path / ".hermes"
    (root / "skills").mkdir(parents=True)
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    (repo / "SKILL.md").write_text("x\n")
    (repo / "sub" / "f.md").write_text("y\n")
    # A link back to the parent is a cycle any naive walk would loop on forever.
    os.symlink(repo, repo / "sub" / "loop")
    plan = _plan()
    ok = _follow_one(plan, root, _FakeArt(), _Fe("skills/cyc", str(repo)),
                     "skills/cyc", 64 * 1024 * 1024)
    assert ok is True
    rels = sorted(e.root_rel for e in plan.entries)
    assert rels == ["skills/cyc/SKILL.md", "skills/cyc/sub/f.md"]


def test_default_options_do_not_follow():
    assert PackOptions().follow_symlinks is False
