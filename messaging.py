import asyncio
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from httpx import AsyncClient as HTTPXClient, BasicAuth
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from db import Message, async_session
from db_utils import save_message_to_db
from llm_utils import (
    get_gpt_vision_response, get_intention_from_user_caption,
    get_intention_from_user_text, get_gpt_response,
    chunk_by_word_boundary, split_replies, split_suggested_messages,
    remove_suggested_messages_block, separate_ocr_name, separate_name_intention
)
from onboarding import redis_client
from utils import fetch_media_as_base64
from validators import normalize_prospect_name, make_prospect_name, extract_country_code

load_dotenv()  

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER")
TWILIO_MESSAGING_URL = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"


async def send_whatsapp_message(to_number: str, message: str, intention: str, sms_message_sid: str, db: AsyncSession):
    MAX_TWILIO_LENGTH = 1550  # WhatsApp message length limit
    sms_message_sid= sms_message_sid
    # Ensure numbers are in Twilio format
    if not to_number.startswith("whatsapp:"):
        to_number = f"whatsapp:{to_number}"
    if not WHATSAPP_NUMBER.startswith("whatsapp:"):
        from_number = f"whatsapp:{WHATSAPP_NUMBER}"
    else:
        from_number = WHATSAPP_NUMBER

    async with HTTPXClient() as client:
        auth = BasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        if intention == "reply_drafting_or_advice":
            # replies = await split_replies(message)
            replies = await split_suggested_messages(message)
            if not replies:
                replies = [message]
            intro = "Absolutely! Here are some engaging and tailored response options for you:"
            all_messages = [intro] + replies
            for chunk in all_messages:
                for part in chunk_by_word_boundary(chunk, MAX_TWILIO_LENGTH):
                    data = {
                        "To": to_number,
                        "From": from_number,
                        "Body": part,
                    }
                    response = await client.post(TWILIO_MESSAGING_URL, data=data, auth=auth)
                    message_data = response.json()
                    # print(message_data)
                    await save_message_to_db(message_data, sms_message_sid, db)
                    response.raise_for_status()
                    await asyncio.sleep(0.5)

        elif intention == "situation_analysis":
            cleaned_message = await remove_suggested_messages_block(message)
            suggested_replies = await split_suggested_messages(message)

            cleaned_chunks = chunk_by_word_boundary(cleaned_message, MAX_TWILIO_LENGTH)
            for idx, chunk in enumerate(cleaned_chunks):
                data = {
                    "To": to_number,
                    "From": from_number,
                    "Body": chunk,
                }
                print(f"Sending cleaned message chunk {idx + 1}/{len(cleaned_chunks)}")
                response = await client.post(TWILIO_MESSAGING_URL, data=data, auth=auth)
                message_data = response.json()
                # print(message_data)
                await save_message_to_db(message_data, sms_message_sid, db)
                response.raise_for_status()
                await asyncio.sleep(0.5)

            if suggested_replies:
                intro = "Here are some response options based on the situation:"
                reply_chunks = [intro] + suggested_replies
                for idx, chunk in enumerate(reply_chunks):
                    for part in chunk_by_word_boundary(chunk, MAX_TWILIO_LENGTH):
                        data = {
                            "To": to_number,
                            "From": from_number,
                            "Body": part,
                        }
                        print(f"Sending suggested reply part {idx + 1}")
                        response = await client.post(TWILIO_MESSAGING_URL, data=data, auth=auth)
                        message_data = response.json()
                        # print(message_data)
                        await save_message_to_db(message_data, sms_message_sid, db)
                        response.raise_for_status()
                        await asyncio.sleep(0.5)

        else:
            for part in chunk_by_word_boundary(message, MAX_TWILIO_LENGTH):
                data = {
                    "To": to_number,
                    "From": from_number,
                    "Body": part,
                }
                response = await client.post(TWILIO_MESSAGING_URL, data=data, auth=auth)
                message_data = response.json()
                # print(message_data)
                await save_message_to_db(message_data, sms_message_sid, db)
                response.raise_for_status()




