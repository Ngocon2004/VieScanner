"""Grid tuning script for OCR Phase 2.7.

Run many parameter combinations on the same image set + ground truth and rank
the best config for demo accuracy targets.

Usage:
    cd backend
    venv\\Scripts\\python.exe scripts\\tune_ocr_grid.py tests/fixtures/cccd_samples \
      --ground-truth tests/fixtures/cccd_samples/ground_truth.json \
      --detector-padding-grid 4,6 \
      --detector-conf-grid 0.25,0.30,0.35 \
      --beamsearch-grid true,false \
      --out scripts/tune_results.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

# UTF-8 for Windows console.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

# Allow importing app/* when running as a script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.services.ocr_engine import _build_real_pipeline  # noqa: E402
import eval_ocr as eo  # noqa: E402


@dataclass(frozen=True, slots=True)
class TuneConfig:
    aligner_conf_threshold: float
    cleaner_shadow_kernel_size: int
    cleaner_clip_hist_percent: float
    detector_conf_threshold: float
    detector_padding: int
    recognizer_beamsearch: bool
    extractor_fuzzy_threshold: int


def _parse_csv_floats(raw: str | None, default: float) -> list[float]:
    if not raw:
        return [float(default)]
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def _parse_csv_ints(raw: str | None, default: int) -> list[int]:
    if not raw:
        return [int(default)]
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _parse_csv_bools(raw: str | None, default: bool) -> list[bool]:
    if not raw:
        return [bool(default)]
    return [eo._parse_bool(x.strip()) for x in raw.split(",") if x.strip()]


def _collect_images(folder: Path, patterns: str, limit: int) -> list[Path]:
    images: list[Path] = []
    for pat in patterns.split(","):
        images.extend(folder.rglob(pat.strip()))
    images = sorted(images)
    if limit > 0:
        images = images[:limit]
    return images


def _apply_config(cfg: TuneConfig, debug_save: bool) -> None:
    settings.ocr_aligner_conf_threshold = cfg.aligner_conf_threshold
    settings.ocr_cleaner_shadow_kernel_size = cfg.cleaner_shadow_kernel_size
    settings.ocr_cleaner_clip_hist_percent = cfg.cleaner_clip_hist_percent
    settings.ocr_detector_conf_threshold = cfg.detector_conf_threshold
    settings.ocr_detector_padding = cfg.detector_padding
    settings.ocr_recognizer_beamsearch = cfg.recognizer_beamsearch
    settings.ocr_extractor_fuzzy_threshold = cfg.extractor_fuzzy_threshold
    settings.ocr_debug_save = debug_save


def _evaluate_combo(
    cfg: TuneConfig,
    images: list[Path],
    folder: Path,
    gt_map: dict[str, dict[str, str]],
    debug_save: bool,
) -> dict:
    _apply_config(cfg, debug_save=debug_save)

    build_t0 = time.perf_counter()
    pipeline = _build_real_pipeline()
    build_ms = round((time.perf_counter() - build_t0) * 1000, 2)

    records: list[dict] = []
    run_t0 = time.perf_counter()
    for img_path in images:
        rel = img_path.relative_to(folder)
        rec = eo.run_one(pipeline, img_path)
        records.append({"path": eo._normalize_rel_path(str(rel)), **rec})
    eval_ms = round((time.perf_counter() - run_t0) * 1000, 2)

    n_total = len(records)
    n_ok = sum(1 for r in records if r.get("status") == "ok")
    n_failed = sum(1 for r in records if r.get("status") == "failed")
    n_error = sum(1 for r in records if r.get("status") == "error")
    success_percent = 100.0 * n_ok / max(1, n_total)

    gt_report = eo._evaluate_with_ground_truth(records, gt_map) if gt_map else None

    # Exact per-image if all fields exactly match gt.
    perfect_percent = None
    if gt_report:
        compared = int(gt_report["compared_images"])
        errors = len(gt_report["image_errors"])
        perfect_count = max(0, compared - errors)
        perfect_percent = (100.0 * perfect_count / compared) if compared else None

    summary = {
        "config": asdict(cfg),
        "build_ms": build_ms,
        "eval_ms": eval_ms,
        "counts": {
            "total": n_total,
            "ok": n_ok,
            "failed": n_failed,
            "error": n_error,
        },
        "success_percent": success_percent,
        "perfect_percent": perfect_percent,
        "ground_truth_report": gt_report,
    }
    return summary


def _field_acc(gt_report: dict | None, field: str) -> float:
    if not gt_report:
        return -1.0
    value = gt_report["field_accuracy_percent"].get(field)
    return -1.0 if value is None else float(value)


def _avg_field_acc(gt_report: dict | None) -> float:
    if not gt_report:
        return -1.0
    vals = [
        float(v)
        for v in gt_report["field_accuracy_percent"].values()
        if v is not None
    ]
    return (sum(vals) / len(vals)) if vals else -1.0


def _cer(gt_report: dict | None) -> float:
    if not gt_report or gt_report["cer_percent"] is None:
        return 1e9
    return float(gt_report["cer_percent"])


def _wer(gt_report: dict | None) -> float:
    if not gt_report or gt_report["wer_percent"] is None:
        return 1e9
    return float(gt_report["wer_percent"])


def _meets_demo_thresholds(summary: dict) -> bool:
    gt = summary.get("ground_truth_report")
    if not gt:
        return False
    acc = gt["field_accuracy_percent"]
    id_ok = (acc.get("id_number") or 0.0) >= 90.0
    name_ok = (acc.get("full_name") or 0.0) >= 80.0
    others = [
        "dob",
        "gender",
        "nationality",
        "origin",
        "residence",
        "expiry_date",
    ]
    others_ok = all((acc.get(f) or 0.0) >= 70.0 for f in others)
    perfect_ok = (summary.get("perfect_percent") or 0.0) >= 60.0
    return id_ok and name_ok and others_ok and perfect_ok


def _ranking_key(summary: dict) -> tuple:
    gt = summary.get("ground_truth_report")
    return (
        1 if _meets_demo_thresholds(summary) else 0,
        round(summary.get("perfect_percent") or -1.0, 3),
        round(_field_acc(gt, "id_number"), 3),
        round(_field_acc(gt, "full_name"), 3),
        round(_avg_field_acc(gt), 3),
        round(summary.get("success_percent") or -1.0, 3),
        -round(_cer(gt), 3),
        -round(_wer(gt), 3),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grid tuning OCR parameters and rank best config by ground truth."
    )
    parser.add_argument("folder", help="Folder chứa ảnh CCCD.")
    parser.add_argument("--ground-truth", required=True, help="Path ground-truth JSON.")
    parser.add_argument("--out", default="scripts/tune_results.json", help="File JSON output.")
    parser.add_argument("--patterns", default="*.jpg,*.jpeg,*.png", help="CSV file patterns.")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số ảnh (0 = all).")
    parser.add_argument("--max-runs", type=int, default=0, help="Giới hạn số combo chạy (0 = all).")
    parser.add_argument("--top-k", type=int, default=5, help="In top K cấu hình.")
    parser.add_argument("--debug-save", action="store_true", help="Bật OCR_DEBUG_SAVE khi tuning.")

    parser.add_argument("--aligner-conf-grid", default="", help="CSV, ví dụ: 0.2,0.25,0.3")
    parser.add_argument("--cleaner-shadow-grid", default="", help="CSV, ví dụ: 5,7,9")
    parser.add_argument("--cleaner-clip-grid", default="", help="CSV, ví dụ: 0.5,1.0,1.5")
    parser.add_argument("--detector-conf-grid", default="", help="CSV, ví dụ: 0.25,0.30,0.35")
    parser.add_argument("--detector-padding-grid", default="", help="CSV, ví dụ: 2,4,6")
    parser.add_argument("--beamsearch-grid", default="", help="CSV bool, ví dụ: true,false")
    parser.add_argument("--fuzzy-grid", default="", help="CSV, ví dụ: 75,80,85")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"[ERR] Folder không tồn tại: {folder}", file=sys.stderr)
        sys.exit(1)

    gt_path = Path(args.ground_truth)
    if not gt_path.exists():
        print(f"[ERR] Ground-truth không tồn tại: {gt_path}", file=sys.stderr)
        sys.exit(1)

    images = _collect_images(folder, args.patterns, args.limit)
    if not images:
        print(f"[ERR] Không tìm thấy ảnh trong {folder}", file=sys.stderr)
        sys.exit(1)

    gt_map = eo._load_ground_truth(gt_path)

    aligner_grid = _parse_csv_floats(args.aligner_conf_grid, settings.ocr_aligner_conf_threshold)
    shadow_grid = _parse_csv_ints(args.cleaner_shadow_grid, settings.ocr_cleaner_shadow_kernel_size)
    clip_grid = _parse_csv_floats(args.cleaner_clip_grid, settings.ocr_cleaner_clip_hist_percent)
    det_conf_grid = _parse_csv_floats(args.detector_conf_grid, settings.ocr_detector_conf_threshold)
    det_pad_grid = _parse_csv_ints(args.detector_padding_grid, settings.ocr_detector_padding)
    beam_grid = _parse_csv_bools(args.beamsearch_grid, settings.ocr_recognizer_beamsearch)
    fuzzy_grid = _parse_csv_ints(args.fuzzy_grid, settings.ocr_extractor_fuzzy_threshold)

    combos = [
        TuneConfig(*items)
        for items in itertools.product(
            aligner_grid,
            shadow_grid,
            clip_grid,
            det_conf_grid,
            det_pad_grid,
            beam_grid,
            fuzzy_grid,
        )
    ]
    if args.max_runs > 0:
        combos = combos[: args.max_runs]

    print(f"=== Grid size: {len(combos)} configs | images: {len(images)} ===")
    run_summaries: list[dict] = []
    all_t0 = time.perf_counter()
    for idx, cfg in enumerate(combos, start=1):
        print(
            f"[{idx:>3}/{len(combos)}] cfg="
            f"align={cfg.aligner_conf_threshold},"
            f"shadow={cfg.cleaner_shadow_kernel_size},"
            f"clip={cfg.cleaner_clip_hist_percent},"
            f"det_conf={cfg.detector_conf_threshold},"
            f"det_pad={cfg.detector_padding},"
            f"beam={cfg.recognizer_beamsearch},"
            f"fuzzy={cfg.extractor_fuzzy_threshold}"
        )
        summary = _evaluate_combo(
            cfg=cfg,
            images=images,
            folder=folder,
            gt_map=gt_map,
            debug_save=args.debug_save,
        )
        run_summaries.append(summary)
        gt = summary["ground_truth_report"]
        id_acc = _field_acc(gt, "id_number")
        name_acc = _field_acc(gt, "full_name")
        print(
            f"      ok={summary['counts']['ok']}/{summary['counts']['total']} "
            f"perfect={summary['perfect_percent'] if summary['perfect_percent'] is not None else 'N/A'} "
            f"id_acc={id_acc if id_acc >= 0 else 'N/A'} "
            f"name_acc={name_acc if name_acc >= 0 else 'N/A'}"
        )

    ranked = sorted(run_summaries, key=_ranking_key, reverse=True)
    best = ranked[0] if ranked else None
    elapsed_sec = round(time.perf_counter() - all_t0, 2)

    print()
    print(f"=== Done in {elapsed_sec}s ===")
    print(f"Top {min(args.top_k, len(ranked))} configs:")
    for i, item in enumerate(ranked[: args.top_k], start=1):
        cfg = item["config"]
        print(
            f"{i:>2}. pass_demo={_meets_demo_thresholds(item)} "
            f"perfect={item['perfect_percent']} success={item['success_percent']:.1f}% "
            f"id={_field_acc(item['ground_truth_report'], 'id_number'):.1f} "
            f"name={_field_acc(item['ground_truth_report'], 'full_name'):.1f} "
            f"cfg={cfg}"
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "folder": str(folder),
        "ground_truth": str(gt_path),
        "images": len(images),
        "grid": {
            "aligner_conf_threshold": aligner_grid,
            "cleaner_shadow_kernel_size": shadow_grid,
            "cleaner_clip_hist_percent": clip_grid,
            "detector_conf_threshold": det_conf_grid,
            "detector_padding": det_pad_grid,
            "recognizer_beamsearch": beam_grid,
            "extractor_fuzzy_threshold": fuzzy_grid,
        },
        "elapsed_sec": elapsed_sec,
        "best": best,
        "ranked": ranked,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[OK] Saved tuning results -> {out_path}")


if __name__ == "__main__":
    main()
