#!/usr/bin/env python3
"""Mechanical Hermes → Sparkii rebrand for upstream sync merges.

Applies identifier/path renames to a clean hermes-agent tree so it can merge
into the already-rebranded Sparkii tree. Preserves third-party HermesClaw refs.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".uv-cache",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "sparkii_agent.egg-info",
    "hermes_agent.egg-info",
}

# Placeholder protects third-party product names during bulk replace.
# Tokens must NOT contain hermes/Hermes/HERMES — the final substring sweep
# would corrupt them before unprotect.
HERMESCLAW_TOKEN = "___THIRDPARTY_CLAW_PRESERVE___"
HERMESCLAW_URL_TOKEN = "___THIRDPARTY_CLAW_URL_PRESERVE___"
HERMESBENCH_TOKEN = "___THIRDPARTY_BENCH_PRESERVE___"
HERMESBENCH_URL_TOKEN = "___THIRDPARTY_BENCH_URL_PRESERVE___"

# Ordered content replacements (apply after third-party protection).
# Longer / more specific first.
CONTENT_REPLACEMENTS: list[tuple[str, str]] = [
    (r"HermesAgent", "SparkiiAgent"),
    (r"HermesCLI", "SparkiiCLI"),
    (r"HermesDesktop", "SparkiiDesktop"),
    (r"HermesGateway", "SparkiiGateway"),
    (r"HermesConsole", "SparkiiConsole"),
    (r"HermesSweEnv", "SparkiiSweEnv"),
    (r"HermesHome", "SparkiiHome"),
    (r"HermesState", "SparkiiState"),
    (r"HermesInk", "SparkiiInk"),
    (r"HermesSkin", "SparkiiSkin"),
    (r"HermesToken", "SparkiiToken"),
    (r"HERMES_", "SPARKII_"),
    (r"_HERMES\b", "_SPARKII"),
    (r"hermes-agent", "sparkii-agent"),
    (r"hermes_agent", "sparkii_agent"),
    (r"hermes-cli", "sparkii-cli"),
    (r"hermes_cli", "sparkii_cli"),
    (r"hermes-ink", "sparkii-ink"),
    (r"hermes_ink", "sparkii_ink"),
    (r"hermes-achievements", "sparkii-achievements"),
    (r"hermes_achievements", "sparkii_achievements"),
    (r"hermes-setup", "sparkii-setup"),
    (r"hermes_setup", "sparkii_setup"),
    (r"hermes-gateway", "sparkii-gateway"),
    (r"hermes_gateway", "sparkii_gateway"),
    (r"hermes-kanban", "sparkii-kanban"),
    (r"hermes_kanban", "sparkii_kanban"),
    (r"hermes-frames", "sparkii-frames"),
    (r"hermes_frames", "sparkii_frames"),
    (r"hermes-sprite", "sparkii-sprite"),
    (r"hermes_sprite", "sparkii_sprite"),
    (r"hermes-frame-", "sparkii-frame-"),
    (r"hermes_frame_", "sparkii_frame_"),
    (r"hermes-exec", "sparkii-exec"),
    (r"hermes_exec", "sparkii_exec"),
    (r"hermes-bootstrap", "sparkii-bootstrap"),
    (r"hermes_bootstrap", "sparkii_bootstrap"),
    (r"hermes-state", "sparkii-state"),
    (r"hermes_state", "sparkii_state"),
    (r"hermes-logging", "sparkii-logging"),
    (r"hermes_logging", "sparkii_logging"),
    (r"hermes-constants", "sparkii-constants"),
    (r"hermes_constants", "sparkii_constants"),
    (r"hermes-time", "sparkii-time"),
    (r"hermes_time", "sparkii_time"),
    (r"hermes-tools", "sparkii-tools"),
    (r"hermes_tools", "sparkii_tools"),
    (r"hermes-parity", "sparkii-parity"),
    (r"hermes_parity", "sparkii_parity"),
    (r"hermes-profile", "sparkii-profile"),
    (r"hermes_profile", "sparkii_profile"),
    (r"hermes-cron", "sparkii-cron"),
    (r"hermes_cron", "sparkii_cron"),
    # Identifier-level leftovers (get_hermes_home, _hermes_bin, hermes_home, …)
    (r"hermes_", "sparkii_"),
    (r"_hermes\b", "_sparkii"),
    (r"hermes-", "sparkii-"),
    (r"hey_hermes", "hey_sparkii"),
    (r"hey-hermes", "hey-sparkii"),
    (r"main-hermes", "main-sparkii"),
    (r"@hermes/", "@sparkii/"),
    (r"~/.hermes", "~/.sparkii"),
    (r"\.hermes/", ".sparkii/"),
    (r"/hermes/", "/sparkii/"),
    (r"hermes\.dev", "sparkii.dev"),
    (r"hermes\.local", "sparkii.local"),
    (r"hermes-agent\.nousresearch\.com", "sparkii-agent.nousresearch.com"),
    (r"X-Hermes-", "X-Sparkii-"),
    (r"x-hermes-", "x-sparkii-"),
    (r"Hermes Agent", "Sparkii Agent"),
    (r"Hermes Desktop", "Sparkii Desktop"),
    (r"Hermes CLI", "Sparkii CLI"),
    (r"Hermes Gateway", "Sparkii Gateway"),
    (r"Hermes HUD", "Sparkii HUD"),
    # CamelCase / PascalCase compounds (word-boundary alone misses these)
    (r"Hermes(?=[A-Z])", "Sparkii"),
    (r"hermes(?=[A-Z])", "sparkii"),
    (r"\bHermes\b", "Sparkii"),
    (r"\bhermes\b", "sparkii"),
    (r"\bHERMES\b", "SPARKII"),
]

BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".icns",
    ".pdf",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".onnx",
    ".tflite",
    ".zip",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".pyc",
    ".so",
    ".dylib",
    ".dll",
    ".node",
    ".wasm",
    ".mp3",
    ".mp4",
    ".wav",
    ".lock",  # still text usually — handled separately
}


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for name in filenames:
            yield Path(dirpath) / name


def protect_third_party(text: str) -> str:
    text = text.replace("HermesClaw", HERMESCLAW_TOKEN)
    text = text.replace("hermesclaw", HERMESCLAW_URL_TOKEN)
    text = text.replace("HermesBench", HERMESBENCH_TOKEN)
    text = text.replace("hermesbench", HERMESBENCH_URL_TOKEN)
    return text


def unprotect_third_party(text: str) -> str:
    text = text.replace(HERMESCLAW_TOKEN, "HermesClaw")
    text = text.replace(HERMESCLAW_URL_TOKEN, "hermesclaw")
    text = text.replace(HERMESBENCH_TOKEN, "HermesBench")
    text = text.replace(HERMESBENCH_URL_TOKEN, "hermesbench")
    return text


def transform_content(text: str) -> str:
    text = protect_third_party(text)
    for pattern, repl in CONTENT_REPLACEMENTS:
        text = re.sub(pattern, repl, text)
    # Final sweep for CamelCase / embedded leftovers (startHermes, Hermes_Gateway,
    # updateHermes, …) that word-boundary rules miss. Third-party tokens already
    # protected above.
    text = text.replace("Hermes", "Sparkii")
    text = text.replace("hermes", "sparkii")
    text = text.replace("HERMES", "SPARKII")
    return unprotect_third_party(text)


def is_probably_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES and path.suffix.lower() != ".lock":
        return True
    try:
        with path.open("rb") as f:
            chunk = f.read(8192)
        if b"\0" in chunk:
            return True
    except OSError:
        return True
    return False


def rename_paths(root: Path) -> int:
    """Rename deepest paths first so parents don't break children."""
    # Collect all paths (files + dirs) containing hermes/Hermes
    all_paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        pdir = Path(dirpath)
        if any(part in SKIP_DIR_NAMES for part in pdir.parts):
            continue
        for name in filenames:
            all_paths.append(pdir / name)
        # directories themselves (except root)
        if pdir != root:
            all_paths.append(pdir)

    renamed = 0
    # Sort by path depth descending
    all_paths.sort(key=lambda p: len(p.parts), reverse=True)
    for path in all_paths:
        if not path.exists():
            continue
        name = path.name
        new_name = transform_content(name)
        # Also handle CamelCase file stems already covered; ensure hermes→sparkii
        if new_name == name:
            continue
        dest = path.with_name(new_name)
        if dest.exists():
            # If both exist, leave for merge conflict resolution later
            print(f"SKIP rename (dest exists): {path} -> {dest}", file=sys.stderr)
            continue
        path.rename(dest)
        renamed += 1
    return renamed


def rewrite_files(root: Path) -> tuple[int, int]:
    changed = 0
    skipped = 0
    for path in iter_files(root):
        # Never rewrite this script itself if present under root
        if path.name == "_rebrand_hermes_to_sparkii.py":
            continue
        # Never rewrite gitlink / git metadata files (worktree .git is a file)
        if path.name == ".git" or ".git" in path.parts:
            skipped += 1
            continue
        if is_probably_binary(path):
            skipped += 1
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            skipped += 1
            continue
        # Decode
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                text = raw.decode(encoding)
                used = encoding
                break
            except UnicodeDecodeError:
                text = None
                used = None
        else:
            skipped += 1
            continue
        new_text = transform_content(text)
        if new_text != text:
            path.write_bytes(new_text.encode(used or "utf-8"))
            changed += 1
    return changed, skipped


def main() -> int:
    if not ROOT.exists():
        print(f"Root not found: {ROOT}", file=sys.stderr)
        return 1
    print(f"Rebranding under {ROOT}")
    renamed = rename_paths(ROOT)
    print(f"Renamed paths: {renamed}")
    changed, skipped = rewrite_files(ROOT)
    print(f"Rewrote files: {changed} (skipped binary/unreadable: {skipped})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
