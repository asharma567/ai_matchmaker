"""
Prompts module - YAML-based prompts for voice and messaging

Usage:
    from prompts import get_voice_prompt, get_help_message, get_welcome_message
    from prompts.legacy_prompts import situation_analysis, reply_drafting_or_advice
"""

from .yaml_voice_builder import get_yaml_voice_builder
from .legacy_prompts import (
    Synopsis, LLM_ONBOARD_PROMPT, OCR_prompt, situation_analysis,
    reply_drafting_or_advice, self_reflection_or_general, greeting_or_smalltalk,
    MASTER_PROMPT, INTENTION_DETECTION_WHEN_NO_IMAGE, INTENTION_DETECTION_FROM_IMAGE_CAPTION
)

# YAML-managed prompts
def get_voice_prompt(user_name: str) -> str:
    """Get voice prompt with current questions from YAML file"""
    return get_yaml_voice_builder().generate_voice_prompt(user_name)

def get_welcome_message(user_name: str) -> str:
    """Get welcome message from YAML file"""
    return get_yaml_voice_builder().get_welcome_message(user_name)

def get_help_message() -> str:
    """Get help message from YAML file"""
    return get_yaml_voice_builder().get_help_message()

__all__ = [
    'get_voice_prompt', 'get_welcome_message', 'get_help_message',
    'Synopsis', 'LLM_ONBOARD_PROMPT', 'OCR_prompt', 'situation_analysis',
    'reply_drafting_or_advice', 'self_reflection_or_general', 'greeting_or_smalltalk',
    'MASTER_PROMPT', 'INTENTION_DETECTION_WHEN_NO_IMAGE', 'INTENTION_DETECTION_FROM_IMAGE_CAPTION'
]