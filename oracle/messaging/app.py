from fastapi import BackgroundTasks, FastAPI, Request, Depends, HTTPException, Response
from fastapi.responses import PlainTextResponse, JSONResponse
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import  AsyncSession
from twilio.request_validator import RequestValidator
import logging
import os
from datetime import datetime
from oracle.data.db import Base, Message, engine, UserProfile
from oracle.utils import get_session
from sqlalchemy import select
from oracle.messaging.onboarding import redis_client
from datetime import datetime, timedelta
from oracle.voice.scheduler import scheduler, schedule_voice_call
from zoneinfo import ZoneInfo
from oracle.messaging.onboarding import get_onboarding_state, handle_new_user
from oracle.messaging.validators import pick_prospect_from_body
from oracle.messaging.handlers import CommandRouter

logging.basicConfig(level=logging.INFO)

# Suppress repeated "change detected" logs from watchfiles.main
class SuppressWatchfilesChangeDetected(logging.Filter):
    def filter(self, record):
        if record.name == "watchfiles.main" and "change detected" in record.getMessage():
            return False
        return True

watch_logger = logging.getLogger("watchfiles.main")
watch_logger.addFilter(SuppressWatchfilesChangeDetected())

# Settings
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER")
DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


collection_name = "rag_books"

print("WHATSAPP_NUMBER is ",WHATSAPP_NUMBER)
# DB Setup
# engine = create_async_engine(DATABASE_URL, echo=False)
# async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
validator = RequestValidator(TWILIO_AUTH_TOKEN)



# FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # ✅ Scheduler setup
    scheduler.configure(timezone=ZoneInfo("America/New_York"))
    if not scheduler.running:
        scheduler.start()
        print("✅ APScheduler started inside lifespannnnn")
    yield
    await engine.dispose()

app = FastAPI(lifespan=lifespan)

@app.get("/scheduled-jobs")
def list_jobs():
    jobs = scheduler.get_jobs()
    return [
        {
            "id": job.id,
            "name": getattr(job, "name", "N/A"),
            "next_run_time": getattr(job, "next_run_time", "N/A") or "N/A"
        }
        for job in jobs
    ]

@app.get("/test-scheduler")
async def test_scheduler():
    to_number = "+919476724253" #"+918133860749"  # Put your real test number
    run_time = datetime.now().astimezone().replace(second=0, microsecond=0) + timedelta(minutes=1)

    schedule_voice_call(to_number, run_time)

    return {"message": f"Call scheduled for {run_time.isoformat()}"}


@app.get("/health", tags=["Health Check"])
async def health_check():
    return JSONResponse(content={"status": "ok"}, status_code=200)

@app.post("/webhook", response_class=PlainTextResponse)
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    # Initialize router
    router = CommandRouter()
    
    # Parse request
    form = await request.form()
    form_dict = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")

    # Validate Twilio signature
    host = request.headers.get("host")
    url = f"https://{host}{request.url.path}"
    if request.url.query:
        url += f"?{request.url.query}"

    if not os.getenv("SKIP_TWILIO_VALIDATION", "").lower() in ("1", "true"):
        if not validator.validate(url, form_dict, signature):
            print("❌ Invalid Twilio signature on /webhook")
            raise HTTPException(status_code=400, detail="Invalid signature")

    # Extract message data
    from_number = form_dict.get("From")
    body = form_dict.get("Body", "").strip()
    ProfileName = form_dict.get("ProfileName", "")
    num_media = int(form_dict.get("NumMedia", 0))
    sms_message_sid = form_dict.get("SmsMessageSid")
    if not sms_message_sid:
        return Response("Missing SmsMessageSid - not a valid Twilio webhook", status_code=400)
    original_replied_message_sender = form_dict.get("OriginalRepliedMessageSender")
    prev_context_id = form_dict.get("OriginalRepliedMessageSid")
    media_urls = [form_dict.get(f"MediaUrl{i}") for i in range(num_media)]
    
    print("message body", body)
    
    # Get user state
    onboarding_state = await get_onboarding_state(from_number)
    existing_profile = await session.execute(
        select(UserProfile).where(UserProfile.whatsapp_number == from_number)
    )
    existing_profile = existing_profile.scalar_one_or_none()

    # Handle onboarding flow
    if (body.lower() in ("/onboard", "/onboard me") or 
        (onboarding_state and onboarding_state.get("step", -2) >= 0)):
        return await router.route_command(
            "onboard", form_dict, session, background_tasks,
            existing_profile=existing_profile,
            onboarding_state=onboarding_state
        )

    # Check if user needs onboarding
    if not existing_profile or existing_profile.status == "incomplete":
        return await handle_new_user(from_number, body, session, ProfileName)

    # Route commands
    command_type = router.get_command_type(body)
    
    if command_type != "message":
        return await router.route_command(
            command_type, form_dict, session, background_tasks,
            from_number=from_number,
            existing_profile=existing_profile,
            onboarding_state=onboarding_state
        )

    # Handle regular messages
    prospect_name = pick_prospect_from_body(body)
    print("Prospect name from @ ----->", prospect_name)

    # Default TwiML response
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message></Message>
</Response>"""

    # Process media or text messages
    if num_media > 0:
        await router.handler.handle_media_message(
            from_number, body, form_dict, prospect_name, sms_message_sid,
            original_replied_message_sender, prev_context_id, session,
            background_tasks, media_urls, num_media, ProfileName
        )
    else:
        await router.handler.handle_text_message(
            from_number, body, form_dict, prospect_name, sms_message_sid,
            original_replied_message_sender, prev_context_id, session,
            background_tasks, media_urls, num_media, ProfileName
        )

    return Response(content=twiml, media_type="application/xml")


# Voice service proxy endpoints - forward to voice service running on port 8002
import httpx

@app.post("/voice/call-user")
async def proxy_call_user(request: Request):
    """Proxy voice call requests to the voice service"""
    to_number = request.query_params.get("to_number")
    async with httpx.AsyncClient() as client:
        response = await client.post(f"http://localhost:8002/call-user?to_number={to_number}")
        return response.json()

@app.api_route("/voice/voice-greeting", methods=["GET", "POST"])
async def proxy_voice_greeting(request: Request):
    """Proxy voice greeting to voice service"""
    form_data = await request.form()
    # Forward the original host header so voice service knows its public URL
    headers = {"host": request.headers.get("host")}
    async with httpx.AsyncClient() as client:
        response = await client.post("http://localhost:8002/voice-greeting", 
                                   data=dict(form_data), 
                                   headers=headers)
        return Response(content=response.text, media_type="text/xml")

@app.post("/voice/call-status")
async def proxy_call_status(request: Request):
    """Proxy call status to voice service"""
    form_data = await request.form()
    async with httpx.AsyncClient() as client:
        response = await client.post("http://localhost:8002/call-status", data=dict(form_data))
        return Response(content=response.text, media_type="text/plain")

# WebSocket proxy removed - Twilio connects directly to voice service on port 8002
