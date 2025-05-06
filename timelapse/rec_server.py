from flask import Flask, jsonify
from subprocess import Popen, signal
from pathlib import Path
import datetime, sqlite3
import os

# ── Config ───────────────────────────────────────────
DEVICE   = "0:none"            # AVFoundation index "camera:audio" (0 = FaceTime HD)
FPS      = 30
SIZE     = "1280x720"
SPEEDUP  = 8                   # 8× faster playback
RAW_DIR  = Path("raw");  RAW_DIR.mkdir(exist_ok=True)
OUT_DIR  = Path("clips"); OUT_DIR.mkdir(exist_ok=True)
DB       = Path("clips.sqlite3")

# ── DB bootstrap ─────────────────────────────────────
with sqlite3.connect(DB) as c:
    c.execute("""CREATE TABLE IF NOT EXISTS clips(
                 id INTEGER PRIMARY KEY,
                 ts TEXT,
                 path TEXT)""")

# ── Flask app ────────────────────────────────────────
app, proc, raw_file = Flask(__name__), None, None

def ffmpeg_capture(outpath):
    return ["ffmpeg","-hide_banner","-loglevel","error",
            "-f","avfoundation","-framerate",str(FPS),
            "-video_size",SIZE,"-i",DEVICE,
            "-vcodec","libx264","-preset","ultrafast","-crf","18",
            str(outpath)]

@app.post("/start")
def start():
    global proc, raw_file
    if proc: return jsonify(status="already recording")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_file = RAW_DIR / f"{ts}.mp4"
    proc = Popen(ffmpeg_capture(raw_file))
    return jsonify(status="started", ts=ts)

@app.post("/stop")
def stop():
    global proc, raw_file
    if not proc: return jsonify(status="not recording")
    proc.send_signal(signal.SIGINT); proc.wait(); proc = None
    stem = raw_file.stem              # e.g. '20250505_205116'
    tl   = OUT_DIR / f"{stem}_tl.mp4" # Path('clips/20250505_205116_tl.mp4')
    Popen(["ffmpeg","-hide_banner","-loglevel","error","-i",str(raw_file),
           "-vf",f"setpts=PTS/{SPEEDUP}","-an","-vcodec","libx264",
           "-preset","ultrafast","-crf","23",str(tl)]).wait()
    with sqlite3.connect(DB) as c:
        c.execute("INSERT INTO clips(ts,path) VALUES(?,?)",
                  (datetime.datetime.now().isoformat(), str(tl)))
    return jsonify(status="saved", file=tl.name)

@app.get("/gallery")
def gallery():
    rows = sqlite3.connect(DB).execute(
        "SELECT path,ts FROM clips ORDER BY id DESC").fetchall()
    body = "".join(f"<video width=320 controls src='/static/{Path(p).name}'></video><br>{ts}<hr>"
                   for p,ts in rows)
    return f"<h2>Daily Timelapses</h2>{body or 'No clips yet.'}"



PORT = int(os.getenv("TL_PORT", 5050))   # default 5050
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
