# v4 Architecture Simplification — Verification Plan

- Date: 2026-08-30
- Status: companion to
  [architecture-simplification-plan.md](architecture-simplification-plan.md),
  draft 3
- Purpose: make migration, updater, security, release, crash, and stress gates
  executable against exact bytes
- Release floor: Godot 4.7+
- Required desktop platforms: Windows, macOS, Linux

## 1. Gate rules

This document is a release contract, not a menu.

- Required engines, historical assets, candidate packages, signing access,
  machines, and platforms may not skip. Missing input means the candidate is
  not qualified.
- Tests run against unmodified candidate bytes. A harness may redirect an
  explicitly authorized qualification channel; it may not patch GDScript,
  synthesize expected digests, bypass discovery/signatures, substitute a dev
  checkout, or rebuild after approval.
- Every result retains machine-readable output, exact commands, source/artifact
  hashes, tool versions, logs, tree hashes, and relevant crash reports.
- Profile or threshold changes after architecture implementation begins require
  a reviewed plan change with baseline evidence.
- A green editor process is necessary but not sufficient. Error, latency,
  resource, state, tree, process, session, and capability assertions all gate.

## 2. Freeze verification inputs

Before the first architecture tranche, check in a verification manifest with:

- pinned landing-base and oracle SHAs;
- each characterization-test commit and how the identical test runs on oracle
  and rebuild;
- every outstanding-PR head/patch ID and disposition;
- every historical tag commit and downloaded asset SHA-256;
- OS image/runner identity, architecture, Godot binary SHA-256, Python/uv
  version, and dependency locks;
- fixed workload seeds and generated operation traces;
- numeric error, latency, recovery, memory, file-descriptor, and thread bounds;
- all failpoint IDs and expected on-disk states;
- expected-red, current-green, oracle-only, and intentional-v4-difference rows;
- evidence output schema and retention path.

The manifest itself is versioned and included in the pre-publication
qualification bundle.

## 3. Mandatory platform matrix

Pin exact current-stable patch/build hashes at implementation start. At minimum:

| Platform | Primary architecture | Godot rows | Python rows |
|---|---|---|---|
| Windows | x86_64 | 4.7.0, current stable if byte-distinct | 3.11, 3.13, 3.14 |
| macOS | arm64 | 4.7.0, current stable if byte-distinct | 3.11, 3.13, 3.14 |
| Linux | x86_64 | 4.7.0, current stable if byte-distinct | 3.11, 3.13, 3.14 |

Each platform/Godot row is keyed by the pinned binary hash. If current stable
is byte-identical to 4.7.0 when inputs freeze, deduplicate it rather than
pretending to have two builds; every gate derives its row count from the unique
pinned manifest. A newer-development Godot can run as a non-blocking Linux
canary; it does not replace a required stable row.

Godot 4.5 and 4.6 run explicit refusal/documentation checks: v4 does not enable,
the user sees the 4.7 floor, and no tree mutation occurs.

Core Python unit/integration suites run all listed versions on all platforms.
The most expensive manual/failure rows may use Python 3.11 and 3.14, provided
ordinary CI covers 3.13 and the exact-candidate server path is proven at both
the floor and ceiling.

## 4. Historical updater inventory and no-mutation proof

### 4.1 Complete classification

Mechanically enumerate every release tag. For each tag, record:

- whether an updater exists;
- release parser and asset-selector implementation hash;
- Update/start-install action implementation hash;
- temp/backup/install implementation hash;
- state-reset/stale-URL behavior;
- expected missing-legacy-asset outcome.

Group identical behavior by normalized patch hash. The source inventory already
found 104 local `v*` tags: v0.2.0/v0.3.0 have no updater and the other 102 use an
exact `godot-ai-plugin.zip` equality match. The executable inventory must
reproduce that result rather than trusting this prose.

Always include these milestone representatives plus one exact tag for every
additional generated behavior class:

