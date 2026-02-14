#!/bin/bash
# One-Click Launcher for SpatialVCS (macOS .command)

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "🚀 Starting SpatialVCS..."

# Function to handle cleanup on exit
cleanup() {
    echo "🛑 Shutting down services..."
    kill $(jobs -p) 2>/dev/null
    exit
}
trap cleanup SIGINT SIGTERM EXIT

# Start Backend
echo "🟢 Starting Standard Backend (Port 8000)..."
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000 &

# Start Frontend
echo "🔵 Starting Frontend (Port 5173)..."
cd frontend
npm run dev -- --host &

# Wait
wait
