from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os
import uuid
import wave
import contextlib
import struct
import math

app = FastAPI()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def compute_rms(samples):
    if not samples:
        return 0
    square_sum = sum(s * s for s in samples)
    mean_square = square_sum / len(samples)
    return int(math.sqrt(mean_square))


@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    file_id = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_id)

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    return {
        "message": "upload ok",
        "file_id": file_id,
        "path": file_path
    }


@app.post("/analyze-audio")
async def analyze_audio(file: UploadFile = File(...)):
    file_id = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_id)

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    try:
        with contextlib.closing(wave.open(file_path, "rb")) as wf:
            channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            frames = wf.getnframes()
            sample_width = wf.getsampwidth()
            duration = frames / float(sample_rate)

            raw_audio = wf.readframes(frames)

            if sample_width != 2:
                raise Exception("Only 16-bit WAV supported")

            samples = struct.unpack("<" + "h" * (len(raw_audio) // 2), raw_audio)
            peak = max(abs(s) for s in samples)
            rms = compute_rms(samples)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"audio analysis failed: {str(e)}")

    return JSONResponse({
        "status": "ok",
        "message": "audio analyzed",
        "analysis_stage": "basic_features",
        "file_id": file_id,
        "analysis": {
            "duration_seconds": round(duration, 3),
            "sample_rate": sample_rate,
            "channels": channels,
            "rms_energy": rms,
            "peak_amplitude": peak
        }
    })


@app.get("/")
def root():
    return {"status": "online"}