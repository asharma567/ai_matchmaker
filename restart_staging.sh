#!/bin/bash
# restart_staging.sh - Restart staging services cleanly

echo "🛑 Stopping existing services..."
pkill -f "python.*voice.py" 2>/dev/null || echo "  No voice service running"
pkill -f "python.*start_staging.py" 2>/dev/null || echo "  No staging service running"
pkill -f "uvicorn.*main:app" 2>/dev/null || echo "  No uvicorn processes running"

echo "⏱️  Waiting for processes to stop..."
sleep 3

echo "🔧 Setting environment variables..."
export VOICE_API_BASE_URL=https://voice-staging.ngrok.pro
echo "  VOICE_API_BASE_URL: $VOICE_API_BASE_URL"

echo "🚀 Starting staging services..."
echo "  📱 Starting main service (port 8000) with integrated voice service (port 8002)..."
python start_staging.py &
MAIN_PID=$!

echo "✅ Services started!"
echo "  Main service PID: $MAIN_PID"
echo ""
echo "📋 Status:"
ps aux | grep -E "(python.*voice|python.*staging)" | grep -v grep
echo ""
echo "🌐 To start ngrok tunnels, run:"
echo "  ./start_ngrok.sh"
echo ""
echo "🧪 Ready for testing!"
echo "  Test with: /call me"