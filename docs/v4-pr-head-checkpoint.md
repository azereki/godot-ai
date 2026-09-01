# v4 architecture checkpoints — 2026-09-01

This document records commit-specific checkpoints for PR #943. Documentation-
only commits may follow a checkpoint without changing its measured production
tree. It supplements the historical
[2026-08-31 implementation checkpoint](v4-local-implementation-checkpoint.md)
rather than rewriting that commit-specific evidence. It is not authorization
to tag, upload, or publish a release.

## One-click migration implementation

- implementation commits: `07416ef`, plus the narrow hosted-CI restart
  correction `7ba82b0`
- permanent production tree: `64,653` physical Python/GDScript lines
  (`44,650` GDScript and `20,003` Python across 259 files)
- permanent-production delta from the `59,859` baseline: **+4,794 lines**
- temporary signed migration bridge: `706` GDScript lines, packaged only in the
  v3 transition capsule and absent from the canonical/live v4 tree

This change deliberately adds a narrow compatibility capsule rather than
putting v3 branches back into the permanent v4 runtime. The final-v3 updater
authenticates the outer capsule; the bridge authenticates and stages the inner
canonical tree, replaces the complete add-on, gracefully restarts Godot, and
hands the transaction to the clean v4 process. The ordinary user flow is one
**Update** click.

Local exact-commit evidence includes 2,250 passing Python tests (9 environment-
gated skips), all 12 Godot self-update integration rows (including the exact
v3.2.4 button-click path), Godot 4.5/4.6 runtime-and-bridge refusal/no-mutation
smokes, GDScript import validation, Ruff, diff hygiene, and all architecture
simplification gates. The restart correction additionally passed the exact
button-click smoke, 4.5/4.6 refusal smokes, five focused transaction/release
tests, and 31 workflow-policy tests. Hosted exact-head evidence is intentionally
not claimed until CI completes on the pushed commit.

## Prior reviewed head

- branch: `v4/architecture-simplification`
- reviewed PR head: `d6444e6`
- frozen production baseline: `59,859` physical Python/GDScript lines
- reviewed production tree: `64,581` physical lines (`44,632` GDScript and
  `19,949` Python across 259 files)
- reviewed production delta from baseline: **+4,722 lines**

The production tree is larger than the baseline. The simplification claim is
about fewer authorities, branches, legal mixed states, and reverse ownership
edges; it is not a claim that v4 reduced physical LOC. Security checks,
transactional update/recovery behavior, and qualification coverage account for
the retained growth.

## Final evidence

| Check | Result |
|---|---|
| Architecture simplification gates | 11/11 passed at `d6444e6`; production tree clean |
| Hosted exact-head matrix | [GitHub Actions run 33515469197](https://github.com/hi-godot/godot-ai/actions/runs/33515469197), 32/32 jobs passed |
| Automated review | CodeRabbit passed; no unresolved review threads |
| Older-PR disposition audit | All six PRs tracked in the architecture plan remain open at their recorded heads |

The hosted matrix and review establish the final PR-head evidence. The
remaining publication blockers are still the ones named by the architecture
and verification plans: complete external failpoint coverage, numeric storm
ceilings, the real-process recovery matrix, and exact-candidate Phase 7
qualification. Passing this checkpoint does not silently close those gates.
The authoritative
[qualification and publication checklist](architecture-simplification-verification-plan.md)
requires complete artifact/dependency inventories, digest-bound A/B approval,
independent verifier/SPKI attestation, and post-publication public-byte hashes;
this checkpoint does not replace any of those requirements.
