# Changelog

## 1.2.0 — 2026-11-01

Two follow-ups from using 1.1.0 on a real install, both about telling the truth: one flag
that makes linked skills actually survive a move, and an install command that exists.

- **`--follow-symlinks`.** A bundle cannot carry a symlink's target (hardening rejects
  symlink members), so only the target string travels and the link is recreated on the
  new machine. That is exact, but if the target path does not exist there the link lands
  dangling and the skill never loads. On a real install 48 of 50 links pointed outside
  `HERMES_HOME`, so 37 skills arrived broken. Following copies the target's real files in
  at the link's own path instead. Costs under a megabyte for all 45 links on a real
  install. Dangling links stay link records, nested cycles are walked once, relative
  targets resolve against the link directory, and `--follow-cap` (default 0.5 GiB) leaves
  anything larger as a link. Verified end to end: 12,442 members packed, applied to a
  fresh home with 0 symlinks and 0 dangling, then verified with Hermes answering.
- **The install instructions pointed at a package that does not exist.** The quick start
  offered `pipx install talaria-hermes` and then said "Not on PyPI yet" three lines
  later. Checked the live index: `talaria-hermes` is 404, and `talaria` is an unrelated
  Django CMS (0.2.0). The docs now give the one command that works, pinned to a tag, and
  say why the obvious names are unusable.
- Manifest gains the additive `followed_symlinks[]`; schema stays 1.

## 1.1.0 — 2026-11-01

Brought Talaria's model of Hermes up from 0.20.1 to **0.22.5** (released 2026-10-23),
verifying each assumption against the real v0.22.5 tree rather than the release notes.
Bundle schema stays 1 and older readers still read new bundles (every addition is an
additive manifest key). Two changes are behaviour-visible: symlinked skills now travel,
and artifact ids for skills are now unique.

- **Version detection rewritten** for Hermes 0.21+. Hermes moved the version out of
  `hermes_cli/__init__.py` (it is now an annotation served by module `__getattr__`),
  `pyproject.toml` carries the `0.0.0` placeholder, and `install-stamp.json` is the
  authoritative record. Every modern install used to report **0.0.0**. Identity now
  follows upstream's own resolution order (install stamp, then live git, then unknown)
  and never reports the placeholder.
- **Named-profile discovery matches `profiles.list_profiles`.** A directory counts only
  when its name matches `PROFILE_ID_RE`, it carries an identity marker
  (`config.yaml`/`.env`/`SOUL.md`/`profile.yaml`/`auth.json`/`state.db`), and it is not
  tombstoned under `profiles/.deleted/`. Runtime side-effect dirs and pre-tombstone ghost
  shells are no longer packed as phantom profiles, and `profiles/default` is not counted
  twice.
- **Active profile follows upstream.** The sticky file is `<root>/active_profile`, read
  as `utf-8-sig`; a missing file means `default` (`set_active_profile("default")`
  deletes it). The legacy uppercase `ACTIVE_PROFILE` has no readers upstream and is no
  longer consulted. Absence used to report `None`.
- **Version comparison fixed.** `0.22.4+7.gabc` parsed as `(0, 22, 47)` and read as NEWER
  than `0.22.5`; a `v2026.8.13` release date parsed as `(2026, 8, 13)` and outranked every
  `0.x` release. Such a false "newer" turns into a bogus FORWARD-OK, and a false "older"
  refuses a legitimate apply as a downgrade.
- **Symlinked skills now travel.** An out-of-tree skill is installed as a symlink and
  Hermes' own `profile export` preserves it (`copytree(symlinks=True)`); Talaria recorded
  the link but wrote no payload member, so every linked skill vanished (42 on a real
  install). Links now travel in the manifest's additive `symlinks[]` section and are
  recreated on apply, verified by target, and restored by rollback — including dangling
  links and pre-existing links being replaced.
- **Artifact ids are unique.** Skills were grouped by path depth, so every skill sitting
  directly at `skills/<name>/` collapsed onto `skill-dir@/SKILL.md` (57 collisions on a
  real install) and category-level files each became their own artifact. Grouping now
  follows the skill directory that owns the file, which also restores provenance tagging
  for 113 previously-untagged skills.
- **Catalog catch-up for the Hermes directory model.** `installs/`, `tools/`,
  `browser-profile/`, retired WAL captures and update/restart markers are now excluded or
  pruned as runtime state; `cache/` is descended instead of dropped wholesale so the
  subtrees Hermes keeps (`images`, `audio`, `videos`, `documents`, `screenshots`,
  `citations`, `generated`) are carried; the credential vault is classified as a
  credential (key and ciphertext side by side are plaintext) rather than `secrecy=none`;
  and `state/`, `briefings/`, `pets/`, `attachments/`, `pending/`, `specs/`, `plans/`,
  `output/` and the active-profile files are classified instead of being unrecognized.
  Unrecognized files on a real install dropped from 23,177 to 4,467.
