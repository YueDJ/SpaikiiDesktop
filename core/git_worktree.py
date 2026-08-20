"""Git worktree safety predicates (moved from the frontend ``cli`` module).

``kanban_db`` (core) needs the same "is this worktree safe to delete" checks
the CLI startup pruner uses.  ``cli.py`` re-exports these names so surface
callers keep working.
"""

from __future__ import annotations


def _worktree_has_unpushed_commits(worktree_path: str, timeout: int = 10) -> bool:
    """Return whether a worktree has commits not reachable from any remote branch.

    ``git log HEAD --not --remotes`` compares against remote-tracking refs under
    ``refs/remotes/*``. If a repo has no remote-tracking refs yet, there is no
    usable remote baseline to compare against, so treat it as having no
    "unpushed" commits.

    SHALLOW-CLONE CAVEAT: in a shallow clone (the installer default) the
    shallow boundary can disconnect an older worktree HEAD from origin/*,
    making already-public commits look unpushed. The verdict here stays
    conservative (True) on purpose — deleting on unverifiable history would
    risk real work. Callers that can afford it should deepen first via
    ``_deepen_shallow_repo`` (the startup pruner does) or check
    ``_repo_is_shallow`` before presenting this verdict as fact.
    """
    import subprocess

    try:
        remote_refs = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname)", "refs/remotes"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, cwd=worktree_path,
        )
        if remote_refs.returncode != 0:
            return True
        if not remote_refs.stdout.strip():
            return False

        result = subprocess.run(
            ["git", "log", "--oneline", "HEAD", "--not", "--remotes"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, cwd=worktree_path,
        )
        if result.returncode != 0:
            return True
        return bool(result.stdout.strip())
    except Exception:
        return True


def _worktree_is_dirty(worktree_path: str, timeout: int = 10) -> bool:
    """Return whether a worktree has uncommitted changes (staged, unstaged, or
    untracked).

    Fails SAFE: on any error returns True so callers do not delete a worktree
    whose state they cannot determine.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, cwd=worktree_path,
        )
        if result.returncode != 0:
            return True
        return bool(result.stdout.strip())
    except Exception:
        return True
