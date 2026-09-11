#!/bin/bash
cd "$(dirname "$0")/app"
echo "Starting Bank Exam Prep Manager..."
echo "Once it says 'running at http://localhost:8000', open that address in your browser."
echo "Press Ctrl+C to stop the server."
python3 server.py
