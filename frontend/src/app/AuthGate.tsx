import { useEffect, useState } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { api } from '../api/endpoints';
import { useSessionStore } from '../stores/session.store';

type AuthStatus = 'checking' | 'valid' | 'invalid';

export function AuthGate(): JSX.Element {
  const location = useLocation();
  const token = useSessionStore((state) => state.token);
  const updateUser = useSessionStore((state) => state.updateUser);
  const clearSession = useSessionStore((state) => state.clearSession);
  const [authStatus, setAuthStatus] = useState<AuthStatus>(() => token ? 'checking' : 'invalid');

  useEffect(() => {
    if (!token) {
      setAuthStatus('invalid');
      return;
    }
    let cancelled = false;
    setAuthStatus('checking');
    api.me()
      .then(({ user }) => {
        if (cancelled) return;
        updateUser(user);
        setAuthStatus('valid');
      })
      .catch(() => {
        if (cancelled) return;
        clearSession();
        setAuthStatus('invalid');
      });
    return () => {
      cancelled = true;
    };
  }, [token, updateUser, clearSession]);

  if (!token || authStatus === 'invalid') {
    const from = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={{ pathname: '/login', search: location.search }} replace state={{ from }} />;
  }

  if (authStatus === 'checking') {
    return (
      <main className="grid min-h-dvh place-items-center bg-slate-50 px-6 text-sm font-semibold text-slate-600">
        正在验证登录状态...
      </main>
    );
  }

  return <Outlet />;
}
