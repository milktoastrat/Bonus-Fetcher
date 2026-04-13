<img width="1509" height="1183" alt="image" src="https://github.com/user-attachments/assets/25602046-e909-4a09-84f4-ec466ef27d8a" />

# Bonus Fetcher

Search YouTube for official special features (behind the scenes, deleted scenes, interviews, featurettes) and download them directly into your Emby/Jellyfin library structure.

## Features

- Scans your movies folder automatically
- Searches YouTube for official BTS/extras per movie
- Shows thumbnails, duration, channel name
- Auto-suggests the right Emby subfolder (behind the scenes / deleted scenes / interviews / featurettes / extras)
- Downloads via yt-dlp + ffmpeg, names and places files correctly
- Shows download queue/status

---

## Unraid Install (Compose Manager)

### 1. Install the Compose Manager plugin
In Unraid → Apps → search **"Compose Manager"** → Install.

### 2. Copy the project to your Unraid server

```bash
# SSH into Unraid
scp -r bonus-fetcher/ root@YOUR_UNRAID_IP:/mnt/user/appdata/bonus-fetcher
```

Or use the Unraid file manager to upload the folder to `/mnt/user/appdata/bonus-fetcher`.

### 3. Edit docker-compose.yml

Open `/mnt/user/appdata/bonus-fetcher/docker-compose.yml` and update the movies volume path:

```yaml
volumes:
  - /mnt/user/Media/Movies:/movies:rw   # Change left side to your actual path
```

### 4. Add via Compose Manager

- Go to **Docker** tab → **Compose Manager**
- Click **Add New Stack**
- Name it `bonus-fetcher`
- Set the path to `/mnt/user/appdata/bonus-fetcher`
- Click **Compose Up**

### 5. Open the UI

Navigate to `http://YOUR_UNRAID_IP:8787`

---

## Manual Docker Run (alternative)

```bash
docker build -t bonus-fetcher /mnt/user/appdata/bonus-fetcher

docker run -d \
  --name bonus-fetcher \
  --restart unless-stopped \
  -p 8787:8080 \
  -v /mnt/user/Media/Movies:/movies:rw \
  -e MOVIES_PATH=/movies \
  bonus-fetcher
```

---

## Emby Folder Structure

Files are saved following Emby's spec:

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

Emby will automatically pick these up — no library rescans needed beyond the normal scheduled one (or trigger one manually).

---

## Updating yt-dlp

YouTube changes frequently. If downloads stop working, update yt-dlp inside the container:

```bash
docker exec -it bonus-fetcher pip install -U yt-dlp
```

Or just rebuild the container.