- **Non-core directories under `HERMES_HOME` are accounted for.** The standalone web UI
  keeps 3.1 GB of app data in `webui/` (sessions, attachments, model cache); Hermes core
  never reads that path, so it had been scanned as unrecognized and travelled as
  record-only: silently dropped from every bundle. It is now carried as app data. Sidecar
  tooling that watches Hermes rather than being part of it (`lcm-monitor/`, `scratch/`)
  and stale pre-cutover database copies (`state.db.bak-*`, `.broken-*`, `.corrupt-*`,
  `.recovered-*`) are classified and left behind on purpose: they are large, and a
  restore that lands an old database copy can leave Hermes unsure which one is current.
  Unrecognized on a real install dropped from 12.3 GB to 142 MB.
- **Out-of-tree symlinks are reported as dependencies.** Of 50 symlinks on a real
  install, 48 point outside `HERMES_HOME` (to skill repos under `PROJECTS/`, `.agents/`,
  plugin checkouts). The bundle carries the link record but by design cannot carry the
  target, so 37 of 42 linked skills landed dangling on a fresh-machine apply and would
  never load. `talaria deps` now lists each one with its target and remediation, and the
  per-OS verdict is `action`, never `ok`. Hermes' own `profile export` has the same hole;
  the difference is that Talaria tells you.
- `talaria diff` defaults to `skills`; bare invocation used to exit with a dead-end
  "the following arguments are required: what".
- Docs updated for the new layout; research notes keep the version they were written
  against.

## 1.0.0 — 2026-08-15

First release. Talaria moves a Hermes Agent installation between machines — any
direction across Linux, macOS, native Windows, WSL, and Termux — as one verified,
undoable `.hermespack` file.

- Typed scanner over the real Hermes on-disk model (40+ artifact kinds, per-profile,
  both directory layout generations, reference chasing into configs/jobs/plugins).
- Six-tag skill provenance via Hermes' own mechanisms, with per-file stock diffs,
  config-vs-defaults and SOUL-vs-default comparison, checkout ref+patch capture.
- Dependency engine: enforced vs advisory extraction (skills, cron, MCP, providers)
  with per-target-OS verdicts, fully offline predictive mode, live probes.
- Streaming packer: single-pass hash+write, WAL-safe SQLite snapshots, atomic 0600
  publish with self-verify, FAT/space prechecks, machine-bound exclusion belt.
- Bundle format schema 1: eternal header, per-file SHA-256, selection record,
  predictive verdicts, salvage; full reader hardening (traversal, symlinks,
  collisions, bombs, reserved names).
- Optional vault: scrypt + HKDF + AES-256-GCM with AAD binding and section HMAC;
  honest refusal without `cryptography`; "lock everything" extends to content.
- Transactional applier: 18 preflight gates, write-ahead journal, per-file safety
  copies, structural rewrite engine (yaml/json/dotenv editors with byte fidelity and
  refuse-lists), cron claim scrubs, cross-OS provenance rebaselining, conflict
  policies, verified placement, automatic rollback, NEEDS_ATTENTION double-fault
  freeze that deletes nothing.
- Deep-Scan: nonce-bound observation skill for the user's agent + fully distrusting
  ingest (verify/refuse/appendix; values scrubbed; capture set never auto-expands).
- Reports: System Overview and Migration Report from one redacted data model —
  self-contained HTML (CSP, print CSS, light/dark), markdown, JSON.
- Interfaces: 15-subcommand CLI (--json everywhere, D3 exit codes, dry-run), text
  wizard within a 2-decision budget, hardened localhost GUI wizard (token bootstrap,
  Host/Origin checks, job engine, paste-back).
- Distribution: pip package + single-file `talaria.pyz` (Python 3.9 floor,
  2.7-parseable stub).
- 269 tests: unit, integration round-trips, crash-injection rollback, hostile
  bundles, GUI endpoint security, real-browser walkthrough, adversarial regressions.
- Hardened by an adversarial security review (docs/security-review.md): 11 confirmed
  findings fixed, including a vault-member arbitrary-write (RCE), memory-provider
  bundles that were unappliable, and a rollback path that could lose committed
  database WAL data — each with a reproducing regression test.
