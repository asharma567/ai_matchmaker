#!/bin/bash
# start_ngrok.sh - Start ngrok tunnels with custom domains

echo "🛑 Stopping existing ngrok processes..."
pkill -f "ngrok" 2>/dev/null || echo "  No ngrok processes running"

echo "⏱️  Waiting for processes to stop..."
sleep 2

echo "🌐 Starting ngrok tunnels with custom domains..."
echo "  📱 Main service: https://staging.ngrok.pro (port 8000)"
echo "  🎙️ Voice service: https://voice-staging.ngrok.pro (port 8002)"

# Explicitly specify config file path and start specific tunnels
ngrok start --config ~/.ngrok2/ngrok.yml main voice &
NGROK_PID=$!

echo "⏱️  Waiting for ngrok to initialize..."
sleep 5

echo "✅ Ngrok started!"
echo "  Ngrok PID: $NGROK_PID"
echo ""
echo "🌐 Active tunnels:"
echo "  Main: https://staging.ngrok.pro → http://localhost:8000"
echo "  Voice: https://voice-staging.ngrok.pro → http://localhost:8002"
echo ""
echo "📋 Dashboard: http://localhost:4040"
echo ""
echo "📡 Keeping ngrok running... (Press Ctrl+C to stop)"

# Keep the script running to show logs
wait