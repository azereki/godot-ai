# Releasing and self-update

Part of the Godot AI agent guide — see [AGENTS.md](../AGENTS.md) for the
always-loaded rules.

Godot AI v4 has one signed release tree and one transactional v4→v4 update
path. It does not publish an overlay-compatible legacy ZIP, and a pre-v4
installation cannot self-update across the major-version boundary. See the
[v4 migration guide](v4-migration.md) for that manual clean replacement.

## Publication is intentionally closed

`.github/workflows/release.yml` is a read-only, fail-closed publication gate.
It creates no tag or release and publishes nothing to PyPI. The old
`bump-and-release.yml` workflow has been removed. Do not work around this gate
with a tag push, ad-hoc upload, rebuilt artifact, or marketplace update.

The v3 Asset Library and Asset Store listings remain frozen on v3. V4 may be
published only after the Phase-7 immutable A/B qualification described in
[Packaging & Distribution](packaging-distribution.md) is complete on Linux,
macOS, and Windows and the exact approved bytes can be promoted without a
rebuild.

`verify-signing.yml` is safe to dispatch separately: it exercises the protected
`release-signing` environment against a synthetic payload and publishes
nothing. A green signing check proves only that the stored private key matches
the embedded public key; it is not release qualification.

## The only v4 plugin assets

Every release exposes exactly these three same-version assets:

- `godot-ai-v4-plugin.zip` — canonical `addons/godot_ai/**` tree;
- `godot-ai-v4-plugin.manifest.json` — canonical identity, archive metadata,
  and complete file inventory;
- `godot-ai-v4-plugin.manifest.sig` — 512-byte detached RSA signature over the
  exact manifest bytes.

There is no `godot-ai-plugin.zip` alias and no separate Store ZIP. The manifest
binds repository, channel, tag, semantic version, source commit, ZIP hash and
size, and every extracted file hash. The archive itself is deterministic and
must contain no extra or missing path.

## Build, sign, and verify candidate bytes

`script/v4-release` is the source-of-truth CLI. Package unsigned deterministic
bytes first:

```bash
python3 script/v4-release package \
  --repo-root . \
  --output-dir /absolute/path/to/candidate \
  --channel stable \
  --tag v4.0.0 \
  --version 4.0.0 \
  --source-commit <40-hex-source-commit>
```

Sign that prebuilt manifest in the protected signing environment; do not pass
private-key material through logs or commit it to the repository:

```bash
python3 script/v4-release sign \
  --manifest /absolute/path/to/candidate/godot-ai-v4-plugin.manifest.json \
  --signature /absolute/path/to/candidate/godot-ai-v4-plugin.manifest.sig \
  --private-key /secure/path/release-private-key.pem \
  --expected-repository hi-godot/godot-ai \
  --expected-channel stable \
  --expected-tag v4.0.0 \
  --expected-version 4.0.0 \
  --expected-source <40-hex-source-commit>
```

`build` combines local package/sign/verify for development fixtures. It is not
permission to rebuild a qualified public candidate. Verify any candidate with:

```bash
python3 script/v4-release verify \
  --archive /absolute/path/to/candidate/godot-ai-v4-plugin.zip \
  --manifest /absolute/path/to/candidate/godot-ai-v4-plugin.manifest.json \
  --signature /absolute/path/to/candidate/godot-ai-v4-plugin.manifest.sig \
  --expected-repository hi-godot/godot-ai \
  --expected-channel stable \
  --expected-tag v4.0.0 \
  --expected-version 4.0.0 \
  --expected-source <40-hex-source-commit>
```

The standalone migration verifier is exactly `script/v4-release` plus
`src/godot_ai/release_verify.py` from the named source commit. GitHub release
notes are mutable and must not be treated as a trust anchor. Before publication,
a separately administered channel must authenticate the source commit, both
verifier digests, all three asset identities, the embedded public-key SPKI
fingerprint, and its own attestation identity. The migration guide must name
that operational channel; until it does, publication stays closed. The two
verifier files and repository documentation are not their own trust anchor.