- v0.3.1, v1.0.0, v1.5.1, v2.1.1;
- v2.2.0, v2.2.2, v2.3.1, v2.4.0;
- v2.7.6, v3.0.0, v3.1.5, v3.2.4.

### 4.2 Runtime no-mutation rows

Run actual extracted released code, not a reimplementation.

For each behavior class:

1. start from a clean, hashed old add-on/project tree;
2. present the final v4.0 release metadata and complete asset inventory, with
   no `godot-ai-plugin.zip` alias;
3. exercise fresh discovery;
4. where supported, first present a v3 response and then v4 to test stale URL
   reset/repeated discovery;
5. invoke the real Update/start-install button path;
6. assert no v4 payload URL is selected;
7. assert the only navigation is the canonical releases/migration page;
8. assert byte-identical project/add-on hashes;
9. assert no temp, backup, result, marker, or false-success artifact;
10. assert bounded completion and retained logs/UI state.

Run all behavior classes on Linux at Godot 4.7. Run v3.2.4 and the oldest
compatible representative on every mandatory platform. Any behavior class that
cannot execute on 4.7 receives a source proof plus an executable compatible-
engine row; it does not disappear as a skip.

## 5. Bootstrap verifier and clean migration

### 5.1 Independent trust root

v4.0 uses the existing release-signing key. The migration instructions link a
small verifier at a full immutable pre-v4 source commit and show the expected
public-key fingerprint in at least one independently maintained surface not
mutable with GitHub release assets.

The verifier uses the user's Godot executable or another already-required
runtime; it does not download executable dependencies during verification. It
checks, before extraction:

- public-key fingerprint;
- detached manifest signature;
- manifest schema and canonical encoding;
- repository and stable channel;
- source commit, tag, and version;
- exact v4 artifact name, byte size, and SHA-256;
- exact managed-tree inventory and per-entry constraints;
- no encryption, unsafe compression, links/reparse metadata, traversal,
  absolute paths, duplicate paths, case collisions, reserved paths, excessive
  file count, or expansion overflow.

Negative control replaces the archive, manifest, signature, verifier asset, and
release notes as a release-asset publisher could. Verification still fails
because the trusted verifier/key fingerprint is outside that mutable set.

### 5.2 Documentation-driven migration

The harness executes the published commands and paths verbatim:

1. download candidate archive/manifest/signature;
2. run the standalone verifier;
3. prove every editor using the canonical project/install root is closed;
4. stop old MCP clients and old managed backend;
5. canonicalize a recovery destination outside the entire project;
6. reject source/destination aliases, collisions, symlinks, junctions, reparse
   traversal, root disagreement, or unsafe permissions under the platform
   threat claim;
7. rename the old add-on to the recovery root when it is on the same
   filesystem; otherwise copy, compare the full tree/hash, and only then remove
   the live source;
8. extract and verify the exact v4 tree;
9. reopen/enable v4;
10. repin and restart configured clients;
11. start the matching private candidate server;
12. exercise authenticated transport, discovery, representative read/write,
    game run/capture where supported, restart, and editor reopen;
13. prove the external backup remains intact and restorable.

Required old bases are v2.7.6, v3.1.5, and v3.2.4 across every unique pinned
desktop/Godot row. v3.1.5 receives special attention because it is the largest
measured exact-version cohort. Add an older pre-signing base on Linux for the
one-time trust/bootstrap documentation path.

The harness scans the entire project after reopening for duplicate/stale
`class_name` failures and parse cascades. A backup anywhere under the project
is a hard failure.

### 5.3 Installation-surface audit

Before publication:

- GitHub release exposes one v4 plugin ZIP and its signed sidecars, no legacy
  alias and no second store ZIP;
- README/direct links point to the migration page, not an overlay install;
- classic Asset Library and Asset Store v3 listings are frozen/deprecated and
  do not serve v4 bytes;
- source archives cannot be mistaken for updater payloads;
- every old Update fallback lands on instructions that state Godot 4.7+,
  editor closure, external backup, and exact replacement.

