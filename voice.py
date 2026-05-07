

#TODO: Need to make it moduler and clean also need to make a config file for the all the settings and parameter.

# CRITICAL: Load environment BEFORE any imports that might call load_dotenv()
import os
import sys
from dotenv import load_dotenv

# Load environment - detect staging mode FIRST
if len(sys.argv) > 1 and sys.argv[1] == '--staging':
    load_dotenv('.env.staging', override=True)
    print("🎯 Voice service running in STAGING mode")
    print(f"🎯 Using WhatsApp number: {os.getenv('WHATSAPP_NUMBER')}")
else:
    load_dotenv()

# Now import other modules (some of which call load_dotenv but won't override)
import json
import asyncio
import threading
import time
from fastapi import FastAPI, Request, WebSocket, Depends, BackgroundTasks, HTTPException
from fastapi.responses import PlainTextResponse, Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import websocket as ws_client  # `websocket-client` package
from twilio.rest import Client
from sqlalchemy.ext.asyncio import AsyncSession
from db import async_session, UserProfile
from sqlalchemy import update, select
from prompts import get_voice_prompt
from constant import VOICE, MODEL, TRANSCRIPTION_MODEL
from db_utils import save_transcript
from twilio.request_validator import RequestValidator
from messaging import send_signal_user_answered
from onboarding import after_transcript_saved

# import redis.asyncio as aioredis

# REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)

app = FastAPI()

class WebSocketMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Allow all WebSocket connections without authentication
        if request.url.path == "/ws/voice":
            print(f"WebSocket request from {request.client}: {request.headers}")
        response = await call_next(request)
        return response

app.add_middleware(WebSocketMiddleware)

# Add CORS middleware to allow Twilio connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for Twilio
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables - loaded after environment detection
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
# TWILIO_CALLER_NUMBER = os.getenv("WHATSAPP_NUMBER") #(e.g., +14155552671)
TWILIO_CALLER_NUMBER = "+12792392562"

# Debug logging
print(f"🔧 Voice service environment variables:")
print(f"   ENVIRONMENT: {os.getenv('ENVIRONMENT')}")
print(f"   WHATSAPP_NUMBER: {os.getenv('WHATSAPP_NUMBER')}")
print(f"   TWILIO_CALLER_NUMBER: {TWILIO_CALLER_NUMBER}")
print(f"   OPENAI_API_KEY: {'✅ Set' if OPENAI_API_KEY else '❌ Missing'}")
print(f"   TWILIO_AUTH_TOKEN: {'✅ Set' if TWILIO_AUTH_TOKEN else '❌ Missing'}")
print(f"   TWILIO_ACCOUNT_SID: {'✅ Set' if TWILIO_ACCOUNT_SID else '❌ Missing'}")

def get_system_message(user_name="there"):
    return get_voice_prompt(user_name)

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
validator = RequestValidator(TWILIO_AUTH_TOKEN)


@app.get("/")
def health_check():
    return {"status": "ok"}

@app.get("/headers")
async def headers(request: Request):
    return JSONResponse(dict(request.headers))

def hangup_call(call_sid: str):
    try:
        print(f"⏳ Waiting 2 seconds before hanging up Call {call_sid}...")
        time.sleep(2)  # Delay
        twilio_client.calls(call_sid).update(status="completed")
        print(f"✅ Call {call_sid} hung up successfully.")
    except Exception as e:
        print(f"❌ Error hanging up call {call_sid}: {e}")

async def get_session():
    async with async_session() as session:
        yield session

