"""Update-retry recovery state (core).

Tracks whether an updater already completed its deferred dependency install, so
secret-source loading can skip external sources during that same process.
"""


_UPDATE_RETRY_RECOVERED = False


def set_update_retry_recovered() -> None:
    global _UPDATE_RETRY_RECOVERED
    _UPDATE_RETRY_RECOVERED = True


def should_skip_external_secret_sources() -> bool:
    return _UPDATE_RETRY_RECOVERED
