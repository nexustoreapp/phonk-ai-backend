# timebase.py
from typing import Optional
import math


# =========================
# Core musical math
# =========================

def seconds_per_beat(bpm: float) -> float:
    if bpm <= 0:
        raise ValueError("BPM inválido")
    return 60.0 / bpm


def seconds_per_bar(bpm: float, beats_per_bar: int = 4) -> float:
    return seconds_per_beat(bpm) * beats_per_bar


def bars_from_duration(duration_seconds: float, bpm: float, beats_per_bar: int = 4) -> int:
    spb = seconds_per_bar(bpm, beats_per_bar)
    if spb <= 0:
        return 0
    return math.ceil(duration_seconds / spb)


# =========================
# Timebase builder
# =========================

def build_timebase(
    *,
    bpm_real: float,
    duration_seconds: float,
    beats_per_bar: int = 4,
    grid: str = "4/4"
) -> dict:
    """
    Constrói uma base de tempo musical REAL, pensada para DAW (FL Studio).
    Nenhum BPM é inventado aqui.
    """

    spb = seconds_per_beat(bpm_real)
    spbar = seconds_per_bar(bpm_real, beats_per_bar)
    total_bars = bars_from_duration(duration_seconds, bpm_real, beats_per_bar)

    return {
        "timebase": {
            "bpm": round(bpm_real, 3),
            "grid": grid,
            "beats_per_bar": beats_per_bar,
            "seconds_per_beat": round(spb, 6),
            "seconds_per_bar": round(spbar, 6),
            "total_bars": total_bars,
            "total_seconds": round(duration_seconds, 3)
        },
        "fl_studio": {
            "tempo": round(bpm_real, 3),
            "time_signature": grid,
            "snap": "line",
            "default_stretch_mode": "resample",
            "note": "Timebase pronta para sincronização no FL Studio"
        }
    }


# =========================
# Safety helper
# =========================

def can_sync(bpm_real: Optional[float]) -> bool:
    """
    Garante regra filosófica:
    sem BPM real -> sem sync.
    """
    return bpm_real is not None and bpm_real > 0