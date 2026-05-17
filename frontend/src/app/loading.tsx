import Logo from "@/components/Logo";

/**
 * Fallback UI hiển thị qua React Suspense khi route segment đang stream/load.
 * Là Server Component theo mặc định để Next.js có thể prefetch và render
 * ngay lập tức khi điều hướng.
 */
export default function Loading() {
  return (
    <main className="min-h-screen bg-gray-100 flex items-center justify-center px-4">
      <div className="flex flex-col items-center gap-4">
        <Logo className="h-16 w-16 animate-pulse" />
        <p className="text-gray-600 text-sm">Đang tải VieScanner...</p>
      </div>
    </main>
  );
}
