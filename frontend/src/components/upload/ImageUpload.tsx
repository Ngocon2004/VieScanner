"use client";

import React, { useState } from "react";
import { toast } from "sonner";

import Logo from "@/components/Logo";

interface ImageUploadProps {
  onImageSelect: (file: File) => void;
  isLoading: boolean;
}

export default function ImageUpload({ onImageSelect, isLoading }: ImageUploadProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const isImageFile = (file: File) => file.type.startsWith("image/");

  const readFile = (file: File) => {
    if (!isImageFile(file)) {
      toast.warning("Tệp không hợp lệ", {
        description: "Vui lòng chọn ảnh JPG, PNG hoặc WebP.",
      });
      return;
    }

    onImageSelect(file);
    const reader = new FileReader();
    reader.onloadend = () => {
      setPreview(reader.result as string);
    };
    reader.readAsDataURL(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) readFile(file);
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

    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    readFile(file);
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
      {preview ? (
        <div className="relative mb-4 aspect-[1.586/1] w-full max-w-md">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={preview}
            alt="CCCD Preview"
            className="h-full w-full rounded-md object-contain shadow-md"
          />
        </div>
      ) : (
        <Logo className="mb-4 h-16 w-16 opacity-60" />
      )}

      <label className="w-full max-w-xs cursor-pointer">
        <span className="block rounded-md bg-blue-600 px-4 py-2 text-center text-white hover:bg-blue-700 disabled:bg-gray-400">
          {isLoading ? "Đang xử lý..." : preview ? "Chọn ảnh khác" : "Tải ảnh CCCD lên"}
        </span>
        <input
          type="file"
          className="hidden"
          accept="image/*"
          capture="environment"
          onChange={handleFileChange}
          disabled={isLoading}
        />
      </label>
      <p className="mt-2 text-center text-xs text-gray-500 sm:text-sm">
        Kéo thả ảnh hoặc chọn từ thiết bị. Hỗ trợ JPG, PNG, WebP.
      </p>
    </div>
  );
}
