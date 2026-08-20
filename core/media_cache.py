"""Core media cache helpers (image/audio/document) + inbound size cap.

Extracted from ``gateway/platforms/base.py`` during the Block 4 repo split so
kernel modules (``tools/mcp_tool.py``, ``tools/skills_tool.py``) can cache
inbound media and enforce the size cap without importing the messaging gateway
package.  ``gateway/platforms/base.py`` re-exports these names for the gateway
adapters; the video/screenshot cache cluster stays in the gateway module.

The ``*_CACHE_DIR`` module constants are monkeypatch seams: tests override them
to redirect cache writes into a temp dir.  Patch targets for the moved helpers
now live here (``core.media_cache.IMAGE_CACHE_DIR`` etc.).
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from sparkii_constants import get_sparkii_dir

logger = logging.getLogger(__name__)

IMAGE_CACHE_DIR = get_sparkii_dir("cache/images", "image_cache")
AUDIO_CACHE_DIR = get_sparkii_dir("cache/audio", "audio_cache")
DOCUMENT_CACHE_DIR = get_sparkii_dir("cache/documents", "document_cache")

# Import-time defaults; _resolve_cache_dir compares against these to tell a
# test monkeypatch from an unmodified constant.
_CACHE_DIR_IMPORT_DEFAULTS = {
    "IMAGE_CACHE_DIR": IMAGE_CACHE_DIR,
    "AUDIO_CACHE_DIR": AUDIO_CACHE_DIR,
    "DOCUMENT_CACHE_DIR": DOCUMENT_CACHE_DIR,
}


def _resolve_cache_dir(constant_name: str, new_subpath: str, old_name: str) -> Path:
    """Resolve fresh via get_sparkii_dir (active profile), unless a test has
    monkeypatched the constant away from its import-time default."""
    fresh = get_sparkii_dir(new_subpath, old_name)
    current = globals().get(constant_name)
    default = _CACHE_DIR_IMPORT_DEFAULTS.get(constant_name)
    if current is not None and default is not None and current != default:
        return Path(current)
    return fresh


# ---------------------------------------------------------------------------
# Inbound media size cap (#13145)
#
# Inbound image / audio / video payloads are buffered fully into process
# memory before being written to the cache directory. With no cap, a single
# large upload (Discord Nitro allows 500 MB) — or a remote URL in an inbound
# message payload pointing at an arbitrarily large file — can spike RAM and
# OOM-kill the gateway. The ``cache_*_from_bytes`` helpers (the shared funnel
# every platform reaches eventually) and the ``cache_*_from_url`` downloaders
# enforce this cap, so the protection holds regardless of which platform
# adapter or code path produced the bytes.
#
# Configurable via ``gateway.max_inbound_media_bytes`` in config.yaml.
# ``0`` disables the cap. Default 128 MiB — generous enough for ordinary
# photos/voice notes/short clips while still bounding a hostile upload.
# ---------------------------------------------------------------------------
DEFAULT_INBOUND_MEDIA_MAX_BYTES = 128 * 1024 * 1024


def get_inbound_media_max_bytes() -> int:
    """Return the max inbound image/audio/video bytes allowed in memory.

    Reads ``gateway.max_inbound_media_bytes`` from config.yaml. ``0`` (or a
    negative / unparseable value) disables the cap. Non-fatal if config is
    unreadable — falls back to the default.
    """
    try:
        from core.config import load_config_readonly as _load_config
        cfg = _load_config()  # read-only: .get() only, never mutated
    except Exception:
        return DEFAULT_INBOUND_MEDIA_MAX_BYTES
    gw = cfg.get("gateway", {}) if isinstance(cfg, dict) else {}
    if not isinstance(gw, dict) or "max_inbound_media_bytes" not in gw:
        return DEFAULT_INBOUND_MEDIA_MAX_BYTES
    try:
        return int(gw["max_inbound_media_bytes"])
    except (TypeError, ValueError):
        return DEFAULT_INBOUND_MEDIA_MAX_BYTES


def validate_inbound_media_size(
    size: int,
    *,
    media_type: str = "media",
    max_bytes: Optional[int] = None,
) -> None:
    """Raise ``ValueError`` if an inbound media payload exceeds the cap.

    A ``max_bytes`` of ``0`` (or the configured cap resolving to ``0``)
    disables the check entirely. Passing ``max_bytes`` lets callers resolve
    the limit once and reuse it across an incremental read.
    """
    limit = get_inbound_media_max_bytes() if max_bytes is None else max_bytes
    if limit and size > limit:
        raise ValueError(
            f"Inbound {media_type} payload is too large "
            f"({size} bytes > {limit} bytes)"
        )


GATEWAY_SECRET_CAPTURE_UNSUPPORTED_MESSAGE = (
    "Secure secret entry is not supported over messaging. "
    "Load this skill in the local CLI to be prompted, or add the key to ~/.sparkii/.env manually."
)


def get_image_cache_dir() -> Path:
    """Return the image cache directory, creating it if it doesn't exist."""
    d = _resolve_cache_dir("IMAGE_CACHE_DIR", "cache/images", "image_cache")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _looks_like_image(data: bytes) -> bool:
    """Return True if *data* starts with a known image magic-byte sequence."""
    if len(data) < 4:
        return False
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return True
    if data[:2] == b"BM":
        return True
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        return True
    return False


