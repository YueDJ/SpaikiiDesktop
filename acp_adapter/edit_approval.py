"""ACP protocol wiring for pre-execution edit approval.

The approval *contract* — :class:`EditProposal`, the ContextVar-bound requester,
proposal builders, auto-approve policy and ``maybe_require_edit_approval`` — is
owned by ``core/edit_approval.py`` so the core tool dispatcher
(``model_tools.py``) can enforce it without importing this frontend package.
This module re-exports the contract (keeping patch targets and callers stable)
and adds the ACP-specific pieces: building ``ToolCallUpdate`` permission
payloads and bridging to ``request_permission``.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Callable

# Block 4: contract moved to core; re-export for surface-side callers and tests.
from core.edit_approval import (  # noqa: F401
    AUTO_APPROVE_ASK,
    AUTO_APPROVE_SESSION,
    AUTO_APPROVE_WORKSPACE,
    EditApprovalRequester,
    EditProposal,
    SENSITIVE_AUTO_APPROVE_NAMES,
    build_edit_proposal,
    clear_edit_approval_requester,
    get_edit_approval_requester,
    maybe_require_edit_approval,
    reset_edit_approval_requester,
    set_edit_approval_requester,
    should_auto_approve_edit,
)
from core.edit_approval import _EDIT_APPROVAL_REQUESTER  # noqa: F401
from core.edit_approval import _PERMISSION_REQUEST_IDS  # noqa: F401

logger = logging.getLogger(__name__)


def build_acp_edit_tool_call(proposal: EditProposal):
    """Build the ToolCallUpdate payload for ACP request_permission."""

    import acp

    tool_call_id = f"edit-approval-{next(_PERMISSION_REQUEST_IDS)}"
    return acp.update_tool_call(
        tool_call_id,
        title=f"Approve edit: {proposal.path}",
        kind="edit",
        status="pending",
        content=[
            acp.tool_diff_content(
                path=proposal.path,
                old_text=proposal.old_text,
                new_text=proposal.new_text,
            )
        ],
        raw_input={"tool": proposal.tool_name, "arguments": proposal.arguments},
    )


def make_acp_edit_approval_requester(
    request_permission_fn: Callable,
    loop: asyncio.AbstractEventLoop,
    session_id: str,
    timeout: float = 60.0,
    auto_approve_getter: Callable[[], tuple[str, str | None]] | None = None,
) -> EditApprovalRequester:
    """Return a sync requester that bridges edit proposals to ACP permissions."""

    def _requester(proposal: EditProposal) -> bool:
        from acp.schema import PermissionOption
        from agent.async_utils import safe_schedule_threadsafe

        if auto_approve_getter is not None:
            try:
                policy, cwd = auto_approve_getter()
                if should_auto_approve_edit(proposal, policy, cwd):
                    logger.info("Auto-approved ACP edit under policy %s: %s", policy, proposal.path)
                    return True
            except Exception:
                logger.debug("ACP edit auto-approval policy check failed", exc_info=True)

        options = [
            PermissionOption(option_id="allow_once", kind="allow_once", name="Allow edit"),
            PermissionOption(option_id="deny", kind="reject_once", name="Deny"),
        ]
        tool_call = build_acp_edit_tool_call(proposal)
        coro = request_permission_fn(
            session_id=session_id,
            tool_call=tool_call,
            options=options,
        )
        future = safe_schedule_threadsafe(
            coro,
            loop,
            logger=logger,
            log_message="Edit approval request: failed to schedule on loop",
        )
        if future is None:
            return False
        try:
            response = future.result(timeout=timeout)
        except (FutureTimeout, Exception) as exc:
            future.cancel()
            logger.warning("Edit approval request timed out or failed: %s", exc)
            return False
        outcome = getattr(response, "outcome", None)
        return (
            getattr(outcome, "outcome", None) == "selected"
            and getattr(outcome, "option_id", None) == "allow_once"
        )

    return _requester
