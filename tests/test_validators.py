# tests/test_validators.py - Tests for validation functions

import pytest
from oracle.messaging.validators import (
    is_valid_phone, parse_and_normalize_phone, parse_birthdate,
    is_valid_gender, is_valid_call_preference, extract_country_code,
    normalize_text, normalize_prospect_name, pick_prospect_from_body,
    make_prospect_name
)


class TestPhoneValidation:
    """Test phone number validation functions"""

    def test_is_valid_phone_valid_numbers(self):
        """Test valid phone numbers"""
        assert is_valid_phone("1234567890") is True
        assert is_valid_phone("9876543210") is True

    def test_is_valid_phone_invalid_numbers(self):
        """Test invalid phone numbers"""
        assert is_valid_phone("123456789") is False  # Too short
        assert is_valid_phone("12345678901") is False  # Too long
        assert is_valid_phone("123abc7890") is False  # Contains letters
        assert is_valid_phone("") is False  # Empty
        assert is_valid_phone("123-456-7890") is False  # Contains dashes

    def test_parse_and_normalize_phone_valid(self):
        """Test parsing and normalizing valid phone numbers"""
        result = parse_and_normalize_phone("1234567890", "whatsapp:+11234567890")
        assert result is not None
        assert result.startswith("+")

    def test_parse_and_normalize_phone_with_formatting(self):
        """Test parsing phone numbers with formatting"""
        result = parse_and_normalize_phone("123-456-7890", "whatsapp:+11234567890")
        assert result is not None
        assert "-" not in result

    def test_parse_and_normalize_phone_invalid(self):
        """Test parsing invalid phone numbers"""
        result = parse_and_normalize_phone("invalid", "whatsapp:+11234567890")
        assert result is None

    def test_extract_country_code_valid(self):
        """Test extracting country code from WhatsApp number"""
        result = extract_country_code("whatsapp:+11234567890")
        assert result == "1"
        
        result = extract_country_code("whatsapp:+919876543210")
        assert result == "91"

    def test_extract_country_code_invalid(self):
        """Test extracting country code from invalid numbers"""
        result = extract_country_code("invalid")
        assert result is None
        
        result = extract_country_code("")
        assert result is None


class TestBirthdateValidation:
    """Test birthdate parsing functions"""

    def test_parse_birthdate_valid_formats(self):
        """Test valid birthdate formats"""
        assert parse_birthdate("01/15/1990") is not None
        assert parse_birthdate("Jan 15 1990") is not None
        assert parse_birthdate("January 15 1990") is not None
        assert parse_birthdate("1990") is not None
        assert parse_birthdate("Jan 1990") is not None

    def test_parse_birthdate_invalid_formats(self):
        """Test invalid birthdate formats"""
        assert parse_birthdate("invalid") is None
        assert parse_birthdate("32/01/1990") is None  # Invalid day
        assert parse_birthdate("01/15/2050") is None  # Future date
        assert parse_birthdate("") is None

    def test_parse_birthdate_edge_cases(self):
        """Test birthdate parsing edge cases"""
        assert parse_birthdate("1900") is not None  # Very old but valid
        assert parse_birthdate("13/01/1990") is None  # Invalid month


class TestGenderValidation:
    """Test gender validation functions"""

    def test_is_valid_gender_valid_options(self):
        """Test valid gender options"""
        assert is_valid_gender("male") is True
        assert is_valid_gender("female") is True
        assert is_valid_gender("non-binary") is True
        assert is_valid_gender("i don't want to say") is True
        assert is_valid_gender("MALE") is True  # Case insensitive
        assert is_valid_gender(" female ") is True  # Whitespace handling

    def test_is_valid_gender_invalid_options(self):
        """Test invalid gender options"""
        assert is_valid_gender("invalid") is False
        assert is_valid_gender("") is False
        assert is_valid_gender("man") is False
        assert is_valid_gender("woman") is False


