"""Tests for talaria.engine.resolve — home/profile/identity resolution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402

from talaria.engine import resolve  # noqa: E402


class TestHomes:
    def test_default_homes(self):
        assert resolve.default_home_for("linux", "/home/a") == "/home/a/.hermes"
        assert resolve.default_home_for("darwin", "/Users/a") == "/Users/a/.hermes"
        assert resolve.default_home_for(
            "win32", "C:\\Users\\a", "C:\\Users\\a\\AppData\\Local"
        ) == "C:\\Users\\a\\AppData\\Local\\hermes"

    def test_env_override(self):
        assert resolve.resolve_home({"HERMES_HOME": "/srv/h"}, "linux") == Path("/srv/h")

    def test_profile_split(self):
        assert resolve.resolve_root_and_profile(Path("/h/.hermes")) == (Path("/h/.hermes"), None)
        root, prof = resolve.resolve_root_and_profile(Path("/h/.hermes/profiles/coder"))
        assert (root, prof) == (Path("/h/.hermes"), "coder")

    def test_profile_homes(self, tmp_path):
        (tmp_path / "profiles" / "coder").mkdir(parents=True)
        (tmp_path / "profiles" / "coder" / "config.yaml").write_text("_config_version: 50\n")
        homes = resolve.profile_homes(tmp_path)
        assert set(homes) == {"", "coder"}

    def test_profile_homes_skips_markerless_dirs(self, tmp_path):
        # Upstream refuses to list a marker-less dir: runtime side-effects (cron heartbeats,
        # log rotation, caches) leave these behind, and seeding one made a phantom profile.
        (tmp_path / "profiles" / "ghost").mkdir(parents=True)
        (tmp_path / "profiles" / "real").mkdir(parents=True)
        (tmp_path / "profiles" / "real" / "SOUL.md").write_text("# soul\n")
        assert set(resolve.profile_homes(tmp_path)) == {"", "real"}

    def test_profile_homes_skips_tombstoned_and_bad_ids(self, tmp_path):
        root = tmp_path / "profiles"
        for name in ("gone", "BadCase", "ok"):
            (root / name).mkdir(parents=True)
            (root / name / "config.yaml").write_text("_config_version: 50\n")
        (root / ".deleted").mkdir()
        (root / ".deleted" / "gone").mkdir()
        assert set(resolve.profile_homes(tmp_path)) == {"", "ok"}

    def test_profile_homes_skips_default_dir(self, tmp_path):
        # Upstream: the default profile IS the root home, so a profiles/default dir is not a
        # second profile.
        d = tmp_path / "profiles" / "default"
        d.mkdir(parents=True)
        (d / "config.yaml").write_text("_config_version: 50\n")
        assert set(resolve.profile_homes(tmp_path)) == {""}

    def test_looks_like_hermes_home(self, tmp_path):
        assert not resolve.looks_like_hermes_home(tmp_path)
        (tmp_path / "config.yaml").write_text("x")
        (tmp_path / "skills").mkdir()
        assert resolve.looks_like_hermes_home(tmp_path)


class TestIdentity:
    @pytest.fixture()
    def install(self, tmp_path):
        return build_fake_install(tmp_path / "hermes", FakeInstallSpec(with_git=True,
                                                                       with_profile="coder"))

    def test_identity_full(self, install):
        ident = resolve.detect_identity(install.home, run_venv_probe=False)
        assert ident.hermes_version == "0.20.1"
        assert ident.release_date == "2026.8.13"
        assert ident.install_method == "git"
        assert ident.git_head and len(ident.git_head) == 40
        assert ident.git_tag == "v2026.8.13"
        assert ident.config_version == 36
        assert ident.profiles == ["coder"]

    def test_dirty_detection(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec(with_git=True,
                                                                  with_dirty_checkout=True))
        ident = resolve.detect_identity(inst.home, run_venv_probe=False)
        assert ident.git_dirty

    def test_modern_layout_reads_install_stamp(self, tmp_path):
        # Hermes 0.21+: __version__ is annotation-only (served by __getattr__) and pyproject
        # carries the 0.0.0 placeholder, so install-stamp.json is the only static truth.
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec(
            modern_layout=True, version="0.21.5", release_date="2026.9.24"))
        ident = resolve.detect_identity(inst.home, run_venv_probe=False)
        assert ident.hermes_version == "0.21.5"
        assert ident.release_date == "2026.9.24"
        assert ident.install_method == "git"
        assert any("lazily" in n for n in ident.notes), ident.notes

    def test_modern_layout_stamp_beats_placeholder(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec(
            modern_layout=True, version="0.21.5",
            stamp_display_version="0.22.3+120.gabc.dirty"))
        ident = resolve.detect_identity(inst.home, run_venv_probe=False)
        assert ident.hermes_version == "0.21.5", "baseVersion wins over displayVersion"
        assert ident.hermes_version != "0.0.0"

    def test_stamp_only_fallback_when_no_base(self, tmp_path):
        # A stamp with no usable baseVersion must fall back to displayVersion, never 0.0.0.
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec(
            modern_layout=True, version="0.21.5", stamp_base_version="0.0.0",
            stamp_display_version="0.22.4+7.gabc"))
        ident = resolve.detect_identity(inst.home, run_venv_probe=False)
        assert ident.hermes_version == "0.22.4+7.gabc"

    def test_corrupt_stamp_degrades(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec(modern_layout=True))
        (inst.code_dir / "install-stamp.json").write_text("{not json", encoding="utf-8")
        ident = resolve.detect_identity(inst.home, run_venv_probe=False)
        assert ident.hermes_version != "0.0.0"

    def test_active_profile_defaults_to_default(self, tmp_path):
        # Absence of <root>/active_profile MEANS "default" upstream (set_active_profile(
        # "default") deletes the file); the legacy uppercase ACTIVE_PROFILE has no readers.
        (tmp_path / "config.yaml").write_text("_config_version: 50\n")
        (tmp_path / "ACTIVE_PROFILE").write_text("jarvis\n")
        ident = resolve.detect_identity(tmp_path, run_venv_probe=False)
        assert ident.active_profile == "default"

    def test_active_profile_reads_sticky_file(self, tmp_path):
        (tmp_path / "config.yaml").write_text("_config_version: 50\n")
        (tmp_path / "active_profile").write_text("\ufeffcoder\n", encoding="utf-8")
        ident = resolve.detect_identity(tmp_path, run_venv_probe=False)
        assert ident.active_profile == "coder", "BOM must be stripped (utf-8-sig)"

    def test_no_checkout_degrades(self, tmp_path):
        (tmp_path / "config.yaml").write_text("_config_version: 36\n")
        ident = resolve.detect_identity(tmp_path, run_venv_probe=False)
        assert ident.install_method == "unknown"
        assert ident.hermes_version is None
        assert any("state-only" in n for n in ident.notes)

    def test_install_method_marker(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec(with_git=False))
        ident = resolve.detect_identity(inst.home, run_venv_probe=False)
        assert ident.install_method == "git"  # from .install_method marker file
