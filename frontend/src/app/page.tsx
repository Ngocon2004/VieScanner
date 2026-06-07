"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import CCCDForm from "@/components/form/CCCDForm";
import ImageUpload from "@/components/upload/ImageUpload";
import BatchResultPanel from "@/components/batch/BatchResultPanel";
import Navbar from "@/components/Navbar";
import { useBatchExtract } from "@/hooks/useBatchExtract";
import { useExportExcel } from "@/hooks/useExportExcel";
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

  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const summaryTokenRef = useRef<string | null>(null);
  const batchErrorTokenRef = useRef<string | null>(null);
  const exportErrorTokenRef = useRef<string | null>(null);

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
    const needsReview = batch.items.length - extractedCount;
    if (extractedCount > 0) {
      toast.success("Hoàn tất xử lý", {
        description: `${extractedCount} ảnh trích xuất thành công, ${needsReview} ảnh cần xem lại.`,
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

  const handleImagesSelect = (files: File[]) => {
    setSelectedIndex(null);
    void batch.run(files);
  };

  const handleReset = () => {
    setSelectedIndex(null);
    batch.reset();
  };

  // Mặc định chọn ảnh đạt đầu tiên; user có thể bấm chọn ảnh khác (derived state,
  // tránh setState trong effect).
  const firstExtractedIndex = useMemo(() => {
    const found = batch.items.find((i) => i.status === "extracted");
    return found ? found.originalIndex : null;
  }, [batch.items]);

  const effectiveIndex = selectedIndex ?? firstExtractedIndex;

  const selectedItem =
    effectiveIndex === null
      ? null
      : batch.items.find(
          (i) => i.originalIndex === effectiveIndex && i.status === "extracted" && i.data,
        ) ?? null;

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

      <main className="flex-grow container mx-auto px-4 py-8 max-w-4xl">
        {!user && (
          <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg text-blue-800 text-sm flex flex-col sm:flex-row justify-between items-center gap-2">
            <p>Đăng nhập để lưu lịch sử scan và quản lý bản ghi CCCD.</p>
            <Link href="/login" className="font-bold underline whitespace-nowrap">Đăng nhập ngay</Link>
          </div>
        )}

        <div className="space-y-6 sm:space-y-8">
          <header className="flex flex-col items-center text-center">
            <h1 className="text-3xl font-extrabold text-blue-900 sm:text-4xl mb-2">
              Trích xuất thông tin CCCD
            </h1>
            <p className="max-w-xl text-sm italic text-gray-600 sm:text-base">
              Tải lên một hoặc nhiều ảnh mặt trước. Hệ thống tự lọc ảnh đạt/không đạt tiêu chuẩn rồi trích xuất.
            </p>
          </header>

          <section className="w-full rounded-xl border border-gray-200 bg-white p-4 shadow-lg sm:p-8">
            <h2 className="mb-4 text-xl font-semibold text-gray-700 sm:mb-6 sm:text-2xl">
              Bước 1: Tải ảnh thẻ
            </h2>
            <ImageUpload
              onImagesSelect={handleImagesSelect}
              isLoading={batch.loading}
            />

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
              <BatchResultPanel
                items={batch.items}
                selectedIndex={effectiveIndex}
                onSelect={(item) => setSelectedIndex(item.originalIndex)}
              />

              {selectedItem && selectedItem.data && (
                <div className="space-y-3">
                  <h2 className="text-xl font-semibold text-gray-700 sm:text-2xl">
                    Bước 3: Kiểm tra & Xuất file ({selectedItem.filename})
                  </h2>
                  <CCCDForm
                    key={selectedItem.originalIndex}
                    initialData={selectedItem.data}
                    confidences={selectedItem.confidences}
                    onExport={(data) =>
                      exporter.exportData(data, selectedItem.scanId ?? undefined)
                    }
                    isExporting={exporter.loading}
                    exportError={exporter.error}
                  />
                </div>
              )}

              <div className="text-center">
                <button
                  type="button"
                  onClick={handleReset}
                  className="text-blue-600 hover:text-blue-800 font-medium underline"
                >
                  Tải lên ảnh khác
                </button>
              </div>
            </section>
          )}
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
