import Link from "next/link";

import Logo from "@/components/Logo";

/**
 * UI cho route 404 – render khi hàm `notFound()` được gọi hoặc URL không khớp
 * bất kỳ segment nào.
 */
export default function NotFound() {
  return (
    <main className="min-h-screen bg-gray-100 flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-white rounded-xl shadow-lg p-8 text-center space-y-4">
        <Logo className="h-16 w-16 mx-auto opacity-80" />
        <h1 className="text-3xl font-bold text-blue-900">404</h1>
        <p className="text-gray-600">
          Không tìm thấy trang bạn yêu cầu.
        </p>
        <Link
          href="/"
          className="inline-block px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
        >
          Về trang chính
        </Link>
      </div>
    </main>
  );
}
