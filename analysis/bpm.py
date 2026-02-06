import numpy as np
import soundfile as sf

# =========================
# Configurações centrais
# =========================

MIN_AUDIO_SECONDS = 5
MAX_AUDIO_SECONDS = 420  # 7 minutos
MIN_BPM = 40
MAX_BPM = 220


# =========================
# Utilidades
# =========================

def _frame_energy(signal, frame_size):
    energy = []
    for i in range(0, len(signal) - frame_size, frame_size):
        frame = signal[i:i + frame_size]
        energy.append(np.sum(frame ** 2))
    return np.array(energy)


def _estimate_onsets(signal, sr):
    frame_size = int(0.02 * sr)  # 20ms
    energy = _frame_energy(signal, frame_size)

    if len(energy) < 10:
        return []

    diff = np.diff(energy)
    diff = np.maximum(diff, 0)

    threshold = np.mean(diff) + np.std(diff)
    onsets = np.where(diff > threshold)[0]

    times = onsets * (frame_size / sr)
    return times


def _intervals_to_bpm(intervals):
    if len(intervals) == 0:
        return None

    median_interval = np.median(intervals)
    if median_interval <= 0:
        return None

    bpm = 60.0 / median_interval

    while bpm < MIN_BPM:
        bpm *= 2
    while bpm > MAX_BPM:
        bpm /= 2

    return bpm


# =========================
# Análise principal
# =========================

def analyze_bpm(audio_path: str):
    signal, sr = sf.read(audio_path)

    if signal.ndim > 1:
        signal = np.mean(signal, axis=1)

    duration = len(signal) / sr

    if duration < MIN_AUDIO_SECONDS:
        raise ValueError("Áudio curto demais para análise confiável")

    if duration > MAX_AUDIO_SECONDS:
        raise ValueError("Áudio excede o limite máximo de 7 minutos")

    onsets = _estimate_onsets(signal, sr)

    if len(onsets) < 4:
        return {
            "bpm_reference": None,
            "bpm_performance": None,
            "bpm_stability": 0.0,
            "confidence": "low"
        }

    intervals = np.diff(onsets)
    bpm_reference = _intervals_to_bpm(intervals)

    # BPM de performance: média móvel
    bpm_series = []
    for i in range(len(intervals)):
        bpm = _intervals_to_bpm(intervals[max(0, i - 3):i + 1])
        if bpm:
            bpm_series.append(bpm)

    if len(bpm_series) == 0:
        bpm_performance = None
        stability = 0.0
    else:
        bpm_performance = float(np.mean(bpm_series))
        stability = float(1.0 - (np.std(bpm_series) / np.mean(bpm_series)))

    stability = max(0.0, min(1.0, stability))

    confidence = "high" if stability > 0.75 else "medium" if stability > 0.4 else "low"

    return {
        "bpm_reference": round(bpm_reference, 2) if bpm_reference else None,
        "bpm_performance": round(bpm_performance, 2) if bpm_performance else None,
        "bpm_stability": round(stability, 3),
        "confidence": confidence
  }
