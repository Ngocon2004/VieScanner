"use client";

import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { getRecords, deleteRecord, APIError, isAbortError } from "@/lib/api";
import type { CCCDRecordRead } from "@/lib/schemas";
import Navbar from "@/components/Navbar";
import { useAuth } from "@/app/AuthContext";
import { useRouter } from "next/navigation";

export default function RecordsPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [records, setRecords] = useState<CCCDRecordRead[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchRecords = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await getRecords(50, 0, signal);
      setRecords(data);
    } catch (error) {
      if (isAbortError(error)) return; // request bị hủy khi unmount → bỏ qua
      const message = error instanceof APIError ? error.message : "Không thể tải danh sách bản ghi";
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
      // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount: state set sau khi getRecords() resolve; hủy khi unmount (backlog N4: migrate to SWR)
      void fetchRecords(controller.signal);
      return () => controller.abort();
    }
  }, [user, authLoading, router, fetchRecords]);

  const handleDelete = async (id: string) => {
    if (!confirm("Bạn có chắc chắn muốn xóa bản ghi này?")) return;

    try {
      await deleteRecord(id);
      setRecords(records.filter((r) => r.id !== id));
      toast.success("Đã xóa bản ghi.");
    } catch {
      toast.error("Không thể xóa bản ghi.");
    }
  };

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
      <main className="flex-grow container mx-auto px-4 py-8 max-w-6xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Danh sách bản ghi CCCD</h1>
        
        {records.length === 0 ? (
          <div className="bg-white p-8 rounded-xl shadow-sm border text-center text-gray-500">
            Bạn chưa có bản ghi CCCD nào được lưu.
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Số CCCD</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Họ và tên</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Ngày sinh</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Giới tính</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Ngày xuất</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Thao tác</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {records.map((record) => (
                  <tr key={record.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono font-medium text-gray-900">{record.id_number}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{record.full_name}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{record.dob}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{record.gender}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {record.exported_at ? new Date(record.exported_at).toLocaleDateString("vi-VN") : "-"}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <button
                        onClick={() => handleDelete(record.id)}
                        className="text-red-600 hover:text-red-900"
                      >
                        Xóa
                      </button>
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
