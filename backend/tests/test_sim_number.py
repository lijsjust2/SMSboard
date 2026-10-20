"""SIM 卡号码智能提取测试"""
from app.services.registry import extract_phone_number, parse_sim_key


def test_extract_11_digit_phone():
    assert extract_phone_number("测试选项项_18888888888") == "18888888888"


def test_extract_fallback_digits():
    assert extract_phone_number("备注1570") == "1570"


def test_extract_none():
    assert extract_phone_number("纯文字备注") == ""


def test_parse_slot():
    assert parse_sim_key("SIM1_13800000000") == ("SIM1", "13800000000")
    assert parse_sim_key("SIM2_测试_1888") == ("SIM2", "测试_1888")
