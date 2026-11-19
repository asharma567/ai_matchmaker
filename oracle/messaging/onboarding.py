from fastapi.responses import PlainTextResponse
from oracle.utils import parse_datetime_from_user_input
from oracle.data.db_utils import upsert_user_profile
from oracle.llm.llm_utils import evaluate_onboarding_llm  # ← make sure this is correctly imported
from oracle.constant import US_EASTERN


from oracle.llm.prompts import get_welcome_message
from oracle.voice.scheduler import schedule_voice_call
from typing import List
import json
import asyncio
from httpx import AsyncClient as HTTPXClient
import os
from oracle.data.db_utils import upsert_user_profile, get_user_profile
from oracle.messaging.validators import is_valid_phone, parse_birthdate, is_valid_gender, is_valid_call_preference, normalize_text, parse_and_normalize_phone
from oracle.constant import POSITIVE_RESPONSES, NEGATIVE_RESPONSES
from oracle.data.db import UserProfile, async_session
from sqlalchemy import select, update
from oracle.constant import US_EASTERN
from oracle.llm.llm_utils import generate_user_synopsis

import time
import uuid

import redis.asyncio as redis
# from tasks import process_media_batch




redis_client = redis.Redis.from_url("redis://localhost:6379", decode_responses=True)



ONBOARDING_QUESTIONS = [
    {"field": "full_name", "prompt": "Is your name {profile_name}? (Reply 'Yes' or type your correct name)"},
    {"field": "phone", "prompt": "Is your phone number {whatsapp_number}? (Reply 'Yes' or type your phone number)"},
    {"field": "primary_photo", "prompt": "📸 Please upload a clear headshot of yourself."},
    {"field": "insta_linkedin", "prompt": "📷 Please upload your Instagram or LinkedIn screenshots — or reply ‘Skip’ to move on. (One photo only)"},
    {"field": "call_preference", "prompt": "Free for a quick call? Reply ‘yes’ to hop on now"}
]


async def handle_onboarding(form_dict, session):
    from_number = form_dict["From"]
    body = form_dict.get("Body", "").strip()
    num_media = int(form_dict.get("NumMedia", 0))
    profile_name = form_dict.get("ProfileName", "").strip() or "friend"
    whatsapp_number = from_number.replace("whatsapp:", "")

    state = await get_onboarding_state(from_number)
    print("STATE AT. START>>>>>>",state)
    if not state:
        state = {"step": 0, "answers": {}}
        await set_onboarding_state(from_number, state)
        return PlainTextResponse(
            ONBOARDING_QUESTIONS[0]["prompt"].format(
                profile_name=profile_name,
                whatsapp_number=whatsapp_number
            )
        )

    step = state["step"]
    if step >= len(ONBOARDING_QUESTIONS):
        await clear_onboarding_state(from_number)
        return PlainTextResponse("")  #🎉 Onboarding complete!

    question = ONBOARDING_QUESTIONS[step]
    field = question["field"]
    prompt = question["prompt"].format(
        profile_name=profile_name,
        whatsapp_number=whatsapp_number
    )

    # --- Media-based fields (single image only) ---
    if field == "primary_photo":
        if num_media > 0:
            media_url = form_dict.get("MediaUrl0")
            if media_url:
                state["answers"][field] = media_url
                state["step"] += 1
            else:
                return PlainTextResponse("Couldn't read the image. Please try again.")
        else:
            # LLM clarification when no media is received
            llm_eval = await evaluate_onboarding_llm(prompt, body)
            if not llm_eval["get_necessary_ans"]:
                return PlainTextResponse(llm_eval["response_message"])
            return PlainTextResponse("Please upload a clear headshot of yourself.")

    elif field == "insta_linkedin":
        if num_media > 0:
            media_url = form_dict.get("MediaUrl0")
            if media_url:
                state["answers"][field] = media_url
                state["step"] += 1
            else:
                return PlainTextResponse("Couldn't read the image. Please try again.")
        elif body.lower() == "skip":
            state["answers"][field] = "skipped"
            state["step"] += 1
        else:
            # LLM clarification when no media & no "skip"
            llm_eval = await evaluate_onboarding_llm(prompt, body)
            if not llm_eval["get_necessary_ans"]:
                return PlainTextResponse(llm_eval["response_message"])
            return PlainTextResponse("Please upload your Instagram or LinkedIn screenshots — or reply 'Skip' to continue.")

    # --- Text-based fields ---
    else:
        llm_eval = await evaluate_onboarding_llm(prompt, body)

        print("llm_eval>>>>>>>>>", llm_eval)
        print("prompt body>>>>", prompt, body)

        if not llm_eval["get_necessary_ans"]:
            return PlainTextResponse(llm_eval["response_message"])

        parsed = llm_eval["parsed_answer"]

        if field == "phone":
            if parsed.lower() in ("skip", "yes"):
                parsed = whatsapp_number
            else:
                parsed = parse_and_normalize_phone(parsed, from_number)
                if not parsed:
                    return PlainTextResponse("Please enter a valid phone number with country code or type 'skip'.")

        elif field == "full_name" and parsed.lower() == "yes":
            parsed = profile_name

        elif field == "call_preference":
            if parsed.lower() not in ("yes", "text", "no"):
                return PlainTextResponse("Please reply with 'yes' to start a voice call or 'text' for a chat-based interview.")

            if parsed.lower() == "yes":
                to_number = from_number.replace("whatsapp:", "")
                VOICE_API_URL = f"{os.getenv('VOICE_API_BASE_URL')}/call-user"
                try:
                    async with HTTPXClient() as client:
                        resp = await client.post(f"{VOICE_API_URL}?to_number={to_number}")
                        result = resp.json()
                        print("VOICE CALL RESPONSE >>>", result)
                        if result.get("status") != "initiated":
                            print("⚠️ Voice call failed:", result.get("message"))
                except Exception as e:
                    print("🔥 Voice call error:", str(e))

        state["answers"][field] = parsed
        state["step"] += 1

    # --- Final step check ---
    await set_onboarding_state(from_number, state)
    if state["step"] < len(ONBOARDING_QUESTIONS):
        next_prompt = ONBOARDING_QUESTIONS[state["step"]]["prompt"].format(
            profile_name=profile_name,
            whatsapp_number=whatsapp_number
        )
        return PlainTextResponse(next_prompt)
    else:
        await upsert_user_profile(from_number, state["answers"], session, status="complete")
        await clear_onboarding_state(from_number)
        return PlainTextResponse("")
        # return PlainTextResponse("🎉 Onboarding complete! Let me know if you need anything else 😊")



