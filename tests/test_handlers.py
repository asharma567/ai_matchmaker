# tests/test_handlers.py - Unit tests for webhook handlers

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import BackgroundTasks
from oracle.messaging.handlers import WebhookHandler, CommandRouter
from oracle.data.db import UserProfile


class TestWebhookHandler:
    """Test WebhookHandler functionality"""

    @pytest.fixture
    def webhook_handler(self):
        return WebhookHandler()

    @pytest.mark.asyncio
    async def test_handle_help_command(self, webhook_handler):
        """Test help command handler"""
        response = await webhook_handler.handle_help_command()
        assert response.status_code == 200
        assert "Available Commands" in response.body.decode()

    @pytest.mark.asyncio
    async def test_handle_call_command_success(self, webhook_handler):
        """Test successful call command"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "initiated"}
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            response = await webhook_handler.handle_call_command("whatsapp:+1234567890")
            
            assert response.status_code == 200
            assert "calling you right now" in response.body.decode()

    @pytest.mark.asyncio
    async def test_handle_call_command_failure(self, webhook_handler):
        """Test failed call command"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "failed", "message": "Error"}
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            response = await webhook_handler.handle_call_command("whatsapp:+1234567890")
            
            assert response.status_code == 200
            assert "failed" in response.body.decode()

    @pytest.mark.asyncio
    async def test_handle_summary_command_with_profile(self, webhook_handler, sample_user_profile):
        """Test summary command with existing profile"""
        background_tasks = BackgroundTasks()
        
        with patch('oracle.messaging.handlers.send_simple_whatsapp_message') as mock_send:
            response = await webhook_handler.handle_summary_command(
                "whatsapp:+1234567890",
                sample_user_profile,
                background_tasks
            )
            
            assert response.status_code == 200
            assert response.media_type == "application/xml"

    @pytest.mark.asyncio
    async def test_handle_summary_command_no_profile(self, webhook_handler):
        """Test summary command without profile"""
        background_tasks = BackgroundTasks()
        
        response = await webhook_handler.handle_summary_command(
            "whatsapp:+1234567890",
            None,
            background_tasks
        )
        
        assert response.status_code == 200
        assert "don't have your summary" in response.body.decode()

    @pytest.mark.asyncio
    async def test_handle_prospects_command_with_prospects(self, webhook_handler, test_session, sample_message):
        """Test prospects command with existing prospects"""
        with patch('sqlalchemy.ext.asyncio.AsyncSession.execute') as mock_execute:
            mock_result = MagicMock()
            mock_result.scalars.return_value.unique.return_value.all.return_value = ["prospect1", "prospect2"]
            mock_execute.return_value = mock_result
            
            response = await webhook_handler.handle_prospects_command(
                "whatsapp:+1234567890",
                test_session
            )
            
            assert response.status_code == 200
            assert "prospect1" in response.body.decode()
            assert "prospect2" in response.body.decode()

    @pytest.mark.asyncio
    async def test_handle_prospects_command_no_prospects(self, webhook_handler, test_session):
        """Test prospects command with no prospects"""
        with patch('sqlalchemy.ext.asyncio.AsyncSession.execute') as mock_execute:
            mock_result = MagicMock()
            mock_result.scalars.return_value.unique.return_value.all.return_value = []
            mock_execute.return_value = mock_result
            
            response = await webhook_handler.handle_prospects_command(
                "whatsapp:+1234567890",
                test_session
            )
            
            assert response.status_code == 200
            assert "don't have any saved prospects" in response.body.decode()

    @pytest.mark.asyncio
    async def test_handle_reset_command_with_profile(self, webhook_handler, test_session, sample_user_profile):
        """Test reset command with existing profile"""
        with patch.object(test_session, 'delete') as mock_delete, \
             patch.object(test_session, 'commit') as mock_commit:
            
            response = await webhook_handler.handle_reset_command(
                "whatsapp:+1234567890",
                sample_user_profile,
                test_session
            )
            
            assert response.status_code == 200
            assert "reset" in response.body.decode()
            mock_delete.assert_called_once_with(sample_user_profile)
            mock_commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_reset_command_no_profile(self, webhook_handler, test_session):
        """Test reset command without existing profile"""
        response = await webhook_handler.handle_reset_command(
            "whatsapp:+1234567890",
            None,
            test_session
        )
        
        assert response.status_code == 200
        assert "No existing profile" in response.body.decode()

    @pytest.mark.asyncio
    async def test_handle_media_message(self, webhook_handler, test_session):
        """Test media message handling"""
        background_tasks = BackgroundTasks()
        
        with patch('oracle.messaging.handlers.redis_client') as mock_redis, \
             patch('oracle.messaging.handlers.process_media_after_delay') as mock_process:
            
            mock_redis.rpush.return_value = None
            mock_redis.expire.return_value = None
            mock_redis.set.return_value = True  # Lock acquired
            
            await webhook_handler.handle_media_message(
                "whatsapp:+1234567890",
                "Check this image",
                {"ProfileName": "Test User"},
                "test_prospect",
                "test_sid",
                None,
                None,
                test_session,
                background_tasks,
                ["https://example.com/image.jpg"],
                1,
                "Test User"
            )
            
            # Verify Redis operations
            mock_redis.rpush.assert_called_once()
            mock_redis.expire.assert_called_once()
            mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_text_message(self, webhook_handler, test_session):
        """Test text message handling"""
        background_tasks = BackgroundTasks()
        
        with patch('oracle.messaging.handlers.process_and_send_reply') as mock_process:
            await webhook_handler.handle_text_message(
                "whatsapp:+1234567890",
                "Hello",
                {"ProfileName": "Test User"},
                "test_prospect",
                "test_sid",
                None,
                None,
                test_session,
                background_tasks,
                [],
                0,
                "Test User"
            )
            
            # Verify background task was added
            assert len(background_tasks.tasks) == 1


