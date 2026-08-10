---
sidebar_position: 3
title: "Updating & Uninstalling"
description: "How to update Sparkii Agent to the latest version or uninstall it"
---

# Updating & Uninstalling

## Updating

Update to the latest version with a single command:

```bash
sparkii update
```

This pulls the latest code from `main`, updates dependencies, and prompts you to configure any new options that were added since your last update.

:::tip
`sparkii update` automatically detects new configuration options and prompts you to add them. If you skipped that prompt, you can manually run `sparkii config check` to see missing options, then `sparkii config migrate` to interactively add them.
:::

### What happens during an update

When you run `sparkii update`, the following steps occur:

1. **Pre-update snapshot** — a lightweight state snapshot is saved by default (covers pairing data, cron jobs, `config.yaml`, `.env`, `auth.json`, and other state files that get modified at runtime; individual files over 1 GiB are skipped so a large sessions DB never slows the update down). Controlled by `updates.pre_update_backup` (`quick` by default, `full` for a zip of all of `SPARKII_HOME`, `off` to disable). Recoverable via the snapshot restore flow described under [Snapshots and rollback](../user-guide/checkpoints-and-rollback.md).
2. **Git pull** — pulls the latest code from the `main` branch and updates submodules
3. **Post-pull syntax validation + auto-rollback** — after the pull, Sparkii compiles the nine critical files every `sparkii` invocation imports at startup. If any fails to parse (e.g. an orphan merge-conflict marker, an accidentally truncated file), Sparkii runs `git reset --hard <pre-pull-sha>` to roll the install back so your shell stays bootable. Re-run `sparkii update` once the upstream fix lands.
4. **Dependency install** — runs `uv pip install -e ".[all]"` to pick up new or changed dependencies
5. **Config migration** — detects new config options added since your version and prompts you to set them
6. **Gateway auto-restart** — running gateways are refreshed after the update completes so the new code takes effect immediately. Service-managed gateways (systemd on Linux, launchd on macOS) are restarted through the service manager. Manual gateways are relaunched automatically when Sparkii can map the running PID back to a profile.

### Updating against a non-default branch: `--branch`

By default `sparkii update` tracks `origin/main`. Pass `--branch <name>` to update against a different branch — useful for QA channels, feature branches, or release-candidate testing:

```bash
sparkii update --branch release-candidate
sparkii update --check --branch experimental   # preview behindness only
```

If your local checkout is on a different branch, Sparkii auto-stashes any uncommitted work, switches HEAD to the target branch, and then pulls. Branches that don't exist locally are auto-tracked from `origin/<name>` (`git checkout -B <name> origin/<name>`). Branches that don't exist anywhere fail cleanly — your stashed changes are restored before exit so you're never stranded in a weird state. The `main`-only fork-upstream sync logic is automatically skipped on non-`main` branches.

### Local changes on non-interactive updates

When you run `sparkii update` in a terminal, Sparkii stashes any uncommitted source-tree changes, pulls, then **asks** whether to restore them — exactly as it always has. Nothing changes for interactive updates.

When the update runs **without a terminal** — from the desktop/chat app's "Update" button or a gateway-triggered update — there's no prompt to answer. The `updates.non_interactive_local_changes` setting decides what happens to your stashed changes:

```yaml
# ~/.sparkii/config.yaml
updates:
  non_interactive_local_changes: stash   # default: keep + auto-restore
  # non_interactive_local_changes: discard  # throw local source edits away
```

- `stash` (default) — auto-stash, pull, then auto-restore your changes on top of the updated code. Nothing is lost; if a restore hits conflicts they're preserved in a git stash for manual recovery.
- `discard` — auto-stash and drop the stash after the pull, so the update always lands on a clean tree. Use this only on machines where you never intend to keep local edits to the Sparkii source. It stash-drops (not `git reset --hard` + `git clean -fd`), so ignored paths like `node_modules`, `venv`, and build outputs are never touched.

In the desktop app this is **Settings → Advanced → In-App Update Local Changes**.

### Preview-only: `sparkii update --check`

Want to know if an update is available before pulling? Run `sparkii update --check` — it fetches and compares commits against `origin/main`. No files are modified, no gateway is restarted. Useful in scripts and cron jobs that gate on "is there an update".

### Full pre-update backup: `--backup`

For high-value profiles (production gateways, shared team installs) you can opt into a full pre-pull backup of `SPARKII_HOME` (config, auth, sessions, skills, pairing):

```bash
sparkii update --backup
```

Or make it the default for every run:

```yaml
# ~/.sparkii/config.yaml
updates:
  pre_update_backup: full
```

`updates.pre_update_backup` is a single knob with three modes: `quick` (default — the lightweight state snapshot described above), `full` (the quick snapshot plus a complete `SPARKII_HOME` zip; can add minutes on large homes), and `off` (no pre-update backup at all — `--no-backup` does the same for a single run). Legacy boolean values still work: `true` means `full`, `false` means `off`.

:::tip Moving to a new machine instead?
Update backups protect an in-place update. If you're migrating your whole setup to different hardware, use `sparkii backup` + `sparkii import` instead — see [Exporting Sparkii to another machine](/reference/faq#exporting-sparkii-to-another-machine) and [`sparkii backup` vs `sparkii profile export`](/reference/faq#sparkii-backup-vs-sparkii-profile-export).
:::

### Windows: another `sparkii.exe` is running

On Windows, `sparkii update` will refuse to run if it detects another `sparkii.exe` process holding the venv's entry-point executable open — most commonly the Sparkii Desktop app's spawned backend, an open `sparkii` REPL in another terminal, or a running gateway:

