#!/bin/bash
set -e

cd /Users/LENOVO/Downloads/DLW26

# Start backend
echo "Starting backend server..."
./.venv/bin/python -m uvicorn backend:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Wait for backend to be ready
sleep 3

# Start frontend  
echo "Starting frontend server..."
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 > ../frontend.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

sleep 2

echo ""
echo "✅ Servers are running!"
echo "Frontend: http://127.0.0.1:5173"
echo "Backend: http://127.0.0.1:8000"
echo ""
echo "Logs:"
echo "Backend log: backend.log"
echo "Frontend log: frontend.log"
echo ""
echo "To stop servers, run: kill $BACKEND_PID $FRONTEND_PID"