class TestCommandRouter:
    """Test CommandRouter functionality"""

    @pytest.fixture
    def command_router(self):
        return CommandRouter()

    def test_get_command_type_help(self, command_router):
        """Test command type detection for help"""
        assert command_router.get_command_type("/help") == "help"

    def test_get_command_type_onboard(self, command_router):
        """Test command type detection for onboard"""
        assert command_router.get_command_type("/onboard") == "onboard"
        assert command_router.get_command_type("/onboard me") == "onboard"

    def test_get_command_type_call(self, command_router):
        """Test command type detection for call"""
        assert command_router.get_command_type("/call") == "call"
        assert command_router.get_command_type("/call me") == "call"

    def test_get_command_type_summary(self, command_router):
        """Test command type detection for summary"""
        assert command_router.get_command_type("/summary") == "summary"
        assert command_router.get_command_type("/aboutme") == "summary"

    def test_get_command_type_prospects(self, command_router):
        """Test command type detection for prospects"""
        assert command_router.get_command_type("/prospects") == "prospects"
        assert command_router.get_command_type("/prospect") == "prospects"

    def test_get_command_type_reset(self, command_router):
        """Test command type detection for reset"""
        assert command_router.get_command_type("/reset") == "reset"
        assert command_router.get_command_type("/restart") == "reset"
        assert command_router.get_command_type("/startover") == "reset"

    def test_get_command_type_message(self, command_router):
        """Test command type detection for regular message"""
        assert command_router.get_command_type("Hello there") == "message"
        assert command_router.get_command_type("How are you?") == "message"

    @pytest.mark.asyncio
    async def test_route_command_help(self, command_router, test_session):
        """Test routing help command"""
        background_tasks = BackgroundTasks()
        
        response = await command_router.route_command(
            "help", {}, test_session, background_tasks
        )
        
        assert response is not None
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_route_command_unknown(self, command_router, test_session):
        """Test routing unknown command"""
        background_tasks = BackgroundTasks()
        
        response = await command_router.route_command(
            "unknown", {}, test_session, background_tasks
        )
        
        assert response is None

    @pytest.mark.asyncio
    async def test_route_command_call(self, command_router, test_session):
        """Test routing call command"""
        background_tasks = BackgroundTasks()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"status": "initiated"}
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            response = await command_router.route_command(
                "call", {}, test_session, background_tasks,
                from_number="whatsapp:+1234567890"
            )
            
            assert response is not None
            assert response.status_code == 200