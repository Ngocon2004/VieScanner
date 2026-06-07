"use client";

import React, { useEffect, useState } from "react";
import { toast } from "sonner";

import Logo from "@/components/Logo";
import { prepareImageForUpload } from "@/lib/image";

interface ImageUploadProps {
  /** Callback nhận danh sách ảnh (đã nén/resize) sẵn sàng upload. */
  onImagesSelect: (files: File[]) => void;
  isLoading: boolean;
  maxFiles?: number;
}

export default function ImageUpload({
  onImagesSelect,
  isLoading,
  maxFiles = 20,
}: ImageUploadProps) {
  const [previews, setPreviews] = useState<{ url: string; name: string }[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  // Revoke object URLs khi previews đổi/unmount.
  useEffect(() => {
    return () => {
      for (const p of previews) URL.revokeObjectURL(p.url);
    };
  }, [previews]);

  const readFiles = async (fileList: FileList | File[]) => {
    const all = Array.from(fileList);
    const images = all.filter((f) => f.type.startsWith("image/"));
    const skipped = all.length - images.length;
    if (skipped > 0) {
      toast.warning("Đã bỏ qua tệp không hợp lệ", {
        description: `${skipped} tệp không phải ảnh (chỉ nhận JPG, PNG, WebP).`,
      });
    }
    if (images.length === 0) return;

    let selected = images;
    if (selected.length > maxFiles) {
      toast.warning("Vượt quá số lượng cho phép", {
        description: `Chỉ xử lý tối đa ${maxFiles} ảnh mỗi lần. Đã lấy ${maxFiles} ảnh đầu.`,
      });
      selected = selected.slice(0, maxFiles);
    }

    const prepared = await Promise.all(selected.map((f) => prepareImageForUpload(f)));
    setPreviews(prepared.map((f) => ({ url: URL.createObjectURL(f), name: f.name })));
    onImagesSelect(prepared);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) void readFiles(files);
    // reset để chọn lại cùng tệp vẫn trigger onChange
    e.target.value = "";
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!isLoading) setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (isLoading) return;
    const files = e.dataTransfer.files;
    if (files && files.length > 0) void readFiles(files);
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`flex w-full flex-col items-center justify-center rounded-lg border-2 border-dashed p-4 transition-colors sm:p-6 ${
        isDragging
          ? "border-blue-500 bg-blue-50"
          : "border-gray-300 bg-gray-50 hover:bg-gray-100"
      }`}
    >
      {previews.length > 0 ? (
        <div className="mb-4 grid w-full max-w-2xl grid-cols-3 gap-2 sm:grid-cols-4">
          {previews.map((p) => (
            <div key={p.url} className="relative aspect-[1.586/1] overflow-hidden rounded-md border border-gray-200 bg-white">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={p.url} alt={p.name} className="h-full w-full object-cover" />
            </div>
          ))}
        </div>
      ) : (
        <Logo className="mb-4 h-16 w-16 opacity-60" />
      )}

      <label className="w-full max-w-xs cursor-pointer">
        <span className="block rounded-md bg-blue-600 px-4 py-2 text-center text-white hover:bg-blue-700 disabled:bg-gray-400">
          {isLoading
            ? "Đang xử lý..."
            : previews.length > 0
              ? `Đã chọn ${previews.length} ảnh - chọn lại`
              : "Tải ảnh CCCD lên (có thể chọn nhiều)"}
        </span>
        <input
          type="file"
          className="hidden"
          accept="image/*"
          multiple
          onChange={handleFileChange}
          disabled={isLoading}
        />
      </label>
      <p className="mt-2 text-center text-xs text-gray-500 sm:text-sm">
        Kéo thả hoặc chọn tối đa {maxFiles} ảnh. Hỗ trợ JPG, PNG, WebP.
      </p>
    </div>
  );
}
