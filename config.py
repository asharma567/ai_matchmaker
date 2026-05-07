"""
Configuration module - Environment-specific settings
"""
import os
from dotenv import load_dotenv

# Load environment file
load_dotenv()

# Core settings
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
IS_STAGING = ENVIRONMENT == "staging"
IS_PRODUCTION = ENVIRONMENT == "production"

# Twilio settings
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER")
SKIP_TWILIO_VALIDATION = os.getenv("SKIP_TWILIO_VALIDATION", "false").lower() in ("1", "true")

# OpenAI settings
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Database settings
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

# Voice API settings
VOICE_API_BASE_URL = os.getenv("VOICE_API_BASE_URL")

# Voice services
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Build URLs
TWILIO_MESSAGING_URL = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

def get_required_env(key: str) -> str:
    """Get required environment variable, fail fast if missing"""
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Required environment variable {key} is not set")
    return value