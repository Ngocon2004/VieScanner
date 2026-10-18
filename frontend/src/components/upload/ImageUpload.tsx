"use client";

import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import Logo from "@/components/Logo";
import { UPLOAD_ACCEPT, prepareImageForUpload, uploadKind } from "@/lib/image";

interface ImageUploadProps {
  /** Callback nhận danh sách file (ảnh đã nén/resize, HEIC/PDF giữ nguyên) sẵn sàng upload. */
  onImagesSelect: (files: File[]) => void;
  isLoading: boolean;
  maxFiles?: number;
}

export default function ImageUpload({
  onImagesSelect,
  isLoading,
  maxFiles = 20,
}: ImageUploadProps) {
  const [previews, setPreviews] = useState<{ url: string | null; name: string }[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isPreparing, setIsPreparing] = useState(false);
  const busy = isLoading || isPreparing;
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    return () => {
      for (const p of previews) if (p.url) URL.revokeObjectURL(p.url);
    };
  }, [previews]);

  const readFiles = async (fileList: FileList | File[]) => {
    if (busy) return;
    const all = Array.from(fileList);
    const images = all.filter((f) => uploadKind(f) !== null);
    const otherCount = all.length - images.length;
    if (otherCount > 0) {
      toast.warning("Đã bỏ qua tệp không hợp lệ", {
        description: `${otherCount} tệp không phải JPG, PNG, WebP, HEIC hoặc PDF.`,
      });
    }
    if (images.length === 0) return;

    let selected = images;
    if (selected.length > maxFiles) {
      toast.warning("Vượt quá số lượng cho phép", {
        description: `Chỉ xử lý tối đa ${maxFiles} file mỗi lần. Đã lấy ${maxFiles} file đầu.`,
      });
      selected = selected.slice(0, maxFiles);
    }

    // Nén tuần tự: giải mã song song nhiều ảnh 12MP làm đứng tab và tốn hàng GB RAM.
    setIsPreparing(true);
    try {
      const prepared: File[] = [];
      for (const file of selected) {
        prepared.push(await prepareImageForUpload(file));
      }
      // Người dùng đã reset (component bị remount) trong lúc nén -> bỏ lượt chọn cũ.
      if (!mountedRef.current) return;
      setPreviews(
        prepared.map((f) => ({
          url: uploadKind(f) === "image" ? URL.createObjectURL(f) : null,
          name: f.name,
        })),
      );
      onImagesSelect(prepared);
    } finally {
      if (mountedRef.current) setIsPreparing(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) void readFiles(files);
    e.target.value = "";
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!busy) setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files && files.length > 0) void readFiles(files);
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      aria-busy={busy}
      className={`flex w-full flex-col items-center justify-center rounded-lg border-2 border-dashed p-4 transition-colors sm:p-6 ${
        isDragging
          ? "border-blue-500 bg-blue-50"
          : "border-gray-300 bg-gray-50 hover:bg-gray-100"
      } ${busy ? "cursor-wait opacity-75" : ""}`}
    >
      {previews.length > 0 ? (
        <div className="mb-4 grid w-full max-w-2xl grid-cols-3 gap-2 sm:grid-cols-4">
          {previews.map((p, i) => (
            <div key={`${i}-${p.name}`} className="relative aspect-[1.586/1] overflow-hidden rounded-md border border-gray-200 bg-white">
              {p.url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={p.url} alt={p.name} className="h-full w-full object-cover" />
              ) : (
                <div className="flex h-full w-full items-center justify-center break-all p-1 text-center text-[10px] text-gray-500">
                  {p.name}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <Logo className="mb-4 h-16 w-16 opacity-60" />
      )}

      <label className={`w-full max-w-xs ${busy ? "cursor-wait" : "cursor-pointer"}`}>
        <span
          className={`block rounded-md px-4 py-2 text-center text-white ${
            busy ? "bg-gray-400" : "bg-blue-600 hover:bg-blue-700"
          }`}
        >
          {isPreparing
            ? "Đang chuẩn bị ảnh..."
            : isLoading
              ? "Đang xử lý..."
              : previews.length > 0
                ? `Đã chọn ${previews.length} ảnh - chọn lại`
                : "Tải ảnh hoặc PDF CCCD lên (có thể chọn nhiều)"}
        </span>
        <input
          type="file"
          className="hidden"
          accept={UPLOAD_ACCEPT}
          multiple
          onChange={handleFileChange}
          disabled={busy}
        />
      </label>
      <p className="mt-2 text-center text-xs text-gray-500 sm:text-sm">
        Kéo thả hoặc chọn tối đa {maxFiles} file. Hỗ trợ JPG, PNG, WebP, HEIC và PDF (mỗi trang là một ảnh).
      </p>
    </div>
  );
}
