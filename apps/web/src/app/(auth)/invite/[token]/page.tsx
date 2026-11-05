"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Callout, LoadingBlock } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/primitives";
import { api, setOrgId } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Preview {
  email: string;
  role: string;
  organization: string;
  has_account: boolean;
}

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const { acceptToken } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const preview = useQuery({ queryKey: ["invite", token], queryFn: () => api<Preview>(`/api/invitations/${token}`), retry: false });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const t = await api<{ access_token: string }>("/api/invitations/accept", {
        body: { token, name: name || undefined, password },
      });
      setOrgId(null);
      await acceptToken(t.access_token);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not accept invitation");
    } finally {
      setBusy(false);
    }
  }

  if (preview.isLoading) return <LoadingBlock />;
  if (preview.error || !preview.data)
    return (
      <Callout tone="danger" title="Invitation unavailable">
        {preview.error instanceof Error ? preview.error.message : "This invitation link is invalid."}
      </Callout>
    );
  const p = preview.data;
  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Join {p.organization}</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        You&apos;ve been invited as <span className="font-medium capitalize text-foreground">{p.role}</span> ({p.email}).
      </p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        {!p.has_account && (
          <div className="space-y-1.5">
            <Label htmlFor="name">Full name</Label>
            <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="password">{p.has_account ? "Your existing password" : "Choose a password"}</Label>
          <Input
            id="password"
            type="password"
            required
            minLength={p.has_account ? 1 : 10}
            autoComplete={p.has_account ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" loading={busy}>
          Accept invitation
        </Button>
      </form>
    </>
  );
}
