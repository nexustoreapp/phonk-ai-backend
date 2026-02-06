from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import wave
import audioop
import numpy as np
import subprocess

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Phonk AI – Audio Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- UTILIDADES ----------

def convert_to_wav(input_path, output_path):
    subprocess.run([
        "ffmpeg", "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", "44100",
        output_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def read_wav(path):
    with wave.open(path, "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16)
        return audio, wf.getframerate(), wf.getnframes() / wf.getframerate()

def detect_onsets(audio, sr):
    diff = np.abs(np.diff(audio))
    threshold = np.mean(diff) + 2 * np.std(diff)
    onsets = np.where(diff > threshold)[0]
    times = onsets / sr
    return times

def estimate_bpm_from_onsets(onsets):
    if len(onsets) < 4:
        return None
    intervals = np.diff(onsets)
    intervals = intervals[(intervals > 0.2) & (intervals < 2.0)]
    if len(intervals) == 0:
        return None
    median_interval = np.median(intervals)
    bpm = 60 / median_interval
    return round(bpm, 2)

def estimate_performance_bpm(duration, event_count):
    if duration <= 0 or event_count < 2:
        return None
    avg_interval = duration / event_count
    bpm = 60 / avg_interval
    return round(bpm, 2)

# ---------- ENDPOINT ----------

@app.post("/analyze-audio")
async def analyze_audio(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    original_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    wav_path = os.path.join(UPLOAD_DIR, f"{file_id}.wav")

    with open(original_path, "wb") as f:
        f.write(await file.read())

    convert_to_wav(original_path, wav_path)

    audio, sr, duration = read_wav(wav_path)
    onsets = detect_onsets(audio, sr)
    bpm_rhythmic = estimate_bpm_from_onsets(onsets)

    if bpm_rhythmic and 40 <= bpm_rhythmic <= 220:
        bpm = bpm_rhythmic
        bpm_type = "rhythmic"
        confidence = min(1.0, len(onsets) / (duration * 2))
    else:
        bpm_perf = estimate_performance_bpm(duration, max(len(onsets), 1))
        if not bpm_perf:
            raise HTTPException(status_code=422, detail="Could not determine BPM")
        bpm = bpm_perf
        bpm_type = "performance"
        confidence = 0.6

    return {
        "file_id": file_id,
        "filename": file.filename,
        "analysis": {
            "duration_seconds": round(duration, 2),
            "sample_rate": sr,
            "bpm": bpm,
            "bpm_type": bpm_type,
            "confidence": round(confidence, 2)
        }
    }

@app.get("/")
def root():
    return {"status": "ok", "service": "Phonk AI Analyzer"}