async def handle_new_user(from_number: str, body: str, session, profile_name: str):
    normalized_body = normalize_text(body)

    state = await get_onboarding_state(from_number)
    print("get_onboarding_state is", state)

    # Case 1: First-time message from unknown user
    if not state:
        reply = get_welcome_message(profile_name)
        await set_onboarding_state(from_number, {"step": -1, "answers": {}})
        return PlainTextResponse(reply)

    # Case 2: Waiting for user’s onboarding decision
    if state.get("step") == -1:
        if normalized_body in POSITIVE_RESPONSES:
            state = None
            await set_onboarding_state(from_number, state)
            # Start onboarding by asking the first question
            return await handle_onboarding({"From": from_number, "Body": "", "NumMedia": "0", "ProfileName": profile_name}, session)

        elif normalized_body in NEGATIVE_RESPONSES:
            existing = await session.execute(
                select(UserProfile).where(UserProfile.whatsapp_number == from_number)
            )
            existing_profile = existing.scalar_one_or_none()

            if not existing_profile:
                new_profile = UserProfile(whatsapp_number=from_number, status="skipped")
                session.add(new_profile)
            else:
                existing_profile.status = "skipped"

            await session.commit()
            await clear_onboarding_state(from_number)

            reply = (
                "No problem! In case you want to get onboarded in the future, just send `/onboard` to start the onboarding process.\n\n"
                "How can I help you today other than onboarding? 😃"
            )
            return PlainTextResponse(reply)

        else:
            # Still unclear — ask again
            return PlainTextResponse(
                "Just to confirm — would you like to begin the onboarding process?\n(Reply with Yes or No)"
            )

    # Fallback: if step is somehow corrupted, reset it cleanly
    # return await handle_onboarding(form_dict={"From": from_number, "Body": body, "NumMedia": "0"}, session=session)


# Save onboarding state in Redis (async)
async def set_onboarding_state(whatsapp_number, state):
    await redis_client.set(f"onboard:{whatsapp_number}", json.dumps(state), ex=86400)  # 1 day expiry

# Get onboarding state from Redis (async)
async def get_onboarding_state(whatsapp_number):
    data = await redis_client.get(f"onboard:{whatsapp_number}")
    return json.loads(data) if data else None

# Clear state when done 
async def clear_onboarding_state(whatsapp_number):
    await redis_client.delete(f"onboard:{whatsapp_number}")


async def after_transcript_saved(whatsapp_number: str):
    if not whatsapp_number.startswith("whatsapp:"):
        whatsapp_number = f"whatsapp:{whatsapp_number}"

    async with async_session() as session:
        try:
            profile = await get_user_profile(whatsapp_number, session)
            summary = await generate_user_synopsis(profile)

            stmt = (
                update(UserProfile)
                .where(UserProfile.whatsapp_number == whatsapp_number)
                .values(about_me=summary)
            )
            result = await session.execute(stmt)

            if result.rowcount == 0:
                print(f"⚠️ No rows updated for {whatsapp_number}. Check number format or DB record.")
            else:
                print(f"✅ Updated about_me for {whatsapp_number}")

            await session.commit()

        except Exception as e:
            print(f"❌ Error in after_transcript_saved: {e}")
            await session.rollback()

