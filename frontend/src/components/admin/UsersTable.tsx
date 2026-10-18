"use client";

import React from "react";

import type { AdminUser } from "@/lib/admin";

interface UsersTableProps {
  users: AdminUser[];
  currentUserId: string;
  query: string;
  onQueryChange: (value: string) => void;
  onUpdate: (user: AdminUser, patch: { role?: "admin" | "user"; is_active?: boolean }) => void;
  busyId: string | null;
}

export const USERS_PAGE_SIZE = 200;

const dateFmt = new Intl.DateTimeFormat("vi-VN", { dateStyle: "short" });
const dateTimeFmt = new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" });

export default function UsersTable({ users, currentUserId, query, onQueryChange, onUpdate, busyId }: UsersTableProps) {
  return (
    <div className="space-y-3">
      <input
        type="search"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder="Tìm theo email hoặc tên"
        aria-label="Tìm người dùng"
        className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm sm:w-72"
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="text-xs uppercase text-gray-500">
            <tr>
              <th className="py-2 pr-3">Người dùng</th>
              <th className="py-2 pr-3">Vai trò</th>
              <th className="py-2 pr-3">Trạng thái</th>
              <th className="py-2 pr-3 text-right">Lượt quét</th>
              <th className="py-2 pr-3 text-right">Đã xuất</th>
              <th className="py-2 pr-3">Quét gần nhất</th>
              <th className="py-2">Tạo lúc</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const self = u.id === currentUserId;
              const busy = busyId === u.id;
              return (
                <tr key={u.id} className="border-t border-gray-100 align-middle">
                  <td className="py-2 pr-3">
                    <div className="font-medium text-gray-800">{u.full_name || "—"}{self && <span className="ml-1 text-xs text-gray-500">(bạn)</span>}</div>
                    <div className="text-xs text-gray-500">{u.email}</div>
                  </td>
                  <td className="py-2 pr-3">
                    <select
                      aria-label={`Vai trò của ${u.email}`}
                      value={u.role}
                      disabled={self || busy}
                      onChange={(e) => onUpdate(u, { role: e.target.value as "admin" | "user" })}
                      className="rounded-md border border-gray-300 px-2 py-1 text-sm disabled:bg-gray-50"
                    >
                      <option value="user">Người dùng</option>
                      <option value="admin">Quản trị</option>
                    </select>
                  </td>
                  <td className="py-2 pr-3">
                    <button
                      type="button"
                      disabled={self || busy}
                      onClick={() => onUpdate(u, { is_active: !u.is_active })}
                      aria-label={`${u.is_active ? "Khóa" : "Mở khóa"} ${u.email}`}
                      className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold disabled:opacity-60 ${
                        u.is_active
                          ? "border-green-200 bg-green-50 text-green-800 hover:bg-green-100"
                          : "border-red-200 bg-red-50 text-red-800 hover:bg-red-100"
                      }`}
                    >
                      {u.is_active ? "✓ Hoạt động" : "✕ Đã khóa"}
                    </button>
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">{u.scans}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{u.exported_scans}</td>
                  <td className="py-2 pr-3 text-gray-600">{u.last_scan_at ? dateTimeFmt.format(new Date(u.last_scan_at)) : "—"}</td>
                  <td className="py-2 text-gray-600">{dateFmt.format(new Date(u.created_at))}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {users.length === 0 && <p className="py-4 text-center text-sm text-gray-500">Không tìm thấy người dùng.</p>}
        {users.length >= USERS_PAGE_SIZE && (
          <p className="pt-2 text-xs text-gray-500">Đang hiện {USERS_PAGE_SIZE} người dùng mới nhất. Dùng ô tìm kiếm để tìm người khác.</p>
        )}
      </div>
    </div>
  );
}
