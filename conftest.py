# conftest.py - pytest configuration and fixtures

import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient
from fastapi.testclient import TestClient

from oracle.messaging.app import app
from oracle.data.db import Base, UserProfile, Message
from oracle.messaging.services import MessageService, UserService, VoiceService, NotificationService


# Test database URL (use in-memory SQLite for tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_engine():
    """Create test database engine"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=True)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest.fixture
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session"""
    async_session = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session


@pytest.fixture
def test_client():
    """Create test client for FastAPI app"""
    return TestClient(app)


@pytest.fixture
async def async_test_client():
    """Create async test client for FastAPI app"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
async def sample_user_profile(test_session):
    """Create a sample user profile for testing"""
    profile = UserProfile(
        whatsapp_number="whatsapp:+1234567890",
        full_name="Test User",
        phone="+1234567890",
        status="complete",
        about_me="Test user profile for testing purposes"
    )
    test_session.add(profile)
    await test_session.commit()
    await test_session.refresh(profile)
    return profile


@pytest.fixture
async def sample_message(test_session):
    """Create a sample message for testing"""
    message = Message(
        whatsapp_number="whatsapp:+1234567890",
        prospect_name="test_prospect",
        input_query="Hello, this is a test message",
        intention="greeting_or_smalltalk",
        ai_response="Hello! How can I help you today?"
    )
    test_session.add(message)
    await test_session.commit()
    await test_session.refresh(message)
    return message


@pytest.fixture
def message_service():
    """Create MessageService instance for testing"""
    return MessageService()


@pytest.fixture
def user_service():
    """Create UserService instance for testing"""
    return UserService()


@pytest.fixture
def voice_service():
    """Create VoiceService instance for testing"""
    return VoiceService(voice_api_url="http://test-voice-api.com/call")


@pytest.fixture
def notification_service():
    """Create NotificationService instance for testing"""
    return NotificationService()


@pytest.fixture
def mock_twilio_form_data():
    """Sample Twilio webhook form data"""
    return {
        "From": "whatsapp:+1234567890",
        "To": "whatsapp:+0987654321",
        "Body": "Hello, this is a test message",
        "ProfileName": "Test User",
        "NumMedia": "0",
        "SmsMessageSid": "test_sid_123",
        "MessageSid": "test_msg_sid_123"
    }


@pytest.fixture
def mock_twilio_media_data():
    """Sample Twilio webhook form data with media"""
    return {
        "From": "whatsapp:+1234567890",
        "To": "whatsapp:+0987654321",
        "Body": "Check out this image",
        "ProfileName": "Test User",
        "NumMedia": "1",
        "MediaUrl0": "https://api.twilio.com/test-image.jpg",
        "MediaContentType0": "image/jpeg",
        "SmsMessageSid": "test_sid_456",
        "MessageSid": "test_msg_sid_456"
    }


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response"""
    return {
        "choices": [{
            "message": {
                "content": "This is a mock AI response for testing purposes."
            }
        }]
    }