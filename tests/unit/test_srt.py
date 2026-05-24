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
    assert items[0]["split_index"] == 1
    assert items[-1]["split_count"] == len(items)
    assert all(item["time_estimated"] is True for item in items)


def test_split_subtitle_items_uses_word_timestamps_for_sentence_gap():
    items = split_subtitle_items(
        [
            {
                "item_id": "parent-1",
                "start": 0.0,
                "end": 8.0,
                "text": "第一句。第二句。",
                "words": [
                    {"text": "第", "start": 0.0, "end": 0.2},
                    {"text": "一", "start": 0.2, "end": 0.4},
                    {"text": "句", "start": 0.4, "end": 0.8},
                    {"text": "第", "start": 2.0, "end": 2.2},
                    {"text": "二", "start": 2.2, "end": 2.4},
                    {"text": "句", "start": 2.4, "end": 2.8},
                ],
            }
        ]
    )

    assert [(item["start"], item["end"], item["time_source"]) for item in items] == [
        (0.0, 0.8, "word"),
        (2.0, 2.8, "word"),
    ]


def test_split_subtitle_items_word_matching_normalizes_punctuation_and_width():
    items = split_subtitle_items(
        [
            {
                "item_id": "parent-1",
                "start": 0.0,
                "end": 8.0,
                "text": "Ａ B 第一句。第二句？",
                "words": [
                    {"text": "a", "start": 0.0, "end": 0.2},
                    {"text": "b", "start": 0.2, "end": 0.4},
                    {"text": "第", "start": 0.4, "end": 0.6},
                    {"text": "一", "start": 0.6, "end": 0.8},
                    {"text": "句", "start": 0.8, "end": 1.0},
                    {"text": "第", "start": 2.0, "end": 2.2},
                    {"text": "二", "start": 2.2, "end": 2.4},
                    {"text": "句", "start": 2.4, "end": 2.8},
                ],
            }
        ]
    )

    assert items[0]["start"] == 0.0
    assert items[0]["end"] == 1.0
    assert items[1]["start"] == 2.0
    assert all(item["time_source"] == "word" for item in items)


def test_split_subtitle_items_falls_back_when_word_matching_fails():
    items = split_subtitle_items(
        [
            {
                "item_id": "parent-1",
                "start": 0.0,
                "end": 8.0,
                "text": "第一句。第二句。",
                "words": [{"text": "完", "start": 0.0, "end": 0.2}],
            }
        ]
    )

    assert len(items) == 2
    assert all(item["time_source"] == "estimated" for item in items)


def test_split_subtitle_items_splits_on_word_gap_without_punctuation():
    items = split_subtitle_items(
        [
            {
                "item_id": "parent-1",
                "start": 31.09,
                "end": 35.73,
                "text": "OK，我先啊缩放的小一点哈，同时呢我们再来看。",
                "words": [
                    {"text": "OK", "start": 31.09, "end": 31.35},
                    {"text": "我", "start": 31.36, "end": 31.52},
                    {"text": "先", "start": 31.52, "end": 31.68},
                    {"text": "啊", "start": 31.70, "end": 31.86},
                    {"text": "缩放", "start": 31.90, "end": 32.35},
                    {"text": "的", "start": 32.36, "end": 32.48},
                    {"text": "小", "start": 32.50, "end": 32.66},
                    {"text": "一点", "start": 32.68, "end": 33.05},
                    {"text": "哈", "start": 33.06, "end": 33.30},
                    {"text": "同时", "start": 34.20, "end": 34.55},
                    {"text": "呢", "start": 34.56, "end": 34.68},
                    {"text": "我们", "start": 34.70, "end": 35.02},
                    {"text": "再", "start": 35.04, "end": 35.18},
                    {"text": "来看", "start": 35.20, "end": 35.73},
                ],
            }
        ]
    )

    assert [(item["text"], item["start"], item["end"], item["split_reason"]) for item in items] == [
        ("OK我先啊缩放的小一点哈", 31.09, 33.3, "word_gap"),
        ("同时呢我们再来看", 34.2, 35.73, "word_gap"),
    ]
    assert all(item["time_source"] == "word" for item in items)


def test_split_subtitle_items_does_not_split_when_word_gap_below_threshold():
    items = split_subtitle_items(
        [
            {
                "item_id": "parent-1",
                "start": 0.0,
                "end": 3.0,
                "text": "OK我先啊缩放的小一点哈同时呢我们再来看",
                "words": [
                    {"text": "OK", "start": 0.0, "end": 0.2},
                    {"text": "我", "start": 0.3, "end": 0.5},
                    {"text": "先", "start": 0.6, "end": 0.8},
                    {"text": "同时", "start": 1.5, "end": 1.8},
                    {"text": "呢", "start": 1.9, "end": 2.0},
                    {"text": "来看", "start": 2.2, "end": 3.0},
                ],
            }
        ]
    )

    assert len(items) == 1
    assert items[0]["text"] == "OK我先啊缩放的小一点哈同时呢我们再来看"


def test_split_subtitle_items_falls_back_when_word_gap_chunk_is_too_short():
    items = split_subtitle_items(
        [
            {
                "item_id": "parent-1",
                "start": 0.0,
                "end": 2.0,
                "text": "啊第一句。第二句。",
                "words": [
                    {"text": "啊", "start": 0.0, "end": 0.1},
                    {"text": "第", "start": 1.0, "end": 1.2},
                    {"text": "一", "start": 1.2, "end": 1.4},
                    {"text": "句", "start": 1.4, "end": 1.8},
                ],
            }
        ]
    )

    assert len(items) == 1
    assert items[0]["text"] == "啊第一句。第二句。"
    assert "split_reason" not in items[0]


def test_split_subtitle_items_does_not_force_split_for_too_short_parent():
    items = split_subtitle_items(
        [
            {
                "item_id": "parent-1",
                "start": 10.0,
                "end": 10.5,
                "text": "第一句话很长，需要拆开。第二句话也很长，需要变成另一条字幕。",
            },
            {"item_id": "parent-2", "start": 11.0, "end": 12.0, "text": "下一句"},
        ]
    )

    assert len(items) == 2
    assert items[0]["start"] == 10.0
    assert items[0]["end"] == 10.5
    assert items[1]["start"] == 11.0


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


def test_render_srt_cleans_subtitle_punctuation_by_default():
    content = render_srt([{"start": 0.0, "end": 1.0, "text": "你好，世界。真的；可以、吗？可以！"}])

    assert "你好世界真的可以吗？可以！" in content
    assert "，" not in content
    assert "。" not in content


def test_render_srt_can_remove_question_and_exclamation():
    content = render_srt(
        [{"start": 0.0, "end": 1.0, "text": "可以吗？可以！"}],
        keep_question_exclamation=False,
    )

    assert "可以吗可以" in content