@app.post("/call-status")
async def call_status_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    form = await request.form()
    form_dict = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")

    # Reconstruct the public URL as Twilio saw it
    host = request.headers.get("host")
    url = f"https://{host}{request.url.path}"
    if request.url.query:
        url += f"?{request.url.query}"

    if not os.getenv("SKIP_TWILIO_VALIDATION", "").lower() in ("1", "true"):
        print("SKIP_TWILIO_VALIDATION:>>",os.getenv("SKIP_TWILIO_VALIDATION", ""))
        print("VALIDATOR RESULTS:",validator.validate(url, form_dict, signature))
        if not validator.validate(url, form_dict, signature):
            print("❌ Invalid Twilio signature on /call-status")
            raise HTTPException(status_code=400, detail="Invalid signature")

    call_status = form.get("CallStatus")
    to_number = form.get("To")

    whatsapp_number = to_number.strip()
    if not whatsapp_number.startswith("whatsapp:"):
        whatsapp_number = f"whatsapp:{whatsapp_number}"
        
    print(f"📞 Call status callback received: {call_status} to {to_number}")

    # Fetch profile
    result = await session.execute(
        select(UserProfile).where(UserProfile.whatsapp_number == whatsapp_number)
    )
    profile = result.scalar_one_or_none()

    if call_status.lower() in ["answered", "in-progress"]:
        if profile and not profile.call_answered:
            stmt = (
                update(UserProfile)
                .where(UserProfile.whatsapp_number == whatsapp_number)
                .values(call_answered=True)
            )
            await session.execute(stmt)
            await session.commit()
            print(f"✅ Updated call_answered=True for {whatsapp_number}")

    elif call_status.lower() == "completed":
        #Only send onboarding confirmation if call was answered
        if profile and profile.call_answered:
            background_tasks.add_task(send_signal_user_answered, to_number, message=(
                "Thank you so much for sharing your story 😊 I’ll start working on finding the perfect match for you right away.\n\n"
                "If you’d like to see a summary, just send us `/summary` at any time after the call 📄."
            ))
            # background_tasks.add_task(send_signal_user_answered, to_number, message=(
            #     "🎉 Onboarding complete! Welcome. I'm all set to help you with everything 😃"
            # ))
            # Optionally, reset call_answered if you want to allow for future calls
            # stmt = (
            #     update(UserProfile)
            #     .where(UserProfile.whatsapp_number == whatsapp_number)
            #     .values(call_answered=True)
            # )
            # await session.execute(stmt)
            # await session.commit()
        else:
            print(f"⚠️ Call completed but not answered → likely missed.")
            background_tasks.add_task(send_signal_user_answered, to_number, message=(
                "Our call got disconnected 😔. Please send us `/call me` to complete the onboarding at your convenience."
            ))

    else:
        # Handle other statuses if needed
        pass
        
    return PlainTextResponse("OK", status_code=200)


@app.post("/call-user")
async def call_user(request: Request):
    """
    Initiates a voice call to the user's phone number and connects them to the voice WebSocket stream.
    `to_number` must be in E.164 format (e.g., +14155552671)
    """
    to_number = request.query_params.get("to_number")
    if not to_number:
        return {"status": "error", "message": "to_number query parameter is required"}
    
    # Clean the phone number
    to_number = to_number.strip()
    if not to_number.startswith('+'):
        to_number = f"+{to_number}"
    
    host = request.headers.get("host")
    print(f"🌐 Request host: {host}")
    print(f"📞 Calling number: {to_number}")
    
    # TODO: Fix environment variable passing to subprocess - HARDCODED FOR NOW
    ngrok_base = 'https://voice-staging.ngrok.pro'  # BAD PRACTICE - HARDCODED
    print(f"🎙️ Using ngrok_base: {ngrok_base}")
    
    stream_url = f"{ngrok_base}/voice-greeting"
    status_callback_url = f"{ngrok_base}/call-status"
    print(f"🎙️ Using stream_url: {stream_url}")
    print(f"📞 Using status_callback_url: {status_callback_url}")
    
    try:
        call = twilio_client.calls.create(
            to=to_number,
            from_=TWILIO_CALLER_NUMBER,
            url=stream_url,
            status_callback=status_callback_url,
            status_callback_event=["answered", "completed"],
            status_callback_method="POST",
            timeout=60  # Ring for 60 seconds instead of default ~20
        )

        print(f"✅ Twilio call initiated, SID: {call.sid}")

        # Save call.sid -> to_number mapping in Redis (1 hour expiry)
        # await redis_client.setex(f"call:{call.sid}:whatsapp", 3600, to_number)
        # print(f"📌 Saved mapping: call:{call.sid}:whatsapp → {to_number}")


        return {"status": "initiated", "sid": call.sid}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.api_route("/voice-greeting", methods=["GET", "POST"])
