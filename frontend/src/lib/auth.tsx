"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { api, onUnauthorized, tokenStore } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/format";
import type { CurrentUser } from "@/types/api";

interface AuthState {
  user: CurrentUser | null;
  ready: boolean; // false until the stored token has been checked
  login: (email: string, password: string) => Promise<CurrentUser>;
  switchUser: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);
export const FLASH_KEY = "pms.flash";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState(false);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    router.replace("/login");
  }, [router]);

  useEffect(() => {
    onUnauthorized(() => {
      tokenStore.clear();
      setUser(null);
      router.replace("/login?expired=1");
    });
    if (!tokenStore.get()) {
      setReady(true);
      return;
    }
    api.auth
      .me()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setReady(true));
  }, [router]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await api.auth.login(email, password);
    tokenStore.set(response.access_token);
    setUser(response.user);
    return response.user;
  }, []);

  /** Demo "switch user": log in as someone else and start clean on their dashboard. A full page
   *  load (rather than a client-side re-render) means the page you were on never re-fetches as
   *  the new user, so no stray "not allowed" errors flash up. */
  const switchUser = useCallback(async (email: string, password: string) => {
    const response = await api.auth.login(email, password);
    tokenStore.set(response.access_token);
    window.sessionStorage.setItem(FLASH_KEY, `Now signed in as ${response.user.name} (${ROLE_LABELS[response.user.role]})`);
    window.location.assign("/dashboard");
  }, []);

  const value = useMemo(() => ({ user, ready, login, switchUser, logout }), [user, ready, login, switchUser, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}

/** The logged-in user; only call inside the authenticated app shell. */
export function useUser(): CurrentUser {
  const { user } = useAuth();
  if (!user) throw new Error("useUser called without a logged-in user");
  return user;
}
