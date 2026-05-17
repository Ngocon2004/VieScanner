"""Eval script – chạy pipeline OCR full real trên folder ảnh CCCD.

Usage:
    cd backend
    venv\\Scripts\\python.exe scripts\\eval_ocr.py <folder_path> \
      [--limit N] [--out file.json] [--ground-truth gt.json] \
      [--detector-padding 6] [--detector-conf-threshold 0.35] \
      [--recognizer-beamsearch false]

Ground-truth JSON supported shapes:
1) {"images": {"img1.jpg": {"id_number": "...", ...}, ...}}
2) [{"file": "img1.jpg", "fields": {...}}, ...]
3) {"img1.jpg": {"id_number": "...", ...}, ...}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Đặt UTF-8 cho stdout Windows console.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

# Thêm backend/ vào sys.path để chạy script trực tiếp.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.exceptions import OCRFailedError  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services.ocr_engine import _build_real_pipeline  # noqa: E402

FIELD_NAMES = (
    "id_number",
    "full_name",
    "dob",
    "gender",
    "nationality",
    "origin",
    "residence",
    "expiry_date",
)


def _format_id(s: str) -> str:
    """Format id partially redacted để khỏi leak full PII trong console."""
    if len(s) == 12 and s != "000000000000":
        return f"{s[:4]}****{s[8:]}"
    return s


def _normalize_text(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[-1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _levenshtein_tokens(a: list[str], b: list[str]) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ta in enumerate(a, start=1):
        curr = [i]
        for j, tb in enumerate(b, start=1):
            cost = 0 if ta == tb else 1
            curr.append(min(curr[-1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _is_placeholder(field: str, value: str | None) -> bool:
    if not value:
        return True
    v = value.strip()
    if field == "id_number":
        return v == "000000000000"
    if field in ("full_name", "origin", "residence"):
        return v == "(không nhận dạng được)"
    if field == "dob":
        return v == "01/01/2000"
    return False


def _normalize_rel_path(path: str) -> str:
    return path.replace("\\", "/")


def _parse_bool(raw: str) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Giá trị bool không hợp lệ: {raw!r}")


def _apply_tuning_overrides(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {}

    def _set(name: str, value: object | None) -> None:
        if value is None:
            return
        setattr(settings, name, value)
        overrides[name] = getattr(settings, name)

    _set("ocr_aligner_conf_threshold", args.aligner_conf_threshold)
    _set("ocr_cleaner_shadow_kernel_size", args.cleaner_shadow_kernel_size)
    _set("ocr_cleaner_clip_hist_percent", args.cleaner_clip_hist_percent)
    _set("ocr_detector_conf_threshold", args.detector_conf_threshold)
    _set("ocr_detector_padding", args.detector_padding)
    _set("ocr_extractor_fuzzy_threshold", args.extractor_fuzzy_threshold)

    if args.recognizer_beamsearch is not None:
        _set("ocr_recognizer_beamsearch", _parse_bool(args.recognizer_beamsearch))

    return overrides


def _load_ground_truth(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    mapping: dict[str, dict[str, str]] = {}

    if isinstance(raw, dict) and isinstance(raw.get("images"), dict):
        raw = raw["images"]

    if isinstance(raw, dict):
        for key, fields in raw.items():
            if not isinstance(fields, dict):
                continue
            mapping[_normalize_rel_path(str(key))] = {
                k: str(v) for k, v in fields.items() if k in FIELD_NAMES
            }
        return mapping

    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            file_key = item.get("file") or item.get("path")
            fields = item.get("fields") or item
            if not file_key or not isinstance(fields, dict):
                continue
            mapping[_normalize_rel_path(str(file_key))] = {
                k: str(v) for k, v in fields.items() if k in FIELD_NAMES
            }
        return mapping

    raise ValueError("Ground-truth JSON format không hợp lệ.")


def run_one(pipeline, img_path: Path) -> dict:
    """Run pipeline trên 1 ảnh, trả về dict kết quả + lỗi nếu có."""
    record: dict = {
        "file": img_path.name,
        "size_kb": round(img_path.stat().st_size / 1024),
    }
    try:
        with open(img_path, "rb") as f:
            image_bytes = f.read()

        t0 = time.perf_counter()
        result, trace = asyncio.run(pipeline.run_with_trace(image_bytes))
        elapsed_ms = (time.perf_counter() - t0) * 1000

        record["status"] = "ok"
        record["elapsed_ms"] = round(elapsed_ms)
        record["fields"] = result.data.model_dump()
        record["confidences"] = result.confidences
        record["stage_ms"] = trace.stage_ms
        record["total_ms"] = trace.total_ms
        record["num_boxes"] = trace.num_boxes
        record["num_lines"] = trace.num_lines
        if trace.debug_dir:
            record["debug_dir"] = trace.debug_dir
    except OCRFailedError as exc:
        record["status"] = "failed"
        record["error"] = str(exc.message)
        record["error_code"] = exc.code
    except Exception as exc:  # noqa: BLE001
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def _evaluate_with_ground_truth(records: list[dict], gt_map: dict[str, dict[str, str]]) -> dict:
    field_total = {f: 0 for f in FIELD_NAMES}
    field_correct = {f: 0 for f in FIELD_NAMES}

    char_dist = 0
    char_total = 0
    word_dist = 0
    word_total = 0

    compared_images = 0
    image_errors: list[dict] = []

    for rec in records:
        rel_path = _normalize_rel_path(rec["path"])
        gt_fields = gt_map.get(rel_path)
        if not gt_fields:
            continue

        compared_images += 1
        pred_fields = rec.get("fields", {}) if rec.get("status") == "ok" else {}
        mismatches: list[dict] = []

        for field in FIELD_NAMES:
            if field not in gt_fields:
                continue
            expected_raw = str(gt_fields[field])
            predicted_raw = str(pred_fields.get(field, ""))

            expected = _normalize_text(expected_raw)
            predicted = _normalize_text(predicted_raw)

            field_total[field] += 1
            is_exact = predicted == expected
            if is_exact:
                field_correct[field] += 1
            else:
                mismatches.append(
                    {
                        "field": field,
                        "expected": expected_raw,
                        "predicted": predicted_raw,
                    }
                )

            dist_c = _levenshtein(predicted, expected)
            char_dist += dist_c
            char_total += max(1, len(expected))

            exp_tokens = expected.split()
            pred_tokens = predicted.split()
            dist_w = _levenshtein_tokens(pred_tokens, exp_tokens)
            word_dist += dist_w
            word_total += max(1, len(exp_tokens))

        if mismatches:
            image_errors.append({"path": rel_path, "mismatches": mismatches})

    field_accuracy = {
        f: (100.0 * field_correct[f] / field_total[f]) if field_total[f] else None
        for f in FIELD_NAMES
    }

    cer = (100.0 * char_dist / char_total) if char_total else None
    wer = (100.0 * word_dist / word_total) if word_total else None

    return {
        "compared_images": compared_images,
        "field_total": field_total,
        "field_correct": field_correct,
        "field_accuracy_percent": field_accuracy,
        "cer_percent": cer,
        "wer_percent": wer,
        "image_errors": image_errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval OCR pipeline trên folder CCCD.")
    parser.add_argument("folder", help="Đường dẫn folder chứa ảnh .jpg/.png")
    parser.add_argument("--limit", type=int, default=0, help="Chỉ chạy N ảnh đầu (0 = tất cả).")
    parser.add_argument("--out", default="scripts/eval_results.json", help="File JSON output.")
    parser.add_argument(
        "--patterns", default="*.jpg,*.jpeg,*.png", help="CSV của file patterns."
    )
    parser.add_argument(
        "--ground-truth",
        default="",
        help="Path file ground-truth JSON để tính accuracy/CER/WER.",
    )
    parser.add_argument(
        "--aligner-conf-threshold",
        type=float,
        default=None,
        help="Override OCR_ALIGNER_CONF_THRESHOLD.",
    )
    parser.add_argument(
        "--cleaner-shadow-kernel-size",
        type=int,
        default=None,
        help="Override OCR_CLEANER_SHADOW_KERNEL_SIZE.",
    )
    parser.add_argument(
        "--cleaner-clip-hist-percent",
        type=float,
        default=None,
        help="Override OCR_CLEANER_CLIP_HIST_PERCENT.",
    )
    parser.add_argument(
        "--detector-conf-threshold",
        type=float,
        default=None,
        help="Override OCR_DETECTOR_CONF_THRESHOLD.",
    )
    parser.add_argument(
        "--detector-padding",
        type=int,
        default=None,
        help="Override OCR_DETECTOR_PADDING.",
    )
    parser.add_argument(
        "--recognizer-beamsearch",
        default=None,
        help="Override OCR_RECOGNIZER_BEAMSEARCH (true/false).",
    )
    parser.add_argument(
        "--extractor-fuzzy-threshold",
        type=int,
        default=None,
        help="Override OCR_EXTRACTOR_FUZZY_THRESHOLD.",
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"[ERR] Folder không tồn tại: {folder}", file=sys.stderr)
        sys.exit(1)

    images: list[Path] = []
    for pat in args.patterns.split(","):
        images.extend(folder.rglob(pat.strip()))
    images = sorted(images)
    if args.limit:
        images = images[: args.limit]

    if not images:
        print(f"[ERR] Không tìm thấy ảnh trong {folder}", file=sys.stderr)
        sys.exit(1)

    gt_map = _load_ground_truth(Path(args.ground_truth)) if args.ground_truth else {}
    tuning_overrides = _apply_tuning_overrides(args)

    if tuning_overrides:
        print("=== Tuning overrides ===")
        for key in sorted(tuning_overrides):
            print(f"- {key}={tuning_overrides[key]}")
        print()

    print("=== Building OCR pipeline... ===")
    t0 = time.perf_counter()
    pipeline = _build_real_pipeline()
    print(f"Pipeline ready in {time.perf_counter()-t0:.1f}s\n")

    print(f"=== Processing {len(images)} images from {folder} ===\n")
    print(f"{'idx':>3} {'file':45} {'status':8} {'ms':>5}  {'id':12} {'name':30} {'avg_conf':>8}")
    print("-" * 130)

    records: list[dict] = []
    for idx, img_path in enumerate(images):
        rel = img_path.relative_to(folder)
        rec = run_one(pipeline, img_path)
        records.append({"path": _normalize_rel_path(str(rel)), **rec})

        if rec["status"] == "ok":
            fields = rec["fields"]
            confidences = rec.get("confidences", {})
            avg_conf = (
                f"{100 * sum(confidences.values()) / len(confidences):.0f}%"
                if confidences
                else "N/A"
            )
            print(
                f"{idx:>3} {str(rel)[:44]:44} ok       {rec['elapsed_ms']:>5}  "
                f"{_format_id(fields['id_number']):12} {fields['full_name'][:30]:30} {avg_conf:>8}"
            )
        else:
            err_msg = rec.get("error", "?")[:50]
            print(f"{idx:>3} {str(rel)[:44]:44} {rec['status']:8}     -  {err_msg}")

    n_ok = sum(1 for r in records if r["status"] == "ok")
    n_fail = sum(1 for r in records if r["status"] == "failed")
    n_err = sum(1 for r in records if r["status"] == "error")

    print()
    print(f"=== Summary: {n_ok}/{len(records)} ok, {n_fail} failed, {n_err} error ===")

    print()
    print(f"{'field':15} {'success%':>10}")
    for field in FIELD_NAMES:
        cnt = sum(
            1
            for r in records
            if r["status"] == "ok"
            and r["fields"].get(field)
            and not _is_placeholder(field, r["fields"].get(field))
        )
        pct = 100 * cnt / max(1, n_ok)
        print(f"{field:15} {pct:>9.1f}%  ({cnt}/{n_ok})")

    gt_report: dict | None = None
    if gt_map:
        gt_report = _evaluate_with_ground_truth(records, gt_map)
        print("\n=== Ground-truth evaluation ===")
        print(f"Compared images: {gt_report['compared_images']}")
        print(f"CER: {gt_report['cer_percent']:.2f}%" if gt_report["cer_percent"] is not None else "CER: N/A")
        print(f"WER: {gt_report['wer_percent']:.2f}%" if gt_report["wer_percent"] is not None else "WER: N/A")
        print(f"{'field':15} {'acc%':>10} {'correct/total':>14}")
        for field in FIELD_NAMES:
            total = gt_report["field_total"][field]
            correct = gt_report["field_correct"][field]
            acc = gt_report["field_accuracy_percent"][field]
            acc_str = "N/A" if acc is None else f"{acc:.1f}%"
            print(f"{field:15} {acc_str:>10} {f'{correct}/{total}':>14}")
        print(f"Image errors: {len(gt_report['image_errors'])}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "folder": str(folder),
        "tuning_overrides": tuning_overrides,
        "records": records,
        "ground_truth": {"path": args.ground_truth, "report": gt_report} if gt_map else None,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Detailed results saved to {out_path}")


if __name__ == "__main__":
    main()