## V4 self-update transaction

The dock considers only a newer `v4.*` GitHub release with the exact three
bounded assets above. An Update click runs this sequence:

1. Preflight refuses an unresolved transaction, retained backup that still
   needs archival, unsafe recovery namespace, active transaction lock, or a
   second live editor lease before download or quiescence.
2. The actor allocates a random owner-private download directory under the
   external recovery root. The manager downloads only the three trusted HTTPS
   release-asset URLs into that exact directory, enforcing release-declared
   sizes and exact filenames. Successful preparation or cancellation removes
   the bounded files; a later exclusive preflight safely collects a stale
   interrupted directory.
3. The Python transaction actor verifies the signature and complete inventory,
   extracts a fresh stage, and publishes `prepared.json`. Its expected stage
   identity comes from the signed manifest—not from a later re-hash of mutable
   stage contents.
4. The root quiesces plugin-owned work and asks the value-only coordinator to
   disable the plugin. The coordinator owns no live files or plugin/Dock
   reference.
5. The actor reconstructs the prepared intent, proves the stage still equals
   the signed inventory, acquires the activation lock, renames the complete
   live tree to a retained backup, and renames the complete stage into place.
   It never overlays files.
6. The coordinator hands the exact initiating actor command across the swap in
   a bounded environment envelope. After Godot scans and enables the new tree,
   the new plugin's bounded startup barrier uses that old actor—never a newly
   resolved/downloaded package—to publish readiness and claim the result before
   ordinary lifecycle, transport, updater, or client work begins. Interactive
   editors run this barrier on one joined worker so a cold, offline, or wedged
   actor cannot freeze the editor UI; export/import launches run it
   synchronously with the same fixed deadline before registering the export
   filter.
7. A successful claim remains the durable client-migration obligation. The
   root repins configured clients, then asks the exact actor that cleared this
   startup barrier to publish an
   immutable `migration-complete.json` bound to the claim, intent, signed live
   tree, and current editor lease. Normal server/client/update startup is
   released only after that acknowledgement. A crash before it causes the next
   ordinary startup to rediscover the claim and repeat the migration barrier;
   a crash after publication does not repeat completed work. External clients
   reconnect to the stable endpoint; an individual restart is remediation for
   a stale client, not a release gate that the plugin cannot verify.
8. Failure rolls the complete old tree back when that can be proven safe.
   Ambiguous state becomes `repair_required`; normal startup remains barred
   until the explicit repair actor resolves it.

The prepared, intent, journal, readiness, result→claim, migration-completion,
activation-lock, and editor-lease records live in a private recovery root
outside the project on the same filesystem. Namespace changes are atomic
renames. Records are strict, size-bounded canonical JSON; links, unsafe POSIX
ancestors, wrong ownership/modes, identity drift, stale actors, and unknown
fields fail closed.

V4 transaction records use schema 1. Claimed transaction directories remain
part of startup and preflight evidence: the actor scans and validates that
retained history before deciding that no repair or M6 obligation remains. There
is no automatic history compaction. Do not hand-edit or delete record JSON to
bypass a refusal. A future record-schema change must first ship an explicit
bounded migration/compaction policy for retained v4 history.

Only the initiating editor lineage may cross an active activation lock. An
editor already open holds a lease and blocks preflight; an editor opened after
lock acquisition refuses before composition and disables the plugin. Re-enable
it or restart after the transaction so Godot loads the terminal tree afresh.
V4 never lets an old in-memory script continue as a read-only "observer" of a
newly renamed tree.

### Recovering a stranded client mutation lock

