from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.correction import Correction


class CorrectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def bulk_insert(
        self,
        *,
        scan_id: str,
        items: list[dict],
    ) -> list[Correction]:
        rows: list[Correction] = []
        for item in items:
            row = Correction(
                scan_id=scan_id,
                field_name=item["field_name"],
                ocr_value=item.get("ocr_value"),
                corrected_value=item.get("corrected_value"),
                confidence_at_ocr=item.get("confidence_at_ocr"),
            )
            rows.append(row)
        self.session.add_all(rows)
        await self.session.flush()
        return rows

    async def replace_for_scan(self, *, scan_id: str, items: list[dict]) -> list[Correction]:
        # Mỗi scan chỉ giữ bản sửa cuối cùng: xuất lại nhiều lần không được nhân bản dữ liệu huấn luyện.
        await self.session.execute(delete(Correction).where(Correction.scan_id == scan_id))
        return await self.bulk_insert(scan_id=scan_id, items=items) if items else []


__all__ = ["CorrectionRepository"]