async def incoming_call(request: Request):
    form = await request.form()
    form_dict = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")

    # Reconstruct the public URL as Twilio saw it
    host = request.headers.get("host")
    url = f"https://{host}{request.url.path}"
    if request.url.query:
        url += f"?{request.url.query}"

    if not os.getenv("SKIP_TWILIO_VALIDATION", "").lower() in ("1", "true"):
        print("SKIP_TWILIO_VALIDATION:>>",os.getenv("SKIP_TWILIO_VALIDATION", ""))
        print("VALIDATOR RESULTS:",validator.validate(url, form_dict, signature))
        if not validator.validate(url, form_dict, signature):
            print("❌ Invalid Twilio signature on /voice-greeting")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
    to_number = form.get("To")  # The phone number you dialed
    call_sid = form.get("CallSid")
    print(f"📞 Voice greeting requested for number: {to_number}")

    # TODO: Fix environment variable passing to subprocess - HARDCODED FOR NOW  
    ws_host = 'voice-staging.ngrok.pro'  # BAD PRACTICE - HARDCODED
    
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Connect>
            <Stream url="wss://{ws_host}/ws/voice">
                <Parameter name="PhoneNumber" value="{to_number}"/>
                <Parameter name="CallSid" value="{call_sid}"/>
            </Stream>
        </Connect>
    </Response>"""

    # print("🚨 Generated TwiML being sent to Twilio:")
    # print(twiml)

    return Response(content=twiml, media_type="text/xml")


@app.websocket("/ws/voice")
async def media_stream(websocket: WebSocket):
    try:
        print(f"WebSocket connection attempt from: {websocket.client}")
        print(f"WebSocket headers: {websocket.headers}")
        await websocket.accept()
        print("Twilio client connected")
    except Exception as e:
        print(f"WebSocket connection failed: {e}")
        raise

    stream_sid = None
    loop = asyncio.get_event_loop()
    shared = {
        "openai_ws": None,
        "call_sid": None,
        "transcripts": [],
        "transcript": "",
        "personalized_message": get_voice_prompt("there"),  # fallback until personalized
        "not_ready_count": 0  # Track how many times we've logged "not ready"
    }

    async def get_user_name_by_number(phone_number: str, session: AsyncSession):
        stmt = select(UserProfile).where(UserProfile.whatsapp_number == f"whatsapp:{phone_number}")
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        return user.full_name if user else None

    def openai_thread():
        def on_open(ws):
            print("OpenAI connected")
            shared["openai_ws"] = ws
            session_update = {
                "type": "session.update",
                "session": {
                    "instructions": shared.get("personalized_message", get_voice_prompt("there")),
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": VOICE,
                    "modalities": ["audio", "text"],
                    "temperature": 0.7,
                    "turn_detection": {
                        "type": "server_vad",
                        "silence_duration_ms": 1500,  # Increased from 700ms to reduce false triggers
                        "prefix_padding_ms": 300,     # Slightly reduced padding
                        "create_response": True,
                        "interrupt_response": True
                    },
                    "input_audio_transcription": {  
                        "model": TRANSCRIPTION_MODEL,
                        "language": "en"
                    }
                }
            }

            ws.send(json.dumps(session_update))


            # 🟢 Send assistant intro message
            intro_message = "Hello!"

            user_intro_msg = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f'"{intro_message}"'
                        }
                    ]
                }
            }
            ws.send(json.dumps(user_intro_msg))
            print("✅ Sent introductory message as user for greeting.")

            ws.send(json.dumps({"type": "response.create"}))
            print("✅ Triggered response.create to speak the assistant's message.")


        def on_message(ws, message):
            data = json.loads(message)
            event_type = data.get("type")

            if event_type == "response.audio.delta" and "delta" in data:
                audio_msg = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": data["delta"]
                    }
                }
                if websocket.client_state.name == "CONNECTED":
                    asyncio.run_coroutine_threadsafe(
                        websocket.send_text(json.dumps(audio_msg)),
                        loop
                    )

            elif event_type == "response.audio_transcript.delta":
                delta = data.get("delta", "")
                shared["transcript"] += delta

            elif event_type == "response.audio_transcript.done":
                final_ai = shared["transcript"]
                shared["transcripts"].append(f"AI: {final_ai}")
                shared["transcript"] = ""

                if "END CONVERSATION" in final_ai.upper():
                    print("🔚 Detected END CONVERSATION token, triggering hangup...")
                    call_sid = shared.get("call_sid")
                    if call_sid:
                        asyncio.run_coroutine_threadsafe(
                            asyncio.to_thread(hangup_call, call_sid),
                            loop
                        )

            elif event_type == "conversation.item.input_audio_transcription.completed":
                user_speech = data.get("transcript", "")
                shared["transcripts"].append(f"User: {user_speech}")

            elif event_type == "session.updated":
                print("OpenAI session updated")

        def on_error(ws, error):
            print("OpenAI error:", error)

        def on_close(ws, code, reason):
            print(f"OpenAI closed: {code}, {reason}")

        openai_ws_app = ws_client.WebSocketApp(
            f"wss://api.openai.com/v1/realtime?model={MODEL}",
            header=[
                f"Authorization: Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta: realtime=v1"
            ],
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )

        openai_ws_app.run_forever()

    # Start OpenAI relay in background thread
    thread = threading.Thread(target=openai_thread)
    thread.daemon = True
    thread.start()

    phone_number = None
    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
                
            if data["event"] == "start":
                stream_sid = data["start"]["streamSid"]
                print(f"Stream started: {stream_sid}")

                # Extract phone number from start payload
                phone_number = None
                call_sid = None

                parameters = data["start"].get("parameters", [])
                for param in parameters:
                    if param.get("name") == "PhoneNumber":
                        phone_number = param.get("value")
                        print(f"✅ Found PhoneNumber in parameters[]: {phone_number}")

                    elif param.get("name") == "CallSid":
                        call_sid = param.get("value")
                        print(f"✅ Found CallSid in parameters[]: {call_sid}")

                if not phone_number or not call_sid:
                    custom_params = data["start"].get("customParameters", {})
                    phone_number = custom_params.get("PhoneNumber")
                    call_sid = custom_params.get("CallSid")
                    if phone_number:
                        print(f"✅ Found PhoneNumber in customParameters: {phone_number}")
                    if call_sid:
                        print(f"✅ Found CallSid in customParameters: {call_sid}")

                if call_sid:
                    shared["call_sid"] = call_sid

                if phone_number:
                    print(f"✅ WebSocket associated with phone number: {phone_number}")
                    async with async_session() as session:
                        user_name = await get_user_name_by_number(phone_number, session)
                    if user_name:
                        personalized_message = get_voice_prompt(user_name)
                        shared["personalized_message"] = personalized_message
                        print(f"✅ Personalized instructions created for {user_name}")
                        print(f"🔍 DEBUG: Full prompt:\n{personalized_message}\n🔍 END DEBUG")

                        # # 🟢 NOW send the greeting here
                        # greeting = f"Hey {user_name}, I’m so glad to talk with you today 😊 Let's begin!"
                        # if shared["openai_ws"]:
                        #     shared["openai_ws"].send(json.dumps({
                        #         "type": "input.text",
                        #         "text": greeting
                        #     }))

                    else:
                        shared["personalized_message"] = get_voice_prompt("there")
                        print("⚠️ User name not found; using fallback")
                else:
                    print("⚠️ PhoneNumber not found in start event!")

            elif data["event"] == "media":
                payload = data["media"].get("payload", "")
                if shared["openai_ws"]:
                    try:
                        shared["openai_ws"].send(json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": payload
                        }))
                    except Exception as e:
                        print("Failed to send audio chunk:", e)
                else:
                    print("OpenAI WebSocket not ready yet")

    except Exception as e:
        print("Twilio WebSocket error:", e)
    finally:
        print("Twilio client disconnected")
        print("✅ Transcripts")
        print(shared["transcripts"])
        print("✅ Delta Transcripts")
        print(shared["transcript"])

        if phone_number:
            final_transcript = "\n".join(shared["transcripts"])
            print(f"✅ Saving transcript for {phone_number}...")
            try:
                async with async_session() as session:
                    await save_transcript(phone_number, final_transcript, session)

                    # 🟢 Trigger background task AFTER transcript is saved
                    asyncio.create_task(after_transcript_saved(phone_number))
            except Exception as e:
                print(f"❌ Failed to save transcript: {e}")
        else:
            print("⚠️ No phone number available; cannot save transcript.")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("voice:app", host="0.0.0.0", port=8002, reload=True, proxy_headers=True, ws_ping_interval=None, ws_ping_timeout=None)


