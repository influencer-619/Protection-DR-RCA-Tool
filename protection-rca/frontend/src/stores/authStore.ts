import { create } from 'zustand';
import type { User } from '@/types';
import { api, clearAuth, getStoredToken, getStoredUser } from '@/services/api';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hydrate: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  hydrate: () => {
    const token = getStoredToken();
    const user = getStoredUser();
    set({
      token,
      user,
      isAuthenticated: Boolean(token && user),
    });
  },

  login: async (username, password) => {
    set({ isLoading: true, error: null });
    try {
      const res = await api.login(username, password);
      set({
        user: res.user,
        token: res.access_token,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (e) {
      set({
        isLoading: false,
        error: e instanceof Error ? e.message : 'Login failed',
        isAuthenticated: false,
      });
      throw e;
    }
  },

  logout: () => {
    api.logout();
    clearAuth();
    set({ user: null, token: null, isAuthenticated: false, error: null });
  },
}));
