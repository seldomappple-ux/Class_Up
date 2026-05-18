from __future__ import annotations


def ensure_non_negative(seconds: float) -> float:
    if seconds < 0:
        raise ValueError("time value cannot be negative")
    return seconds


def seconds_to_srt_time(seconds: float) -> str:
    seconds = ensure_non_negative(float(seconds))
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def srt_time_to_seconds(value: str) -> float:
    time_part, millis_part = value.split(",", 1)
    hours, minutes, seconds = [int(part) for part in time_part.split(":")]
    millis = int(millis_part)
    total = hours * 3600 + minutes * 60 + seconds + millis / 1000
    return ensure_non_negative(total)


def seconds_to_filename_time(seconds: float) -> str:
    seconds = ensure_non_negative(float(seconds))
    whole = int(seconds)
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}-{minutes:02d}-{secs:02d}"
