import math
from typing import Dict


def bpm_to_timebase(
    bpm: float,
    sample_rate: int,
    beats_per_bar: int = 4
) -> Dict:
    """
    Converte BPM real em time base musical absoluta.
    """

    if bpm <= 0:
        raise ValueError("BPM inválido")

    seconds_per_beat = 60.0 / bpm
    seconds_per_bar = seconds_per_beat * beats_per_bar
    samples_per_beat = seconds_per_beat * sample_rate
    samples_per_bar = seconds_per_bar * sample_rate

    return {
        "bpm_real": round(bpm, 4),
        "beats_per_bar": beats_per_bar,
        "seconds_per_beat": round(seconds_per_beat, 6),
        "seconds_per_bar": round(seconds_per_bar, 6),
        "samples_per_beat": int(samples_per_beat),
        "samples_per_bar": int(samples_per_bar),
        "sample_rate": sample_rate
    }


def seconds_to_fl_position(
    seconds: float,
    bpm: float,
    beats_per_bar: int = 4
) -> Dict:
    """
    Converte segundos absolutos em posição musical do FL:
    Bar / Beat / Tick
    """

    if bpm <= 0:
        raise ValueError("BPM inválido")

    seconds_per_beat = 60.0 / bpm
    total_beats = seconds / seconds_per_beat

    bar = int(total_beats // beats_per_bar) + 1
    beat = int(total_beats % beats_per_bar) + 1

    beat_fraction = total_beats - math.floor(total_beats)
    tick = int(beat_fraction * 960)  # FL usa 960 PPQ

    return {
        "bar": bar,
        "beat": beat,
        "tick": tick,
        "absolute_seconds": round(seconds, 6)
    }


def generate_fl_sync_payload(
    bpm: float,
    duration_seconds: float,
    sample_rate: int,
    beats_per_bar: int = 4
) -> Dict:
    """
    Payload final pronto para o FL Studio
    """

    timebase = bpm_to_timebase(bpm, sample_rate, beats_per_bar)
    end_position = seconds_to_fl_position(
        duration_seconds,
        bpm,
        beats_per_bar
    )

    return {
        "engine": "PHONK_AI_SYNC",
        "timebase": timebase,
        "track_duration_seconds": round(duration_seconds, 6),
        "end_position": end_position,
        "ppq": 960,
        "status": "ready_for_fl"
    }