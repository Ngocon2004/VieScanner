"""Implementations cụ thể (mock + real) cho từng stage của pipeline OCR."""

from app.services.ocr.stages.aligner import MockAligner, RealCardAligner
from app.services.ocr.stages.cleaner import MockCleaner, RealImageCleaner
from app.services.ocr.stages.detector import MockDetector, RealTextDetector
from app.services.ocr.stages.extractor import MockExtractor, RealFieldExtractor
from app.services.ocr.stages.recognizer import MockRecognizer, RealTextRecognizer


__all__ = [
    "MockAligner",
    "MockCleaner",
    "MockDetector",
    "MockExtractor",
    "MockRecognizer",
    "RealCardAligner",
    "RealFieldExtractor",
    "RealImageCleaner",
    "RealTextDetector",
    "RealTextRecognizer",
]
