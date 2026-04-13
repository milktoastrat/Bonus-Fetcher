import os
import re
import json
import asyncio
import threading
import time
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MOVIES_PATH = os.environ.get("MOVIES_PATH", "/movies")
MEDIA_SERVER = os.environ.get("MEDIA_SERVER", "emby").lower()
SETTINGS_FILE = "/app/settings.json"
SEEN_MOVIES_FILE = "/app/seen_movies.json"

# In-memory job store
download_jobs: dict = {}
auto_log: list = []

# ─── Settings ───

DEFAULT_SETTINGS = {
    "automation_enabled": False,
    "schedule_hours": 12,
    "auto_download_count": 5,
    "min_score": 30,
    "official_keywords": ["official", "marvel", "disney", "warner", "universal", "paramount", "sony", "lionsgate", "a24", "netflix", "amazon", "hbo"],
    "avoid_keywords": ["reaction", "review", "top 10", "top10", "explained", "recap", "trailer reaction", "fan made", "fanmade", "commentary", "rant", "ranking"],
}

def load_settings():
    try:
        if Path(SETTINGS_FILE).exists():
            with open(SETTINGS_FILE) as f:
                saved = json.load(f)
                return {**DEFAULT_SETTINGS, **saved}
    except:
        pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings: dict):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

def load_seen_movies():
    try:
        if Path(SEEN_MOVIES_FILE).exists():
            with open(SEEN_MOVIES_FILE) as f:
                return set(json.load(f))
    except:
        pass
    return set()

def save_seen_movies(seen: set):
    with open(SEEN_MOVIES_FILE, 'w') as f:
        json.dump(list(seen), f)

# ─── Category / folder mapping ───

CATEGORY_FOLDERS = {
    "emby": {
        "behind the scenes": "behind the scenes",
        "deleted scenes": "deleted scenes",
        "interviews": "interviews",
        "featurettes": "featurettes",
        "scenes": "scenes",
        "shorts": "shorts",
        "trailers": "trailers",
        "extras": "extras",
    },
    "plex": {
        "behind the scenes": "Behind The Scenes",
        "deleted scenes": "Deleted Scenes",
        "interviews": "Interviews",
        "featurettes": "Featurettes",
        "scenes": "Scenes",
        "shorts": "Shorts",
        "trailers": "Trailers",
        "extras": "Behind The Scenes",
    },
}

EXTRA_CATEGORIES = {
    "behind the scenes": ["behind the scenes", "making of", "making-of", "on set", "production", "bts"],
    "deleted scenes": ["deleted scene", "deleted scenes", "alternate ending", "cut scene"],
    "interviews": ["interview", "cast interview", "director interview", "q&a", "q & a"],
    "featurettes": ["featurette", "featurettes", "mini documentary", "documentary"],
    "scenes": ["scene", "clip"],
    "shorts": ["short film", "short"],
    "trailers": ["trailer", "teaser", "promo"],
    "extras": ["bonus", "special feature"],
}

OFFICIAL_CHANNELS = [
    "marvel entertainment", "marvel", "disney", "warner bros", "universal pictures",
    "paramount pictures", "sony pictures", "lionsgate", "a24", "netflix",
    "amazon prime video", "hbo", "20th century studios", "focus features",
    "searchlight pictures", "neon", "mgm"
]

def get_folder_name(category: str) -> str:
    server = MEDIA_SERVER if MEDIA_SERVER in CATEGORY_FOLDERS else "emby"
    return CATEGORY_FOLDERS[server].get(category, category)

def guess_category(title: str) -> str:
    title_lower = title.lower()
    for category, keywords in EXTRA_CATEGORIES.items():
        for kw in keywords:
            if kw in title_lower:
                return category
    return "extras"

def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:100]

def clean_title(video_title: str, movie_name: str) -> str:
    name = video_title
    base_movie = re.sub(r'\s*\(\d{4}\)\s*$', '', movie_name).strip()
    escaped = re.escape(base_movie)
    pattern = re.compile(rf'^{escaped}\s*(\(\d{{4}}\))?\s*[-–:|]\s*', re.IGNORECASE)
    name = pattern.sub('', name)
    name = re.sub(r'^[\(\[]\d{4}[\)\]]\s*[-–:]?\s*', '', name)
    name = re.sub(r'^\d{4}\s*[-–:]\s*', '', name)
    return name.strip()

# ─── Scoring ───

