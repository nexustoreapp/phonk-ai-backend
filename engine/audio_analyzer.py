import librosa
import numpy as np

def analyze_audio(file_path: str):
    y, sr = librosa.load(file_path, sr=None, mono=True)

    duration = librosa.get_duration(y=y, sr=sr)
    rms = float(np.mean(librosa.feature.rms(y=y)))
    peak = float(np.max(np.abs(y)))

    return {
        "duration_seconds": round(duration, 2),
        "sample_rate": sr,
        "rms_energy": round(rms, 6),
        "peak_amplitude": round(peak, 6)
    }
