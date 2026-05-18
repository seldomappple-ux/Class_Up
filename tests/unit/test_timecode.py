import pytest

from class_up.utils.timecode import seconds_to_filename_time, seconds_to_srt_time, srt_time_to_seconds


def test_seconds_to_srt_time():
    assert seconds_to_srt_time(3661.234) == "01:01:01,234"


def test_srt_time_to_seconds():
    assert srt_time_to_seconds("00:01:02,500") == 62.5


def test_negative_time_rejected():
    with pytest.raises(ValueError):
        seconds_to_srt_time(-0.1)


def test_filename_time():
    assert seconds_to_filename_time(754) == "00-12-34"
