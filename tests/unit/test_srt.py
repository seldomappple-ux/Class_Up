import pytest

from class_up.transcription.srt import render_srt, split_subtitle_items


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


def test_split_subtitle_items_breaks_long_multi_sentence_text():
    items = split_subtitle_items(
        [
            {
                "start": 10.0,
                "end": 18.0,
                "text": "最边缘的一个像素，然后把它做无限的给扩散出去，你看。所以可能就是我们的图大概到这，但是还有很多后续内容。",
            }
        ]
    )

    assert len(items) > 1
    assert all(len(item["text"]) <= 28 for item in items)
    assert items[0]["start"] == 10.0
    assert items[-1]["end"] == 18.0
    assert [item["start"] for item in items] == sorted(item["start"] for item in items)


def test_render_srt_outputs_split_blocks_for_long_text():
    content = render_srt(
        [
            {
                "start": 0.0,
                "end": 8.0,
                "text": "第一句话很长，需要拆开。第二句话也很长，需要变成另一条字幕。",
            }
        ]
    )

    assert "1\n" in content
    assert "2\n" in content
