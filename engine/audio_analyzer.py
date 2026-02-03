import librosa
import numpy as np
import os

def analyze_audio(file_path: str):
    try:
        y, sr = librosa.load(file_path, sr=None, mono=True)

        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        tempo = float(round(tempo, 2))

        duration = float(round(librosa.get_duration(y=y, sr=sr), 2))

        rms = np.mean(librosa.feature.rms(y=y))
        energy = float(round(rms, 6))

        intervals = librosa.effects.split(y, top_db=30)
        intro_silence = 0.0
        if len(intervals) > 0:
            intro_silence = round(intervals[0][0] / sr, 2)

        if energy < 0.01:
            content_type = "ambient_or_fx"
        elif tempo < 90:
            content_type = "vocal_or_reference"
        else:
            content_type = "rhythmic_sample"

        return {
            "bpm": tempo,
            "duration_seconds": duration,
            "energy": energy,
            "intro_silence_seconds": intro_silence,
            "content_type": content_type
        }

    except Exception as e:
        return {"error": str(e)}