## 6. Exact two-candidate qualification

### 6.1 Candidate identities

- **A:** final stable identity `4.0.0`, source SHA A. A's plugin ZIP, signed
  manifest, wheel, and sdist are the only bytes eligible for v4.0 publication.
- **B:** qualification-only identity `4.1.0rc1`, source SHA B. B is a reviewed
  minimal child of A whose only functional changes are version/channel metadata
  and removal of an explicitly v4.0-only migration marker, proving exact-tree
  deletion. B is never relabeled or published as stable v4.1.

Both manifests bind source SHA, repository, channel, tag/version, artifact
name/size/digest, and inventory.

```text
accepted green tranches
        |
        v
SHA A / 4.0.0
  |-- credential-free build --> unsigned bundle A
  |-- protected signer -------> signed digest set A
  |
  `-- reviewed minimal child SHA B / 4.1.0rc1
       |-- credential-free build --> unsigned bundle B
       `-- protected signer -------> signed digest set B

A + B digests
  |-> historical no-mutation
  |-> clean migration to exact A
  |-> exact A -> B hot self-update
  |-> failure/lock/repair/storm evidence
  `-> pre-publication qualification bundle
       `-> approval bound to sources, versions, channels, and every digest
            `-> publish A byte-for-byte
                 `-> public redownload/hash attestation
```

Signing disposable and eventual artifacts under one stable identity is
forbidden.

### 6.2 Private release and Python-package path

Qualification provides:

- a private or draft GitHub-like API/asset endpoint serving exact A under the
  final `v4.0.0` tag/artifact path and exact B under its unique
  `v4.1.0rc1` path;
- stable artifact names and documentation commands whose local paths and
  arguments are identical before and after publication; qualification changes
  only an explicit process-local authorized release base, never candidate
  bytes or the reviewed instructions;
- B served through the normal v4 discovery/parser/authentication path;
- a private PEP 503 index containing the exact A and B wheel/sdist bytes;
- an explicit process-local qualification switch and endpoint/index
  authorization that cannot be enabled by downloaded metadata;
- proof that private endpoints/tokens are never persisted into client config,
  project files, result records, logs, or telemetry.

The unmodified A plugin uses normal `uvx --from godot-ai==<version>` semantics
against the authorized private index. The matrix exercises prewarm, server
restart, client repin, client restart, attach, and matching-version transport.
A dev venv, source symlink, or public-package substitution fails this gate.

### 6.3 Publication promotion

1. create/protect final `v4.0.0` tag at SHA A;
2. verify approval record, sources, identities, signer, and every digest;
3. upload A's exact wheel/sdist to PyPI first;
4. download public distributions and compare hashes with A;
5. if the version already exists, compare hashes and fail on any mismatch;
   `skip-existing` alone is forbidden evidence;
6. publish A's exact signed GitHub assets without checkout/rebuild;
7. download/audit the public asset inventory and hashes;
8. preserve an immutable recovery checkpoint for a forward-only emergency
   release.

If GitHub publication fails after PyPI, resume with the immutable A artifacts.
Before a future stable v4.1 release, public v4.0 must qualify the exact private
v4.1 candidate that will be published byte-for-byte; B cannot stand in for it.

## 7. Interprocess activation-lock matrix

The policy is refusal, not invisible multi-editor coordination.

Required cases:

- two update clicks on one canonical install root: exactly one transaction
  starts; the loser fails before quiescence/disable/mutation;
- a retained successful backup causes the next update to refuse before
  download/quiescence/mutation; after an explicit editor-closed archive or
  removal, the same update may proceed without rotating or overwriting it;
- a non-initiating editor already live on the root: activation refuses before
  mutation;
- a second editor starts after lock acquisition: it enters the activation
  barrier as observer and runs no normal side effects;
