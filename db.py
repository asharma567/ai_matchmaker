
import os
import uuid
from sqlalchemy import Column, String, Text, DateTime, func, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()
Base = declarative_base()

class Message(Base):
    __tablename__ = "whatsapp_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, nullable=True)  # WhatsApp profile username
    sms_message_sid = Column(String, nullable=True)  
    original_replied_message_sender = Column(String, nullable=True) 
    prospect_name=Column(String, nullable=False)
    whatsapp_number = Column(String, nullable=False)
    country_code = Column(String, nullable=True)
    input_query = Column(Text, nullable=True)
    image_uri = Column(Text, nullable=True)  # CDN URL or data URI
    ocr_text = Column(Text, nullable=True)
    ocr_name = Column(String, nullable=True)  # Name(s) from OCR
    query_name = Column(String, nullable=True)  # Name(s) from user query/body
    follow_up = Column(Text, nullable=True)
    about_me = Column(Text, nullable=True)
    intention = Column(String, nullable=True)
    ai_response = Column(Text, nullable=True)
    raw_message = Column(Text, nullable=True)  # Full incoming payload (optional)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class WhatsAppReply(Base):
    __tablename__ = "whatsapp_replies"

    id = Column(Integer, primary_key=True, index=True)
    sid = Column(String, unique=True, nullable=False)  # Twilio SID
    account_sid = Column(String, nullable=False)
    sms_message_sid = Column(String, nullable=True)  
    body = Column(Text, nullable=False)


class UserProfile(Base):
    __tablename__ = "user_profiles"
    id = Column(Integer, primary_key=True)
    whatsapp_number = Column(String, unique=True)
    full_name = Column(String)
    phone = Column(String)
    primary_photo = Column(String)
    birthdate = Column(String)
    gender = Column(String)
    sexual_orientation = Column(String)
    referral = Column(String)
    status = Column(String, default="incomplete")  # Values: 'incomplete', 'skipped', 'complete'
    call_preference= Column(String)
    call_answered = Column(Boolean, default=False)
    transcriptions = Column(Text, nullable=True)  
    about_me = Column(Text, nullable=True)    
    insta_linkedin = Column(String, nullable=True)


POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
# DB Setup
# DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)