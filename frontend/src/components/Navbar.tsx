"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/app/AuthContext";
import Logo from "./Logo";

export default function Navbar() {
  const { user, logout } = useAuth();
  const pathname = usePathname();

  const navItems = [
    { label: "Trang chủ", href: "/" },
    { label: "Lịch sử", href: "/history" },
    { label: "Bản ghi", href: "/records" },
    ...(user?.role === "admin" ? [{ label: "Quản trị", href: "/admin" }] : []),
  ];

  return (
    <nav className="bg-white shadow-sm border-b">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <Link href="/" className="flex-shrink-0 flex items-center gap-2">
              <Logo className="h-8 w-8" />
              <span className="font-bold text-xl text-blue-600 hidden sm:block">
                VieScanner
              </span>
            </Link>
            <div className="hidden sm:ml-8 sm:flex sm:space-x-4">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    pathname === item.href
                      ? "bg-blue-50 text-blue-700"
                      : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-4">
            {user ? (
              <div className="flex items-center gap-3">
                <span className="text-sm text-gray-600 hidden md:block">
                  {user.full_name || user.email}
                </span>
                <button
                  onClick={logout}
                  className="text-sm font-medium text-red-600 hover:text-red-700"
                >
                  Đăng xuất
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-4">
                <Link
                  href="/login"
                  className="text-sm font-medium text-gray-500 hover:text-gray-700"
                >
                  Đăng nhập
                </Link>
                <Link
                  href="/register"
                  className="bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700"
                >
                  Đăng ký
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
      {/* Mobile nav */}
      <div className="sm:hidden border-t flex justify-around py-2 bg-gray-50">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`text-xs font-medium px-2 py-1 rounded ${
              pathname === item.href ? "text-blue-700 bg-blue-100" : "text-gray-500"
            }`}
          >
            {item.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
