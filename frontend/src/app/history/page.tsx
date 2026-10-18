"use client";

import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { getScans, APIError, isAbortError } from "@/lib/api";
import type { ScanListItem } from "@/lib/schemas";
import Navbar from "@/components/Navbar";
import { useAuth } from "@/app/AuthContext";
import { useRouter } from "next/navigation";

export default function HistoryPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [scans, setScans] = useState<ScanListItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchScans = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await getScans(50, 0, signal);
      setScans(data);
    } catch (error) {
      if (isAbortError(error)) return; // request bị hủy khi unmount → bỏ qua
      const message = error instanceof APIError ? error.message : "Không thể tải lịch sử";
      toast.error(message);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login");
      return;
    }

    if (user) {
      const controller = new AbortController();
      // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount: state set sau khi getScans() resolve; hủy khi unmount (backlog N4: migrate to SWR)
      void fetchScans(controller.signal);
      return () => controller.abort();
    }
  }, [user, authLoading, router, fetchScans]);

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex flex-col">
        <Navbar />
        <div className="flex-grow flex items-center justify-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <Navbar />
      <main className="flex-grow container mx-auto px-4 py-8 max-w-4xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Lịch sử quét CCCD</h1>
        
        {scans.length === 0 ? (
          <div className="bg-white p-8 rounded-xl shadow-sm border text-center text-gray-500">
            Bạn chưa thực hiện quét CCCD nào.
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Thời gian
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    File
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Trạng thái
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Thời gian xử lý
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {scans.map((scan) => (
                  <tr key={scan.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(scan.created_at).toLocaleString("vi-VN")}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {scan.filename || "N/A"}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                        scan.status === "success" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
                      }`}>
                        {scan.status === "success" ? "Thành công" : "Thất bại"}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {scan.duration_ms ? `${scan.duration_ms}ms` : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