class TestCallPreferenceValidation:
    """Test call preference validation functions"""

    def test_is_valid_call_preference_valid_options(self):
        """Test valid call preference options"""
        assert is_valid_call_preference("now") is True
        assert is_valid_call_preference("today 5pm") is True
        assert is_valid_call_preference("tomorrow 10am") is True
        assert is_valid_call_preference("06/26 5pm") is True
        assert is_valid_call_preference("26 Apr 6pm") is True

    def test_is_valid_call_preference_invalid_options(self):
        """Test invalid call preference options"""
        assert is_valid_call_preference("maybe") is False
        assert is_valid_call_preference("never") is False
        assert is_valid_call_preference("invalid time") is False
        assert is_valid_call_preference("") is False


class TestTextNormalization:
    """Test text normalization functions"""

    def test_normalize_text_basic(self):
        """Test basic text normalization"""
        assert normalize_text("Hello, World!") == "hello world"
        assert normalize_text("Test@123") == "test123"
        assert normalize_text("  spaces  ") == "spaces"

    def test_normalize_text_edge_cases(self):
        """Test text normalization edge cases"""
        assert normalize_text("") == ""
        assert normalize_text("!!!@@@###") == ""
        assert normalize_text("123abc456") == "123abc456"

    def test_normalize_prospect_name(self):
        """Test prospect name normalization"""
        assert normalize_prospect_name("John Doe", "fallback") == "john doe"
        assert normalize_prospect_name("", "fallback") == "fallback"
        assert normalize_prospect_name("   ", "fallback") == "fallback"


class TestProspectNameExtraction:
    """Test prospect name extraction functions"""

    def test_pick_prospect_from_body_valid(self):
        """Test valid prospect name extraction"""
        assert pick_prospect_from_body("@john help me") == "john"
        assert pick_prospect_from_body("@ mary what do you think") == "mary"
        assert pick_prospect_from_body("@sarah123 is amazing") == "sarah123"

    def test_pick_prospect_from_body_invalid(self):
        """Test invalid prospect name extraction"""
        assert pick_prospect_from_body("no prospect here") is None
        assert pick_prospect_from_body("") is None
        assert pick_prospect_from_body("@") is None
        assert pick_prospect_from_body("email@domain.com") is None

    def test_make_prospect_name_intentions(self):
        """Test prospect name generation based on intention"""
        result = make_prospect_name("self_reflection_or_general", "testuser")
        assert result.startswith("genQ_testuser_")
        
        result = make_prospect_name("greeting_or_smalltalk", "testuser")
        assert result == "greeting_prospect"
        
        result = make_prospect_name("unknown_intention", "testuser")
        assert result is None


class TestValidationIntegration:
    """Test validation functions working together"""

    def test_phone_validation_flow(self):
        """Test complete phone validation flow"""
        whatsapp_number = "whatsapp:+11234567890"
        phone_input = "123-456-7890"
        
        # Extract country code
        country_code = extract_country_code(whatsapp_number)
        assert country_code == "1"
        
        # Parse and normalize
        normalized = parse_and_normalize_phone(phone_input, whatsapp_number)
        assert normalized is not None
        assert normalized.startswith("+1")

    def test_prospect_extraction_flow(self):
        """Test complete prospect extraction flow"""
        message_body = "@sarah help me reply to this"
        
        # Extract prospect name
        prospect = pick_prospect_from_body(message_body)
        assert prospect == "sarah"
        
        # Normalize prospect name
        normalized = normalize_prospect_name(prospect, "unknown")
        assert normalized == "sarah"

    def test_user_input_validation_flow(self):
        """Test validating various user inputs"""
        # Test valid inputs
        assert is_valid_phone("1234567890") is True
        assert is_valid_gender("female") is True
        assert is_valid_call_preference("today 5pm") is True
        assert parse_birthdate("01/15/1990") is not None
        
        # Test invalid inputs
        assert is_valid_phone("invalid") is False
        assert is_valid_gender("invalid") is False
        assert is_valid_call_preference("invalid") is False
        assert parse_birthdate("invalid") is None