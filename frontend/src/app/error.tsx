"use client"; // Error boundaries phải là Client Component (Next.js 16)

import Link from "next/link";
import { useEffect } from "react";

import Logo from "@/components/Logo";

/**
 * Error boundary cho toàn route segment `/`.
 * Hứng mọi uncaught exception từ Server Component, Client Component, hoặc
 * async hooks ở phía dưới cây component.
 *
 * Next.js 16 dùng `unstable_retry` thay cho `reset` của Next 15.
 */
export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    // TODO Phase 7: gửi sang Sentry. Hiện chỉ log console.
    console.error("Route error:", error);
  }, [error]);

  return (
    <main className="min-h-screen bg-gray-100 flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-white rounded-xl shadow-lg p-8 text-center space-y-4">
        <Logo className="h-16 w-16 mx-auto opacity-80" />
        <h1 className="text-2xl font-bold text-gray-800">Đã xảy ra lỗi</h1>
        <p className="text-gray-600">
          Có lỗi không mong muốn xảy ra. Vui lòng thử lại hoặc quay lại trang chính.
        </p>
        {error.digest && (
          <p className="text-xs text-gray-400 font-mono">digest: {error.digest}</p>
        )}
        <div className="flex justify-center gap-3 pt-2">
          <button
            type="button"
            onClick={() => unstable_retry()}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            Thử lại
          </button>
          <Link
            href="/"
            className="px-4 py-2 border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50"
          >
            Trang chính
          </Link>
        </div>
      </div>
    </main>
  );
}
