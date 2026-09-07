import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { useEffect } from 'react';

export function ProtectedRoute() {
  const { isAuthenticated, hydrate } = useAuthStore();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  if (!isAuthenticated && !localStorage.getItem('protection_rca_token')) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