def score_result(result: dict, movie_name: str, settings: dict) -> int:
    score = 0
    title = result.get("title", "").lower()
    channel = result.get("channel", "").lower()
    duration = result.get("duration", 0)
    view_count = result.get("view_count", 0)
    base_movie = re.sub(r'\s*\(\d{4}\)\s*$', '', movie_name).strip().lower()

    # Movie name in title
    if base_movie in title:
        score += 25

    # Official keywords in title
    for kw in ["official", "featurette", "behind the scenes", "making of", "deleted scene", "interview"]:
        if kw in title:
            score += 15
            break

    # Official channel
    for ch in OFFICIAL_CHANNELS:
        if ch in channel:
            score += 30
            break

    # User-defined official keywords in channel or title
    for kw in settings.get("official_keywords", []):
        if kw.lower() in channel or kw.lower() in title:
            score += 10
            break

    # Avoid keywords
    for kw in settings.get("avoid_keywords", []):
        if kw.lower() in title or kw.lower() in channel:
            score -= 40

    # Duration scoring: prefer longer content (more likely to be full featurettes)
    if duration:
        if duration < 60:
            score -= 20          # Too short, probably a clip
        elif duration < 300:     # 1-5 min
            score += 5
        elif duration < 900:     # 5-15 min
            score += 15
        elif duration < 2700:    # 15-45 min: sweet spot for making-ofs
            score += 25
        elif duration < 7200:    # 45min-2hr: full documentaries, still good
            score += 20
        else:
            score -= 10          # Over 2 hours, probably not an extra

    # View count boost (log scale)
    if view_count:
        import math
        score += min(int(math.log10(view_count + 1) * 3), 15)

    return score

# ─── Download ───

