# Tài liệu tham khảo — VieScanner

Tổng hợp các bài báo, dự án mã nguồn mở, model và văn bản pháp lý liên quan tới OCR căn cước công dân (CCCD) / giấy tờ tùy thân. Chỉ giữ các tài liệu phát hành hoặc công bố trong **2024–2026**. Quét ngày 11/10/2026.

**Ký hiệu mức xác minh**

- ✓ — đã mở và đọc trực tiếp trang gốc.
- ◐ — chỉ đọc được phần tóm tắt trong kết quả tìm kiếm (trang chặn truy cập hoặc không mở được); cần kiểm tra lại trước khi trích dẫn.
- *(suy ra)* — nguồn không ghi ngày phát hành; năm được suy ra từ nội dung, ví dụ có hỗ trợ thẻ mẫu 2024 hoặc dùng model ra đời từ 2024 trở về sau.

---

## 1. Nghiên cứu về CCCD/CMND và OCR tiếng Việt

| # | Công trình | Năm | Nội dung chính | Xác minh |
|:-:|---|:-:|---|:-:|
| 1.1 | [A Survey on Vietnamese Document Analysis and Recognition: Challenges and Future Directions](https://arxiv.org/abs/2506.05061) — Anh Le, Thanh Lam, Dung Nguyen | 06/2025 | Tổng quan OCR tài liệu tiếng Việt: dấu thanh phức tạp, thiếu dữ liệu gắn nhãn; đề xuất hướng LLM/VLM | ✓ |
| 1.2 | [Automatic Information Extraction from Student ID Card Images Using DB and VietOCR](https://www.researchgate.net/publication/404301154_Automatic_Information_Extraction_from_Student_ID_Card_Images_Using_DB_and_VietOCR_A_Case_Study_at_a_Vietnamese_University) — Journal of Technical Education Science | 2026 | Phân loại thẻ bằng MobileNetV3-Small, sau đó DB + VietOCR | ◐ |
| 1.3 | [Comprehensive Approach to Vietnamese Scene Text Recognition: Challenges, Models and Framework Development](https://link.springer.com/chapter/10.1007/978-3-032-03527-1_3) — Springer | 2025 | So sánh các model nhận dạng chữ tiếng Việt trong ảnh | ◐ |
| 1.4 | [Vietnamese Scene Text Detection via Edge Information and Text Region Feature Enhancement](https://link.springer.com/chapter/10.1007/978-3-031-78498-9_11) — Springer | 2025 | Module tăng cường biên để không bỏ sót dấu tiếng Việt khi detect | ◐ |

**Nhận xét:**

- Không tìm thấy công trình nào trong 2024–2026 nghiên cứu riêng về CCCD gắn chip hoặc thẻ Căn cước mẫu 2024, kể cả ở RIVF/SoICT/KSE/MAPR. Các bài chuyên về CCCD đều từ năm 2022 trở về trước nên đã bị loại khỏi danh sách.
- Dữ liệu CCCD thật không được công bố vì lý do bảo mật.

---

## 2. Dự án mã nguồn mở về CCCD

| # | Dự án | Năm | Kiến trúc / nội dung | Điểm có thể học | Xác minh |
|:-:|---|:-:|---|---|:-:|
| 2.1 | [Shinoaki0145/VN_ID](https://github.com/Shinoaki0145/VN_ID) | ≥ 2024 *(suy ra: hỗ trợ thẻ mẫu 2024)* | Nắn phối cảnh. Detect bằng DBNet18 (EasyOCR), `canvas_size` 1600 cho cả thẻ và 640 cho vùng MRZ. Nhận dạng bằng VietOCR VGG-Seq2Seq, padding box `pad_y=4, pad_x=2`. QR bằng QReader (YOLOv8 + pyzbar), dự phòng zxing-cpp. MRZ có checksum. Trích xuất bằng regex | Hỗ trợ CCCD 2021 và Căn cước 2024, cả hai mặt. Ghép dữ liệu theo thứ tự QR > mặt trước > mặt sau. Kiểm tra chéo số CCCD với mã tỉnh, giới tính, năm sinh. Không công bố độ chính xác | ✓ |
| 2.2 | [Shinoaki0145/VN-ID-Demo](https://github.com/Shinoaki0145/VN-ID-Demo) | ≥ 2024 *(suy ra)* | Bản demo của 2.1 | — | ◐ |
| 2.3 | [phgrouptechs/scanocr-identity-vi](https://huggingface.co/phgrouptechs/scanocr-identity-vi) — Apache-2.0 | ≥ 2024 *(suy ra: dùng YOLOv11)* | YOLOv11 (ONNX) phát hiện thẳng vùng từng trường (số, tên, ngày sinh, quê quán, thường trú), sau đó VietOCR | Không cần căn 4 góc, không phụ thuộc dòng nhãn. Hỗ trợ CCCD chip, CCCD mã vạch, CMND 9 số. Không công bố số đo | ✓ |
| 2.4 | [Khanhly239/OCR_any_Docs](https://github.com/Khanhly239/OCR_any_Docs) | ≥ 2026 *(suy ra: dùng Chandra 2)* | So sánh 6 engine chạy local: PaddleOCR, Vintern-1B, Chandra 2, EasyOCR, OpenOCR, Marker | Chuẩn hóa Unicode NFC và sửa dấu sau OCR | ◐ |

---

## 3. Căn thẻ / tìm góc thẻ

| # | Công trình | Năm | Ý chính | Xác minh |
|:-:|---|:-:|---|:-:|
| 3.1 | [Synthetic-to-real deep learning for identity card segmentation and line-based geometric rectification](https://www.sciencedirect.com/science/article/pii/S2590123026016014) — ScienceDirect | 2026 | Segmentation thẻ, sau đó tìm 4 cạnh bằng Hough lines để nắn phối cảnh. Bài chỉ ra phương pháp dò góc kém tin cậy với thẻ bo góc. Đánh giá trên MIDV-500/2020 | ◐ |
| 3.2 | [Exploring Light-Weight Object Recognition for Real-Time Document Detection](https://arxiv.org/abs/2509.06246) — Wojcik, Coelho, Granada, Menotti | 09/2025 | Chuyển IWPOD-Net (phát hiện biển số) sang tìm góc thẻ; train trên thẻ tổng hợp NBID, kiểm định trên MIDV. Kết luận: OCR tốt không cần căn thẻ hoàn hảo. Đề xuất đo chất lượng bằng Levenshtein của chữ thay cho IoU. Có code | ✓ |
| 3.3 | [Identity Documents Recognition and Detection using Semantic Segmentation](https://arxiv.org/abs/2503.01085) | 03/2025 | Nhận dạng và phát hiện giấy tờ bằng segmentation | ◐ |
| 3.4 | [MIDV-UP: A Dataset of Pakistani and Iranian ID Documents](https://link.springer.com/chapter/10.1007/978-3-032-04627-7_35) | 2025 | Dataset giấy tờ tùy thân tiếng Urdu và Ba Tư (họ dataset MIDV) | ◐ |

---

## 4. Model OCR / VLM

| # | Model | Năm | Kích thước | Điểm nổi bật | Xác minh |
|:-:|---|:-:|:-:|---|:-:|
| 4.1 | [Vintern-1B: An Efficient Multimodal LLM for Vietnamese](https://arxiv.org/abs/2408.12480) | 08/2024 | 1B | VLM tiếng Việt (InternViT-300M + Qwen2-0.5B), tối ưu cho OCR và trích xuất tài liệu | ✓ |
| 4.2 | [5CD-AI/Vintern-1B-v3_5](https://huggingface.co/5CD-AI/Vintern-1B-v3_5) — MIT | ≥ 2024 | 0,9B | Fine-tune từ InternVL2.5-1B. OCRBench 706, DocVQA 78,8, vi-MTVQA 41,9. Model card không có ví dụ CCCD | ✓ |
| 4.3 | [Vintern-1B-v3.5 — bài giới thiệu trên Viblo](https://viblo.asia/p/vintern-1b-v35-mo-hinh-ket-hop-ocr-va-xu-ly-van-ban-nho-nhe-danh-cho-tieng-viet-AZoJj8WOVY7) | ≥ 2024 *(suy ra)* | — | Hướng dẫn tiếng Việt | ◐ |
| 4.4 | [5CD-AI/Vintern-3B-beta](https://huggingface.co/5CD-AI/Vintern-3B-beta) | ≥ 2024 *(suy ra)* | 3B | Trên vi-MTVQA vượt GPT-4o; OCRBench 619, thấp hơn bản 1B | ◐ |
| 4.5 | [PaddleOCR 3.0 Technical Report](https://arxiv.org/abs/2507.05595) | 07/2025 | — | PP-OCRv5, PP-StructureV3, PP-ChatOCRv4 (trích xuất trường), PaddleOCR-VL-0.9B (109 ngôn ngữ) | ✓ |
| 4.6 | [HunyuanOCR Technical Report](https://arxiv.org/abs/2511.19575) | 11/2025 | 1B | OCR, trích xuất thông tin, VQA; hạng 1 nhóm model nhỏ tại ICDAR 2025 DIMT; không nêu hỗ trợ tiếng Việt | ✓ |
| 4.7 | [Qianfan-OCR](https://arxiv.org/abs/2603.13398) — Baidu, CC-BY-4.0 | 03/2026 | 4B | Điểm trích xuất trường (KIE) cao nhất trên các benchmark công khai; OmniDocBench 93,12 | ✓ |
| 4.8 | [Qwen2.5-VL Technical Report](https://arxiv.org/abs/2502.13923) | 02/2025 | 3–72B | Trích xuất dữ liệu có cấu trúc từ form/hóa đơn | ◐ |
| 4.9 | [Qwen3-VL](https://github.com/qwenlm/qwen3-vl) · [OCR & KIE](https://qwenlm-qwen3-vl.mintlify.app/capabilities/ocr) | 2025 | 2–235B | Có ví dụ trích xuất trường từ giấy tờ tùy thân | ◐ |
| 4.10 | [olmOCR 2](https://arxiv.org/abs/2510.19817) | 10/2025 | 7B | OCR PDF quy mô lớn, Apache-2.0 | ◐ |
| 4.11 | [StrucTexTv3](https://arxiv.org/abs/2405.21013) | 05/2024 | — | VLM cho ảnh nhiều chữ | ◐ |
| 4.12 | [H2OVL-Mississippi](https://arxiv.org/abs/2410.13611) | 10/2024 | 0,8–2B | VLM nhỏ cho OCR | ◐ |
| 4.13 | [So sánh DeepSeek-OCR 2, MinerU2.5-Pro, Chandra OCR 2, dots.mocr](https://www.docsumo.com/blog/best-ocr-models) · [bản khác](https://www.spheron.network/blog/best-open-source-ocr-vlm-self-host-gpu-cloud-2026/) | 2026 | 1,2–5B | Tối ưu cho phân tích trang PDF/tài liệu dài | ◐ |
| 4.14 | [OmniDocBench](https://github.com/opendatalab/OmniDocBench) — CVPR 2025 | 2025 | — | Benchmark phân tích tài liệu | ◐ |

### Benchmark VLM tiếng Việt

| # | Tên | Năm | Xác minh |
|:-:|---|:-:|:-:|
| 4.15 | [ViOCRVQA](https://arxiv.org/abs/2404.18397) — 28k+ ảnh, 120k+ cặp hỏi-đáp về chữ trong ảnh | 04/2024 | ◐ |
| 4.16 | [ViInfographicVQA](https://arxiv.org/abs/2512.12424) | 12/2025 | ◐ |
| 4.17 | [VMMU / ViExam](https://arxiv.org/abs/2508.13680) | 08/2025 | ◐ |
| 4.18 | [SEA-Vision](https://arxiv.org/abs/2603.15409) — benchmark tài liệu và chữ trong ảnh cho Đông Nam Á | 03/2026 | ◐ |

---

## 5. Trích xuất trường (KIE), độ tin cậy, chống ảo giác

| # | Công trình | Năm | Ý chính | Xác minh |
|:-:|---|:-:|---|:-:|
| 5.1 | [Evaluating Structured Information Extraction with Open Models in a High Risk Public Sector Application](https://arxiv.org/abs/2608.18289) — Schubert, Bießmann | 08/2026 | Đánh giá 35 cấu hình OCR+LLM và VLM: chỉ 4 cấu hình đạt F1 > 0,5, khoảng 75% dưới 0,25. VLM nhìn chung tốt hơn. Việc OCR giữ được cấu trúc tài liệu là yếu tố then chốt | ✓ |
| 5.2 | [RaV-IDP: Reconstruction-as-Validation Framework](https://arxiv.org/abs/2604.23644) — Pritesh Jha | 04/2026 | Dựng lại kết quả trích xuất rồi so với vùng ảnh gốc để phát hiện lỗi, thay vì tin confidence của model | ✓ |
| 5.3 | [ConfBench: Can You Trust the Confidence?](https://arxiv.org/html/2608.01792v1) | 08/2026 | Benchmark đo xem confidence của VLM khi trích xuất trường có đáng tin không (1.346 biến thể, hơn 70k đánh giá) | ◐ |
| 5.4 | [UNIKIE-BENCH](https://arxiv.org/abs/2602.07038) — ACL 2026 | 2026 | Benchmark trích xuất trường bằng model đa phương thức | ◐ |
| 5.5 | [KIEval](https://arxiv.org/abs/2503.05488) | 03/2025 | Chỉ số đánh giá trích xuất trường | ◐ |
| 5.6 | [ExtractBench](https://arxiv.org/abs/2607.29677) | 07/2026 | Trích xuất theo schema cho tài liệu doanh nghiệp | ◐ |
| 5.7 | [Identify, Locate, Link (SmolDocling, ICDAR 2026)](https://research.ibm.com/publications/identify-locate-link-end-to-end-key-value-extraction-from-document-images) — IBM | 2026 | VLM 256M trích xuất key-value trực tiếp, không qua OCR | ◐ |
| 5.8 | [Survey on MLLM-based Visually Rich Document Understanding](https://arxiv.org/abs/2507.09861) | 07/2025 | Tổng quan hiểu tài liệu bằng MLLM | ◐ |
| 5.9 | [Hybrid OCR-LLM Framework for Enterprise-Scale Document Information Extraction](https://arxiv.org/abs/2510.10138) | 10/2025 | Kết hợp OCR và LLM | ◐ |
| 5.10 | [Reference-Based Post-OCR Processing with LLM for Precise Diacritic Text](https://arxiv.org/abs/2410.13305) | 10/2024 | Dùng LLM sửa dấu sau OCR | ◐ |

---

## 6. Giả mạo giấy tờ (PAD)

| # | Tài liệu | Năm | Ý chính | Xác minh |
|:-:|---|:-:|---|:-:|
| 6.1 | [From Forgeries to Foundation Models: A Systematic Survey of Identity Document Attack and Detection](https://arxiv.org/abs/2607.01442) — Das, Kumar C, Ramachandra | 07/2026 | Tấn công vật lý, tấn công tiêm ảnh số, ảnh do AI tạo. Model tốt nhất vẫn có APCER trên 25% với thẻ giả do AI tạo. Phát hiện lỗi kiểu chữ khi AI tạo chữ không phải Latin (SDGI) | ✓ |
| 6.2 | [Second Competition on Presentation Attack Detection on ID Card](https://arxiv.org/abs/2507.20404) | 07/2025 | 12.000 ảnh, 24 quốc gia, 155 mẫu thẻ; các kiểu tấn công màn hình, in lại, ghép ảnh | ◐ |
| 6.3 | [SynID: Passport Synthetic Dataset for PAD](https://arxiv.org/abs/2505.07540) | 05/2025 | Hộ chiếu tổng hợp theo chuẩn ICAO | ◐ |
| 6.4 | [SIDTD: Synthetic dataset of ID and Travel Documents](https://arxiv.org/abs/2401.01858) | 01/2024 | Dataset giấy tờ giả lập | ◐ |

---

## 7. Văn bản pháp lý và mẫu thẻ

| # | Văn bản | Năm | Nội dung | Xác minh |
|:-:|---|:-:|---|:-:|
| 7.1 | [Mẫu thẻ Căn cước áp dụng từ 01/07/2024 (Thông tư 16/2024/TT-BCA)](https://baochinhphu.vn/mau-the-can-cuoc-giay-chung-nhan-can-cuoc-moi-ap-dung-tu-1-7-2024-10224062510341914.htm) | 2024 | Mặt sau có QR lớn, nơi cư trú, nơi đăng ký khai sinh, ngày cấp, ngày hết hạn, MRZ | ◐ |
| 7.2 | [Đặc điểm mẫu thẻ căn cước từ 1/7/2024](https://xaydungchinhsach.chinhphu.vn/tu-1-7-mau-the-can-cuoc-mau-giay-chung-nhan-can-cuoc-co-nhung-dac-diem-gi-119240623064056645.htm) | 2024 | Chi tiết bố cục thẻ | ◐ |
| 7.3 | [Luật Bảo vệ dữ liệu cá nhân 2025 (số 91/2025/QH15)](https://thuvienphapluat.vn/van-ban/bo-may-hanh-chinh/Luat-Bao-ve-du-lieu-ca-nhan-2025-so-91-2025-QH15-625628.aspx) | 2025 | Ban hành 26/06/2025, hiệu lực 01/01/2026 | ◐ |
| 7.4 | [06 quyền của chủ thể dữ liệu từ 01/01/2026](https://lsvn.vn/06-quyen-cua-chu-the-du-lieu-theo-luat-bao-ve-du-lieu-ca-nhan-tu-01-01-2026-a162604.html) | 2025 | Quyền được biết, đồng ý/rút đồng ý, xem/sửa, xóa/hạn chế xử lý, phản đối | ◐ |
| 7.5 | [Sử dụng dữ liệu cá nhân sai trái có thể bị phạt đến 3 tỷ đồng](https://lsvn.vn/su-dung-du-lieu-ca-nhan-sai-trai-co-the-bi-phat-den-03-ti-dong-a167866.html) | 2025–2026 | Mức phạt | ◐ |

---

## 8. Đối chiếu với các vấn đề hiện tại của VieScanner (Tầng 2–3)

| Vấn đề | Hướng xử lý trong tài liệu | Tham khảo |
|---|---|---|
| Căn thẻ lỗi/méo ở khoảng 46% ảnh (`aligner.py`) | Segmentation + Hough; IWPOD-Net; hoặc bỏ căn thẻ, phát hiện thẳng vùng trường | 3.1, 3.2, 3.3, 2.3 |
| QR đọc được 1/63 (`qr.py`) | QReader (YOLOv8 + pyzbar), zxing-cpp | 2.1 |
| Extractor phụ thuộc dòng nhãn (`extractor.py`) | YOLO phát hiện vùng trường; VLM trả JSON | 2.3, 4.2, 4.5, 5.1 |
| Kiểm tra số CCCD | Kiểm tra chéo mã tỉnh, giới tính, năm sinh; checksum MRZ | 2.1 |
| Mặt sau / thẻ mẫu 2024 | Parser mặt sau + MRZ | 2.1, 7.1 |
| Sửa dấu sau OCR | Chuẩn hóa NFC; dùng LLM sửa dấu | 2.4, 5.10 |
| Đánh giá độ chính xác | Đo bằng Levenshtein của chữ; KIEval | 3.2, 5.5 |
| Confidence và trường cần kiểm tra lại | Hiệu chỉnh confidence; kiểm tra bằng cách dựng lại | 5.3, 5.2 |
| PII và pháp lý | Luật BVDLCN 2025 | 7.3–7.5 |

> **Lưu ý:** chưa model/dự án nào ở trên được thử trên dữ liệu của VieScanner. Các dự án CCCD mã nguồn mở (2.1, 2.3) đều không công bố độ chính xác nên chưa so sánh trực tiếp được.
