#!/bin/sh
echo "[startup] Updating yt-dlp..."
pip install -q -U yt-dlp
echo "[startup] yt-dlp $(yt-dlp --version) ready"
exec uvicorn main:app --host 0.0.0.0 --port 8080
