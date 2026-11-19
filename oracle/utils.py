#utils.py

import os
import re
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)
import base64
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from openai import AsyncOpenAI
from httpx import AsyncClient, BasicAuth
from oracle.data.models import TempConversation, PermanentConversation
from oracle.llm.prompts.legacy_prompts import OCR_prompt, situation_analysis, reply_drafting_or_advice, self_reflection_or_general
from dotenv import load_dotenv

load_dotenv()  # ✅ MUST come before using os.getenv

openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")

AUTH = BasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
US_EASTERN = ZoneInfo("America/New_York")

def parse_datetime_from_user_input(text: str) -> Optional[datetime]:
    text = text.lower().strip()

    now = datetime.now(US_EASTERN)
    try:
        if "tomorrow" in text:
            match = re.search(r"(\d{1,2})(:(\d{2}))?\s*(am|pm)", text)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(3)) if match.group(3) else 0
                if "pm" in text and hour < 12:
                    hour += 12
                return datetime(now.year, now.month, now.day + 1, hour, minute, tzinfo=US_EASTERN) 

        elif "today" in text:
            match = re.search(r"(\d{1,2})(:(\d{2}))?\s*(am|pm)", text)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(3)) if match.group(3) else 0
                if "pm" in text and hour < 12:
                    hour += 12
                return datetime(now.year, now.month, now.day, hour, minute, tzinfo=US_EASTERN) 

        elif re.match(r"\d{1,2}/\d{1,2}", text):
            match = re.search(r"(\d{1,2})/(\d{1,2}).*?(\d{1,2})(:(\d{2}))?\s*(am|pm)", text)
            if match:
                month = int(match.group(1))
                day = int(match.group(2))
                hour = int(match.group(3))
                minute = int(match.group(5)) if match.group(5) else 0
                if "pm" in text and hour < 12:
                    hour += 12
                return datetime(now.year, month, day, hour, minute, tzinfo=US_EASTERN) 

        elif re.search(r"\d{1,2}\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", text):
            match = re.search(r"(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec).*?(\d{1,2})(:(\d{2}))?\s*(am|pm)", text)
            if match:
                day = int(match.group(1))
                month_str = match.group(2)
                hour = int(match.group(3))
                minute = int(match.group(5)) if match.group(5) else 0
                if "pm" in text and hour < 12:
                    hour += 12

                month = datetime.strptime(month_str, "%b").month
                return datetime(now.year, month, day, hour, minute, tzinfo=US_EASTERN) 

    except:
        return None

    return None


async def fetch_media_as_base64(media_urls: List[str]) -> List[str]:
    """Downloads Twilio media URLs and returns them as base64 image data URIs."""
    data_uris = []

    async with AsyncClient(auth=AUTH, follow_redirects=True, timeout=10) as http:
        for media_url in media_urls:
            try:
                resp = await http.get(media_url)
                resp.raise_for_status()

                content_type = resp.headers.get("Content-Type", "").lower()
                if not content_type.startswith("image/"):
                    logging.warning(f"Unexpected content type: {content_type}")
                    continue

                b64 = base64.b64encode(resp.content).decode("utf-8")
                data_uri = f"data:{content_type};base64,{b64}"
                data_uris.append(data_uri)

            except Exception as e:
                logging.error(f"Media download error: {e}")

    return data_uris


async def get_session() -> AsyncSession:
    from oracle.data.db import async_session
    async with async_session() as session:
        yield session


async def run_ocr_gpt4o(image_uris):
    prompt = OCR_prompt
    content = [{"type": "text", "text": prompt}] + [
        {"type": "image_url", "image_url": {"url": uri}} for uri in image_uris
    ]
    try:
        resp = await openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": content}]
        )
        reply = resp.choices[0].message.content.strip()

        # Try to extract names
        names = []
        first_20_words = " ".join(reply.split()[:20])
        # Match the PERSON_NAME pattern within the first 20 words
        match = re.search(r"PERSON_NAME\s*:\s*\[(.*?)\]", first_20_words)
        if match:
            try:
                # Extract the raw name string (e.g., Justina)
                raw = match.group(1).strip()
                # Check if the raw value is in a valid format
                if raw:
                    # Normalize to a list of strings if valid
                    names = [raw]  # Use raw directly as it's a valid string
            except Exception as e:
                logging.warning(f"Failed to parse PERSON_NAME: {e}")

        return reply, names

    
    except Exception as e:
        logging.error(f"OCR error: {e}")
        return "", []
    


