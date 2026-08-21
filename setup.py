"""
setup.py — wheel/sdist build guard.

pip/PyPI and Homebrew are no longer supported distribution methods for
Sparkii Agent. The wheel would ship without bundled assets (locales, skills,
optional-mcps) since those are resolved at runtime via env-var overrides set
by the nix wrapper or the source-checkout layout. The frontend surfaces
(CLI, gateway, desktop) live in the separate sparkii-frontends repo.

This file overrides the ``bdist_wheel`` and ``sdist`` setuptools commands
to raise an error when run outside a Nix build or an explicit release
build. The PEP 517
``build_wheel`` / ``build_sdist`` hooks in
``setuptools.build_meta`` call these commands internally, so the guard
fires for ``uv build``, ``pip wheel``, ``python -m build``, and direct
``setup.py`` invocations alike.

The one legitimate consumer of ``build_wheel`` is uv2nix, which calls
``setuptools.build_meta.build_wheel`` (→ ``bdist_wheel``) inside a Nix
build sandbox. ``nix/python.nix`` sets ``SPARKII_NIX_BUILD=1`` on the
Sparkii package derivation, so only that build may create an artifact.

Since the split, the frontends repo depends on ``sparkii-agent`` as a git
URL, which pip installs by building a wheel. The release pipeline opts in
explicitly with ``SPARKII_ALLOW_PYPI_BUILD=1``; everyone else keeps the
guard (a wheel without the bundled assets is never accidentally published).

Editable installs (``uv sync``, ``pip install -e .``, ``nix develop``)
use ``build_editable``, which does NOT call ``bdist_wheel`` — it calls
``build_ext`` in editable mode. So the guard does not affect development.
"""

import os

from setuptools import setup
from setuptools.command.sdist import sdist

_IN_NIX_BUILD = os.environ.get("SPARKII_NIX_BUILD") == "1"
_ALLOW_PYPI_BUILD = os.environ.get("SPARKII_ALLOW_PYPI_BUILD") == "1"

_GUARDED = _IN_NIX_BUILD or _ALLOW_PYPI_BUILD

_BLOCK_MESSAGE = (
    "Building wheels or sdists for sparkii-agent is not supported.\n"
    "Sparkii is distributed via the shell installer, Docker image, or Nix.\n"
    "See: https://sparkii-agent.nousresearch.com/docs/getting-started/installation\n"
    "\n"
    "If you are developing, use an editable install instead:\n"
    "  uv sync          # or: uv pip install -e .\n"
    "\n"
    "If you are building with Nix (uv2nix), this error should not fire —\n"
    "the Sparkii Nix derivation sets SPARKII_NIX_BUILD=1. If it does, file a bug."
)


class _GuardedSdist(sdist):
    def run(self, *args, **kwargs):
        if not _GUARDED:
            raise RuntimeError(_BLOCK_MESSAGE)
        return super().run(*args, **kwargs)


cmdclass = {"sdist": _GuardedSdist}

# bdist_wheel is only available when the `wheel` package is installed.
# setuptools.build_meta.build_wheel() calls it internally, so the guard
# fires for all PEP 517 wheel build paths. Define the subclass only when
# the import succeeds — otherwise a None base class raises TypeError at
# class-definition time, before the cmdclass guard can run.
try:
    from setuptools.command.bdist_wheel import bdist_wheel

    class _GuardedBdistWheel(bdist_wheel):
        def run(self, *args, **kwargs):
            if not _GUARDED:
                raise RuntimeError(_BLOCK_MESSAGE)
            return super().run(*args, **kwargs)

    cmdclass["bdist_wheel"] = _GuardedBdistWheel
except ImportError:
    pass

setup(cmdclass=cmdclass)
