#models.py

from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Text, DateTime, func

Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    from_number = Column(String(32), index=True)
    to_number = Column(String(32))
    
    body = Column(Text)
    role = Column(String(10))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class TempConversation(Base):
    __tablename__ = "temp_conversations"
    id = Column(Integer, primary_key=True)
    from_number = Column(String(32), index=True)
    body = Column(Text, nullable=True)
    media_url = Column(Text, nullable=True)
    ocr_result = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PermanentConversation(Base):
    __tablename__ = "permanent_conversations"
    id = Column(Integer, primary_key=True)
    prospect_name = Column(String(100), index=True)
    from_number = Column(String(32), index=True)
    body = Column(Text)
    media_url = Column(Text, nullable=True)
    ocr_result = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
