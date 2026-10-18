"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { useAuth } from "@/app/AuthContext";
import Navbar from "@/components/Navbar";
import { ErrorBars, FieldQualityTable, Panel, StatTiles, SystemPanel } from "@/components/admin/AdminPanels";
import DailyScansChart from "@/components/admin/DailyScansChart";
import RecentScans, { ScanFilterTabs, type ScanFilter } from "@/components/admin/RecentScans";
import UsersTable, { USERS_PAGE_SIZE } from "@/components/admin/UsersTable";
import {
  getAdminOverview,
  getAdminScans,
  getAdminSystem,
  getAdminUsers,
  updateAdminUser,
  type AdminOverview,
  type AdminScan,
  type AdminSystem,
  type AdminUser,
} from "@/lib/admin";
import { APIError, isAbortError } from "@/lib/api";

const PERIODS = [7, 30, 90] as const;
const SEARCH_DEBOUNCE_MS = 300;

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof APIError ? err.message : fallback;
}

export default function AdminPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const isAdmin = user?.role === "admin";

  const [days, setDays] = useState<number>(30);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [system, setSystem] = useState<AdminSystem | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [query, setQuery] = useState("");
  const [scans, setScans] = useState<AdminScan[]>([]);
  const [scanFilter, setScanFilter] = useState<ScanFilter>("");
  const [busyUserId, setBusyUserId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !user) router.push("/login");
  }, [authLoading, user, router]);

  useEffect(() => {
    if (!isAdmin) return;
    const controller = new AbortController();
    Promise.all([getAdminOverview(days, controller.signal), getAdminSystem(controller.signal)])
      .then(([o, s]) => {
        setOverview(o);
        setSystem(s);
        setOverviewError(null);
      })
      .catch((err) => {
        if (!isAbortError(err)) setOverviewError(errorMessage(err, "Không tải được số liệu tổng quan."));
      });
    return () => controller.abort();
  }, [isAdmin, days, refreshKey]);

  useEffect(() => {
    if (!isAdmin) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      getAdminUsers(query, USERS_PAGE_SIZE, controller.signal)
        .then(setUsers)
        .catch((err) => {
          if (!isAbortError(err)) toast.error(errorMessage(err, "Không tải được danh sách người dùng."));
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [isAdmin, query, refreshKey]);

  useEffect(() => {
    if (!isAdmin) return;
    const controller = new AbortController();
    getAdminScans(scanFilter, controller.signal)
      .then(setScans)
      .catch((err) => {
        if (!isAbortError(err)) toast.error(errorMessage(err, "Không tải được lượt quét gần đây."));
      });
    return () => controller.abort();
  }, [isAdmin, scanFilter, refreshKey]);

  const handleUserUpdate = useCallback(
    async (target: AdminUser, patch: { role?: "admin" | "user"; is_active?: boolean }) => {
      setBusyUserId(target.id);
      try {
        const updated = await updateAdminUser(target.id, patch);
        setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
        toast.success(`Đã cập nhật ${updated.email}`);
      } catch (err) {
        toast.error(errorMessage(err, "Không cập nhật được người dùng."));
      } finally {
        setBusyUserId(null);
      }
    },
    [],
  );

  if (authLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-100">
        <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-blue-600" />
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="flex min-h-screen flex-col bg-gray-100">
        <Navbar />
        <main className="container mx-auto max-w-xl flex-grow px-4 py-16 text-center">
          <h1 className="text-xl font-bold text-gray-900">Không có quyền truy cập</h1>
          <p className="mt-2 text-gray-600">Trang quản trị chỉ dành cho tài khoản quản trị viên.</p>
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-gray-100">
      <Navbar />
      <main className="container mx-auto max-w-6xl flex-grow space-y-5 px-4 py-6 sm:py-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Quản trị hệ thống</h1>
            <p className="text-sm text-gray-500">Số liệu quét CCCD, chất lượng OCR và người dùng.</p>
          </div>
          <div className="flex items-center gap-2">
            <div role="tablist" aria-label="Khoảng thời gian" className="inline-flex rounded-lg border border-gray-200 bg-white p-0.5 text-sm">
              {PERIODS.map((p) => (
                <button
                  key={p}
                  type="button"
                  role="tab"
                  aria-selected={days === p}
                  onClick={() => setDays(p)}
                  className={`rounded-md px-3 py-1 font-medium ${days === p ? "bg-blue-50 text-blue-700" : "text-gray-600"}`}
                >
                  {p} ngày
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setRefreshKey((k) => k + 1)}
              className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Làm mới
            </button>
          </div>
        </div>

        {overviewError && (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            <span>{overviewError}</span>
            <button type="button" onClick={() => setRefreshKey((k) => k + 1)} className="font-semibold underline">
              Thử lại
            </button>
          </div>
        )}

        {overview ? (
          // Đổi kỳ: giữ số liệu cũ nhưng làm mờ tới khi số liệu của kỳ mới về.
          <div className={`space-y-5 transition-opacity ${overview.days !== days ? "opacity-50" : ""}`} aria-busy={overview.days !== days}>
            <StatTiles overview={overview} />
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <Panel title={`Lượt quét theo ngày (${overview.days} ngày)`}>
                  <DailyScansChart daily={overview.daily} />
                </Panel>
              </div>
              <Panel title="Lý do thất bại">
                <ErrorBars errors={overview.errors} />
              </Panel>
            </div>
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <Panel title="Chất lượng đọc từng trường">
                  <FieldQualityTable overview={overview} />
                </Panel>
              </div>
              <Panel title="Hệ thống">
                <SystemPanel system={system} jobs={overview.jobs} />
              </Panel>
            </div>
          </div>
        ) : overviewError ? null : (
          <div className="grid animate-pulse grid-cols-2 gap-3 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-24 rounded-xl bg-gray-200" />
            ))}
          </div>
        )}

        <Panel title="Người dùng">
          <UsersTable
            users={users}
            currentUserId={user.id}
            query={query}
            onQueryChange={setQuery}
            onUpdate={handleUserUpdate}
            busyId={busyUserId}
          />
        </Panel>

        <Panel title="50 lượt quét gần nhất" action={<ScanFilterTabs value={scanFilter} onChange={setScanFilter} />}>
          <RecentScans scans={scans} />
        </Panel>
      </main>
    </div>
  );
}