async def process_and_send_reply(
    from_number,
    body,
    num_media,
    media_urls,
    ProfileName,
    form_dict,
    prospect_name=None,
    sms_message_sid=None,
    original_replied_message_sender=None,
    prev_context_id=None,
    session: AsyncSession = None      # ← ADD this
):
    ai_response = "I can only reply to text/images 🙄, And please—wait for my first response before asking a new question 💆‍♀️."
    MAX_TWILIO_LENGTH = 4096
    ocr_name= None
    name= None
    intention= None

    if num_media > 0:
        user_input = body if body else " "
        data_uris = await fetch_media_as_base64(media_urls)
        print("LEN data_uris:", len(data_uris))
        print()

        full_ocr_text = ""
        ocr_names = []

        for data_uri in data_uris:
            # data_uri = data_uris[0]
            mime_type = data_uri.split(";")[0].split(":")[1]
            print("mime_type", mime_type)
            base64_data = data_uri.split(",")[1]
            # Pass base64_data directly, do NOT decode/encode again
            ocr_input= "Please do the OCR from the given image and extract PERSON_NAME if present in the image"
            vision_response = get_gpt_vision_response(ocr_input, base64_data, mime_type) #NOTE: get_gpt_vision_response donot need user_input, Please DONOT change it
            ocr_part, ocr_name_part = separate_ocr_name(vision_response)
            
            if ocr_part:
                full_ocr_text += ocr_part.strip() + "\n\n----------------------\n"

            if ocr_name_part:
                ocr_names.append(ocr_name_part)

        # Use the first detected name if multiple
        ocr_name = ocr_names[0] if ocr_names else None

        caption_name_intention = get_intention_from_user_caption(user_input)
        print("caption_name_intention :", caption_name_intention)
        name, intention = separate_name_intention(caption_name_intention)
        print()
        print("Combined OCR:\n", full_ocr_text)
        print(f"ocr_name:{ocr_name}, caption_name:{name}, intention:{intention}" )
        ai_response = await get_gpt_response(
            user_input=user_input,
            ocr=full_ocr_text,
            intention=intention,
            session=session,
            prev_context_id=prev_context_id,
        )

        if not intention:
            print("Warnning !! No intention is detected, Default fallback intention to reply_drafting_or_advice ")
            intention= "reply_drafting_or_advice"
    elif body:
        intention_text = get_intention_from_user_text(body)
        name, intention = separate_name_intention(intention_text)
        ai_response = await get_gpt_response(
            user_input=body,
            ocr="",
            intention=intention,
            session=session,
            prev_context_id=prev_context_id,
        )

    print(len(ai_response))
    print()
    ai_response = ai_response[:MAX_TWILIO_LENGTH]
    print("ai_response:", ai_response)
    # await send_whatsapp_message(from_number, ai_response, intention)

    if not prospect_name:
        prospect_name = ocr_name or name or make_prospect_name(intention, ProfileName)
        
        if not prospect_name:
            timestamp_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            prospect_name = f"Oracle_{ProfileName}_{timestamp_id}"
        
        print(f"prospect name resolved as: {prospect_name}")

    fallback_name = f"Oracle_{ProfileName}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    normalized_prospect_name = normalize_prospect_name(prospect_name, fallback_name)
    # After you have all the info you want to store:
    async with async_session() as session:
        await send_whatsapp_message(from_number, ai_response, intention, sms_message_sid, session)
        msg = Message(
            username=ProfileName,  # Set this if you have the WhatsApp profile username
            prospect_name=normalized_prospect_name, 
            whatsapp_number=from_number,
            country_code=extract_country_code(from_number),
            input_query=body,
            image_uri=media_urls[0] if media_urls else None,
            ocr_text=full_ocr_text if num_media > 0 else None,
            ocr_name=ocr_name if num_media > 0 else None, 
            query_name=name ,
            follow_up="false",
            about_me=None,
            intention=intention,
            ai_response=ai_response,
            raw_message=str(form_dict),  # Or the full Twilio payload if you want
            sms_message_sid=sms_message_sid,  
            original_replied_message_sender=original_replied_message_sender  # ✅ NEW
        )
        session.add(msg)
        await session.commit()


