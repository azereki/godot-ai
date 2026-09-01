# v4 local implementation checkpoint — 2026-08-31

This is the current local implementation checkpoint for the architecture
simplification rebuild. It records evidence from the dirty working candidate;
it is not Phase-7 exact-candidate qualification, independent approval, or
authorization to publish.

## Outcome

The ownership simplification and core transactional update/recovery reducer are
implemented, and all eleven structural gates pass. Phase 6 is not
implementation-complete: its production-inert external failpoint adapter covers
only a subset of activation and coordinator effects, does not uniquely address
repeated effect names, and therefore cannot yet drive the complete section-8.1
two-editor/crash/rollback/quarantine/repair matrix against signed fixtures. The
codebase is larger than the frozen baseline, but its authority graph is smaller:
one lifecycle episode, one Python session-membership table, one authenticated
transport, one release ZIP shape, no Dock-owned client worker stores, no
retained update-manager plugin/Dock owner, no detached runner owner, and no
reverse owner cycle in the changed graph.

Production physical LOC is 64,084 (44,523 GDScript and 19,561 Python across 259
files), versus the frozen 59,859-line baseline: +4,225. This is not a LOC
reduction. The claimed simplification is the deletion of competing owners,
writers, protocol branches, compatibility obligations, and representable mixed
states. The security and release machinery accounts for the net growth.

## Local evidence

All rows below ran on macOS 26.5.2 arm64 with pinned Godot
`4.7.stable.official.5b4e0cb0f`. Telemetry was disabled and isolated ports and
capability directories were used; the user's server on 8000/9500 was untouched.

| Gate | Result |
|---|---|
| Architecture simplification gates | pass; all eleven targets met |
| Python 3.14.5 | 2,217 passed, 8 skipped; one known Starlette/httpx deprecation warning |
| Python 3.12.8 | 2,217 passed, 8 skipped; same warning |
| Godot suite, current source | 2,137 passed, 0 failed, 11 skipped; 71/71 suites |
| Fresh Godot import/parse scan | pass; no GDScript parse/load errors |
| Ruff and shell syntax | pass |
| Reload smoke | pass; ten capability/server/session rotations, followed by 2,119 passed / 26 skipped / 0 failed on the reloaded plugin |
| Stale/foreign/adopted server smokes | pass; foreign occupants preserved, compatible external server survived reload |
| Signed v4-to-v4 update | current automated and interactive rows pass; exact signed tree, retained backup, durable claim-before-startup, automatic client repin/completion, fresh authenticated v4.0.1 server, clean banner transition, and no new crash report |
| Signed/clean-major integration file | 11 passed on current source with `GODOT_BIN` set to pinned Godot 4.7 |
| Durable M6 election follow-up | hot-update and clean-major completion now use actor-owned atomic elections; simultaneous two-process tests have exactly one winner; five real-Godot clean-major rows pass |
| Clean-major migration | simulated cold and offline rows pass through a fake `uvx`; wedged prewarm fails before client repin, marker removal, server start, or tool write because descendant authority cannot be disproved |
| Rendering/game capture | pass; 1,920×1,080 output and exact red/green/blue/white quadrant samples |
| Product quit | pass; exact editor process exited with its managed server |
| Stress, pre-review exploratory steady | 4,000 scheduled operations, 5,143 calls, 130.1 calls/sec, editor live, no abort |
| Stress, pre-review exploratory reload-only | 10/10 reloads survived, ten fresh authenticated sessions, editor live |
| Stress, pre-review exploratory mixed reload traffic | 1,520 scheduled operations, 1,923 calls during four reloads; 4/4 survived, editor live, original scene restored |
| macOS crash reports | no product-lane crash after corrected runs; a later invalid agent-only `Godot --script` invocation against a `RefCounted` (PID 29571) created `Godot-2026-08-31-151153.ips` and is excluded from updater evidence |

The exploratory headless stress rows predate the final harness corrections and
are historical robustness evidence, not locked qualification of the current
harness. Their expected nonzero operation errors remain visible:
headless viewport screenshots return `EDITOR_NOT_READY`, and legacy exploratory
input-map operations deliberately try duplicate/missing mutations. Reload-
affected connection failures are recorded separately. Reusing an unlocked
scratch tree also produces expected resource/name collisions, which is why only
a fresh disposable locked run can grant qualification.

Fresh local Python artifacts were also built and inspected from the final
production tree:

- `godot_ai-4.0.0-py3-none-any.whl` — SHA-256
  `6f61918b0acf75ec7371cfedbd5c1b036fe0f2ce4dc696fcd2917317f53ba9ff`
- `godot_ai-4.0.0.tar.gz` — SHA-256
  `a0e8b0c13dc9cca51f36669d08e461ea3415fa7b1edb74c40f4d1e6be9804633`

Wheel integrity, sdist listing, `pip check`, and byte-for-byte comparison of all
123 packaged Python source files passed. A clean Python 3.14 environment
resolved and installed all 67 packages, `pip check` reported no broken
requirements, and `godot-ai-update-transaction identity` returned package
4.0.0 / protocol 1. These are disposable local artifacts, not frozen
source-A/source-B release bytes.

## Evidence identity

- base commit: `dc162f16dab5c095a05c283df28dba891b2e47d0`
- base-commit tree hash reported by the architecture gate (the gate separately
  records that production sources are dirty):
  `17b6f2f801671b7540f71a635e36ea630a31bd91`
- dirty-candidate payload digest (780 tracked and untracked files, excluding
  this self-referential checkpoint, Git metadata, and generated caches):
  `32770ecbbc8b85de2d7dabbf673848895bc2d4a51c9dcd669e7265a858d13cb8`
- interactive automatic-update log:
  `/private/tmp/godot-ai-v4-manual-update-postreview-final-20260831/.godot-ai-self-update-smoke/godot-editor.log`
- interactive transaction:
  `f4bc405ed49524545c41d7f9638767fd`
- retained backup:
  `/private/tmp/.godot-ai-recovery/4ae186ee6210ea0e94f726bd/retained-backup`
- steady report:
  `/private/tmp/godot-ai-v4-gds-suite-clean-20260831/storm-steady-report.json`
- reload-only report:
  `/private/tmp/godot-ai-v4-gds-suite-clean-20260831/storm-reload-report.json`
- mixed reload report:
  `/private/tmp/godot-ai-v4-gds-suite-clean-20260831/storm-concurrent-reload-report.json`
- disposable artifact directory:
  `/private/tmp/godot-ai-v4-final-artifacts-20260831/`

Representative final commands were:

```text
python3 script/architecture_simplification_gates.py --check
GODOT_BIN=<pinned-godot> .venv/bin/pytest -q tests/integration/test_self_update_upgrade_paths.py
.venv/bin/python script/stormtest.py  # with the isolated SS_* environments recorded above
uv build --out-dir <disposable-artifact-directory> --clear
```

## Open release gates

The following remain deliberately open and must not be described as completed:

- reviewed numeric latency/resource ceilings and five repetitions for each
  locked storm profile;
- the complete uniquely addressable section-8.1 external failpoint surface and
  Phase-6 actual-path two-editor/crash/rollback/quarantine/repair matrix against
  signed fixtures;
- the required Windows/macOS/Linux/Godot/Python qualification matrix;
- frozen exact source A and minimal qualification child B, signed plugin assets,
  complete dependency inventories, and independent approval;
- public upload/redownload hash attestation;
- any publication action.

The interactive local row is complete. It required only the user-owned Update
click: repin, durable completion, verified server startup, and banner clearing
continued automatically. Restarting an external client is now remediation for
a client that does not reconnect, not an unverifiable global confirmation gate.
