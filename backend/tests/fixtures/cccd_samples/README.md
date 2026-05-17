# CCCD Samples (Local Only)

Folder này dùng cho Phase 2.7 tuning/eval với ảnh CCCD thực.

- Không commit ảnh CCCD thật (PII).
- Không commit ground-truth thật.
- Chỉ giữ `.gitkeep` và `ground_truth.template.json` làm mẫu cấu trúc.

Ví dụ chạy eval:

```powershell
cd backend
venv\Scripts\python.exe scripts\eval_ocr.py tests/fixtures/cccd_samples `
  --ground-truth tests/fixtures/cccd_samples/ground_truth.json `
  --detector-padding 6 `
  --detector-conf-threshold 0.35 `
  --recognizer-beamsearch false `
  --extractor-fuzzy-threshold 85 `
  --out scripts/eval_results.json
```

Ví dụ chạy grid tuning:

```powershell
cd backend
venv\Scripts\python.exe scripts\tune_ocr_grid.py tests/fixtures/cccd_samples `
  --ground-truth tests/fixtures/cccd_samples/ground_truth.json `
  --detector-padding-grid 4,6 `
  --detector-conf-grid 0.25,0.30,0.35 `
  --beamsearch-grid true,false `
  --fuzzy-grid 80,85 `
  --out scripts/tune_results.json
```