async def process_with_small_llm(text, media=False):

    sys_prompt = (
        "You are a warm, emotionally intelligent receptionist assistant for a relationship and life advice coach.\n\n"
        "Your job is to:\n"
        "- Greet users kindly and reply in 2–3 short lines.\n"
        "- Sound like a real, human receptionist — empathetic, respectful, natural.\n"
        "- If the user describes someones person name, **internally add at the end of your message** like: (name: Aakash, Tritya)\n"
        "- Internally, try to guess what type of help the user wants based on one of these categories:\n"
        "   1. situation_analysis: The user is describing a real-life situation involving another person and seeking insight into that situation or person's behavior.\n"
        "   2. reply_drafting_or_advice: The user wants help drafting a message or planning how to respond/interact with someone.\n"
        "   3. self_reflection_or_general: The user is asking a general or personal question (about love, relationships, psychology, self), without referring to a specific person.\n"
        "   4. negative_feedback_or_regenerate: The user is expressing dissatisfaction with the previous answer, or asking to regenerate a better or clearer reply.\n\n"
        "Mention this category **at the end of your message** like: (intention: situation_analysis)\n"
        "Only mention one intention. Do not explain or repeat the category — just tag it.\n"
        "NOTE: If user provide Hint (i.e, Hint: Intention cannot be 'self_reflection_or_general') is given then follow the hint when deciding intention. So the intention could be falls under situation_analysis or reply_drafting_or_advice or negative_feedback_or_regenerate but not self_reflection_or_general.\n"
    )


    if media:
        text = f"{text} \n\n (Hint: Intention cannot be 'self_reflection_or_general')"
    print("*******>>",text)
    try:
        resp = await openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": text}
            ]
        )
        full_response = resp.choices[0].message.content.strip()

        # Extract intention (e.g., (intention: reply_drafting_or_advice))
        intention_match = re.search(r"\(intention:\s*(.*?)\)", full_response.lower())
        intention = intention_match.group(1).strip() if intention_match else None

        # Extract names (e.g., (name: Aakash, Tritya))
        name_match = re.search(r"\(name:\s*([^)]+)\)", full_response)
        raw_names = name_match.group(1).strip() if name_match else None

        # Normalize name(s) to a list
        names = [n.strip() for n in raw_names.split(",")] if raw_names else []
        # If only one name, return as string, else list
        name = names[0] if len(names) == 1 else names or None

        # Clean the reply for user-facing output by removing tags
        cleaned_response = re.sub(r"\(name:\s*[^)]+\)", "", full_response)
        cleaned_response = re.sub(r"\(intention:\s*[^)]+\)", "", cleaned_response)
        cleaned_response = cleaned_response.strip()

        return cleaned_response, name, intention

    except Exception as e:
        logging.error(f"Mini LLM error: {e}")
        return "Sorry, something went wrong.", None, None


    


async def migrate_temp_to_permanent(session: AsyncSession, from_number: str, prospect_name: str):
    results = await session.execute(
        select(TempConversation).where(TempConversation.from_number == from_number)
    )
    temp_msgs = results.scalars().all()
    for msg in temp_msgs:
        session.add(PermanentConversation(
            from_number=msg.from_number,
            prospect_name=prospect_name,
            body=msg.body,
            media_url=msg.media_url,
            ocr_result=msg.ocr_result
        ))
        await session.delete(msg)




async def run_final_gpt4o_analysis(body: str, ocr_result: str, intention: str) -> str:
    """
    Combines user message and OCR result, selects prompt and temperature based on intention,
    sends to GPT-4o, and returns a helpful assistant response.
    """
    print("intention:",intention)
    # Select system prompt and temperature based on intention
    if intention == "situation_analysis":
        system_prompt = situation_analysis
        temperature = 0.2   # VIBECHECK
    elif intention == "reply_drafting_or_advice":
        system_prompt = reply_drafting_or_advice
        temperature = 0.5   # REPLY DRAFTER
    elif intention == "self_reflection_or_general":
        system_prompt = self_reflection_or_general
        temperature = 0.3   # GENERAL QUERY
    else:
        logging.warning(f"Unknown intention '{intention}', using fallback system prompt.")
        system_prompt = (
            "You are a helpful assistant. Analyze WhatsApp messages and attached documents/images. "
            "Respond with clarity, empathy, and relevance based on context."
        )
        temperature = 0.1  # Neutral fallback

    # Compose user message
    user_prompt = (
        "Here is the message from the user:\n"
        f"{body or '[No message]'}\n\n"
    )

    if ocr_result:
        user_prompt += (
            "Here is the extracted text from the attached image:\n"
            f"{ocr_result}\n\n"
        )

    try:
        response = await openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logging.error(f"Final GPT-4o response failed: {e}")
        return "Sorry, I couldn't process your message right now."


