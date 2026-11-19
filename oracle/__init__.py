"""0racle application package.

Subpackages:
    messaging  WhatsApp/Twilio webhook app, command routing, onboarding
    voice      Voice call app (audio WebSocket) and call scheduling
    llm        LLM helpers, prompts and the voice-question YAML
    data       SQLAlchemy models, engine/session and query helpers

The runnable entry points live at the repository root (main.py, voice.py,
start_staging.py); they import from this package.
"""
