"use client";

import React, { useEffect, useRef } from "react";
import { toast } from "sonner";

import CCCDForm from "@/components/form/CCCDForm";
import Logo from "@/components/Logo";
import ImageUpload from "@/components/upload/ImageUpload";
import { useExportExcel } from "@/hooks/useExportExcel";
import { useExtractCCCD } from "@/hooks/useExtractCCCD";

function OCRResultSkeleton() {
  return (
    <section className="animate-pulse">
      <div className="mb-4 h-8 w-40 max-w-full rounded bg-gray-200 sm:mb-6 sm:w-64" />
      <div className="w-full space-y-4 rounded-lg bg-white p-4 shadow-md sm:p-6">
        <div className="h-7 w-36 max-w-full rounded bg-gray-200 sm:w-48" />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {Array.from({ length: 8 }).map((_, idx) => (
            <div key={idx} className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="h-4 w-24 rounded bg-gray-200" />
                <div className="h-5 w-14 rounded-full bg-gray-100" />
              </div>
              <div className="h-10 rounded-md bg-gray-100" />
            </div>
          ))}
        </div>
        <div className="flex justify-end pt-4">
          <div className="h-10 w-36 rounded-md bg-gray-200" />
        </div>
      </div>
    </section>
  );
}

export default function Home() {
  const extractor = useExtractCCCD();
  const exporter = useExportExcel();
  const lastExtractSuccessTokenRef = useRef<string | null>(null);
  const lastExtractErrorTokenRef = useRef<string | null>(null);
  const lastExportErrorTokenRef = useRef<string | null>(null);

  useEffect(() => {
    if (!extractor.error) {
      lastExtractErrorTokenRef.current = null;
      return;
    }

    const token = `${extractor.error.code}:${extractor.error.message}:${extractor.error.requestId ?? ""}`;
    if (token === lastExtractErrorTokenRef.current) return;
    lastExtractErrorTokenRef.current = token;

    toast.error("OCR thất bại", {
      description: extractor.error.requestId
        ? `${extractor.error.message} (request_id: ${extractor.error.requestId})`
        : extractor.error.message,
    });
  }, [extractor.error]);

  useEffect(() => {
    if (!extractor.data) return;

    const token = `${extractor.data.id_number}|${extractor.data.full_name}|${extractor.data.dob}`;
    if (token === lastExtractSuccessTokenRef.current) return;
    lastExtractSuccessTokenRef.current = token;

    toast.success("OCR hoàn tất", {
      description:
        "Kiểm tra các ô có độ tin cậy thấp trước khi xuất Excel.",
    });
  }, [extractor.data]);

  useEffect(() => {
    if (!exporter.error) {
      lastExportErrorTokenRef.current = null;
      return;
    }

    const token = `${exporter.error.code}:${exporter.error.message}:${exporter.error.requestId ?? ""}`;
    if (token === lastExportErrorTokenRef.current) return;
    lastExportErrorTokenRef.current = token;

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

  return (
    <main className="min-h-screen overflow-x-hidden bg-gray-100 px-3 py-8 sm:px-4 sm:py-12">
      <div className="mx-auto max-w-4xl space-y-6 sm:space-y-8">
        <header className="flex flex-col items-center text-center">
          <div className="mb-2 flex flex-col items-center gap-2 sm:flex-row sm:gap-3">
            <Logo className="h-12 w-12" />
            <h1 className="text-3xl font-extrabold text-blue-900 sm:text-4xl">
              VieScanner
            </h1>
          </div>
          <p className="max-w-xl text-sm italic text-gray-600 sm:text-base">
            Trích xuất thông tin CCCD Việt Nam sang Excel trong nháy mắt
          </p>
        </header>

        <section className="w-full rounded-xl border border-gray-200 bg-white p-4 shadow-lg sm:p-8">
          <h2 className="mb-4 text-xl font-semibold text-gray-700 sm:mb-6 sm:text-2xl">
            Bước 1: Tải ảnh CCCD
          </h2>
          <ImageUpload
            onImageSelect={extractor.extract}
            isLoading={extractor.loading}
          />

          {extractor.error && (
            <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-red-700 sm:p-4">
              <div className="break-words font-semibold">{extractor.error.message}</div>
              {extractor.error.requestId && (
                <div className="mt-1 break-all text-xs text-red-500">
                  request_id: {extractor.error.requestId}
                </div>
              )}
            </div>
          )}
        </section>

        {extractor.loading && !extractor.data && <OCRResultSkeleton />}

        {extractor.data && (
          <section className="animate-in fade-in slide-in-from-bottom-4 duration-500">
            <h2 className="mb-4 text-xl font-semibold text-gray-700 sm:mb-6 sm:text-2xl">
              Bước 2: Kiểm tra & Xuất file
            </h2>
            <CCCDForm
              key={extractor.data.id_number}
              initialData={extractor.data}
              confidences={extractor.confidences}
              onExport={exporter.exportData}
              isExporting={exporter.loading}
              exportError={exporter.error}
            />
          </section>
        )}
      </div>
    </main>
  );
}
