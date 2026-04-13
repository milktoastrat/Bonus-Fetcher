<img width="1509" height="1183" alt="image" src="https://github.com/user-attachments/assets/25602046-e909-4a09-84f4-ec466ef27d8a" />

# Bonus Fetcher

Search YouTube for official special features (behind the scenes, deleted scenes, interviews, featurettes) and download them directly into your Emby, Jellyfin, or Plex library. 

**NOTE**: This app was made with Claude Code. I am not a developer, I just wanted this tool to exist. ❤️

---

## Features

- Scans your movies folder automatically
- Searches YouTube for extras when you select a movie
- Shows thumbnails, duration, and channel name for each result
- Auto-suggests the right subfolder (behind the scenes / deleted scenes / interviews / featurettes / extras)
- Downloads via yt-dlp + ffmpeg, names and places files correctly
- Live download progress bars with speed and ETA
- **Automation** - automatically downloads extras for new movies as they appear in your library
- Supports both **Emby/Jellyfin** and **Plex** folder structures

---

## Install

### Prerequisites
- Docker and Docker Compose

### Setup

1. Clone or download this repo
2. Edit `docker-compose.yml` and set your movies path:

```yaml
version: "3.8"
services:
  bonus-fetcher:
    build: .
    container_name: bonus-fetcher
    restart: unless-stopped
    ports:
      - "8787:8080"
    volumes:
      - /path/to/your/movies:/movies:rw
    environment:
      - MOVIES_PATH=/movies
      - MEDIA_SERVER=emby  # Change to "plex" for Plex users
```

3. Start the container:

```bash
docker compose up -d
```

4. Open `http://YOUR_SERVER_IP:8787`

---

## Plex Mode

By default Bonus Fetcher uses Emby/Jellyfin folder naming (lowercase). To use Plex's Title Case folder structure, set the environment variable in your `docker-compose.yml`:

```yaml
environment:
  - MEDIA_SERVER=plex
```

Then restart the container. The app will use Plex's expected folder names (`Behind The Scenes`, `Deleted Scenes`, `Interviews`, etc.) and the UI will update to reflect this.

---

## Automation

Bonus Fetcher can automatically download extras whenever a new movie appears in your library.

Go to **Settings** in the app to configure:

- **Enable automation** — toggle auto-downloading on/off
- **Check every (hours)** — how often to scan for new movies
- **Videos per movie** — how many extras to download per new movie (default: 5)

When enabled, the app polls your movies folder on the configured schedule. When it detects a new movie folder it hasn't seen before, it searches YouTube and downloads the top results automatically — the same videos you'd see at the top of a manual search.

**Important:** On first run, click **Mark All as Seen** in the Settings page to prevent Bonus Fetcher from downloading extras for your entire existing library at once.

The **Automation Log** in Settings shows a history of every auto-download run.

---

## Emby / Jellyfin Folder Structure

```
/movies
  /Interstellar (2014)
    Interstellar (2014).mkv
    /behind the scenes/
      The Science of Interstellar.mp4
    /deleted scenes/
      Alternate Ending.mp4
    /interviews/
      Christopher Nolan Interview.mp4
    /featurettes/
      IMAX Making Of.mp4
    /extras/
      Theatrical Trailer.mp4
```

## Plex Folder Structure

```
/movies
  /Interstellar (2014)
    Interstellar (2014).mkv
    /Behind The Scenes/
      The Science of Interstellar.mp4
    /Deleted Scenes/
      Alternate Ending.mp4
    /Interviews/
      Christopher Nolan Interview.mp4
    /Featurettes/
      IMAX Making Of.mp4
```

---

## Keeping yt-dlp Updated

yt-dlp updates automatically every time the container starts. If downloads stop working unexpectedly, force an update manually:

```bash
docker exec -it bonus-fetcher pip install -U yt-dlp
```

Or rebuild the container:

```bash
docker compose up --build -d
```
