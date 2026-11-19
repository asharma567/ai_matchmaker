# services.py - Business logic services

import os
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from oracle.data.db import UserProfile, Message
from oracle.utils import fetch_media_as_base64, run_ocr_gpt4o, process_with_small_llm, run_final_gpt4o_analysis
from oracle.data.db_utils import save_message_to_db
from oracle.messaging.validators import normalize_prospect_name, make_prospect_name


class MessageService:
    """Service for processing and analyzing messages"""
    
    async def process_text_message(
        self,
        from_number: str,
        body: str,
        prospect_name: Optional[str] = None
    ) -> Tuple[str, str, str]:
        """
        Process a text message and return AI response, intention, and prospect name
        
        Returns:
            Tuple[ai_response, intention, processed_prospect_name]
        """
        try:
            # Get intention and AI response from text
            ai_response, extracted_name, intention = await process_with_small_llm(body, media=False)
            
            # Handle prospect name logic
            final_prospect_name = self._determine_prospect_name(
                prospect_name, extracted_name, intention, from_number
            )
            
            return ai_response, intention, final_prospect_name
            
        except Exception as e:
            logging.error(f"Error processing text message: {e}")
            return "Sorry, I couldn't process your message right now.", "error", prospect_name

    async def process_media_message(
        self,
        from_number: str,
        body: str,
        media_urls: List[str],
        prospect_name: Optional[str] = None
    ) -> Tuple[str, str, str, str]:
        """
        Process a message with media attachments
        
        Returns:
            Tuple[ai_response, intention, processed_prospect_name, ocr_text]
        """
        try:
            # Fetch and process media
            data_uris = await fetch_media_as_base64(media_urls)
            if not data_uris:
                return "Sorry, I couldn't process your images.", "error", prospect_name, ""
            
            # Run OCR on images
            ocr_text, ocr_names = await run_ocr_gpt4o(data_uris)
            
            # Get intention from text + media context
            user_input = body if body else "analyze this image"
            ai_response, extracted_name, intention = await process_with_small_llm(
                user_input, media=True
            )
            
            # Determine final prospect name
            final_prospect_name = self._determine_prospect_name(
                prospect_name, extracted_name or ocr_names, intention, from_number
            )
            
            # Generate final AI response with OCR context
            if intention and ocr_text:
                final_response = await run_final_gpt4o_analysis(body, ocr_text, intention)
                return final_response, intention, final_prospect_name, ocr_text
            
            return ai_response, intention, final_prospect_name, ocr_text
            
        except Exception as e:
            logging.error(f"Error processing media message: {e}")
            return "Sorry, I couldn't process your images right now.", "error", prospect_name, ""

    def _determine_prospect_name(
        self,
        provided_prospect: Optional[str],
        extracted_name: Optional[str],
        intention: str,
        from_number: str
    ) -> str:
        """Determine the final prospect name based on various inputs"""
        
        # Use provided prospect name if available
        if provided_prospect:
            return normalize_prospect_name(provided_prospect, "unknown_prospect")
        
        # Use extracted name if available
        if extracted_name:
            if isinstance(extracted_name, list):
                extracted_name = extracted_name[0] if extracted_name else None
            if extracted_name:
                return normalize_prospect_name(extracted_name, "unknown_prospect")
        
        # Generate prospect name based on intention
        profile_name = from_number.split(":")[-1] if ":" in from_number else from_number
        return make_prospect_name(intention, profile_name) or "unknown_prospect"


class UserService:
    """Service for user-related operations"""
    
    async def get_user_profile(self, whatsapp_number: str, session: AsyncSession) -> Optional[UserProfile]:
        """Get user profile by WhatsApp number"""
        result = await session.execute(
            select(UserProfile).where(UserProfile.whatsapp_number == whatsapp_number)
        )
        return result.scalar_one_or_none()
    
    async def get_user_prospects(self, whatsapp_number: str, session: AsyncSession) -> List[str]:
        """Get list of prospects for a user"""
        query = select(Message.prospect_name).where(Message.whatsapp_number == whatsapp_number)
        result = await session.execute(query)
        return result.scalars().unique().all()
    
    async def delete_user_profile(self, profile: UserProfile, session: AsyncSession) -> bool:
        """Delete user profile and return success status"""
        try:
            await session.delete(profile)
            await session.commit()
            return True
        except Exception as e:
            logging.error(f"Error deleting user profile: {e}")
            await session.rollback()
            return False


class VoiceService:
    """Service for voice call operations"""
    
    def __init__(self, voice_api_url: str = None):
        if voice_api_url is None:
            voice_api_url = f"{os.getenv('VOICE_API_BASE_URL')}/call-user"
        self.voice_api_url = voice_api_url
    
    async def initiate_call(self, phone_number: str) -> Tuple[bool, str]:
        """
        Initiate a voice call to the given phone number
        
        Returns:
            Tuple[success: bool, message: str]
        """
        from httpx import AsyncClient
        
        # Clean phone number
        clean_number = phone_number.replace("whatsapp:", "")
        
        try:
            async with AsyncClient() as client:
                resp = await client.post(f"{self.voice_api_url}?to_number={clean_number}")
                result = resp.json()
                
                if result.get("status") == "initiated":
                    return True, "Call initiated successfully"
                else:
                    return False, result.get("message", "Call failed")
                    
        except Exception as e:
            logging.error(f"Voice call error: {e}")
            return False, "Something went wrong while trying to call you"


class NotificationService:
    """Service for sending notifications and messages"""
    
    async def send_whatsapp_message(
        self,
        to_number: str,
        message: str,
        session: AsyncSession,
        sms_message_sid: str = None
    ) -> bool:
        """Send a WhatsApp message"""
        from oracle.messaging.messaging import send_simple_whatsapp_message
        
        try:
            # Use existing messaging function
            await send_simple_whatsapp_message(to_number, message)
            return True
        except Exception as e:
            logging.error(f"Error sending WhatsApp message: {e}")
            return False