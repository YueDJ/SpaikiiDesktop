#!/usr/bin/env python3
"""Phase 0 import-graph scanner for the Sparkii foundation trim.

Read-only. The trim's first obstacle is that the core (the Agent kernel) imports
surface packages (`gateway`, `sparkii_cli`, `cli`).  This script measures that
coupling precisely so the cut plan is grounded in data instead of guesswork.

It is intentionally stdlib-only so it can be re-run on any Python 3 checkout:

    .venv/Scripts/python.exe scripts/phase0_import_scan.py

It writes nothing.  Rerun it after each trim step; the goal is for the
"core -> surface" list to shrink to zero.
"""

from __future__ import annotations

import ast
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# What we treat as the CORE today.  These are the modules that, after the trim,
# must form a self-contained package with no imports from the surface below.
# ---------------------------------------------------------------------------
CORE_DIRS = ("agent", "tools", "providers", "core")

CORE_TOP_FILES = {
    "run_agent.py",
    "model_tools.py",
    "toolsets.py",
    "toolset_distributions.py",
    "batch_runner.py",
    "registration_lifecycle.py",
    "sparkii_state.py",
    "sparkii_state_common.py",
    "sparkii_state_portability.py",
    "sparkii_state_schema.py",
    "sparkii_state_search.py",
    "sparkii_constants.py",
    "sparkii_logging.py",
    "sparkii_time.py",
    "utils.py",
    "trajectory_compressor.py",
}

# The surface packages the core must NOT import.  `gateway`, `sparkii_cli` and
# the top-level `cli` are the three big ones measured so far.
SURFACE_PACKAGES = ("gateway", "sparkii_cli", "cli")

SKIP_DIRS = {
    ".git",
    ".venv",
    ".venv-311-broken",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".qoder",
    "tests",
    "tests-js",
    "website",
    "evals",
    "native",
    "assets",
    "locales",
    "logo-concepts",
    ".plans",
    ".github",
    ".agents",
    ".codex",
    "docker",
    "nix",
    "mcp-research-data",
    "optional-mcps",
    "datagen-config-examples",
    "sparkii_agent.egg-info",
    ".idea",
    ".vscode",
}


def iter_py_files(root: Path) -> list[Path]:
    """Yield .py files under *root*, skipping vendored/generated directories."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                out.append(Path(dirpath) / filename)
    return out


def collect_imports(path: Path) -> tuple[set[str], set[str]]:
    """Return (top_level_roots, all_roots) for one module.

    A "root" is the first component of an imported dotted name, e.g.
    ``from gateway.session_context import ...`` -> ``gateway``.
    Top-level imports (col_offset == 0) are the unconditional hard dependency;
    nested imports include lazy imports inside functions and ``TYPE_CHECKING``
    blocks, which are softer but still a dependency we want to know about.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set(), set()

    top: set[str] = set()
    nested: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import -> skip, it is intra-package
                continue
            if not node.module:
                continue
            roots = [node.module.split(".")[0]]
        else:
            continue
        (top if node.col_offset == 0 else nested).update(roots)
    return top, top | nested


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def is_core(path: Path) -> bool:
    r = rel(path)
    if r in CORE_TOP_FILES:
        return True
    first = r.split("/", 1)[0]
    return first in CORE_DIRS