```
$ sparkii update
✗ Another sparkii.exe is running:
    PID 12345  sparkii.exe

  Updating now would fail to overwrite ...\venv\Scripts\sparkii.exe because
  Windows blocks REPLACE on a running executable.

  Close Sparkii Desktop, exit any open `sparkii` REPLs, and
  stop the gateway (`sparkii gateway stop`) before retrying.
  Override with `sparkii update --force` if you've already
  confirmed those processes will not write to the venv.
```

Close the listed processes and re-run. If you're sure the concurrent process won't interfere (rare — usually only useful when an antivirus shim is mis-attributed), pass `--force` to skip the check. In that case the updater will still retry the `.exe` rename with exponential backoff and, on stubborn locks, schedule the replacement for next reboot via `MoveFileEx(MOVEFILE_DELAY_UNTIL_REBOOT)` so the update can complete.

A second, separate guard refuses to touch the venv while any process is running from its Python interpreter (the Desktop app's backend, a gateway, a Python REPL). Those processes keep native extension files (`.pyd`) locked, and a dependency sync that dies partway on an access-denied error strands the install between versions. This guard is **not** bypassed by `--force`; if you're certain the detected holders are false positives, use the explicit `sparkii update --force-venv`.

Expected output looks like:

```
$ sparkii update
Updating Sparkii Agent...
📥 Pulling latest code...
Already up to date.  (or: Updating abc1234..def5678)
📦 Updating dependencies...
✅ Dependencies updated
🔍 Checking for new config options...
✅ Config is up to date  (or: Found 2 new options — running migration...)
🔄 Restarting gateways...
✅ Gateway restarted
✅ Sparkii Agent updated successfully!
```

### Recommended Post-Update Validation

`sparkii update` handles the main update path, but a quick validation confirms everything landed cleanly:

1. `git status --short` — if the tree is unexpectedly dirty, inspect before continuing
2. `sparkii doctor` — checks config, dependencies, and service health
3. `sparkii --version` — confirm the version bumped as expected
4. If you use the gateway: `sparkii gateway status`
5. If `doctor` reports npm audit issues: run `npm audit fix` in the flagged directory

:::warning Dirty working tree after update
If `git status --short` shows unexpected changes after `sparkii update`, stop and inspect them before continuing. This usually means local modifications were reapplied on top of the updated code, or a dependency step refreshed lockfiles.
:::

### If your terminal disconnects mid-update

`sparkii update` protects itself against accidental terminal loss:

- The update ignores `SIGHUP`, so closing your SSH session or terminal window no longer kills it mid-install. `pip` and `git` child processes inherit this protection, so the Python environment cannot be left half-installed by a dropped connection.
- All output is mirrored to `~/.sparkii/logs/update.log` while the update runs. If your terminal disappears, reconnect and inspect the log to see whether the update finished and whether the gateway restart succeeded:

```bash
tail -f ~/.sparkii/logs/update.log
```

- `Ctrl-C` (SIGINT) and system shutdown (SIGTERM) are still honored — those are deliberate cancellations, not accidents.

You no longer need to wrap `sparkii update` in `screen` or `tmux` to survive a terminal drop.

### Checking your current version

```bash
sparkii version
```

Compare against the latest release at the [GitHub releases page](https://github.com/YueDJ/SpaikiiDesktop/releases).

### Updating from Messaging Platforms

You can also update directly from Telegram, Discord, Slack, WhatsApp, or Teams by sending:

```
/update
```

This pulls the latest code, updates dependencies, and restarts running gateways. The bot will briefly go offline during the restart (typically 5–15 seconds) and then resume.

### Manual Update

If you installed manually (not via the quick installer):

```bash
cd /path/to/sparkii-agent
# Activate the venv you created during install (outside the source tree)
export VIRTUAL_ENV="$HOME/.sparkii/venvs/sparkii-dev"
export PATH="$VIRTUAL_ENV/bin:$PATH"

# Pull latest code
git pull origin main

# Reinstall (picks up new dependencies)
uv pip install -e ".[all]"

# Check for new config options
sparkii config check
sparkii config migrate   # Interactively add any missing options
```

### Rollback instructions

If an update introduces a problem, you can roll back to a previous version:

```bash
cd /path/to/sparkii-agent

# List recent versions
git log --oneline -10

# Roll back to a specific commit
git checkout <commit-hash>
uv pip install -e ".[all]"

# Restart the gateway if running
sparkii gateway restart
```

To roll back to a specific release tag (substitute your previous tag — e.g. a recent release like `v2026.5.16`, or any earlier tag from `git tag --sort=-version:refname`):

```bash
git checkout vX.Y.Z
uv pip install -e ".[all]"
```

:::warning
Rolling back may cause config incompatibilities if new options were added. Run `sparkii config check` after rolling back and remove any unrecognized options from `config.yaml` if you encounter errors.
:::

### Note for Nix users

Nix is no longer an explicitly supported install path (best-effort only) — see [Nix Setup](./nix-setup.md). If you installed via Nix flake, updates are managed through the Nix package manager:

```bash
# Update the flake input
nix flake update sparkii-agent

# Or rebuild with the latest
nix profile upgrade sparkii-agent
```

Nix installations are immutable — rollback is handled by Nix's generation system:

```bash
nix profile rollback
```

See [Nix Setup](./nix-setup.md) for more details.

---

## Uninstalling

```bash
sparkii uninstall
```

The uninstaller gives you the option to keep your configuration files (`~/.sparkii/`) for a future reinstall.

### Manual Uninstall

```bash
rm -f ~/.local/bin/sparkii
rm -rf /path/to/sparkii-agent
rm -rf ~/.sparkii            # Optional — keep if you plan to reinstall
```

:::info
If you installed the gateway as a system service, stop and disable it first:
```bash
sparkii gateway stop
# Linux: systemctl --user disable sparkii-gateway
# macOS: launchctl remove ai.sparkii.gateway
```
:::
