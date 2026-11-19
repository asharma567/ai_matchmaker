#!/usr/bin/env python3
"""
Start the WhatsApp bot in staging mode with proper database setup
"""
import os
import asyncio
import uvicorn
import subprocess
import threading
from dotenv import load_dotenv

# Load staging environment
load_dotenv('.env.staging')

async def setup_database():
    """Initialize database tables for staging"""
    print("🔧 Setting up staging database...")
    
    try:
        from oracle.data.db import engine, Base
        from sqlalchemy.ext.asyncio import AsyncSession
        
        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        print("✅ Database tables created successfully")
        return True
        
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        return False

def main():
    """Start the staging server"""
    print("🚀 Starting WhatsApp Dating Bot - STAGING MODE")
    print("=" * 50)
    
    # Verify environment
    print(f"Database: {os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}")
    print(f"WhatsApp: {os.getenv('WHATSAPP_NUMBER')}")
    print(f"Environment: {os.getenv('ENVIRONMENT', 'staging')}")
    print()
    
    # Setup database
    if not asyncio.run(setup_database()):
        print("❌ Failed to setup database. Exiting.")
        return
    
    print("🌐 Starting FastAPI servers...")
    print("📱 Ready for ngrok tunnel!")
    print()
    print("Next steps:")
    print("1. In another terminal: ngrok http 8000")
    print("2. Copy the ngrok URL") 
    print("3. Update Twilio webhook to: https://your-ngrok-url.ngrok.io/webhook")
    print("4. For voice calls, also update voice webhook to: https://your-ngrok-url.ngrok.io/voice-greeting")
    print("5. Send WhatsApp messages to test!")
    print()
    def start_voice_service():
        """Start voice service in background"""
        print("🎙️ Starting voice service on port 8002...")
        subprocess.run([
            "python", "voice.py", "--staging"
        ])
    
    # Start voice service in background thread
    voice_thread = threading.Thread(target=start_voice_service)
    voice_thread.daemon = True
    voice_thread.start()
    
    print("🎙️ Voice service starting on port 8002...")
    print("🌐 Main service starting on port 8000...")
    
    # Start main server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()