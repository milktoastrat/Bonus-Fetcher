# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Dockerized tool that searches YouTube for movie special features (behind the scenes, deleted scenes, interviews, featurettes) and downloads them into the correct Emby/Jellyfin or Plex folder structure using yt-dlp + ffmpeg.

## Build & Run

```bash
# Build and start via Docker Compose
docker compose up --build -d

# Manual build and run
docker build -t bonus-fetcher .
docker run -d --name bonus-fetcher --restart unless-stopped \
  -p 8787:8080 \
  -v /mnt/user/Media/Movies:/movies:rw \
  -e MOVIES_PATH=/movies \
  -e MEDIA_SERVER=emby \
  bonus-fetcher
```

UI is at `http://localhost:8787` (or `http://YOUR_UNRAID_IP:8787`).

**Update yt-dlp without rebuilding:**
```bash
docker exec -it bonus-fetcher pip install -U yt-dlp
```

There are no tests and no linter configured.

## Architecture

**Single container, two parts:**

- `backend/main.py` — FastAPI app. Handles all API routes, download logic, automation, and also serves the frontend as static files.
- `frontend/index.html` — Single self-contained HTML file (no build step, no framework, no bundler). All CSS and JS are inline.

**Request flow:**
- `GET /` and `GET /{path}` serve the frontend from `/app/frontend/`
- `GET|POST /api/*` are the JSON API endpoints

**Key backend concepts:**

- `download_jobs: dict` — in-memory job store. All job state is lost on container restart.
- `run_download()` — runs in a `threading.Thread` (daemon). Uses yt-dlp with `bestvideo+bestaudio/best` format and ffmpeg merge to mp4.
- `run_automation()` — long-running daemon thread. Polls `MOVIES_PATH` on a configurable interval, detects new movie directories not in `seen_movies.json`, and auto-downloads top-scored results.
- `score_result()` — scores YouTube search results by: movie name in title (+25), official keywords (+10–30), avoid keywords (−40), duration (−20 to +25), and log-scale view count (up to +15). Minimum score threshold is configurable.
- `guess_category()` — maps video title keywords to Emby/Plex subfolder categories.

**Persistent state (inside container at `/app/`):**
- `settings.json` — automation config (enabled, schedule interval, score threshold, keyword lists)
- `seen_movies.json` — set of movie directory names that automation has already processed

**Folder mapping:**
- Emby: lowercase (`behind the scenes`, `deleted scenes`, etc.)
- Plex: Title Case (`Behind The Scenes`, `Deleted Scenes`, etc.)
- Controlled by `MEDIA_SERVER` env var (`emby` or `plex`)

**Download path safety:** `POST /api/download` validates that the resolved `movie_path` is under `MOVIES_PATH` before downloading.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MOVIES_PATH` | `/movies` | Path to movies library inside container |
| `MEDIA_SERVER` | `emby` | `emby` or `plex` — controls subfolder casing |
