from __future__ import annotations

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


__all__ = ["CorrectionRepository"]

