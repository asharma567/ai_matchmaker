# scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.date import DateTrigger
from zoneinfo import ZoneInfo
from datetime import datetime
import asyncio
import httpx
import os
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv()
# Define where jobs will be stored (PostgreSQL connection URL)
IST = ZoneInfo("Asia/Kolkata")
US_EASTERN = ZoneInfo("America/New_York")

POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

jobstores = {
    "default": SQLAlchemyJobStore(url=DATABASE_URL)
}

scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=US_EASTERN)

async def trigger_twilio_voice_call(to_number: str):
    to_number = to_number.strip()

    # Add leading '+' if missing
    if not to_number.startswith("+"):
        to_number = f"+{to_number}"

    url = f"{os.getenv('VOICE_API_BASE_URL')}/call-user?to_number={to_number}"
    print(f"🔁 Calling Twilio: {url}")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url)
            print("📞 Twilio Response:", resp.json())
        except Exception as e:
            print("❌ Call trigger failed:", str(e))


def schedule_voice_call(to_number: str, when: datetime):
    when = when.astimezone(US_EASTERN)

    async def wrapper():
        print(f"🔔 Running scheduled call for {to_number} at {datetime.now().isoformat()}")
        await trigger_twilio_voice_call(to_number)

    def job_runner():
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(wrapper())

    job_id = f"call_{to_number}_{when.isoformat()}_{uuid4().hex[:4]}"
    print(f"📅 Scheduling job: {job_id} → {when.isoformat()}")
    scheduler.add_job(
        job_runner,
        trigger=DateTrigger(run_date=when),
        id=job_id,
        replace_existing=True
    )