from __future__ import annotations

import pytest

from app.services.card_split import split_cards
from app.services.intake import expand_file

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


def _page(cards: list[tuple[int, int, tuple[int, int, int]]], size: tuple[int, int] = (1500, 2000)) -> bytes:
    """Giấy trắng có các thẻ dọc 540x856 (tỉ lệ ID-1) tô màu, đặt tại (x, y)."""
    img = np.full((*size, 3), 245, np.uint8)
    for x, y, color in cards:
        cv2.rectangle(img, (x, y), (x + 540, y + 856), color, -1)
        cv2.putText(img, "CAN CUOC", (x + 40, y + 200), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (20, 20, 20), 3)
    return cv2.imencode(".jpg", img)[1].tobytes()


TEAL = (190, 200, 120)


def test_two_colored_cards_are_split_left_to_right_and_rotated_landscape() -> None:
    crops = split_cards(_page([(1100, 300, TEAL), (200, 320, TEAL)]))
    assert len(crops) == 2
    shapes = [cv2.imdecode(np.frombuffer(c, np.uint8), cv2.IMREAD_COLOR).shape for c in crops]
    assert all(w > h for h, w, _ in shapes)


def test_single_card_and_gray_boxes_are_not_split() -> None:
    assert split_cards(_page([(700, 300, TEAL)])) == []
    assert split_cards(_page([(200, 300, (200, 200, 200)), (1100, 300, (200, 200, 200))])) == []


def test_intake_turns_multi_card_photo_into_one_item_per_card() -> None:
    items = expand_file(0, "hai_the.jpg", _page([(200, 300, TEAL), (1100, 300, TEAL)]))
    assert [i.filename for i in items] == ["hai_the.jpg - thẻ 1", "hai_the.jpg - thẻ 2"]
    assert all(i.container_filename == "hai_the.jpg" and i.contents for i in items)
