"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/primitives";
import { useAuth } from "@/lib/auth";

export default function RegisterPage() {
  const { register, status } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ name: "", email: "", password: "", organization_name: "" });
  const [seed, setSeed] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (status === "authenticated") router.replace("/dashboard");
  }, [status, router]);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register({ ...form, seed_demo_data: seed });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Create your workspace</h1>
      <p className="mt-1 text-sm text-muted-foreground">You&apos;ll be the owner. Invite your team afterwards.</p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="name">Full name</Label>
          <Input id="name" required autoComplete="name" value={form.name} onChange={set("name")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="org">Firm / organization</Label>
          <Input id="org" required minLength={2} value={form.organization_name} onChange={set("organization_name")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="email">Work email</Label>
          <Input id="email" type="email" required autoComplete="email" value={form.email} onChange={set("email")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            required
            minLength={10}
            autoComplete="new-password"
            value={form.password}
            onChange={set("password")}
            aria-describedby="pw-hint"
          />
          <p id="pw-hint" className="text-xs text-muted-foreground">
            At least 10 characters, including letters and numbers.
          </p>
        </div>
        <label className="flex items-start gap-2.5 rounded-md border bg-muted/40 p-3 text-sm">
          <input type="checkbox" checked={seed} onChange={(e) => setSeed(e.target.checked)} className="mt-0.5 accent-[var(--accent)]" />
          <span>
            <span className="font-medium">Load sample portfolio</span>
            <span className="block text-xs text-muted-foreground">
              Five clearly-labelled, fictional demo deals (incl. multifamily &amp; industrial) with sample documents.
            </span>
          </span>
        </label>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" loading={busy}>
          Create workspace
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
          Sign in
        </Link>
      </p>
    </>
  );
}
