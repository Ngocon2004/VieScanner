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

Chỉ số chính (theo từng trường):
- exact / CER: so với nhãn; giá trị nhãn là placeholder bị bỏ qua vì nghĩa là "chưa biết".
- silent error: sai mà confidence >= ngưỡng cảnh báo của form -> lọt qua người duyệt. Đây là
  chỉ số quan trọng nhất vì app dựa vào người dùng rà soát trường confidence thấp.
- review burden: đúng nhưng vẫn bị cảnh báo -> người dùng phải xem lại thừa.
"Đọc được" tính theo confidence > 0, không so giá trị với placeholder ("Nam", "Việt Nam" trùng
giá trị thật). Console chỉ in số liệu tổng hợp + số CCCD đã che; file --out chứa dữ liệu thật.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
import unicodedata
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
from app.services.ocr.cccd_number import decode_cccd_number  # noqa: E402
from app.services.ocr.placeholders import FIELD_PLACEHOLDERS  # noqa: E402
from app.services.ocr_engine import _build_real_pipeline  # noqa: E402
from app.utils.privacy import mask_id_number  # noqa: E402

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
TEXT_FIELDS = ("full_name", "origin", "residence")
# Khớp ngưỡng tô cảnh báo trong frontend CCCDForm.
REVIEW_THRESHOLD = 0.6
# Placeholder trùng giá trị thật nên không thể coi là "nhãn chưa biết".
_AMBIGUOUS_PLACEHOLDER_FIELDS = {"gender", "nationality"}


def _normalize_text(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s or "").casefold().split())


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


def _is_unknown_label(field: str, value: str | None) -> bool:
    if not value:
        return True
    if field in _AMBIGUOUS_PLACEHOLDER_FIELDS:
        return False
    return value.strip() == FIELD_PLACEHOLDERS.get(field)


def _cer(predicted: str, expected: str) -> float:
    return min(1.0, _levenshtein(predicted, expected) / max(1, len(expected)))


def _percentiles(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "median": round(statistics.median(ordered), 1),
        "p90": round(ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))], 1),
    }


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


def _summarize_records(records: list[dict]) -> dict:
    """Chỉ số không cần nhãn: tỉ lệ đọc được, nhất quán số CCCD, thời gian."""
    ok = [r for r in records if r["status"] == "ok"]
    read = {
        f: sum(1 for r in ok if r.get("confidences", {}).get(f, 0) > 0) for f in FIELD_NAMES
    }
    flagged = {
        f: sum(
            1 for r in ok if 0 < r.get("confidences", {}).get(f, 0) < REVIEW_THRESHOLD
        )
        for f in FIELD_NAMES
    }
    consistency = {"id_decodable": 0, "id_checked": 0, "gender_match": 0, "birth_year_match": 0, "cross_checked": 0}
    for r in ok:
        fields, conf = r["fields"], r.get("confidences", {})
        if conf.get("id_number", 0) <= 0:
            continue
        consistency["id_checked"] += 1
        info = decode_cccd_number(fields.get("id_number"))
        if info is None:
            continue
        consistency["id_decodable"] += 1
        if conf.get("gender", 0) > 0 and conf.get("dob", 0) > 0:
            consistency["cross_checked"] += 1
            consistency["gender_match"] += fields.get("gender") == info.gender
            consistency["birth_year_match"] += str(fields.get("dob", ""))[-4:] == str(info.birth_year)
    stages = sorted({s for r in ok for s in r.get("stage_ms", {})})
    errors: dict[str, int] = {}
    for r in records:
        if r["status"] != "ok":
            key = r.get("error_code") or r["status"]
            errors[key] = errors.get(key, 0) + 1
    return {
        "images": len(records),
        "ok": len(ok),
        "errors_by_code": errors,
        "read_count": read,
        "flagged_count": flagged,
        "id_consistency": consistency,
        "total_ms": _percentiles([r["total_ms"] for r in ok if "total_ms" in r]),
        "stage_ms": {s: _percentiles([r["stage_ms"][s] for r in ok if s in r.get("stage_ms", {})]) for s in stages},
    }


