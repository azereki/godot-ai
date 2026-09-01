# Migrating a project to Godot AI v4

Godot AI v4 is a clean break. It requires Godot 4.7 or newer within the 4.x
line, uses a new
authenticated local transport, and is installed as one signed exact tree. Do
not extract v4 over an older `addons/godot_ai` directory and do not use a v3
self-updater to cross the major-version boundary.

The migration command moves the complete old add-on to a retained recovery
directory outside the project, stages and verifies the complete v4 tree, then
renames that tree into place. It never merges the two versions. If activation
or final verification fails, it restores the old tree or reports the exact
recovery path that needs operator attention.

## Before starting

> **Publication is closed.** There is currently no independently anchored v4
> release attestation, so GitHub assets and release notes alone are not a safe
> installation source. Do not run this migration against public downloads
> until this guide names the separately administered attestation location and
> the release checklist records its successful verification.

You need:

- Godot 4.7 or newer within the 4.x line;
- Python 3.11 through 3.14;
- `uv` installed with `uvx` available on `PATH` (Python alone is not enough:
  the first v4 startup requires the exact-version transaction actor);
- all Godot editor processes for the project closed;
- every configured AI client and the old Godot AI managed backend stopped;
- a recovery path outside the project, on the same filesystem, whose final
  directory does not already exist;
- the release-specific independent attestation described below.

Download these three release assets without renaming them:

- `godot-ai-v4-plugin.zip`
- `godot-ai-v4-plugin.manifest.json`
- `godot-ai-v4-plugin.manifest.sig`

Also obtain `script/v4-release` and its sibling
`src/godot_ai/release_verify.py` from the exact source commit named by the
release. Preserve that directory layout: the command loads the verifier by
path and does not import an installed `godot-ai` package.

GitHub release notes are mutable and are not a trust anchor. Before executing
either verifier file or trusting any release asset, obtain the independently
published v4 attestation through the separately administered location that
will be named here when publication opens. That attestation must bind all of:

- repository, stable channel, tag, version, and exact 40-hex source commit;
- SHA-256 and size of all three release assets;
- filename, SHA-256, and size of the matching `godot-ai` wheel and sdist;
- the complete qualified Python distribution inventory for each supported
  OS/Python row (name, version, artifact filename, size, and SHA-256);
- SHA-256 of `script/v4-release` and `src/godot_ai/release_verify.py`;
- the RSA public-key SubjectPublicKeyInfo SHA-256 fingerprint; and
- the attestation mechanism and identity used to authenticate those values.

The current candidate's embedded SPKI fingerprint is:

```text
84ebbd811f3a12c09ff4e236bbbbb9310fc23e03fcfc3717ba546747d0d21072
```

This value in the repository is descriptive, not self-authenticating. If the
independent attestation is absent, cannot be authenticated, or disagrees with
the source commit, either verifier hash, the key fingerprint, any plugin or
Python-package identity, or the applicable dependency inventory, stop. The
release is not safe to install.

The dependency inventories attest the environments used to qualify the
release. Production server and transaction commands run uv in isolated,
no-config/no-build mode with official PyPI named explicitly; Godot-owned
spawns also clear inherited uv resolver controls. A later public resolve still
does not cryptographically compare the selected wheel or every dependency to
those attested hashes. PyPI/TLS delivery, the installed uv executable/cache,
and same-user local-machine integrity remain trust roots. Exact critical pins
are checked before FastMCP imports; other transitive drift remains an explicit
packaging risk rather than a claim of a fully locked runtime.

## Verify the release

From the root containing `script/` and `src/`, substitute the source commit
authenticated by the independent attestation.

POSIX shell:

```bash
SOURCE_COMMIT=<attested-40-hex-source-commit>

python3 script/v4-release verify \
  --archive /path/to/godot-ai-v4-plugin.zip \
  --manifest /path/to/godot-ai-v4-plugin.manifest.json \
  --signature /path/to/godot-ai-v4-plugin.manifest.sig \
  --expected-channel stable \
  --expected-repository hi-godot/godot-ai \
  --expected-tag v4.0.0 \
  --expected-version 4.0.0 \
  --expected-source "$SOURCE_COMMIT"
```

PowerShell (use `python` or `py -3`, whichever resolves Python 3.11–3.14):

```powershell
$SourceCommit = "<attested-40-hex-source-commit>"

py -3 script/v4-release verify `
  --archive C:\path\to\godot-ai-v4-plugin.zip `
  --manifest C:\path\to\godot-ai-v4-plugin.manifest.json `
  --signature C:\path\to\godot-ai-v4-plugin.manifest.sig `
  --expected-channel stable `
  --expected-repository hi-godot/godot-ai `
  --expected-tag v4.0.0 `
  --expected-version 4.0.0 `
  --expected-source $SourceCommit
```

Success prints:

```text
OK: signed v4 release identity, archive, and exact tree verified
```

This checks the signature, repository/channel/tag/version/source identity,
archive hash and size, canonical ZIP metadata, path safety, bounded expansion,
every file hash, and the version inside `plugin.cfg`.

## Install the exact tree

Close every Godot editor using the project. Choose a new recovery path outside
the project on the same filesystem. Then run the same identity checks through
the install command:

