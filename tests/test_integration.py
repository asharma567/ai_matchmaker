# tests/test_integration.py - Integration tests for the application

import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from httpx import AsyncClient

from main import app


class TestWebhookIntegration:
    """Test webhook endpoint integration"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_scheduled_jobs_endpoint(self, client):
        """Test scheduled jobs endpoint"""
        response = client.get("/scheduled-jobs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @patch('main.validator.validate')
    @patch('main.get_onboarding_state')
    @patch('main.handle_new_user')
    def test_webhook_new_user_flow(self, mock_handle_new_user, mock_get_state, mock_validate, client):
        """Test webhook flow for new user"""
        # Setup mocks
        mock_validate.return_value = True
        mock_get_state.return_value = None
        mock_handle_new_user.return_value = "Welcome! Would you like to get onboarded?"
        
        # Prepare form data
        form_data = {
            "From": "whatsapp:+1234567890",
            "To": "whatsapp:+0987654321",
            "Body": "Hello",
            "ProfileName": "Test User",
            "NumMedia": "0",
            "SmsMessageSid": "test_sid_123"
        }
        
        with patch('main.session') as mock_session:
            mock_session.execute.return_value.scalar_one_or_none.return_value = None
            
            response = client.post(
                "/webhook",
                data=form_data,
                headers={"X-Twilio-Signature": "test_signature"}
            )
            
            assert response.status_code == 200
            mock_handle_new_user.assert_called_once()

    @patch('main.validator.validate')
    @patch('main.get_onboarding_state')
    def test_webhook_help_command(self, mock_get_state, mock_validate, client):
        """Test webhook help command"""
        mock_validate.return_value = True
        mock_get_state.return_value = None
        
        form_data = {
            "From": "whatsapp:+1234567890",
            "Body": "/help",
            "NumMedia": "0",
            "SmsMessageSid": "test_sid_123"
        }
        
        with patch('main.session') as mock_session:
            mock_session.execute.return_value.scalar_one_or_none.return_value = MagicMock(status="complete")
            
            response = client.post(
                "/webhook",
                data=form_data,
                headers={"X-Twilio-Signature": "test_signature"}
            )
            
            assert response.status_code == 200
            assert "Available Commands" in response.text

    @patch('main.validator.validate')
    @patch('main.get_onboarding_state')
    def test_webhook_invalid_signature(self, mock_get_state, mock_validate, client):
        """Test webhook with invalid signature"""
        mock_validate.return_value = False
        
        form_data = {
            "From": "whatsapp:+1234567890",
            "Body": "Hello",
            "NumMedia": "0",
            "SmsMessageSid": "test_sid_123"
        }
        
        response = client.post(
            "/webhook",
            data=form_data,
            headers={"X-Twilio-Signature": "invalid_signature"}
        )
        
        assert response.status_code == 400
        assert "Invalid signature" in response.json()["detail"]

    @patch('main.validator.validate')
    @patch('main.get_onboarding_state')
    @patch('httpx.AsyncClient')
    def test_webhook_call_command_success(self, mock_client, mock_get_state, mock_validate, client):
        """Test webhook call command success"""
        mock_validate.return_value = True
        mock_get_state.return_value = None
        
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "initiated"}
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
        
        form_data = {
            "From": "whatsapp:+1234567890",
            "Body": "/call me",
            "NumMedia": "0",
            "SmsMessageSid": "test_sid_123"
        }
        
        with patch('main.session') as mock_session:
            mock_profile = MagicMock(status="complete")
            mock_session.execute.return_value.scalar_one_or_none.return_value = mock_profile
            
            response = client.post(
                "/webhook",
                data=form_data,
                headers={"X-Twilio-Signature": "test_signature"}
            )
            
            assert response.status_code == 200
            assert "calling you right now" in response.text

    @patch('main.validator.validate')
    @patch('main.get_onboarding_state')
    def test_webhook_media_message(self, mock_get_state, mock_validate, client):
        """Test webhook with media message"""
        mock_validate.return_value = True
        mock_get_state.return_value = None
        
        form_data = {
            "From": "whatsapp:+1234567890",
            "Body": "Check this image",
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/test-image.jpg",
            "SmsMessageSid": "test_sid_123"
        }
        
        with patch('main.session') as mock_session, \
             patch('main.redis_client') as mock_redis:
            
            mock_profile = MagicMock(status="complete")
            mock_session.execute.return_value.scalar_one_or_none.return_value = mock_profile
            mock_redis.set.return_value = True  # Lock acquired
            
            response = client.post(
                "/webhook",
                data=form_data,
                headers={"X-Twilio-Signature": "test_signature"}
            )
            
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/xml"


class TestEndToEndFlow:
    """Test complete user flow scenarios"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @patch('main.validator.validate')
    @patch('main.get_onboarding_state')
    @patch('main.handle_onboarding')
    def test_complete_onboarding_flow(self, mock_handle_onboarding, mock_get_state, mock_validate, client):
        """Test complete user onboarding flow"""
        mock_validate.return_value = True
        
        # Step 1: User starts onboarding
        mock_get_state.return_value = None
        mock_handle_onboarding.return_value = "Is your name Test User?"
        
        form_data = {
            "From": "whatsapp:+1234567890",
            "Body": "/onboard",
            "ProfileName": "Test User",
            "NumMedia": "0",
            "SmsMessageSid": "test_sid_123"
        }
        
        response = client.post(
            "/webhook",
            data=form_data,
            headers={"X-Twilio-Signature": "test_signature"}
        )
        
        assert response.status_code == 200
        mock_handle_onboarding.assert_called_once()

    @patch('main.validator.validate')
    @patch('main.get_onboarding_state')
    def test_user_journey_help_to_call(self, mock_get_state, mock_validate, client):
        """Test user journey from help to call command"""
        mock_validate.return_value = True
        mock_get_state.return_value = None
        
        # Step 1: User asks for help
        help_data = {
            "From": "whatsapp:+1234567890",
            "Body": "/help",
            "NumMedia": "0",
            "SmsMessageSid": "test_sid_123"
        }
        
        with patch('main.session') as mock_session:
            mock_profile = MagicMock(status="complete")
            mock_session.execute.return_value.scalar_one_or_none.return_value = mock_profile
            
            help_response = client.post(
                "/webhook",
                data=help_data,
                headers={"X-Twilio-Signature": "test_signature"}
            )
            
            assert help_response.status_code == 200
            assert "/call me" in help_response.text

        # Step 2: User requests call
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"status": "initiated"}
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            call_data = {
                "From": "whatsapp:+1234567890",
                "Body": "/call me",
                "NumMedia": "0",
                "SmsMessageSid": "test_sid_124"
            }
            
            with patch('main.session') as mock_session:
                mock_session.execute.return_value.scalar_one_or_none.return_value = mock_profile
                
                call_response = client.post(
                    "/webhook",
                    data=call_data,
                    headers={"X-Twilio-Signature": "test_signature"}
                )
                
                assert call_response.status_code == 200
                assert "calling you right now" in call_response.text


