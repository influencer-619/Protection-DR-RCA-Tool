import { useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

export function useAuth() {
  const navigate = useNavigate();
  const {
    user,
    token,
    isAuthenticated,
    isLoading,
    error,
    login: storeLogin,
    logout: storeLogout,
    hydrate,
  } = useAuthStore();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const login = useCallback(
    async (username: string, password: string) => {
      await storeLogin(username, password);
      // Replace so browser Back does not return to /login (which auto-bounces
      // to dashboard and looks like Back/Forward is broken).
      navigate('/plant', { replace: true });
    },
    [storeLogin, navigate],
  );

  const logout = useCallback(() => {
    storeLogout();
    navigate('/login', { replace: true });
  }, [storeLogout, navigate]);

  return {
    user,
    token,
    isAuthenticated,
    isLoading,
    error,
    login,
    logout,
    hydrate,
  };
}
