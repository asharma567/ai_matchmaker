# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
- `python main.py` - Start the FastAPI server on port 8050 with hot reload
- `uvicorn main:app --host 0.0.0.0 --port 8050 --reload` - Alternative way to start the server

### Dependencies
- `pip install -r requirements.txt` - Install Python dependencies
- Dependencies include: FastAPI, SQLAlchemy, Twilio, OpenAI, Redis, ChromaDB, LangChain

### Testing
- `python test_twilio_media.py` - Test Twilio media functionality

## Architecture Overview

This is a WhatsApp AI dating coach bot that provides personalized dating advice and conversation suggestions. The application uses:

### Core Components
- **FastAPI** server handling Twilio webhooks for WhatsApp integration
- **PostgreSQL** with SQLAlchemy async ORM for persistent data storage
- **Redis** for temporary state management and media processing
- **OpenAI GPT-4** for AI responses and conversation analysis
- **Twilio** for WhatsApp messaging and voice calls
- **ChromaDB** for vector storage and RAG (Retrieval Augmented Generation)
- **APScheduler** for scheduling voice calls

### Database Models (`models.py`)
- `Message` - Stores WhatsApp message history
- `UserProfile` - User onboarding data and preferences (defined in `db.py`)
- `TempConversation` - Temporary message storage during processing
- `PermanentConversation` - Saved conversations with specific prospects

### Key Modules
- `main.py` - FastAPI app with webhook endpoint and command handlers
- `messaging.py` - WhatsApp message processing and sending logic
- `onboarding.py` - User registration flow with multi-step questions
- `llm_utils.py` - OpenAI integration and prompt management
- `db_utils.py` - Database operations and utilities
- `scheduler.py` - Voice call scheduling functionality
- `voice.py` - Voice call handling and processing
- `validators.py` - Input validation and data normalization

### Message Flow
1. WhatsApp messages received via Twilio webhook at `/webhook`
2. Signature validation for security
3. Onboarding state check and routing
4. Media processing with delay mechanism using Redis
5. AI response generation using OpenAI
6. Response chunking for WhatsApp length limits
7. Background task execution for async processing

### Command System
Users can send slash commands:
- `/help` - Show help message
- `/onboard` - Start onboarding process
- `/call` or `/call me` - Request voice callback
- `/summary` or `/aboutme` - Get profile summary
- `/prospects` - List saved conversation prospects
- `/reset` - Delete profile and restart onboarding

### Environment Variables Required
- `TWILIO_AUTH_TOKEN` - Twilio authentication
- `TWILIO_ACCOUNT_SID` - Twilio account identifier
- `WHATSAPP_NUMBER` - Bot's WhatsApp number
- `DATABASE_URL` - PostgreSQL connection string
- `OPENAI_API_KEY` - OpenAI API access
- `SKIP_TWILIO_VALIDATION` - Skip signature validation for development

### Redis Usage
- Media processing locks to prevent duplicate handling
- Onboarding state management
- Temporary media URL storage with expiration

### Voice Integration
- External voice API at `voice.0racle.ai` for phone calls
- Scheduled voice calls using APScheduler
- Voice questions configuration in `voice_questions.yaml`

## Development Notes

### Media Processing
The app implements a delay mechanism for media processing to handle multiple images sent rapidly. Media URLs are queued in Redis and processed after a brief delay.

### Message Length Handling
WhatsApp has a 1600 character limit. The app automatically chunks longer responses and uses TwiML for proper formatting.

### Async Architecture
Heavy use of async/await patterns with SQLAlchemy async sessions and HTTPX for external API calls.

### Background Tasks
FastAPI BackgroundTasks used extensively for non-blocking operations like message processing and external API calls.