def cache_image_from_bytes(data: bytes, ext: str = ".jpg") -> str:
    """
    Save raw image bytes to the cache and return the absolute file path.

    Args:
        data: Raw image bytes.
        ext:  File extension including the dot (e.g. ".jpg", ".png").

    Returns:
        Absolute path to the cached image file as a string.

    Raises:
        ValueError: If *data* does not look like a valid image (e.g. an HTML
            error page returned by the upstream server).
    """
    validate_inbound_media_size(len(data), media_type="image")
    if not _looks_like_image(data):
        snippet = data[:80].decode("utf-8", errors="replace")
        raise ValueError(
            f"Refusing to cache non-image data as {ext} "
            f"(starts with: {snippet!r})"
        )
    cache_dir = get_image_cache_dir()
    filename = f"img_{uuid.uuid4().hex[:12]}{ext}"
    filepath = cache_dir / filename
    filepath.write_bytes(data)
    return str(filepath)


def get_audio_cache_dir() -> Path:
    """Return the audio cache directory, creating it if it doesn't exist."""
    d = _resolve_cache_dir("AUDIO_CACHE_DIR", "cache/audio", "audio_cache")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sniff_audio_ext(data: bytes, fallback_ext: str) -> str:
    """Prefer a container-matching extension when audio magic bytes are obvious.

    Thin wrapper around the shared sniffer in ``tools.audio_container`` —
    ONE module owns container detection for both the outbound TTS repair
    (``tools/tts_tool.py``) and this inbound cache path.
    """
    from tools.audio_container import sniff_audio_ext

    return sniff_audio_ext(data, fallback_ext)


def cache_audio_from_bytes(data: bytes, ext: str = ".ogg") -> str:
    """
    Save raw audio bytes to the cache and return the absolute file path.

    Args:
        data: Raw audio bytes.
        ext:  File extension including the dot (e.g. ".ogg", ".mp3").

    Returns:
        Absolute path to the cached audio file as a string.
    """
    validate_inbound_media_size(len(data), media_type="audio")
    cache_dir = get_audio_cache_dir()
    sniffed_ext = _sniff_audio_ext(data, ext)
    filename = f"audio_{uuid.uuid4().hex[:12]}{sniffed_ext}"
    filepath = cache_dir / filename
    filepath.write_bytes(data)
    return str(filepath)


def get_document_cache_dir() -> Path:
    """Return the document cache directory, creating it if it doesn't exist."""
    d = _resolve_cache_dir("DOCUMENT_CACHE_DIR", "cache/documents", "document_cache")
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_document_from_bytes(data: bytes, filename: str) -> str:
    """
    Save raw document bytes to the cache and return the absolute file path.

    The cached filename preserves the original human-readable name with a
    unique prefix: ``doc_{uuid12}_{original_filename}``.

    Args:
        data: Raw document bytes.
        filename: Original filename (e.g. "report.pdf").

    Returns:
        Absolute path to the cached document file as a string.

    Raises:
        ValueError: If the sanitized path escapes the cache directory.
    """
    cache_dir = get_document_cache_dir()
    # Sanitize: strip directory components, null bytes, and control characters
    safe_name = Path(filename).name if filename else "document"
    safe_name = safe_name.replace("\x00", "").strip()
    if not safe_name or safe_name in {".", ".."}:
        safe_name = "document"
    cached_name = f"doc_{uuid.uuid4().hex[:12]}_{safe_name}"
    filepath = cache_dir / cached_name
    # Final safety check: ensure path stays inside cache dir
    if not filepath.resolve().is_relative_to(cache_dir.resolve()):
        raise ValueError(f"Path traversal rejected: {filename!r}")
    filepath.write_bytes(data)
    return str(filepath)