async def process_media_after_delay(
    from_number,
    body,
    ProfileName,
    form_dict,
    prospect_name,
    session,                        # ← already passed from webhook
    sms_message_sid=None,
    original_replied_message_sender=None,
    prev_context_id=None
):
    await asyncio.sleep(7)

    redis_key = f"media:{from_number}"
    media_urls = await redis_client.lrange(redis_key, 0, -1)
    await redis_client.delete(redis_key)
    await redis_client.delete(f"media_lock:{from_number}")

    print(f"[Batched Media] Processing {len(media_urls)} media files from {from_number}")

    # Process your batched media here
    await process_and_send_reply(
        from_number,
        body,
        len(media_urls),
        media_urls,
        ProfileName,
        form_dict,
        prospect_name,
        sms_message_sid,
        original_replied_message_sender,
        prev_context_id,
        session                     # ← ADD session here
    )



async def send_signal_user_answered(to_number: str, message: str):
    """
    to_number: Phone number in E.164 format (for SMS: "+1...", for WhatsApp: "+1...")
    use_whatsapp: If True, send via WhatsApp; else, SMS.
    """
    # Ensure numbers are in Twilio format
    if not to_number.startswith("whatsapp:"):
        to_number = f"whatsapp:{to_number}"
    if not WHATSAPP_NUMBER.startswith("whatsapp:"):
        from_number = f"whatsapp:{WHATSAPP_NUMBER}"
    else:
        from_number = WHATSAPP_NUMBER

    data = {
        "From": from_number,
        "To": to_number,
        "Body": message
    }

    async with HTTPXClient() as client:
        auth = BasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        try:
            response = await client.post(
                TWILIO_MESSAGING_URL,
                data=data,
                auth=auth,
                timeout=10
            )
            response.raise_for_status()
            print(f"✅ Thank you message sent to {to_number}")
        except Exception as e:
            print(f"❌ Failed to send thank you message: {e}")



async def send_simple_whatsapp_message(to_number: str, message: str, max_length: int = 1550):
    if not to_number.startswith("whatsapp:"):
        to_number = f"whatsapp:{to_number}"
    if not WHATSAPP_NUMBER.startswith("whatsapp:"):
        from_number = f"whatsapp:{WHATSAPP_NUMBER}"
    else:
        from_number = WHATSAPP_NUMBER

    message += (
        "\n\n📝 Want to revise your profile summary? Just send `/call me` in chat."
    )
    async with HTTPXClient() as client:
        auth = BasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        chunks = chunk_by_word_boundary(message, max_length)

        for idx, part in enumerate(chunks):
            data = {
                "To": to_number,
                "From": from_number,
                "Body": part,
            }
            print(f"📤 Sending chunk {idx + 1}/{len(chunks)}")
            response = await client.post(TWILIO_MESSAGING_URL, data=data, auth=auth)
            response.raise_for_status()
            await asyncio.sleep(0.5)  # throttle to avoid rate limits


async def send_simple_whatsapp_message_prompt(to_number: str, message: str, max_length: int = 1550):
    if not to_number.startswith("whatsapp:"):
        to_number = f"whatsapp:{to_number}"
    if not WHATSAPP_NUMBER.startswith("whatsapp:"):
        from_number = f"whatsapp:{WHATSAPP_NUMBER}"
    else:
        from_number = WHATSAPP_NUMBER

    async with HTTPXClient() as client:
        auth = BasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        chunks = chunk_by_word_boundary(message, max_length)

        for idx, part in enumerate(chunks):
            data = {
                "To": to_number,
                "From": from_number,
                "Body": part,
            }
            print(f"📤 Sending chunk {idx + 1}/{len(chunks)}")
            response = await client.post(TWILIO_MESSAGING_URL, data=data, auth=auth)
            response.raise_for_status()
            await asyncio.sleep(0.5)  # throttle to avoid rate limits