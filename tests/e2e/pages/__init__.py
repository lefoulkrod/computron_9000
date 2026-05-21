"""Page Object Models for e2e tests.

Naming follows docs/ui_architecture.md: the three main views are
Chat, Network View, and Agent Activity View. Shared sub-panels
(PreviewPanel, FilePreview, FullscreenPreview) live here too.
"""

from .chat_view import ChatView
from .network_view import NetworkView
from .agent_activity_view import AgentActivityView
from .recent_conversations import RecentConversations
from .preview_panel import PreviewPanel
from .file_preview import FilePreview
from .fullscreen_preview import FullscreenPreview
from .goals_view import GoalsView
from .settings_page import SettingsPage
from .sidebar import Sidebar

__all__ = [
    "ChatView",
    "NetworkView",
    "AgentActivityView",
    "RecentConversations",
    "PreviewPanel",
    "FilePreview",
    "FullscreenPreview",
    "GoalsView",
    "SettingsPage",
    "Sidebar",
]