- after the matching terminal claim exists and the activation lock is
  released, that observer validates without renaming/consuming the claim,
  exits the barrier exactly once, starts its normal owners, and emits no
  `PostUpdateOutcome` fanout, client repin, or update-outcome telemetry;
- a missing, malformed, mismatched, timed-out, or still-locked terminal state
  keeps the observer barred and points to existing-runtime repair;
- different canonical roots do not block each other;
- case, separator, relative, symlink, junction, and reparse aliases resolve to
  the same identity or fail closed;
- live locks are never stolen;
- killed/stale owner cannot be taken over automatically;
- repair takeover requires explicit user action, closed editors, dead-process
  fingerprint proof, and atomic claim;
- PID reuse, malformed/unknown records, mismatched roots/transactions, and
  unverifiable ownership fail closed;
- only the initiating reload lineage writes readiness and claims result;
- another editor cannot consume outcome or replacement authorization.

Use two real Godot editor processes, not mocked consumers.

## 8. Failpoint and crash matrix

### 8.1 Deterministic barriers

Every updater/recovery reducer effect has stable `before_*` and `after_*`
barrier IDs, including:

- recovery-root and activation-lock creation;
- editor census and client quiescence;
- candidate/manifest/staged-tree revalidation;
- intent temporary write and atomic commit;
- disable request and verified disable;
- live-to-backup rename;
- stage-to-live rename;
- filesystem scan and enable;
- readiness temporary write and atomic commit;
- result temporary write and atomic commit;
- result rename-to-claim;
- claim validation and pre-fanout;
- fanout and startup-barrier release;
- every rollback/quarantine rename, rescan, and re-enable;
- repair transaction claim and each repair effect;
- replacement-authorization spend;
- activation-lock release.

The exact candidate writes an out-of-project barrier record bound to
project/install root, transaction, effect, and monotonic sequence, then waits
for an external continue/fail token. It is owner-private on verified POSIX
paths; on Windows it uses the fixed canonical default and reparse checks under
the explicitly narrowed threat claim. The controller injects one failure or
kill only after observing the record. It does not race console logs.

Failpoint control is disabled by default, requires an explicit local
qualification capability, cannot be armed by release metadata/project data,
and never leaks its token.

### 8.2 Assertions per injected boundary

Each before/after failure and process-kill case declares:

- expected live, stage, backup, and quarantine tree hashes;
- expected lock, intent, readiness, result, and claim presence/content;
- which process may still be live;
- whether normal startup remains barred;
- exact next restart or repair action;
- final immutable `PostUpdateOutcome`;
- retained backup/evidence paths;
- expected user message and exit/error code.

Corrupt, truncated, duplicate-key, unknown-schema, stale, mismatched-version,
mismatched-root, and syntactically valid but impossible-state records each have
explicit rows.

The normal successful backup is never auto-deleted, so no post-success cleanup
failpoint exists.

### 8.3 Repeated crash regression smoke

The user observed multiple macOS Godot crashes during prior updater testing.
Qualification therefore runs repeated fresh-snapshot cycles:

- 10 exact A -> B hot updates on Windows;
- 10 exact A -> B hot updates on macOS;
- 5 exact A -> B hot updates on Linux;
- 5 clean v3.1.5/v3.2.4 -> A migrations per platform;
- repeated Dock detach/reattach and plugin disable/enable around success and
  failure rows.

Before and after each run, capture platform crash-report directories, Godot
logs, process trees, and tree hashes. Any new Godot crash, abort, parse cascade,
or unexplained process death fails the candidate.

## 9. Functional and security matrix

At exact A and after A -> B, run:

- all Python unit/integration suites;
- all GDScript suites and pre-launch parse/import validation;
- protocol schema/error-code synchronization;
- transport challenge, transcript tamper, replay, wrong-scope, wrong-project,
  timeout, size, connection, and pending-budget cases;
- duplicate/pending session race and ACK-send failure;
- immutable session snapshots and atomic peer/session removal;
- managed, adopted, mismatched, lost, recovered, and explicitly replaced server
  lifecycle rows;