Automatic Configure/Remove writes and M6 repins share one account-wide durable
lock at `OS.get_config_dir()/godot-ai/client_mutation.lock` (the error prints
the exact platform path). Each claim covers the mutation and its readback. If a
timed-out CLI mutation cannot prove that its process tree stopped, the lock
survives plugin reload, editor restart, and crashes, and later client mutation
or M6 startup fails closed.

Stop the relevant MCP client processes—or reboot—then explicitly remove the
**entire exact lock directory printed in the error** before retrying. Restarting
Godot alone is insufficient, and deleting only `owner.json` deliberately leaves
the deny marker in place. This recovery concerns global client configuration;
it does not authorize editing update-transaction records or rolling back the
live add-on.

### Retained backup and the next update

A successful update keeps one retained backup. Godot AI never silently deletes
it. After validating and externally backing up the new version, close every
editor for the project and archive it explicitly. Use the exact
`recovery_root` printed by `prepare`/`root`—not its parent directory:

```bash
python -m godot_ai.update_transaction archive-backup \
  --project /absolute/path/to/project \
  --install /absolute/path/to/project/addons/godot_ai \
  --recovery-root /absolute/path/to/recovery-base/INSTALL-ID \
  --editors-closed
```

The actor refuses archival if it finds a live or unverifiable editor lease or
an activation lock. On success it atomically moves the retained tree into
hash-named immutable history, allowing the next update while preserving
recovery evidence.

The CLI deliberately distinguishes the two meanings. `--recovery-root` is an
exact, already-derived install root and is required by `activate`,
`abort-prepared`, `repair`, and `archive-backup`. `--recovery-base` is the
optional parent used by `root`, `prepare`, `startup`, and `lease`; those
commands append the deterministic install ID themselves. Passing an exact
root as a base would derive a different path and is refused rather than
guessing operator intent.

### Recovering an abandoned prepared update

If an editor dies after `prepare` (or after publishing an abort intent) but
before activation, first make sure that editor process is gone. Use the exact
project, install, recovery-root, and transaction values printed for the failed
update, and invoke the actor from the same exact installed environment:

```bash
python -m godot_ai.update_transaction abort-prepared \
  --project /absolute/path/to/project \
  --install /absolute/path/to/project/addons/godot_ai \
  --recovery-root /absolute/path/to/recovery-base/INSTALL-ID \
  --transaction TRANSACTION-ID \
  --dead-owner-takeover
```

For an `uvx` installation, use the same isolated/no-config/no-build,
official-PyPI resolver options rendered by the plugin, followed by
`--from godot-ai==LIVE_VERSION godot-ai-update-transaction`; substitute the
exact version in the still-live add-on's `plugin.cfg`. Do not let an alternate
index from local uv configuration choose a repair actor. The takeover refuses
while the prepared editor, another abort requester, or a prior repairer remains
live or unverifiable. It also refuses after activation begins or if any bound
identity/hash has changed. On success it deletes only the authenticated staged
candidate, publishes durable cleanup, and leaves the live add-on untouched.
Do not use this command as a general rollback tool; post-activation ambiguity
belongs to the separate `repair` command.

## Required self-update smoke

Any change to release identity/layout, verification, update discovery,
transaction records, lease/startup barriers, plugin disable/enable, client
repinning, or recovery must run:

```bash
python script/local-self-update-smoke
```

The harness builds a disposable signed v4-to-v4 fixture from the current tree and
launches a real editor. The operator clicks **Update** in the dock. Passing
requires exact version/tree advancement, a healthy authenticated backend after
reload, no parse/load error in the disable→enable window, no new macOS Godot
crash report, no activation artifact inside the project, and a retained
recoverable backup. This interactive check is release-blocking and supplements,
rather than replaces, the automated failpoint, rollback, multi-editor, exact
release-shape, and clean-migration suites. Pre-v4 updater behavior is a completed
one-time audit recorded in
[pre-v4-updater-one-time-evidence.md](../verification/pre-v4-updater-one-time-evidence.md),
not a recurring compatibility obligation.
