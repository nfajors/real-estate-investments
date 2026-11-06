"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, getOrgId, onSessionExpired, refreshSession, setAccessToken, setOrgId } from "./api";
import type { Me, Membership, Role } from "./types";

const RANK: Record<Role, number> = { viewer: 0, analyst: 1, admin: 2, owner: 3 };

interface AuthState {
  status: "loading" | "authenticated" | "anonymous";
  me: Me | null;
  org: Membership | null;
  login: (email: string, password: string) => Promise<void>;
  register: (body: { email: string; password: string; name: string; organization_name: string; seed_demo_data: boolean }) => Promise<void>;
  acceptToken: (accessToken: string) => Promise<void>;
  logout: () => Promise<void>;
  switchOrg: (orgId: string) => void;
  reload: () => Promise<void>;
  hasRole: (role: Role) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [me, setMe] = useState<Me | null>(null);
  const [orgId, setOrg] = useState<string | null>(null);
  const qc = useQueryClient();
  const router = useRouter();

  const loadMe = useCallback(async () => {
    const data = await api<Me>("/api/auth/me");
    setMe(data);
    const stored = getOrgId();
    const chosen = data.memberships.find((m) => m.org_id === stored) ?? data.memberships[0] ?? null;
    setOrgId(chosen?.org_id ?? null);
    setOrg(chosen?.org_id ?? null);
    setStatus("authenticated");
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      const ok = await refreshSession();
      if (!alive) return;
      if (ok) {
        try {
          await loadMe();
          return;
        } catch {
          /* fall through */
        }
      }
      setStatus("anonymous");
    })();
    return () => {
      alive = false;
    };
  }, [loadMe]);

  useEffect(
    () =>
      onSessionExpired(() => {
        setAccessToken(null);
        setMe(null);
        setStatus("anonymous");
        qc.clear();
        router.replace("/login?expired=1");
      }),
    [qc, router],
  );

  const acceptToken = useCallback(
    async (token: string) => {
      setAccessToken(token);
      await loadMe();
    },
    [loadMe],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const t = await api<{ access_token: string }>("/api/auth/login", { body: { email, password } });
      await acceptToken(t.access_token);
    },
    [acceptToken],
  );

  const register = useCallback<AuthState["register"]>(
    async (body) => {
      const t = await api<{ access_token: string }>("/api/auth/register", { body });
      setOrgId(null);
      await acceptToken(t.access_token);
    },
    [acceptToken],
  );

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      setAccessToken(null);
      setMe(null);
      setStatus("anonymous");
      qc.clear();
      router.replace("/login");
    }
  }, [qc, router]);

  const switchOrg = useCallback(
    (id: string) => {
      setOrgId(id);
      setOrg(id);
      qc.clear();
      router.push("/dashboard");
    },
    [qc, router],
  );

  const org = useMemo(() => me?.memberships.find((m) => m.org_id === orgId) ?? null, [me, orgId]);
  const hasRole = useCallback((role: Role) => !!org && RANK[org.role] >= RANK[role], [org]);

  const value = useMemo<AuthState>(
    () => ({ status, me, org, login, register, acceptToken, logout, switchOrg, reload: loadMe, hasRole }),
    [status, me, org, login, register, acceptToken, logout, switchOrg, loadMe, hasRole],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
