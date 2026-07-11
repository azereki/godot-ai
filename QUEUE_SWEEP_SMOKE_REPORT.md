# Queue-Sweep Integration Smoke Report

- **Date:** 2026-07-11
- **Integration branch:** `integration/queue-sweep-smoke` (merge tip `17087a9`, built from `origin/main` = `0ffbce6`)
- **Scope:** all 12 open queue-sweep PRs merged and gauntleted together. This branch is for inspection only — **do not merge it**; the individual PRs stay the source of truth.

## 0. Engine caveat (read first)

The entire run executed on **Godot 4.6.2-stable, not 4.7.0**. The remote-session
bootstrap (`.claude/hooks/session-start.sh:27`) pins `GODOT_VERSION="4.6.2"` and the
session network policy blocks downloading 4.7 (godotengine.org and out-of-scope
GitHub repos are denied). The operator explicitly cleared the run on 4.6.2.
4.6.2 is above the plugin's 4.5 floor and is itself a CI compat row, so coverage is
meaningful — but 4.7-specific behavior (notably #655's cinematic render path and
#661's Windows/Vulkan CI leg) is certified only by each PR's own 4.7.0 CI rows.

## 1. Merge matrix

All 12 branches were cut from `0ffbce6`, which is still the tip of `main` →
**nothing is stale vs main**. Merged one at a time, in order:

| Order | PR | Branch | Result |
|---|---|---|---|
| 1 | #660 | claude/issue-623-devin-desktop | clean |
| 2 | #656 | claude/issue-617-config-home-env | clean |
| 3 | #662 | claude/issue-599-release-path-scoping | clean |
| 4 | #666 | claude/issue-529-532-telemetry | clean |
| 5 | #664 | claude/issue-526-ws-frame-robustness | clean |
| 6 | #657 | claude/issue-635-run-scope-attribution | clean |
| 7 | #665 | claude/issue-536-534-robustness | clean |
| 8 | #661 | claude/issue-586-ci-vulkan | clean |
| 9 | #655 | claude/pr-issue-queue-review-pmfjvr | clean |
| 10 | #658 | claude/issue-498-idle-backstop | clean |
| 11 | #659 | claude/issue-647-port-in-use | clean |
| 12 | #663 | claude/issue-507-allow-host-ui | clean |

**Zero textual conflicts.** Every hotspot (`server_lifecycle.gd` #658+#659,
`mcp_dock.gd` #659+#663, `test_clients.gd` #656+#660+#665, `plugin.gd` #663)
auto-merged; the changes are additive at disjoint locations. The semantic union was
validated by the full gauntlet below. No merge-order risks found.

## 2. Test totals

| Gate | Result |
|---|---|
| gdparse (union diff, 24 changed .gd files) | **24/24 clean** |
| `ci-check-gdscript` | **PASS** — "All GDScript files OK", real godot binary (#661's fail-loud path not triggered) |
| `pytest tests/ -q` | **1293 passed, 4 skipped, 0 failed** (skips: 2× IPv6-unavailable — #659's own env guard; 1× `GODOT_BIN` unset; 1× opt-in historical) |
| `ruff check src tests` | **clean** |
| `ci-godot-tests` (live editor, full suite) | **1683/1690 passed, 0 failed** (7 version-gated/env skips) |

### Harness gauntlet

| Harness | Result | Evidence |
|---|---|---|
| `ci-stale-server-smoke --mode stale` | **PASS** | `MCP \| strong proof: pidfile_listener`, `MCP \| killed pids [15221]`, respawned server reports v2.9.1, sim pid gone |
| `ci-stale-server-smoke --mode foreign` | **PASS** (2nd run) | `MCP \| proof: (none)`, `suggested free port 8001 (set godot_ai/http_port)`, no kill attempted. First run flaked: the back-to-back stale run's plugin-spawned server was still in its reap window and got adopted — harness sequencing contamination, **not a PR defect**; clean re-run passed |
| `ci-reload-test` | **PASS** | 10 reload iterations OK, post-churn suite 1680 passed / 0 failed / 10 skipped |
| `ci-game-capture-smoke` | **PASS** | attempt 1, 1920×1080, all four quadrants exact RGB match |
| `ci-quit-test` | **PASS** | clean quit, session disconnected ~0s, external server correctly survived |
| `manual-orphan-test` | prep helper exits 0; full matrix is **operator-driven by design** (not run headlessly). Automated equivalents covered by stale-smoke + scenario (b) |
| `local-self-update-smoke` | **not runnable headlessly** (requires clicking Update in the dock). Compensated: `test_update_manager.gd` (#662's 144 new test lines) passed in-suite, and the `GODOT_BIN`-gated `test_self_update_upgrade_paths.py` integration test **passed** (1/1) |
| **stormtest** (8×5, `SS_RELOAD=1`, external server) | **PASS — editor alive** | 1418 calls, 1392 ok / 26 err (1.8%), 65.8 calls/s, **reloads survived 2/2**, recovery 2.1s each, latency p50 54ms / p95 232ms / max 5.3s. Error histogram entirely in documented healthy-noise classes: CONNECTION:7 (reload windows), EDITOR_NOT_READY:5, NODE_NOT_FOUND:4, VALUE_OUT_OF_RANGE:4, ToolError:4, INVALID_PARAMS:2. No wedge, no timeout |

### Targeted cross-PR scenarios

- **(a) #659×#658 foreign port — PASS.** Foreign squatter on 8000 (404s
  `/godot-ai/status`) → plugin logs `MCP | proof: (none)` and the
  concrete-alternate-port diagnosis (`suggested free port 8001`), lands in
  non-recoverable INCOMPATIBLE — not a bare CRASHED — and never attempts a kill
  (verified over an 8s watch window).
- **(b) #658 idle backstop — PASS.** Real end-to-end path: plugin-spawned server
  carried `GODOT_AI_PLUGIN_SPAWNED=1` + both 10s graces (verified in
  `/proc/<pid>/environ`). SIGKILL of the editor → **server exited exactly 10s
  later**. Controls: unmarked manual server with the *same* grace envs survived a
  connect/disconnect cycle 40s+ without exiting; the `--reload` dev server survived
  disconnect indefinitely (dev-transport opt-out). Reload note: the plugin
  *deliberately* stops its managed server on reload (`MCP | stopped server` —
  documented, #514); the respawned marked server reconnected in ~3s, comfortably
  inside the 10s boot grace, confirming the reload-gap claim.
- **(c) #664 WS frame robustness — PASS.** On an established (handshaken) session:
  non-JSON text, `[]`, `42`, and invalid-UTF8 binary frames all logged as
  `Dropping non-JSON frame` / `Dropping non-object JSON frame`, connection stayed
  open, and the real editor session's tools kept working. Pre-handshake garbage gets
  the connection closed — correct, pre-existing behavior.
- **(d) #666 telemetry — PASS.** Local sink received events whose session hash
  `8d807c7d@23d5` ≠ unsalted `sha256(slug)[:8]` = `75c84d20` and **equals** the
  salted `sha256(customer_uuid + slug)[:8]`. With `http://192.0.2.1/` and no escape
  hatch: both warnings emitted ("uses plain http to a non-loopback host…" and
  "…is invalid; sends will be skipped"), no sends attempted.
- **(e) #655 — PASS.** `editor_screenshot(source="cinematic")` returned a 525×640
  PNG with 109 distinct sampled colors (not sky-only);
  `node_get_properties(path="/")` resolved to the scene root (`Node3D`, 15
  properties).
- **(f) #663 — PASS.** With `godot_ai/allow_remote_hosts = "127.0.0.1/32"` in
  EditorSettings, the plugin-spawned server's `/proc` cmdline contains
  `--allow-host 127.0.0.1/32`; token validation rejects `"10.0.0.0/-1"`
  (`token_is_valid` false, `invalid_tokens` flags it) while accepting
  `127.0.0.1/32`.

## 3. Recommended merge order

The union is conflict-free from a common base, so any order lands without conflicts
as long as nothing else merges to main first. To keep attribution clean, use the
tested order: **#660 → #656 → #662 → #666 → #664 → #657 → #665 → #661 → #655 →
#658 → #659 → #663**. No pair *must* merge together; #658+#659 are the most
intertwined behaviorally (`server_lifecycle.gd`) and are cleanest merged
adjacently. No rebases needed as of this report — every PR is based on current main.

## 4. Potential blockers, ranked

1. **None found in the code under test.** No failures anywhere in the gauntlet
   attribute to any PR or PR pair.
2. **Engine-version residual risk (environmental):** 4.7-specific behavior was not
   exercised here (see §0). Rely on each PR's green 4.7.0 CI rows before merging.
3. **Housekeeping (non-blocking):** `.claude/hooks/session-start.sh` pins Godot
   4.6.2 for web sessions — worth bumping to 4.7.0 alongside a network-policy
   allowance. Also, back-to-back `ci-stale-server-smoke` runs can cross-contaminate
   via the previous run's server reap window; a port-drain wait at startup would
   deflake it.

## 5. Tested-at table

| PR | Branch | Tip SHA merged |
|---|---|---|
| #660 | claude/issue-623-devin-desktop | `d8505ec57638fd307f6c3e30bbfa4ac4818540a3` |
| #656 | claude/issue-617-config-home-env | `9ad56958bc14f7f0d883f53aa7e3fa9aa6adbfad` |
| #662 | claude/issue-599-release-path-scoping | `46a1b6adeb36129f835cbc6f0d5a1dc0a5a8d8d5` |
| #666 | claude/issue-529-532-telemetry | `bbffc573137e03dc42558f7c31a84921f192be7d` |
| #664 | claude/issue-526-ws-frame-robustness | `41b8dd50e3fa93095a8904f34e13f7afa3cf9122` |
| #657 | claude/issue-635-run-scope-attribution | `9b7c5b772d1c1dbe81e91893ce25d04a331d54d6` |
| #665 | claude/issue-536-534-robustness | `57eb726a1014472526458b6aba6fe869d7751e57` |
| #661 | claude/issue-586-ci-vulkan | `200abdc0f2e2262c2bb46c4160c8f8579ba465da` |
| #655 | claude/pr-issue-queue-review-pmfjvr | `8d733f676506af9ed315826bd7ebe41d265ef340` |
| #658 | claude/issue-498-idle-backstop | `a863c64b72013c7342295e1c1bafa62f0700c37e` |
| #659 | claude/issue-647-port-in-use | `97b10265b0a1306a252bbad213dc3d405e461deb` |
| #663 | claude/issue-507-allow-host-ui | `b4eaa76cb52eee34da2187cc57d69d378243a082` |

**This report certifies these SHAs only** — if any PR gains commits after this
(e.g. late CodeRabbit-response fixes on #659/#660/#662/#664/#665/#666, which were
still awaiting their CodeRabbit pass when this task was written), re-run the
affected scenarios or diff the delta before trusting the verdict for that PR.
Post-run re-fetch: all 12 tips and `origin/main` (`0ffbce6`) unchanged — no tip
moved during the smoke run. (One unrelated new branch appeared upstream during the
run: `claude/editor-not-ready-subcodes-xm8jwg` — not part of this sweep.)
