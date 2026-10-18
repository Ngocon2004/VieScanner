from __future__ import annotations

from app.services.ocr.address import ends_with_province, match_address


def test_corrects_accents_province_district_ward() -> None:
    result = match_address("Thôn 2, Xã Tam Kỳ, Huyen Núi Thanh, Tinh Quàng Nam")
    assert result.text == "Thôn 2, Xã Tam Kỳ, Huyện Núi Thành, Tỉnh Quảng Nam"
    assert result.has_province
    assert result.corrected_parts == 2


def test_keeps_abbreviated_prefix() -> None:
    assert match_address("Quận 1, TP. Hồ Chi Minh").text == "Quận 1, TP. Hồ Chí Minh"


def test_short_names_need_exact_match() -> None:
    result = match_address("Hà Nan")
    assert result.text == "Hà Nan"
    assert not result.has_province


def test_unknown_parts_are_left_untouched() -> None:
    result = match_address("Số 12, Tổ 3, Khu phố 6")
    assert result.text == "Số 12, Tổ 3, Khu phố 6"
    assert not result.has_province


def test_dot_inside_multiword_unit_becomes_space() -> None:
    assert match_address("Tổ Dân.Phố 5, Khu.phố 2, Thành.Phố Hà Nội").text == "Tổ Dân Phố 5, Khu phố 2, Thành phố Hà Nội"
    assert match_address("P.5, Q.1, TP.Hồ Chí Minh").text == "P.5, Q.1, TP. Hồ Chí Minh"
    assert match_address("12/34.Lê Lợi, Phường 5").text == "12/34 Lê Lợi, Phường 5"


def test_post_2025_address_without_district_level() -> None:
    result = match_address("Phường Ba Đình, Thành phố Hà Nội")
    assert result.has_province
    assert result.text == "Phường Ba Đình, Thành phố Hà Nội"


def test_ends_with_province_accepts_old_province_name() -> None:
    assert ends_with_province("Phú Vang, Thừa Thiên Huế")
    assert not ends_with_province("Phường Bến Nghé")


def test_empty_parts_from_joined_lines_are_dropped() -> None:
    assert match_address("Thôn 2, Xã Tam Kỳ,, Huyện Núi Thành, Tỉnh Quảng Nam").text == (
        "Thôn 2, Xã Tam Kỳ, Huyện Núi Thành, Tỉnh Quảng Nam"
    )


def test_unverified_keeps_only_parts_outside_the_dictionary() -> None:
    result = match_address("12 Lê Lợi, Xã Tam Kỳ, Huyen Núi Thanh, Tinh Quàng Nam")
    assert result.unverified.startswith("12 Lê Lợi")
    assert "Núi Thành" not in result.unverified and "Quảng Nam" not in result.unverified
