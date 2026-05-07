from sqlalchemy import select, update
from db import WhatsAppReply, UserProfile, Message
from sqlalchemy.ext.asyncio import AsyncSession


async def save_message_to_db(message_data: dict, sms_message_sid: str,db: AsyncSession):
    try:
        new_message = WhatsAppReply(
            sid=message_data.get("sid"),
            account_sid=message_data.get("account_sid"),
            body=message_data.get("body"),
            sms_message_sid= sms_message_sid

        )

        db.add(new_message)
        await db.commit()
        await db.refresh(new_message)
        print(f"Message saved with SID: {new_message.sid}")

    except Exception as e:
        await db.rollback()
        print(f"Error saving message to DB: {e}")


async def upsert_user_profile(from_number, data: dict, session, status="incomplete"):
    existing = await session.execute(
        select(UserProfile).where(UserProfile.whatsapp_number == from_number)
    )
    profile = existing.scalar_one_or_none()

    if profile:
        for key, value in data.items():
            setattr(profile, key, value)
        profile.status = status
    else:
        profile = UserProfile(whatsapp_number=from_number, **data, status=status)
        session.add(profile)

    await session.commit()



async def get_previous_convo(prev_context_id, session: AsyncSession) -> str:
    # Try to find in whatsapp_messages
    stmt_msg = select(Message).where(Message.sms_message_sid == prev_context_id)
    result_msg = await session.execute(stmt_msg)
    message = result_msg.scalar_one_or_none()

    if message:
        return (
            f"🧠 Previous Conversation Context\n"
            f"👤 User Query: {message.input_query or '[None]'}\n"
            f"📄 OCR Extracted Text: {message.ocr_text or '[None]'}\n"
            f"🤖 AI Response: {message.ai_response or '[None]'}"
        )

    # Try in whatsapp_replies (sid → sms_message_sid → Message)
    stmt_reply = select(WhatsAppReply).where(WhatsAppReply.sid == prev_context_id)
    result_reply = await session.execute(stmt_reply)
    reply = result_reply.scalar_one_or_none()

    if reply and reply.sms_message_sid:
        stmt_related_msg = select(Message).where(Message.sms_message_sid == reply.sms_message_sid)
        result_related_msg = await session.execute(stmt_related_msg)
        related_message = result_related_msg.scalar_one_or_none()

        if related_message:
            return (
                f"🧠 Previous Conversation Context (via Reply)\n"
                f"👤 User Query: {related_message.input_query or '[None]'}\n"
                f"📄 OCR Extracted Text: {related_message.ocr_text or '[None]'}\n"
                f"🤖 AI Response: {related_message.ai_response or '[None]'}"
            )

    # If nothing found
    return " "



async def save_transcript(whatsapp_number: str, transcript_text: str, session: AsyncSession):
    try:
        if not whatsapp_number.startswith("whatsapp:"):
            whatsapp_number = f"whatsapp:{whatsapp_number}"

        # Fetch current transcript
        stmt_select = select(UserProfile.transcriptions).where(UserProfile.whatsapp_number == whatsapp_number)
        result = await session.execute(stmt_select)
        current_transcript = result.scalar_one_or_none()

        # Append if exists
        if current_transcript:
            updated_transcript = (
                f"{current_transcript.strip()}\n\n--- REVISED CONVERSATION ---\n\n{transcript_text.strip()}"
            )
        else:
            updated_transcript = transcript_text.strip()

        # Update the field
        stmt_update = (
            update(UserProfile)
            .where(UserProfile.whatsapp_number == whatsapp_number)
            .values(transcriptions=updated_transcript)
        )
        await session.execute(stmt_update)
        await session.commit()
        print(f"💾 Transcript saved for {whatsapp_number}")

    except Exception as e:
        await session.rollback()
        print(f"Error saving transcript for {whatsapp_number}: {e}")



async def get_user_profile(whatsapp_number: str, session: AsyncSession) -> dict:
    if not whatsapp_number.startswith("whatsapp:"):
        whatsapp_number = f"whatsapp:{whatsapp_number}"
    
    stmt = select(UserProfile).where(UserProfile.whatsapp_number == whatsapp_number)
    result = await session.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile:
        raise ValueError(f"No profile found for {whatsapp_number}")
    
    return {
        "name": profile.full_name,
        "phone": profile.whatsapp_number,
        "dob": profile.birthdate or "",
        "gender": profile.gender,
        "orientation": profile.sexual_orientation,
        "transcript": profile.transcriptions,
    }
