#!/bin/bash
cd /Users/LENOVO/Downloads/DLW26
source .venv/bin/activate

# Start backend
python -m uvicorn backend:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"

sleep 3

# Start frontend
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 > ../frontend.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend started with PID: $FRONTEND_PID"

sleep 2

echo ""
echo "✅ Both servers started successfully!"
echo "Frontend: http://127.0.0.1:5173"
echo "Backend: http://127.0.0.1:8000/docs"
echo ""
