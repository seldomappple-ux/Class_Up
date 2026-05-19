import pytest

from class_up.transcription.doubao import _doubao_api_model_name, convert_doubao_result


def _segment():
    return {
        "segment_id": "segment-0001",
        "audio_path": "intermediate/segments/segment-0001.wav",
        "start": 10.0,
        "end": 20.0,
    }


def test_doubao_utterances_convert_to_internal_items():
    result = convert_doubao_result(
        segment=_segment(),
        doubao_body={
            "result": {
                "text": "第一句 第二句",
                "utterances": [
                    {"start_time": 200, "end_time": 1000, "text": " 第一句 "},
                    {"start_time": 1100, "end_time": 2500, "text": "第二句"},
                ],
            }
        },
        model="bigmodel",
        raw_output_path="intermediate/transcription/raw/segment-0001.doubao.json",
    )
    assert result["provider"] == "doubao"
    assert result["time_base"] == "segment_relative"
    assert result["items"] == [
        {
            "item_id": "segment-0001-item-0001",
            "start": 0.2,
            "end": 1.0,
            "text": "第一句",
            "confidence": None,
        },
        {
            "item_id": "segment-0001-item-0002",
            "start": 1.1,
            "end": 2.5,
            "text": "第二句",
            "confidence": None,
        },
    ]
    assert "API" not in str(result)


def test_doubao_text_fallback_adds_review_marker():
    result = convert_doubao_result(
        segment=_segment(),
        doubao_body={"result": {"text": "没有 utterances 的整段文本"}},
        model="bigmodel",
        raw_output_path="intermediate/transcription/raw/segment-0001.doubao.json",
    )
    assert result["items"][0]["start"] == 0.0
    assert result["items"][0]["end"] == 10.0
    assert result["_review"]["type"] == "transcription_timestamp_fallback"


def test_doubao_rejects_negative_duration_item():
    with pytest.raises(ValueError, match="end_time"):
        convert_doubao_result(
            segment=_segment(),
            doubao_body={"result": {"utterances": [{"start_time": 2000, "end_time": 1000, "text": "错序"}]}},
            model="bigmodel",
            raw_output_path="raw.json",
        )


def test_doubao_display_model_maps_to_api_model_name():
    assert _doubao_api_model_name("Doubao-录音文件识别2.0") == "bigmodel"
    assert _doubao_api_model_name("bigmodel") == "bigmodel"
