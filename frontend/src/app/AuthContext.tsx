"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { APIError, AUTH_EXPIRED_EVENT, TOKEN_STORAGE_KEY, getMe } from "@/lib/api";
import type { UserRead } from "@/lib/schemas";

interface AuthContextType {
  user: UserRead | null;
  loading: boolean;
  loginSuccess: (token: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserRead | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const fetchUser = useCallback(async () => {
    const token = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (!token) {
      return;
    }

    try {
      const userData = await getMe();
      setUser(userData);
    } catch (error) {
      // Chỉ bỏ token khi server khẳng định nó không hợp lệ; mất mạng/backend lỗi tạm thời không được đăng xuất người dùng.
      if (error instanceof APIError && error.status === 401) {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        setUser(null);
      }
    }
  }, []);

  useEffect(() => {
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount: state is set after async getMe() resolves (backlog N4: migrate to SWR)
    fetchUser().finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [fetchUser]);

  useEffect(() => {
    const onExpired = () => setUser(null);
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, []);

  const loginSuccess = async (token: string) => {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
    setLoading(true);
    try {
      await fetchUser();
    } finally {
      setLoading(false);
    }
    router.push("/");
  };

  const logout = () => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setUser(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider value={{ user, loading, loginSuccess, logout, refreshUser: fetchUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
