"""Just the `ProposalActionType` enum, split out from app/chat/intent.py into its own module so
app/chat/proposals.py (which app/chat/models.py depends on, for `ProposalSummary`) doesn't have to import
app/chat/intent.py (which itself depends on app/chat/models.py for `ChatMessage`) — avoids a circular
import, nothing more."""

from enum import Enum


class ProposalActionType(str, Enum):
    update_project_fields = "UPDATE_PROJECT_FIELDS"
    add_preference = "ADD_PREFERENCE"
    update_preference = "UPDATE_PREFERENCE"
    remove_preference = "REMOVE_PREFERENCE"
    rollback_design_version = "ROLLBACK_DESIGN_VERSION"
    no_action = "NO_ACTION"
