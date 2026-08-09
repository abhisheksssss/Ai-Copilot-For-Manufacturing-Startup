import { create } from "zustand";

import type { AuthUser } from "@/lib/api";

type AuthState = {
  token: string | null;
  user: AuthUser | null;
  isReady: boolean;
  setSession: (session: { token: string; user: AuthUser }) => void;
  setUser: (user: AuthUser | null) => void;
  logout: () => void;
  initializeAuth: () => void;
};

const TOKEN_KEY = "manufacturing_copilot_token";
const USER_KEY = "manufacturing_copilot_user";

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isReady: false,
  setSession: ({ token, user }) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    set({ token, user, isReady: true });
  },
  setUser: (user) => {
    if (user) {
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(USER_KEY);
    }

    set({ user });
  },
  logout: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    set({ token: null, user: null, isReady: true });
  },
  initializeAuth: () => {
    const token = localStorage.getItem(TOKEN_KEY);
    const storedUser = localStorage.getItem(USER_KEY);
    const user = storedUser ? (JSON.parse(storedUser) as AuthUser) : null;

    set({ token, user, isReady: true });
  },
}));