class TestErrorHandling:
    """Test error handling scenarios"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @patch('main.validator.validate')
    def test_webhook_missing_required_fields(self, mock_validate, client):
        """Test webhook with missing required fields"""
        mock_validate.return_value = True
        
        # Missing SmsMessageSid
        form_data = {
            "From": "whatsapp:+1234567890",
            "Body": "Hello",
            "NumMedia": "0"
        }
        
        response = client.post(
            "/webhook",
            data=form_data,
            headers={"X-Twilio-Signature": "test_signature"}
        )
        
        # Should handle gracefully or return appropriate error
        assert response.status_code in [400, 500]

    @patch('main.validator.validate')
    @patch('main.get_onboarding_state')
    def test_webhook_database_error(self, mock_get_state, mock_validate, client):
        """Test webhook behavior during database errors"""
        mock_validate.return_value = True
        mock_get_state.return_value = None
        
        form_data = {
            "From": "whatsapp:+1234567890",
            "Body": "/help",
            "NumMedia": "0",
            "SmsMessageSid": "test_sid_123"
        }
        
        with patch('main.session') as mock_session:
            mock_session.execute.side_effect = Exception("Database connection failed")
            
            response = client.post(
                "/webhook",
                data=form_data,
                headers={"X-Twilio-Signature": "test_signature"}
            )
            
            # Should handle database errors gracefully
            assert response.status_code in [200, 500]