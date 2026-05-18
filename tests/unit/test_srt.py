import pytest

from class_up.transcription.srt import render_srt


def test_render_srt_numbering_and_timecodes():
    content = render_srt(
        [
            {"start": 0.0, "end": 1.2, "text": "第一句"},
            {"start": 1.2, "end": 2.0, "text": "第二句"},
        ]
    )
    assert "1\n00:00:00,000 --> 00:00:01,200\n第一句" in content
    assert "2\n00:00:01,200 --> 00:00:02,000\n第二句" in content


def test_render_srt_rejects_non_monotonic_items():
    with pytest.raises(ValueError):
        render_srt(
            [
                {"start": 1.0, "end": 2.0, "text": "a"},
                {"start": 1.5, "end": 3.0, "text": "b"},
            ]
        )


def test_render_srt_rejects_negative_time():
    with pytest.raises(ValueError):
        render_srt([{"start": -1.0, "end": 1.0, "text": "a"}])