def _evaluate_with_ground_truth(records: list[dict], gt_map: dict[str, dict[str, str]]) -> dict:
    field_total = {f: 0 for f in FIELD_NAMES}
    field_correct = {f: 0 for f in FIELD_NAMES}
    field_cer: dict[str, list[float]] = {f: [] for f in FIELD_NAMES}
    silent_errors = {f: 0 for f in FIELD_NAMES}
    review_burden = {f: 0 for f in FIELD_NAMES}
    unknown_labels = {f: 0 for f in FIELD_NAMES}

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
        is_ok = rec.get("status") == "ok"
        pred_fields = rec.get("fields", {}) if is_ok else {}
        pred_conf = rec.get("confidences", {}) if is_ok else {}
        mismatches: list[dict] = []

        for field in FIELD_NAMES:
            if field not in gt_fields:
                continue
            expected_raw = str(gt_fields[field])
            if _is_unknown_label(field, expected_raw):
                unknown_labels[field] += 1
                continue
            predicted_raw = str(pred_fields.get(field) or "")

            expected = _normalize_text(expected_raw)
            predicted = _normalize_text(predicted_raw)
            flagged = pred_conf.get(field, 0.0) < REVIEW_THRESHOLD

            field_total[field] += 1
            field_cer[field].append(_cer(predicted, expected))
            is_exact = predicted == expected
            if is_exact:
                field_correct[field] += 1
                review_burden[field] += flagged
            else:
                silent_errors[field] += not flagged
                mismatches.append(
                    {
                        "field": field,
                        "expected": expected_raw,
                        "predicted": predicted_raw,
                        "confidence": pred_conf.get(field),
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
        "field_cer_percent": {
            f: round(100 * statistics.mean(v), 1) if v else None for f, v in field_cer.items()
        },
        "text_fields_cer_percent": (
            round(100 * statistics.mean(c for f in TEXT_FIELDS for c in field_cer[f]), 1)
            if any(field_cer[f] for f in TEXT_FIELDS)
            else None
        ),
        "silent_errors": silent_errors,
        "review_burden": review_burden,
        "unknown_labels_skipped": unknown_labels,
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
    print(f"{'idx':>3} {'status':8} {'ms':>6}  {'id':12} {'read':>5} {'flag':>5}  error")
    print("-" * 70)

    records: list[dict] = []
    for idx, img_path in enumerate(images):
        rel = img_path.relative_to(folder)
        rec = run_one(pipeline, img_path)
        records.append({"path": _normalize_rel_path(str(rel)), **rec})

        if rec["status"] == "ok":
            conf = rec.get("confidences", {})
            n_read = sum(1 for f in FIELD_NAMES if conf.get(f, 0) > 0)
            n_flag = sum(1 for f in FIELD_NAMES if 0 < conf.get(f, 0) < REVIEW_THRESHOLD)
            print(
                f"{idx:>3} ok       {rec['elapsed_ms']:>6}  "
                f"{mask_id_number(rec['fields']['id_number']):12} {n_read:>5} {n_flag:>5}"
            )
        else:
            print(f"{idx:>3} {rec['status']:8} {'-':>6}  {'':12} {'':>5} {'':>5}  {rec.get('error_code', '?')}")

    summary = _summarize_records(records)
    n_ok = summary["ok"]
    print()
    print(f"=== Summary: {n_ok}/{summary['images']} ok | lỗi theo mã: {summary['errors_by_code']} ===")
    if summary["total_ms"]:
        print(f"Thời gian (ms) total: {summary['total_ms']}")
        for stage, pct in summary["stage_ms"].items():
            print(f"  {stage:10} {pct}")

    print()
    print(f"{'field':15} {'đọc được (conf>0)':>20} {'bị cảnh báo':>12}")
    for field in FIELD_NAMES:
        cnt = summary["read_count"][field]
        print(
            f"{field:15} {100 * cnt / max(1, n_ok):>12.1f}% ({cnt}/{n_ok})"
            f" {summary['flagged_count'][field]:>8}"
        )
    c = summary["id_consistency"]
    print(
        f"\nSố CCCD: giải mã hợp lệ {c['id_decodable']}/{c['id_checked']} | "
        f"khớp giới tính {c['gender_match']}/{c['cross_checked']} | "
        f"khớp năm sinh {c['birth_year_match']}/{c['cross_checked']}"
        " (giới tính suy từ số CCCD luôn khớp)"
    )

    gt_report: dict | None = None
    if gt_map:
        gt_report = _evaluate_with_ground_truth(records, gt_map)
        print("\n=== Ground-truth evaluation ===")
        print(f"Compared images: {gt_report['compared_images']} (ảnh lỗi tính là sai + đã cảnh báo)")
        text_cer = gt_report["text_fields_cer_percent"]
        print(f"CER họ tên/quê quán/thường trú: {'N/A' if text_cer is None else f'{text_cer}%'}")
        print(
            f"{'field':15} {'exact%':>8} {'đúng/tổng':>10} {'CER%':>6} "
            f"{'sai lọt':>8} {'đúng bị CB':>11} {'nhãn bỏ qua':>12}"
        )
        for field in FIELD_NAMES:
            total = gt_report["field_total"][field]
            acc = gt_report["field_accuracy_percent"][field]
            cer_f = gt_report["field_cer_percent"][field]
            ratio = f"{gt_report['field_correct'][field]}/{total}"
            print(
                f"{field:15} {'N/A' if acc is None else f'{acc:.1f}':>8} "
                f"{ratio:>10} "
                f"{'N/A' if cer_f is None else cer_f:>6} "
                f"{gt_report['silent_errors'][field]:>8} {gt_report['review_burden'][field]:>11} "
                f"{gt_report['unknown_labels_skipped'][field]:>12}"
            )
        print("(sai lọt = sai mà confidence >= ngưỡng cảnh báo; đúng bị CB = đúng nhưng vẫn bị cảnh báo)")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "folder": str(folder),
        "tuning_overrides": tuning_overrides,
        "summary": summary,
        "records": records,
        "ground_truth": {"path": args.ground_truth, "report": gt_report} if gt_map else None,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Detailed results saved to {out_path}")


if __name__ == "__main__":
    main()
