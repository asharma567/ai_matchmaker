# handlers.py - WhatsApp webhook command handlers
"""
This breaks down the massive 180-line webhook function into focused handlers.

Before: One giant function handled all WhatsApp commands (/help, /call, /onboard, etc.)
After: Each command gets its own handler function for easier maintenance and testing.

The CommandRouter decides which handler to call based on the user's message.
"""

import os
from fastapi import BackgroundTasks, Request, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from httpx import AsyncClient as HTTPXClient

from db import UserProfile, Message
from utils import get_session
from onboarding import get_onboarding_state, handle_onboarding, handle_new_user
from messaging import process_media_after_delay, process_and_send_reply, send_simple_whatsapp_message
from validators import pick_prospect_from_body
from prompts import get_help_message
from onboarding import redis_client


class WebhookHandler:
    """
    Handles individual WhatsApp commands. Each method processes one type of user request.
    
    This replaces the giant if/elif chain that was in main.py with clean, testable functions.
    """
    
    def __init__(self):
        self.MAX_TWILIO_LENGTH = 1500

    async def handle_help_command(self):
        """
        Handle /help command - shows user available commands
        Returns the help message that explains what the bot can do
        """
        try:
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(get_help_message())
        except ImportError:
            # For testing without FastAPI installed
            return {"type": "text", "content": get_help_message()}

    async def handle_onboard_command(
        self, 
        form_dict: dict, 
        session,  # AsyncSession when available
        existing_profile,  # UserProfile when available
        onboarding_state: dict
    ):
        """Handle /onboard command"""
        if existing_profile and existing_profile.status == "complete" and not onboarding_state:
            return PlainTextResponse("You have already completed onboarding.")
        return await handle_onboarding(form_dict, session)

    async def handle_call_command(self, from_number: str) -> PlainTextResponse:
        """Handle /call or /call me command"""
        print("✅ CALL ME is called")
        to_number = from_number.replace("whatsapp:", "")
        
        VOICE_API_URL = f"{os.getenv('VOICE_API_BASE_URL')}/call-user"
        print(f"🔥 Calling voice service at: {VOICE_API_URL}?to_number={to_number}")
        try:
            async with HTTPXClient() as client:
                resp = await client.post(f"{VOICE_API_URL}?to_number={to_number}")
                result = resp.json()
                print(f"📞 Voice call trigger response: {result}")
                print("📞 Voice call trigger response:", result)

                if result.get("status") == "initiated":
                    return PlainTextResponse("📞 I'm calling you right now. Please keep your phone nearby!")
                else:
                    print(f"⚠️ Voice call failed 😓 {result.get('message')}")
                    return PlainTextResponse(f"⚠️ Voice call failed 😓")
        except Exception as e:
            print("🔥 Voice call error:", str(e))
            return PlainTextResponse("😓 Something went wrong while trying to call you.")

    async def handle_summary_command(
        self, 
        from_number: str, 
        existing_profile: UserProfile,
        background_tasks: BackgroundTasks
    ) -> Response:
        """Handle /summary or /aboutme command"""
        if not existing_profile or not existing_profile.about_me:
            return PlainTextResponse("I don't have your summary yet. Try finishing onboarding first.")

        background_tasks.add_task(
            send_simple_whatsapp_message,
            to_number=from_number,
            message=existing_profile.about_me.strip()
        )
        print("📄 profile summary is called")
        
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Message></Message>
    </Response>"""
        return Response(content=twiml, media_type="application/xml")

    async def handle_prospects_command(
        self, 
        from_number: str, 
        session: AsyncSession
    ) -> Response:
        """Handle /prospects command"""
        query = select(Message.prospect_name).where(Message.whatsapp_number == from_number)
        result = await session.execute(query)
        prospects = result.scalars().unique().all()

        if prospects:
            response_body = "Here are your saved prospects:\n" + "\n".join(f"- {name}" for name in prospects)
        else:
            response_body = "You don't have any saved prospects yet."

        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{response_body[:self.MAX_TWILIO_LENGTH]}</Message>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    async def handle_reset_command(
        self, 
        from_number: str, 
        existing_profile: UserProfile,
        session: AsyncSession
    ) -> Response:
        """Handle /reset, /restart, /startover commands"""
        if existing_profile:
            await session.delete(existing_profile)
            await session.commit()
            print(f"🗑️ Deleted UserProfile for {from_number}")
            response_body = "Your onboarding profile has been reset. You can now send `/onboard` to start again."
        else:
            response_body = "No existing profile found. You can send `/onboard` to start your profile."

        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{response_body[:self.MAX_TWILIO_LENGTH]}</Message>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    async def handle_media_message(
        self,
        from_number: str,
        body: str,
        form_dict: dict,
        prospect_name: str,
        sms_message_sid: str,
        original_replied_message_sender: str,
        prev_context_id: str,
        session: AsyncSession,
        background_tasks: BackgroundTasks,
        media_urls: list,
        num_media: int,
        ProfileName: str
    ) -> None:
        """Handle messages with media attachments"""
        redis_key = f"media:{from_number}"
        
        await redis_client.rpush(redis_key, *media_urls)
        await redis_client.expire(redis_key, 15)
        lock_key = f"media_lock:{from_number}"
        lock_acquired = await redis_client.set(lock_key, "1", ex=15, nx=True)

        if lock_acquired:
            background_tasks.add_task(
                process_media_after_delay,
                from_number,
                body,
                ProfileName,
                form_dict,
                prospect_name,
                session,
                sms_message_sid,
                original_replied_message_sender,
                prev_context_id,
            )

    async def handle_text_message(
        self,
        from_number: str,
        body: str,
        form_dict: dict,
        prospect_name: str,
        sms_message_sid: str,
        original_replied_message_sender: str,
        prev_context_id: str,
        session: AsyncSession,
        background_tasks: BackgroundTasks,
        media_urls: list,
        num_media: int,
        ProfileName: str
    ) -> None:
        """Handle text-only messages"""
        background_tasks.add_task(
            process_and_send_reply,
            from_number,
            body,
            num_media,
            media_urls,
            ProfileName,
            form_dict,
            prospect_name,
            sms_message_sid,
            original_replied_message_sender,
            prev_context_id,
            session
        )


class CommandRouter:
    """Routes commands to appropriate handlers"""
    
    def __init__(self):
        self.handler = WebhookHandler()
    
    def get_command_type(self, body: str) -> str:
        """Determine command type from message body"""
        body_lower = body.lower()
        
        if body_lower == "/help":
            return "help"
        elif body_lower in ("/onboard", "/onboard me"):
            return "onboard"
        elif body_lower in ("/call", "/call me"):
            return "call"
        elif body_lower in ("/summary", "/aboutme"):
            return "summary"
        elif body_lower in ("/prospect", "/prospects"):
            return "prospects"
        elif body_lower in ("/reset", "/restart", "/startover"):
            return "reset"
        else:
            return "message"
    
    async def route_command(
        self,
        command_type: str,
        form_dict: dict,
        session: AsyncSession,
        background_tasks: BackgroundTasks,
        **kwargs
    ):
        """Route command to appropriate handler"""
        if command_type == "help":
            return await self.handler.handle_help_command()
        elif command_type == "onboard":
            return await self.handler.handle_onboard_command(
                form_dict, session, kwargs['existing_profile'], kwargs['onboarding_state']
            )
        elif command_type == "call":
            return await self.handler.handle_call_command(kwargs['from_number'])
        elif command_type == "summary":
            return await self.handler.handle_summary_command(
                kwargs['from_number'], kwargs['existing_profile'], background_tasks
            )
        elif command_type == "prospects":
            return await self.handler.handle_prospects_command(kwargs['from_number'], session)
        elif command_type == "reset":
            return await self.handler.handle_reset_command(
                kwargs['from_number'], kwargs['existing_profile'], session
            )
        else:
            return None  # Handle as regular message