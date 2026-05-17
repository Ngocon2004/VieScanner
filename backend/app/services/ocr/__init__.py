"""OCR subsystem cho VieScanner.

Modular pipeline: aligner → cleaner → detector → recognizer → extractor.
Mỗi stage là 1 `Protocol` (interfaces.py) có nhiều implementation (mock / real).
`OCRPipeline` (pipeline.py) orchestrate các stage qua dependency injection.
"""

from app.services.ocr.interfaces import (
    BBox,
    OCRStageError,
    TextLine,
)
from app.services.ocr.pipeline import OCRPipeline


__all__ = ["BBox", "OCRPipeline", "OCRStageError", "TextLine"]
