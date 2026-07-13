"""
Toaster - Scalable Discord Bot Module System
Provides command registry, scheduling, configuration management, and AI integrations.
"""

from toaster.commands import CommandRegistry
from toaster.scheduler import ScheduleRegistry
from toaster.config import load_config, load_token

try:
    from toaster.llm_agents.gemini import get_gemini_response, get_gemini_response_with_key, load_gemini_key
except Exception:
    get_gemini_response = None
    get_gemini_response_with_key = None
    load_gemini_key = None

try:
    from toaster.llm_agents.grok import get_grok_response, get_grok_response_with_key, load_grok_key
except Exception:
    get_grok_response = None
    get_grok_response_with_key = None
    load_grok_key = None

__all__ = [
    "CommandRegistry", 
    "ScheduleRegistry", 
    "load_config", 
    "load_token",
    "get_gemini_response",
    "get_gemini_response_with_key", 
    "load_gemini_key",
    "get_grok_response",
    "get_grok_response_with_key",
    "load_grok_key"
]
