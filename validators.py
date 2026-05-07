import re
import phonenumbers
from datetime import datetime
from typing import Optional
from uuid import uuid4



def is_valid_phone(phone: str) -> bool:
    return phone.isdigit() and len(phone) == 10

def parse_and_normalize_phone(phone_str: str, from_number: str) ->  Optional[str]:
    """
    Parse and normalize a phone number using the region inferred from WhatsApp's from_number.
    Returns E.164 format or None if invalid.
    """
    try:
        # Clean formatting
        phone_str = phone_str.strip().replace(" ", "").replace("-", "")
        # Infer default region from WhatsApp number
        default_region = phonenumbers.region_code_for_number(
            phonenumbers.parse(from_number.replace("whatsapp:", ""), None)
        )
        parsed = phonenumbers.parse(phone_str, default_region)

        if phonenumbers.is_possible_number(parsed) and phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        else:
            return None
    except phonenumbers.NumberParseException:
        return None

def parse_birthdate(input_str: str) -> Optional[str]:
    input_str = input_str.strip()
    today = datetime.today()

    # Try full date formats
    for fmt in ("%m/%d/%Y", "%b %d %Y", "%B %d %Y"):
        try:
            dt = datetime.strptime(input_str, fmt)
            if dt > today:
                return None
            return dt.strftime("%m/%d/%Y")
        except ValueError:
            continue

    # Try month and year formats (default day = 1)
    for fmt in ("%b %Y", "%B %Y"):
        try:
            dt = datetime.strptime(input_str, fmt).replace(day=1)
            if dt > today:
                return None
            return dt.strftime("%m/%d/%Y")
        except ValueError:
            continue

    # Try year-only format (default Jan 1)
    if re.fullmatch(r"\d{4}", input_str):
        try:
            dt = datetime.strptime(input_str, "%Y").replace(month=1, day=1)
            if dt > today:
                return None
            return dt.strftime("%m/%d/%Y")
        except ValueError:
            return None

    return None

def is_valid_gender(gender: str) -> bool:
    allowed = {"male", "female", "non-binary", "i don't want to say"}
    return gender.lower().strip() in allowed

def is_valid_call_preference(text: str) -> bool:
    text = text.lower().strip()

    # Direct "now"
    if text == "now":
        return True

    # Today/Tomorrow + time
    time_patterns = [
        r"(today|tomorrow)\s*(at\s*)?\d{1,2}(:\d{2})?\s*(am|pm)",
    ]
    
    # Date formats like 06/26 5pm or 26 Apr 6pm
    date_patterns = [
        r"(\d{1,2}/\d{1,2})(/\d{2,4})?\s*(at\s*)?\d{1,2}(:\d{2})?\s*(am|pm)",
        r"(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(at\s*)?\d{1,2}(:\d{2})?\s*(am|pm)",
    ]

    patterns = time_patterns + date_patterns

    for pattern in patterns:
        if re.search(pattern, text):
            return True
    return False

def extract_country_code(whatsapp_number: str) -> str:
    if whatsapp_number and whatsapp_number.startswith("whatsapp:+"):
        number = whatsapp_number[len("whatsapp:"):]  # "+919876543210"
        parsed = phonenumbers.parse(number, None)
        return str(parsed.country_code)
    return None

def normalize_text(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower().strip())  # remove punctuation, lowercase

def normalize_prospect_name(name: str, fallback: str) -> str:
    cleaned = name.strip().lower()
    return cleaned if cleaned else fallback

def pick_prospect_from_body(body: str) -> Optional[str]:
    """
    Extract the prospect name from the message body if it's mentioned with '@'.
    Supports formats like '@riya' or '@ riya'.
    Returns the extracted name or None if not found.
    """
    if not body:
        return None

    # Match @name or @ name (optional space)
    match = re.search(r"@ ?([a-zA-Z0-9_]+)", body)
    if match:
        return match.group(1).strip()
    return None


def make_prospect_name(intention,ProfileName):
    prospect= None
    if intention == "self_reflection_or_general":
        prospect = f"genQ_{ProfileName}_{uuid4()}"
    elif intention =="greeting_or_smalltalk":
        prospect = "greeting_prospect"
    return prospect

