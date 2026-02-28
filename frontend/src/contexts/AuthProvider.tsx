import { createContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import api from '@/services/api';
import type { User, Organization } from '@/types';

interface AuthContextType {
  user: User | null;
  organization: Organization | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (orgName: string, username: string, email: string, password: string) => Promise<void>;
  joinViaInvite: (token: string, username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextType | null>(null);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const isAuthenticated = user !== null;

  const fetchCurrentUser = useCallback(async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      setIsLoading(false);
      return;
    }
    try {
      const resp = await api.get('/auth/me');
      setUser(resp.data.user);
      setOrganization(resp.data.organization ?? null);
    } catch {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      setUser(null);
      setOrganization(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCurrentUser();
  }, [fetchCurrentUser]);

  const login = async (email: string, password: string) => {
    const resp = await api.post('/auth/login', { email, password });
    localStorage.setItem('access_token', resp.data.access_token);
    if (resp.data.refresh_token) {
      localStorage.setItem('refresh_token', resp.data.refresh_token);
    }
    setUser(resp.data.user);
    setOrganization(resp.data.organization ?? null);
  };

  const register = async (
    orgName: string,
    username: string,
    email: string,
    password: string
  ) => {
    const resp = await api.post('/auth/register', {
      org_name: orgName,
      username,
      email,
      password,
    });
    localStorage.setItem('access_token', resp.data.access_token);
    if (resp.data.refresh_token) {
      localStorage.setItem('refresh_token', resp.data.refresh_token);
    }
    setUser(resp.data.user);
    setOrganization(resp.data.organization ?? null);
  };

  const joinViaInvite = async (
    token: string,
    username: string,
    email: string,
    password: string
  ) => {
    const resp = await api.post('/auth/join', { token, username, email, password });
    localStorage.setItem('access_token', resp.data.access_token);
    if (resp.data.refresh_token) {
      localStorage.setItem('refresh_token', resp.data.refresh_token);
    }
    setUser(resp.data.user);
    setOrganization(resp.data.organization ?? null);
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setUser(null);
    setOrganization(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        organization,
        isAuthenticated,
        isLoading,
        login,
        register,
        joinViaInvite,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