def run_download(job_id: str, movie_path: str, video_url: str, video_title: str, category: str, movie_name: str = ''):
    try:
        download_jobs[job_id]["status"] = "downloading"
        download_jobs[job_id]["percent"] = 0
        download_jobs[job_id]["speed"] = ""
        download_jobs[job_id]["eta"] = ""

        folder_name = get_folder_name(category)
        target_dir = Path(movie_path) / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)

        safe_title = sanitize_filename(clean_title(video_title, movie_name))
        output_template = str(target_dir / f"{safe_title}.%(ext)s")

        def progress_hook(d):
            if d["status"] == "downloading":
                raw = d.get("_percent_str", "0%").strip().replace("%", "")
                try:
                    pct = float(raw)
                except ValueError:
                    pct = 0
                download_jobs[job_id]["percent"] = round(pct, 1)
                download_jobs[job_id]["speed"] = d.get("_speed_str", "").strip()
                download_jobs[job_id]["eta"] = d.get("_eta_str", "").strip()
                if pct >= 100:
                    download_jobs[job_id]["percent"] = 99
            elif d["status"] == "finished":
                download_jobs[job_id]["percent"] = 99

        ydl_opts = {
            "format": "bestvideo+bestaudio/best",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        download_jobs[job_id]["status"] = "done"
        download_jobs[job_id]["percent"] = 100
        download_jobs[job_id]["speed"] = ""
        download_jobs[job_id]["eta"] = ""
    except Exception as e:
        download_jobs[job_id]["status"] = "error"
        download_jobs[job_id]["error"] = str(e)
        download_jobs[job_id]["percent"] = 0

# ─── Automation ───

def search_youtube_for_movie(movie_name: str, max_results: int = 20) -> list:
    queries = [
        f"{movie_name} official behind the scenes",
        f"{movie_name} making of featurette",
        f"{movie_name} deleted scenes",
        f"{movie_name} cast interviews featurette",
    ]
    seen_ids = set()
    results = []
    ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for query in queries:
            if len(results) >= max_results:
                break
            try:
                sr = ydl.extract_info(f"ytsearch8:{query}", download=False)
                if not sr or "entries" not in sr:
                    continue
                for entry in sr["entries"]:
                    if not entry:
                        continue
                    vid_id = entry.get("id")
                    if not vid_id or vid_id in seen_ids:
                        continue
                    seen_ids.add(vid_id)
                    duration = entry.get("duration", 0)
                    if duration and (duration < 30 or duration > 10800):
                        continue
                    results.append({
                        "id": vid_id,
                        "title": entry.get("title", "Unknown"),
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "thumbnail": entry.get("thumbnail") or f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg",
                        "duration": duration,
                        "channel": entry.get("channel") or entry.get("uploader", "Unknown"),
                        "view_count": entry.get("view_count", 0),
                        "suggested_category": guess_category(entry.get("title", "")),
                    })
                    if len(results) >= max_results:
                        break
            except Exception as e:
                print(f"Auto-search error: {e}")
    return results

def auto_download_movie(movie_dir: Path, settings: dict):
    movie_name = movie_dir.name
    log_entry = {"movie": movie_name, "timestamp": time.strftime("%Y-%m-%d %H:%M"), "downloads": [], "skipped": []}

    try:
        count = settings.get("auto_download_count", 5)
        results = search_youtube_for_movie(movie_name, max_results=count)
        top = results[:count]

        for result in top:
            job_id = f"auto-{int(time.time())}-{result['id']}"
            download_jobs[job_id] = {
                "status": "queued", "job_id": job_id,
                "title": result["title"], "percent": 0,
                "speed": "", "eta": "", "auto": True,
                "movie": movie_name,
            }
            log_entry["downloads"].append({"title": result["title"], "category": result["suggested_category"]})

            t = threading.Thread(target=run_download, args=(
                job_id, str(movie_dir), result["url"],
                result["title"], result["suggested_category"], movie_name
            ))
            t.daemon = True
            t.start()
            time.sleep(2)  # stagger downloads

    except Exception as e:
        log_entry["error"] = str(e)

    auto_log.insert(0, log_entry)
    if len(auto_log) > 100:
        auto_log.pop()

def run_automation():
    while True:
        settings = load_settings()
        if not settings.get("automation_enabled"):
            time.sleep(60)
            continue

        seen = load_seen_movies()
        movies_dir = Path(MOVIES_PATH)

        if movies_dir.exists():
            current = {item.name for item in movies_dir.iterdir() if item.is_dir()}
            new_movies = current - seen

            for movie_name in new_movies:
                movie_dir = movies_dir / movie_name
                print(f"[auto] New movie detected: {movie_name}")
                auto_download_movie(movie_dir, settings)

            save_seen_movies(current)

        interval = settings.get("schedule_hours", 12) * 3600
        time.sleep(interval)

# Start automation thread
_auto_thread = threading.Thread(target=run_automation, daemon=True)
_auto_thread.start()

# ─── Routes ───

@app.get("/api/config")
def get_config():
    return {
        "media_server": MEDIA_SERVER if MEDIA_SERVER in CATEGORY_FOLDERS else "emby",
        "movies_path": MOVIES_PATH,
        "categories": list(CATEGORY_FOLDERS.get(MEDIA_SERVER, CATEGORY_FOLDERS["emby"]).keys()),
    }

@app.get("/api/settings")
def get_settings():
    return load_settings()

@app.post("/api/settings")
def update_settings(body: dict):
    current = load_settings()
    current.update(body)
    save_settings(current)
    return current

@app.get("/api/auto-log")
def get_auto_log():
    return auto_log

@app.post("/api/auto-scan")
def trigger_auto_scan(background_tasks: BackgroundTasks):
    settings = load_settings()
    def do_scan():
        seen = load_seen_movies()
        movies_dir = Path(MOVIES_PATH)
        if not movies_dir.exists():
            return
        current = {item.name for item in movies_dir.iterdir() if item.is_dir()}
        new_movies = current - seen
        for movie_name in new_movies:
            auto_download_movie(movies_dir / movie_name, settings)
        save_seen_movies(current)
    background_tasks.add_task(do_scan)
    return {"status": "scan started"}

@app.post("/api/mark-all-seen")
def mark_all_seen():
    movies_dir = Path(MOVIES_PATH)
    if not movies_dir.exists():
        raise HTTPException(status_code=404, detail="Movies path not found")
    current = {item.name for item in movies_dir.iterdir() if item.is_dir()}
    save_seen_movies(current)
    return {"marked": len(current)}

@app.get("/api/movies")
def list_movies():
    movies_dir = Path(MOVIES_PATH)
    if not movies_dir.exists():
        raise HTTPException(status_code=404, detail=f"Movies path not found: {MOVIES_PATH}")
    server = MEDIA_SERVER if MEDIA_SERVER in CATEGORY_FOLDERS else "emby"
    all_folder_names = list(set(CATEGORY_FOLDERS[server].values()))
    movies = []
    for item in sorted(movies_dir.iterdir()):
        if item.is_dir():
            existing_extras = []
            for folder_name in all_folder_names:
                cat_path = item / folder_name
                if cat_path.exists():
                    for f in cat_path.iterdir():
                        if f.suffix.lower() in ['.mkv', '.mp4', '.avi', '.mov']:
                            existing_extras.append({"category": folder_name, "filename": f.name})
            movies.append({"name": item.name, "path": str(item), "existing_extras": existing_extras})
    return movies

class SearchRequest(BaseModel):
    movie_name: str
    max_results: int = 15

@app.post("/api/search")
def search_youtube(req: SearchRequest):
    return search_youtube_for_movie(req.movie_name, req.max_results)

class DownloadRequest(BaseModel):
    movie_path: str
    video_url: str
    video_title: str
    category: str
    job_id: str

@app.post("/api/download")
def start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    movie_path = Path(req.movie_path).resolve()
    movies_root = Path(MOVIES_PATH).resolve()
    if not str(movie_path).startswith(str(movies_root)):
        raise HTTPException(status_code=403, detail="Invalid movie path")
    download_jobs[req.job_id] = {
        "status": "queued", "job_id": req.job_id,
        "title": req.video_title, "percent": 0, "speed": "", "eta": "",
    }
    background_tasks.add_task(
        run_download, req.job_id, str(movie_path),
        req.video_url, req.video_title, req.category,
        Path(req.movie_path).name,
    )
    return {"job_id": req.job_id, "status": "queued"}

@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    if job_id not in download_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return download_jobs[job_id]

@app.get("/api/jobs")
def get_all_jobs():
    return list(download_jobs.values())

@app.get("/")
def root():
    return FileResponse("/app/frontend/index.html")

@app.get("/{path:path}")
def serve_static(path: str):
    file_path = Path(f"/app/frontend/{path}")
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return FileResponse("/app/frontend/index.html")
