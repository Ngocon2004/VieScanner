"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import ImageUpload from "@/components/upload/ImageUpload";
import CameraScanner from "@/components/scan/CameraScanner";
import BatchResultPanel from "@/components/batch/BatchResultPanel";
import CCCDListTable from "@/components/list/CCCDListTable";
import Navbar from "@/components/Navbar";
import { useBatchExtract } from "@/hooks/useBatchExtract";
import { useCccdList } from "@/hooks/useCccdList";
import { useExportExcel } from "@/hooks/useExportExcel";
import { getOcrEngine, type JobSource } from "@/lib/api";
import { rowFromResult, toExportRows } from "@/lib/cccdList";
import { useAuth } from "./AuthContext";

function BatchSkeleton() {
  return (
    <section className="animate-pulse space-y-4">
      <div className="h-16 rounded-lg bg-gray-200" />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, idx) => (
          <div key={idx} className="h-24 rounded-md bg-gray-100" />
        ))}
      </div>
    </section>
  );
}

export default function Home() {
  const { user, loading: authLoading } = useAuth();
  const batch = useBatchExtract();
  const exporter = useExportExcel();
  const list = useCccdList();
  const { addRows } = list;
  const importedRef = useRef<Set<string>>(new Set());
  const [uploadKey, setUploadKey] = useState(0);
  const [inputMode, setInputMode] = useState<JobSource>("upload");
  const [ocrEngine, setOcrEngine] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void getOcrEngine(controller.signal).then(setOcrEngine);
    return () => controller.abort();
  }, []);

  const summaryTokenRef = useRef<string | null>(null);
  const batchErrorTokenRef = useRef<string | null>(null);
  const exportErrorTokenRef = useRef<string | null>(null);

  // Ảnh trích xuất xong được thêm ngay vào danh sách (mỗi ảnh 1 lần), kể cả khi job còn đang chạy.
  useEffect(() => {
    if (!batch.jobId) return;
    const fresh = batch.items.filter(
      (item) =>
        item.status === "extracted" &&
        item.data &&
        !importedRef.current.has(`${batch.jobId}:${item.originalIndex}`),
    );
    if (fresh.length === 0) return;
    for (const item of fresh) importedRef.current.add(`${batch.jobId}:${item.originalIndex}`);
    addRows(
      fresh.map((item) =>
        rowFromResult(
          item.data!,
          item.confidences,
          item.scanId,
          item.filename,
          (item.quality?.issues ?? []).map((issue) => issue.code),
        ),
      ),
    );
  }, [batch.jobId, batch.items, addRows]);

  // Reset token tóm tắt khi bắt đầu lần xử lý mới.
  useEffect(() => {
    if (batch.loading) summaryTokenRef.current = null;
  }, [batch.loading]);

  // Toast tóm tắt + auto chọn ảnh đạt đầu tiên khi xử lý xong.
  useEffect(() => {
    if (batch.loading || batch.items.length === 0) return;
    const token = `${batch.items.length}|${batch.acceptedCount}|${batch.rejectedCount}`;
    if (token === summaryTokenRef.current) return;
    summaryTokenRef.current = token;

    const extractedCount = batch.items.filter((i) => i.status === "extracted").length;
    const needsReview = batch.rejectedCount;
    if (extractedCount > 0) {
      toast.success("Hoàn tất xử lý", {
        description: `${extractedCount} ảnh đã thêm vào danh sách, ${needsReview} ảnh cần chụp lại.`,
      });
    } else {
      toast.error("Không có ảnh đạt tiêu chuẩn", {
        description: `${needsReview} ảnh cần xem lại. Vui lòng chụp lại theo hướng dẫn.`,
      });
    }
  }, [batch.items, batch.loading, batch.acceptedCount, batch.rejectedCount]);

  useEffect(() => {
    if (!batch.error) {
      batchErrorTokenRef.current = null;
      return;
    }
    const token = `${batch.error.code}:${batch.error.message}:${batch.error.requestId ?? ""}`;
    if (token === batchErrorTokenRef.current) return;
    batchErrorTokenRef.current = token;
    toast.error("Xử lý thất bại", {
      description: batch.error.requestId
        ? `${batch.error.message} (request_id: ${batch.error.requestId})`
        : batch.error.message,
    });
  }, [batch.error]);

  useEffect(() => {
    if (!exporter.error) {
      exportErrorTokenRef.current = null;
      return;
    }
    const token = `${exporter.error.code}:${exporter.error.message}:${exporter.error.requestId ?? ""}`;
    if (token === exportErrorTokenRef.current) return;
    exportErrorTokenRef.current = token;
    toast.error("Xuất Excel thất bại", {
      description: exporter.error.requestId
        ? `${exporter.error.message} (request_id: ${exporter.error.requestId})`
        : exporter.error.message,
    });
  }, [exporter.error]);

  useEffect(() => {
    if (exporter.successCount <= 0) return;
    toast.success("Xuất Excel thành công", {
      description: "File .xlsx đã được tải về máy của bạn.",
    });
  }, [exporter.successCount]);

  const handleImagesSelect = (files: File[], source: JobSource = "upload") => {
    void batch.run(files, source);
  };

  const handleReset = () => {
    setUploadKey((k) => k + 1);
    batch.reset();
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-100">
      <Navbar />

      <main className="flex-grow container mx-auto px-4 py-8 max-w-6xl">
        {!user && (
          <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg text-blue-800 text-sm flex flex-col sm:flex-row justify-between items-center gap-2">
            <p>Đăng nhập để lưu lịch sử scan và quản lý bản ghi CCCD.</p>
            <Link href="/login" className="font-bold underline whitespace-nowrap">Đăng nhập ngay</Link>
          </div>
        )}

        {ocrEngine === "mock" && (
          <div role="alert" className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
            <p className="font-semibold">Server đang chạy chế độ thử (OCR_ENGINE=mock)</p>
            <p>Kết quả quét là dữ liệu mẫu cố định, không đọc từ ảnh. Đặt OCR_ENGINE=real cho backend để đọc CCCD thật.</p>
          </div>
        )}

        <div className="space-y-6 sm:space-y-8">
          <header className="flex flex-col items-center text-center">
            <h1 className="text-3xl font-extrabold text-blue-900 sm:text-4xl mb-2">
              Trích xuất thông tin CCCD
            </h1>
            <p className="max-w-xl text-sm italic text-gray-600 sm:text-base">
              Tải ảnh/PDF hoặc quét bằng camera mặt trước CCCD. Hệ thống tự lọc ảnh đạt/không đạt tiêu chuẩn rồi trích xuất.
            </p>
          </header>

          <section className="w-full rounded-xl border border-gray-200 bg-white p-4 shadow-lg sm:p-8">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 sm:mb-6">
              <h2 className="text-xl font-semibold text-gray-700 sm:text-2xl">
                Bước 1: Đưa ảnh thẻ vào
              </h2>
              <div role="tablist" className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1 text-sm">
                {(
                  [
                    ["upload", "Tải file"],
                    ["camera", "Quét camera"],
                  ] as const
                ).map(([mode, label]) => (
                  <button
                    key={mode}
                    type="button"
                    role="tab"
                    aria-selected={inputMode === mode}
                    onClick={() => setInputMode(mode)}
                    disabled={batch.loading}
                    className={`rounded-md px-3 py-1.5 font-medium ${
                      inputMode === mode ? "bg-white text-blue-700 shadow" : "text-gray-600"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {inputMode === "upload" ? (
              <ImageUpload
                key={uploadKey}
                onImagesSelect={(files) => handleImagesSelect(files, "upload")}
                isLoading={batch.loading}
              />
            ) : (
              <CameraScanner
                onSubmit={(files) => handleImagesSelect(files, "camera")}
                isLoading={batch.loading}
              />
            )}

            {batch.loading && batch.progress && (
              <div className="mt-4 space-y-2" aria-live="polite">
                <div className="flex items-center justify-between text-sm text-gray-600">
                  <span>
                    Đang xử lý {batch.progress.processed}/{batch.progress.total} ảnh
                  </span>
                  <button
                    type="button"
                    onClick={batch.cancel}
                    className="font-medium text-red-600 underline hover:text-red-800"
                  >
                    Hủy
                  </button>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-gray-200">
                  <div
                    className="h-full bg-blue-600 transition-all"
                    style={{
                      width: `${batch.progress.total ? (batch.progress.processed / batch.progress.total) * 100 : 0}%`,
                    }}
                  />
                </div>
              </div>
            )}

            {batch.error && (
              <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-red-700 sm:p-4">
                <div className="break-words font-semibold">{batch.error.message}</div>
                {batch.error.requestId && (
                  <div className="mt-1 break-all text-xs text-red-500">
                    request_id: {batch.error.requestId}
                  </div>
                )}
              </div>
            )}
          </section>

          {batch.loading && batch.items.length === 0 && <BatchSkeleton />}

          {batch.items.length > 0 && (
            <section className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
              <h2 className="text-xl font-semibold text-gray-700 sm:text-2xl">
                Bước 2: Kết quả phân loại
              </h2>
              <BatchResultPanel items={batch.items} />

              <div className="text-center">
                <button
                  type="button"
                  onClick={handleReset}
                  className="text-blue-600 hover:text-blue-800 font-medium underline"
                >
                  Quét tiếp ảnh khác
                </button>
              </div>
            </section>
          )}

          <section className="space-y-3">
            <h2 className="text-xl font-semibold text-gray-700 sm:text-2xl">
              Bước 3: Danh sách đã quét &amp; xuất Excel
            </h2>
            <CCCDListTable
              rows={list.rows}
              onUpdate={list.updateField}
              onMarkReviewed={list.markReviewed}
              onMerge={list.mergeRows}
              onRemove={list.removeRow}
              onAdd={list.addEmpty}
              onClear={list.clear}
              onExport={() => exporter.exportRows(toExportRows(list.rows))}
              isExporting={exporter.loading}
              exportError={exporter.error}
            />
          </section>
        </div>
      </main>

      <footer className="py-6 border-t bg-white mt-auto">
        <div className="container mx-auto px-4 text-center text-gray-400 text-sm italic">
          &copy; {new Date().getFullYear()} VieScanner - Hệ thống OCR CCCD Việt Nam
        </div>
      </footer>
    </div>
  );
}