```bash
python3 script/v4-release install \
  --archive /path/to/godot-ai-v4-plugin.zip \
  --manifest /path/to/godot-ai-v4-plugin.manifest.json \
  --signature /path/to/godot-ai-v4-plugin.manifest.sig \
  --expected-channel stable \
  --expected-repository hi-godot/godot-ai \
  --expected-tag v4.0.0 \
  --expected-version 4.0.0 \
  --expected-source "$SOURCE_COMMIT" \
  --project-root /path/to/your/project \
  --recovery-root /path/outside/project/my-game-before-godot-ai-v4 \
  --editors-closed \
  --clients-and-backend-stopped
```

PowerShell equivalent:

```powershell
py -3 script/v4-release install `
  --archive C:\path\to\godot-ai-v4-plugin.zip `
  --manifest C:\path\to\godot-ai-v4-plugin.manifest.json `
  --signature C:\path\to\godot-ai-v4-plugin.manifest.sig `
  --expected-channel stable `
  --expected-repository hi-godot/godot-ai `
  --expected-tag v4.0.0 `
  --expected-version 4.0.0 `
  --expected-source $SourceCommit `
  --project-root C:\path\to\your\project `
  --recovery-root C:\path\outside\project\my-game-before-godot-ai-v4 `
  --editors-closed `
  --clients-and-backend-stopped
```

`--editors-closed` and `--clients-and-backend-stopped` are explicit assertions,
not process killers. If an editor can still write the add-on, a client can
still invoke the old endpoint, or the old managed backend is running, stop it
before retrying. A fresh install has no old endpoint, but using both assertions
keeps the documented command identical for fresh and migrating projects.

Before it creates an install claim, recovery directory, migration marker, or
add-on tree, `install` runs the exact target actor through the production uv
resolver policy: isolated/no-config/no-build, official PyPI passed explicitly,
and inherited `UV_*` controls removed. The command pins
`godot-ai==4.0.0 godot-ai-update-transaction identity` (with the release's
target version substituted), has a 120-second deadline, and must return the
exact package version and transaction protocol. This proves compatibility and
warms a cold cache; it does not authenticate the wheel independently of the
PyPI trust root. If it fails, install `uv`, restore official PyPI access, and
retry; the project has not been mutated. Do not bypass this check with a merely
compatible or locally different actor.

On success the command prints the retained backup path. Keep that directory
until the project has been exercised and backed up normally. Godot AI never
deletes a successful backup automatically.

For a migrated project, the installer writes a small deny-only marker at
`.godot/godot-ai-v4-migration.json`. Open the project with Godot 4.7 or newer
within the 4.x line. The first v4 start keeps the server dormant, replaces
owned pre-v4 `godot-ai` entries for clients registered in v4 with authenticated
v4 entries. It then removes the marker, records migration completion, and
starts the matching server automatically. A click cannot prove that another
application restarted, so v4 has no global restart-confirmation gate. Clients
normally reconnect to the stable endpoint; restart an individual client only
if its Godot AI tools remain stale or disconnected. If repinning, durable
completion, or marker removal fails, the server remains dormant; retry the
indicated step or restore the retained backup.

The transaction actor atomically elects one editor before any first-start
client mutation. A simultaneous editor is refused before it can claim the same
work. Marker removal is actor-owned and bound to the exact marker digest and
editor process identity; a crashed owner may be replaced only after its process
fingerprint is proven gone (or by the sole reloaded plugin instance in that
same editor process).

Automatic client writes are serialized by one durable account-wide mutation
lock below the OS config directory. If first-start repinning reports that this
lock is safety-stranded, stop the relevant client processes—or reboot—then
remove the **entire exact lock directory named by the error** and retry. Merely
restarting Godot or deleting the lock's `owner.json` does not prove that a
timed-out CLI descendant stopped and leaves automatic mutation barred.

Cherry Studio is not registered in v4 because its MCP server entries live in
an internal database for which Godot AI has no verified read/write surface. If
you configured Godot AI in Cherry Studio before migration, remove that old
entry manually in Cherry Studio; the clean add-on replacement cannot inspect
or delete it.

The marker cannot grant transport or process authority and a fresh install
does not create one. v4 client entries launch the authenticated stdio attach
bridge; old persistent HTTP URL entries cannot carry the rotating private
capability and are not a supported v4 configuration.

## What happens to older state

- The entire old `addons/godot_ai` directory is moved, not overlaid.
- Old `user://godot_ai_update/` state is ignored by v4.
- The v3 Asset Library surface remains frozen and cannot update a project to
  v4.
- Historical v3 updaters do not recognize the v4-only asset name and instead
  direct the user to the release page.
- Existing project scenes, scripts, imports, and settings outside
  `addons/godot_ai` are not migration targets.

Godot 4.5 and 4.6 can parse the v4 entry script only far enough to refuse it.
They construct no lifecycle, updater, transport, or server objects and report:

```text
Godot AI v4 requires Godot 4.7 or newer in the 4.x line; plugin remains inactive.
```

## Recovery

The installer restores the old add-on automatically when a post-backup
activation check fails. If it reports that manual recovery is required, keep
all editors closed and follow the exact paths in the error. The retained old
tree is named `retained-pre-v4-addon`; a rejected v4 tree, when present, is
named `failed-v4-tree`.

Do not delete either tree while diagnosing a failed migration. Record the full
command output and preserve the signed assets, manifest, signature, source
commit, and recovery directory together.
