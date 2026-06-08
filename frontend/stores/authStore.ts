"use client"
import { create } from "zustand";
import { api, setTokens, clearTokens, getAccessToken } from "@/lib/api";

export interface User {
  id: string;
  email: string;
  name: string;
  role: string;
  avatar_url: string | null;
}

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, name: string, password: string) => Promise<void>;
  logout: () => void;
  fetchUser: () => Promise<void>;
  init: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isLoading: true,
  isAuthenticated: typeof window !== "undefined" && !!sessionStorage.getItem("access_token"),

  init: () => {
    const hasToken = typeof window !== "undefined" && !!sessionStorage.getItem("access_token");
    set({ isAuthenticated: hasToken, isLoading: true });
    if (hasToken) {
      get().fetchUser();
    } else {
      set({ isLoading: false });
    }
  },

  login: async (email, password) => {
    const data = await api<{
      access_token: string;
      refresh_token: string;
      user: User;
    }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setTokens(data.access_token, data.refresh_token);
    set({ user: data.user, isAuthenticated: true, isLoading: false });
  },

  register: async (email, name, password) => {
    const data = await api<{
      access_token: string;
      refresh_token: string;
      user: User;
    }>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, name, password }),
    });
    setTokens(data.access_token, data.refresh_token);
    set({ user: data.user, isAuthenticated: true, isLoading: false });
  },

  logout: () => {
    clearTokens();
    set({ user: null, isAuthenticated: false, isLoading: false });
  },

  fetchUser: async () => {
    const token = getAccessToken();
    if (!token) {
      set({ user: null, isAuthenticated: false, isLoading: false });
      return;
    }
    try {
      const data = await api<User>("/api/v1/profile");
      set({ user: data, isAuthenticated: true, isLoading: false });
    } catch (err) {
      // 401 = token truly invalid; network error = keep logged in
      if (err instanceof Error && err.message.includes("认证已过期")) {
        clearTokens();
        set({ user: null, isAuthenticated: false, isLoading: false });
      } else {
        set({ isLoading: false });
      }
    }
  },
}));