- capability path/permission/link/reparse rows within each platform claim;
- client configure/remove/repin/restart and private-index non-persistence;
- representative tool domains, resources, batches, reads, writes, undoable and
  non-undoable outcomes;
- release ZIP/manifest/signing/workflow contracts;
- telemetry opt-out before/after server start and update outcome exactly once;
- graceful editor/server/client restart and stale-artifact absence.

No test may enable the removed v3 transport as a success path. Mixed pairs must
fail closed within the locked timeout and point to matching-version migration.

## 10. Locked storm profiles

Phase 1 executes five baseline repetitions per platform and checks the numeric
thresholds into the verification manifest before Phase 2. The operation traces
are generated once from these fixed seeds and retained:

- `41001`
- `41002`
- `41003`

### 10.1 Steady profile

- 8 workers;
- 20 waves;
- 25 calls per worker/wave (4,000 calls/seed);
- minimum 100 calls per supported tool domain across the profile;
- no intentional reload;
- every unique pinned platform/Godot row.

### 10.2 Reload-churn profile

- 12 workers;
- 30 waves;
- 25 calls per worker/wave (9,000 calls/seed);
- plugin/Dock reload every third wave;
- managed and adopted-server topologies;
- client configure/repin churn;
- latest-stable Godot on all platforms plus Linux 4.7.0.

### 10.3 Multi-editor profile

- two distinct project roots plus a separate same-root activation-refusal row;
- four workers per editor;
- 20 waves, 25 calls per worker/wave;
- at least half of calls explicitly session-pinned;
- focus, Dock, plugin, client, and server churn;
- all three platforms at current stable Godot.

### 10.4 Acceptance

- zero unexpected errors;
- `CONNECTION`/`EDITOR_NOT_READY` only inside recorded reload windows and zero
  outside;
- 100% required reload survival;
- recovery p95 <= 15 seconds and maximum <= 30 seconds;
- per-operation p95/p99 below the checked-in baseline-derived thresholds and
  absolute caps;
- no operation/domain below its minimum coverage;
- after 60 seconds quiescence: zero pending requests, exact expected
  session/process/capability/lock counts, no orphan transaction, and no tree
  drift;
- checked-in absolute RSS/file-descriptor/thread ceilings and no monotonic
  post-quiescence growth across the five repetitions;
- replay of any failed generated trace reproduces the same operation sequence.

The current storm harness must be extended to seed per worker, route multiple
editors, record p99, enforce thresholds, and exit nonzero on contract failure
before it can satisfy this gate.

## 11. Evidence and release approval

### 11.1 Pre-publication qualification bundle

The bundle required for publication approval contains:

- plan/review/verification versions;
- pinned base/oracle/PR/tag manifest;
- source A/B SHAs and parentage;
- plugin/Python artifact inventories, signatures, and hashes;
- protected-signing approval identity;
- historical updater class inventory and runtime reports;
- all platform/Godot/Python results;
- migration transcripts and verifier output;
- interprocess/failpoint/crash reports;
- storm traces, thresholds, and summaries;
- simplification-gate before/after values;
- production/test LOC additions/deletions/net per tranche;
- every skip (required count: zero).

Publication approval names the exact A/B digest set. Any source, workflow,
document, manifest, package, or asset change after approval invalidates the
affected rows and requires a new pre-publication bundle.

### 11.2 Post-publication attestation

After publishing the already-approved A bytes, append a separate attestation
containing:

- public PyPI wheel/sdist download URLs and hash comparisons;
- public GitHub asset inventory, download URLs, and hash comparisons;
- release/tag visibility and canonical migration-link checks;
- the immutable pre-publication approval identifier and digest set;
- any interrupted-publication recovery transcript.

The release is complete only when this attestation proves that every public
byte equals its approved digest. A mismatch does not revise the approval; it
blocks or withdraws the release and invokes the forward-only recovery plan.
