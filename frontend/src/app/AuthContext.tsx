"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getMe } from "@/lib/api";
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
    const token = localStorage.getItem("vs_token");
    if (!token) {
      return;
    }

    try {
      const userData = await getMe();
      setUser(userData);
    } catch (error) {
      console.error("Auth initialization failed:", error);
      localStorage.removeItem("vs_token");
      setUser(null);
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

  const loginSuccess = async (token: string) => {
    localStorage.setItem("vs_token", token);
    setLoading(true);
    try {
      await fetchUser();
    } finally {
      setLoading(false);
    }
    router.push("/");
  };

  const logout = () => {
    localStorage.removeItem("vs_token");
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
