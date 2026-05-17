"""Database repository layer."""

from app.db.repositories.cccd_record_repository import CCCDRecordRepository
from app.db.repositories.correction_repository import CorrectionRepository
from app.db.repositories.scan_repository import ScanRepository
from app.db.repositories.user_repository import UserRepository


__all__ = [
    "UserRepository",
    "ScanRepository",
    "CCCDRecordRepository",
    "CorrectionRepository",
]