STRATA = ("S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "REVIEW")


def classify_core(relpath: str) -> tuple[str, str, str]:
    """Return (stratum, confidence, reason) for a file inside the core set.

    This is a rule-based first draft, not ground truth.  HIGH confidence is
    rule-clear; REVIEW means no rule matched and a human should look.
    """
    parts = relpath.split("/")
    dirpath = "/".join(parts[:-1])
    name = parts[-1]

    # Directory-level rules first (a whole subtree shares one stratum).
    dir_rules = (
        ("agent/lsp", "S5", "MEDIUM", "LSP coding assistant (edge)"),
        ("agent/monitoring", "S6", "HIGH", "observability/gateway-health (product)"),
        ("agent/pet", "S6", "HIGH", "pet (product)"),
        ("agent/proxy_sources", "S3", "HIGH", "network proxy sources (core)"),
        ("agent/secret_sources", "S3", "HIGH", "secret/credential sources (core)"),
        ("agent/transports", "S3", "HIGH", "model transport adapters (core)"),
        ("agent/verify", "S3", "MEDIUM", "self-verification (core safety)"),
        ("tools/computer_use", "S5", "HIGH", "computer use (edge)"),
        ("tools/environments", "S3", "HIGH", "terminal execution backends (core)"),
        ("providers", "S3", "MEDIUM", "provider ABC (core abstraction)"),
    )
    for prefix, stratum, conf, reason in dir_rules:
        if dirpath == prefix or dirpath.startswith(prefix + "/"):
            return stratum, conf, reason

    # Top-level core files.
    top_map = {
        "run_agent.py": ("S3", "HIGH", "agent loop (core)"),
        "model_tools.py": ("S3", "HIGH", "tool orchestration (core)"),
        "toolsets.py": ("S4", "HIGH", "toolset resolution (core infra)"),
        "toolset_distributions.py": ("S4", "HIGH", "toolset distribution (core infra)"),
        "batch_runner.py": ("S3", "HIGH", "batch runner (core)"),
        "registration_lifecycle.py": ("S3", "MEDIUM", "tool registration lifecycle"),
        "sparkii_constants.py": ("S0", "HIGH", "constants (nucleus)"),
        "sparkii_logging.py": ("S0", "HIGH", "logging (nucleus)"),
        "sparkii_time.py": ("S0", "HIGH", "time helpers (nucleus)"),
        "utils.py": ("S0", "HIGH", "utilities (nucleus)"),
        "trajectory_compressor.py": ("S3", "HIGH", "trajectory compression (core)"),
    }
    if relpath in top_map:
        return top_map[relpath]
    if name.startswith("sparkii_state"):
        return "S3", "HIGH", "session DB (core)"
    if name == "registry.py" and dirpath == "tools":
        return "S0", "HIGH", "tool registry (nucleus)"

    # Ordered filename rules.  Specific / high-signal categories first.
    # S6: consumer/product surface.
    s6_keys = (
        "billing", "subscription", "credit", "onboarding", "portal", "curator",
        "models_dev", "account_usage", "aux_accounting", "i18n", "insight",
        "learn", "title_generator", "trace_upload", "background_review",
        "stream_diag", "outbound_webhook", "nous_rate", "journey", "tips",
        "display.py", "battery",
    )
    for key in s6_keys:
        if key in name:
            return "S6", "HIGH", f"product/consumer surface ({key})"

    # S5: edge capabilities that should leave the core toolset.
    s5_keys = (
        "browser", "image_gen", "image_generation", "video_gen", "video_generation",
        "flux3", "xai_video", "homeassistant", "kanban", "cronjob", "tts",
        "transcription", "computer_use", "desktop_ui", "project_tool",
        "react_to_message", "wake_word", "voice", "feishu", "microsoft_graph",
        "x_search", "tour", "preview", "window", "focus_pane", "apply_layout",
        "neutts", "fal_common", "image_source", "audio_container", "xai_http",
        "moa_", "relay_", "lsp", "vision", "reaction", "image_",
        "read_terminal", "close_terminal", "blueprint",
    )
    for key in s5_keys:
        if key in name:
            return "S5", "HIGH", f"edge capability ({key})"

    # S4: extension infrastructure (skills / plugins / MCP / toolsets).
    s4_keys = ("skill", "plugin", "mcp_", "toolset", "tool_search", "osv")
    for key in s4_keys:
        if key in name:
            return "S4", "HIGH", f"extension infrastructure ({key})"

    top = relpath.split("/", 1)[0]
    if top in ("agent", "tools", "core"):
        return "S3", "MEDIUM", "default kernel (rule-clear by exclusion)"
    return "REVIEW", "LOW", "no rule matched"


def classify_surface(relpath: str) -> tuple[str, str, str]:
    """Classify gateway/ + sparkii_cli/ files into promote-to-core vs stay-surface."""
    parts = relpath.split("/")
    top = parts[0]
    name = parts[-1]

    if top == "gateway":
        if name == "session_context.py":
            return "S7", "HIGH", "compat shim -> core.session_context (surface)"
        return "S7", "HIGH", "messaging gateway (surface)"

    if top == "sparkii_cli" and len(parts) == 2:
        s2_high = {
            "env_loader.py", "timeouts.py", "timefmt.py", "profiles.py",
            "config.py", "config_defaults.py", "config_migrations.py",
            "models.py", "model_catalog.py", "model_normalize.py",
            "build_info.py", "sqlite_runtime.py", "sqlite_util.py",
            "sqlite_safe_read.py", "tools_config.py", "toolset_validation.py",
            "credential_lifecycle.py", "route_identity.py", "runtime_provider.py",
            "codex_models.py", "fallback_config.py",
        }
        s4_high = {
            "plugins.py", "agent_plugins.py", "plugin_capabilities.py",
            "plugin_index.py", "plugin_packs.py", "plugin_dev.py",
            "mcp_catalog.py", "mcp_config.py", "mcp_security.py",
        }
        if name in s2_high:
            return "S2", "HIGH", "service layer needed by core (promote)"
        if name in s4_high:
            return "S4", "HIGH", "extension infra loader (promote)"
        return "S7", "HIGH", "CLI presentation (surface)"

    if top == "sparkii_cli":
        return "S7", "HIGH", "CLI subcommand/web-router (surface)"

    return "REVIEW", "LOW", "unknown top dir"


def report_strata(core_files: list[Path], offenders: dict[str, dict[str, tuple[bool, set[str]]]]) -> None:
    print()
    print("=" * 78)
    print("S0-S6 AUTO-CLASSIFICATION (core files)")
    print("=" * 78)
    grouped: dict[str, list[str]] = {s: [] for s in STRATA}
    core_rows: list[list[str]] = []
    for path in core_files:
        r = rel(path)
        stratum, conf, reason = classify_core(r)
        imports_surface = "yes" if r in offenders else ""
        core_rows.append([r, stratum, conf, reason, imports_surface])
        flag = " SURFACE" if imports_surface else ""
        grouped[stratum].append(f"{conf:6} {r}{flag}  # {reason}")

    # Persist the full machine list; stdout stays compact.
    csv_path = ROOT / "docs" / "foundation-phase0-strata.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["path", "stratum", "confidence", "reason", "imports_surface"])
        writer.writerows(sorted(core_rows))

    counts = {s: len(grouped[s]) for s in STRATA}
    print(f"full list -> {rel(csv_path)}")
    print("counts:", ", ".join(f"{s}={counts[s]}" for s in STRATA if counts[s]))
    for stratum in ("S0", "S5", "S6", "REVIEW"):
        items = grouped[stratum]
        if not items:
            continue
        print(f"\n[{stratum}] {len(items)}")
        for line in sorted(items):
            print(f"  {line}")

    print()
    print("=" * 78)
    print("S1/S2/S4 PROMOTE-TO-CORE (gateway/ + sparkii_cli/)")
    print("=" * 78)
    promote: dict[str, list[str]] = defaultdict(list)
    for sub in ("gateway", "sparkii_cli"):
        for path in iter_py_files(ROOT / sub):
            r = rel(path)
            stratum, conf, reason = classify_surface(r)
            promote[stratum].append(f"{conf:6} {r}  # {reason}")
    for stratum in ("S1", "S2", "S4"):
        items = sorted(promote[stratum])
        print(f"\n[{stratum}] {len(items)}")
        for line in items:
            print(f"  {line}")
    print(f"\n[S7 stay-surface] {len(promote['S7'])} (not listed)")


def main() -> int:
    files = iter_py_files(ROOT)
    core_files = [f for f in files if is_core(f)]

    # file -> {surface_pkg: (has_top_level, symbols)}
    offenders: dict[str, dict[str, tuple[bool, set[str]]]] = {}
    surface_hits: dict[str, set[str]] = defaultdict(set)

    for path in core_files:
        top, all_roots = collect_imports(path)
        hits = all_roots & set(SURFACE_PACKAGES)
        if not hits:
            continue
        r = rel(path)
        offenders[r] = {}
        for pkg in sorted(hits):
            offenders[r][pkg] = (pkg in top, set())
            surface_hits[pkg].add(r)

    print("=" * 78)
    print("PHASE 0 IMPORT SCAN — core modules importing surface packages")
    print("=" * 78)
    print(f"core files scanned : {len(core_files)}")
    print(f"core files offending: {len(offenders)}")
    print()
    for pkg in SURFACE_PACKAGES:
        print(f"  core files importing '{pkg}': {len(surface_hits[pkg])}")
    print()

    print("-" * 78)
    print("Detailed offenders (package -> core file)")
    print("-" * 78)
    for pkg in SURFACE_PACKAGES:
        paths = sorted(surface_hits[pkg])
        if not paths:
            print(f"\n[{pkg}] none")
            continue
        print(f"\n[{pkg}] {len(paths)} file(s)")
        for p in paths:
            top = offenders[p][pkg][0]
            mark = "TOP" if top else "nested"
            print(f"  {mark:6} {p}")

    report_strata(core_files, offenders)

    return 0


if __name__ == "__main__":
    sys.exit(main())
