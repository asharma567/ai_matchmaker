# tests/test_services.py - Unit tests for service layer

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services import MessageService, UserService, VoiceService, NotificationService
from db import UserProfile, Message


class TestMessageService:
    """Test MessageService functionality"""

    @pytest.mark.asyncio
    async def test_process_text_message_success(self, message_service):
        """Test successful text message processing"""
        with patch('services.process_with_small_llm') as mock_llm:
            mock_llm.return_value = ("AI response", "extracted_name", "reply_drafting_or_advice")
            
            ai_response, intention, prospect_name = await message_service.process_text_message(
                "whatsapp:+1234567890",
                "Help me reply to this message",
                "test_prospect"
            )
            
            assert ai_response == "AI response"
            assert intention == "reply_drafting_or_advice"
            assert prospect_name == "test_prospect"
            mock_llm.assert_called_once_with("Help me reply to this message", media=False)

    @pytest.mark.asyncio
    async def test_process_text_message_error_handling(self, message_service):
        """Test error handling in text message processing"""
        with patch('services.process_with_small_llm', side_effect=Exception("API Error")):
            ai_response, intention, prospect_name = await message_service.process_text_message(
                "whatsapp:+1234567890",
                "Test message",
                "test_prospect"
            )
            
            assert ai_response == "Sorry, I couldn't process your message right now."
            assert intention == "error"
            assert prospect_name == "test_prospect"

    @pytest.mark.asyncio
    async def test_process_media_message_success(self, message_service):
        """Test successful media message processing"""
        with patch('services.fetch_media_as_base64') as mock_fetch, \
             patch('services.run_ocr_gpt4o') as mock_ocr, \
             patch('services.process_with_small_llm') as mock_llm, \
             patch('services.run_final_gpt4o_analysis') as mock_final:
            
            mock_fetch.return_value = ["data:image/jpeg;base64,test_data"]
            mock_ocr.return_value = ("OCR text result", ["extracted_name"])
            mock_llm.return_value = ("AI response", "extracted_name", "situation_analysis")
            mock_final.return_value = "Final AI analysis"
            
            ai_response, intention, prospect_name, ocr_text = await message_service.process_media_message(
                "whatsapp:+1234567890",
                "Analyze this image",
                ["https://example.com/image.jpg"]
            )
            
            assert ai_response == "Final AI analysis"
            assert intention == "situation_analysis"
            assert prospect_name == "extracted_name"
            assert ocr_text == "OCR text result"

    @pytest.mark.asyncio
    async def test_process_media_message_no_media(self, message_service):
        """Test media message processing when no media is available"""
        with patch('services.fetch_media_as_base64', return_value=[]):
            ai_response, intention, prospect_name, ocr_text = await message_service.process_media_message(
                "whatsapp:+1234567890",
                "Analyze this image",
                []
            )
            
            assert ai_response == "Sorry, I couldn't process your images."
            assert intention == "error"
            assert ocr_text == ""

    def test_determine_prospect_name_with_provided(self, message_service):
        """Test prospect name determination with provided name"""
        result = message_service._determine_prospect_name(
            "provided_prospect", "extracted_name", "intention", "whatsapp:+1234567890"
        )
        assert result == "provided_prospect"

    def test_determine_prospect_name_with_extracted(self, message_service):
        """Test prospect name determination with extracted name"""
        result = message_service._determine_prospect_name(
            None, "extracted_name", "intention", "whatsapp:+1234567890"
        )
        assert result == "extracted_name"

    def test_determine_prospect_name_with_list(self, message_service):
        """Test prospect name determination with list of extracted names"""
        result = message_service._determine_prospect_name(
            None, ["name1", "name2"], "intention", "whatsapp:+1234567890"
        )
        assert result == "name1"


class TestUserService:
    """Test UserService functionality"""

    @pytest.mark.asyncio
    async def test_get_user_profile_exists(self, user_service, test_session, sample_user_profile):
        """Test getting existing user profile"""
        profile = await user_service.get_user_profile("whatsapp:+1234567890", test_session)
        assert profile is not None
        assert profile.whatsapp_number == "whatsapp:+1234567890"
        assert profile.full_name == "Test User"

    @pytest.mark.asyncio
    async def test_get_user_profile_not_exists(self, user_service, test_session):
        """Test getting non-existent user profile"""
        profile = await user_service.get_user_profile("whatsapp:+9999999999", test_session)
        assert profile is None

    @pytest.mark.asyncio
    async def test_get_user_prospects(self, user_service, test_session, sample_message):
        """Test getting user prospects"""
        prospects = await user_service.get_user_prospects("whatsapp:+1234567890", test_session)
        assert len(prospects) == 1
        assert "test_prospect" in prospects

    @pytest.mark.asyncio
    async def test_delete_user_profile_success(self, user_service, test_session, sample_user_profile):
        """Test successful user profile deletion"""
        success = await user_service.delete_user_profile(sample_user_profile, test_session)
        assert success is True
        
        # Verify profile is deleted
        profile = await user_service.get_user_profile("whatsapp:+1234567890", test_session)
        assert profile is None


class TestVoiceService:
    """Test VoiceService functionality"""

    @pytest.mark.asyncio
    async def test_initiate_call_success(self, voice_service):
        """Test successful call initiation"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "initiated", "call_id": "test_call_123"}
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            success, message = await voice_service.initiate_call("whatsapp:+1234567890")
            
            assert success is True
            assert message == "Call initiated successfully"

    @pytest.mark.asyncio
    async def test_initiate_call_failure(self, voice_service):
        """Test failed call initiation"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "failed", "message": "Invalid number"}
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            success, message = await voice_service.initiate_call("whatsapp:+1234567890")
            
            assert success is False
            assert message == "Invalid number"

    @pytest.mark.asyncio
    async def test_initiate_call_exception(self, voice_service):
        """Test call initiation with exception"""
        with patch('httpx.AsyncClient', side_effect=Exception("Network error")):
            success, message = await voice_service.initiate_call("whatsapp:+1234567890")
            
            assert success is False
            assert "Something went wrong" in message


class TestNotificationService:
    """Test NotificationService functionality"""

    @pytest.mark.asyncio
    async def test_send_whatsapp_message_success(self, notification_service, test_session):
        """Test successful WhatsApp message sending"""
        with patch('services.send_simple_whatsapp_message') as mock_send:
            mock_send.return_value = None  # Successful send
            
            success = await notification_service.send_whatsapp_message(
                "whatsapp:+1234567890",
                "Test message",
                test_session
            )
            
            assert success is True
            mock_send.assert_called_once_with("whatsapp:+1234567890", "Test message")

    @pytest.mark.asyncio
    async def test_send_whatsapp_message_failure(self, notification_service, test_session):
        """Test failed WhatsApp message sending"""
        with patch('services.send_simple_whatsapp_message', side_effect=Exception("Send failed")):
            success = await notification_service.send_whatsapp_message(
                "whatsapp:+1234567890",
                "Test message",
                test_session
            )
            
            assert success is False