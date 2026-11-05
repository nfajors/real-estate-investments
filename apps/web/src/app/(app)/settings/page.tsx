"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Check, Copy, CreditCard, Flag, History, Mail, Plus, Search, Trash2, Users } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Callout, EmptyState, ErrorBlock, LoadingBlock, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, Switch, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlays";
import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Select,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui/primitives";
import { Tooltip } from "@/components/ui/tooltip";
import { useAudit, useFeatures, useOrgKey } from "@/hooks/queries";
import type { AuditEntry } from "@/hooks/queries";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, isNum, num, relativeTime } from "@/lib/format";
import type { Role } from "@/lib/types";
import { cn } from "@/lib/utils";

// ------------------------------------------------------------------ types
interface OrgDetail {
  id: string;
  name: string;
  slug: string;
  plan: string;
  created_at: string;
  role: Role;
  features: Record<string, boolean>;
  feature_overrides: Record<string, boolean>;
}

interface Member {
  user_id: string;
  email: string;
  name: string;
  role: Role;
  joined_at: string;
}

interface Invitation {
  id: string;
  email: string;
  role: Role;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
}

interface InvitationCreated extends Invitation {
  token: string;
  accept_url: string;
}

interface Plan {
  label: string;
  price_monthly: number | null;
  max_deals: number | null;
  max_members: number | null;
  features: string[];
}

interface Billing {
  plan: string;
  plans: Record<string, Plan>;
  usage: { deals: number; members: number };
  billing_mode: "stripe" | "manual";
}

// ---------------------------------------------------------------- helpers
const ROLE_LABELS: Record<Role, string> = { owner: "Owner", admin: "Admin", analyst: "Analyst", viewer: "Viewer" };
const RANK: Record<Role, number> = { viewer: 0, analyst: 1, admin: 2, owner: 3 };
const PLAN_ORDER = ["starter", "professional", "enterprise"];
const TAB_KEYS = ["organization", "members", "billing", "features", "audit"] as const;
type TabKey = (typeof TAB_KEYS)[number];

function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

type InviteStatus = "pending" | "accepted" | "revoked" | "expired";

function inviteStatus(inv: Invitation, now: number): InviteStatus {
  if (inv.revoked_at) return "revoked";
  if (inv.accepted_at) return "accepted";
  if (new Date(inv.expires_at).getTime() < now) return "expired";
  return "pending";
}

const INVITE_TONE: Record<InviteStatus, "accent" | "success" | "default" | "warning"> = {
  pending: "accent",
  accepted: "success",
  revoked: "default",
  expired: "warning",
};

function useOrgDetail() {
  const org = useOrgKey();
  return useQuery({ queryKey: [org, "org"], queryFn: () => api<OrgDetail>("/api/org") });
}

function useBilling() {
  const org = useOrgKey();
  return useQuery({ queryKey: [org, "billing"], queryFn: () => api<Billing>("/api/billing") });
}

function limitText(n: number | null): string {
  return n === null ? "Unlimited" : num(n);
}

// ------------------------------------------------------------------- page
function SettingsInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { org, reload } = useAuth();
  const qc = useQueryClient();
  const orgKey = useOrgKey();
  const initial = params.get("tab");
  const [tab, setTab] = useState<TabKey>(
    params.get("billing") ? "billing" : TAB_KEYS.includes(initial as TabKey) ? (initial as TabKey) : "organization",
  );
  const handled = useRef(false);

  // Stripe Checkout returns to /settings?billing=success.
  useEffect(() => {
    if (handled.current || params.get("billing") !== "success") return;
    handled.current = true;
    toast.success("Checkout complete. Your plan will update as soon as the payment is confirmed.");
    void reload().then(() => qc.invalidateQueries({ queryKey: [orgKey] }));
    router.replace("/settings?tab=billing", { scroll: false });
  }, [params, reload, qc, orgKey, router]);

  const changeTab = (v: string) => {
    setTab(v as TabKey);
    router.replace(v === "organization" ? "/settings" : `/settings?tab=${v}`, { scroll: false });
  };

  if (!org) return <LoadingBlock rows={6} />;

  return (
    <>
      <PageHeader title="Settings" description={`Workspace configuration for ${org.org_name}.`} />
      <Tabs value={tab} onValueChange={changeTab}>
        <div className="-mx-1 mb-5 overflow-x-auto px-1">
          <TabsList aria-label="Settings sections">
            <TabsTrigger value="organization">
              <Building2 className="size-3.5" /> Organization
            </TabsTrigger>
            <TabsTrigger value="members">
              <Users className="size-3.5" /> Members
            </TabsTrigger>
            <TabsTrigger value="billing">
              <CreditCard className="size-3.5" /> Billing &amp; plan
            </TabsTrigger>
            <TabsTrigger value="features">
              <Flag className="size-3.5" /> Features
            </TabsTrigger>
            <TabsTrigger value="audit">
              <History className="size-3.5" /> Audit log
            </TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="organization" className="rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring">
          <OrganizationTab />
        </TabsContent>
        <TabsContent value="members" className="rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring">
          <MembersTab />
        </TabsContent>
        <TabsContent value="billing" className="rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring">
          <BillingTab />
        </TabsContent>
        <TabsContent value="features" className="rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring">
          <FeaturesTab />
        </TabsContent>
        <TabsContent value="audit" className="rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring">
          <AuditTab />
        </TabsContent>
      </Tabs>
    </>
  );
}

// ------------------------------------------------------------ organization
function OrganizationTab() {
  const { org, me, hasRole, switchOrg } = useAuth();
  const detail = useOrgDetail();
  const [createOpen, setCreateOpen] = useState(false);
  if (!org || !me) return null;

  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <Card className="xl:col-span-2">
        <CardHeader>
          <CardTitle>Workspace</CardTitle>
          <CardDescription>Deals, documents and members are isolated to this workspace.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs text-muted-foreground">Name</dt>
              <dd className="mt-0.5 font-medium">{org.org_name}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Slug</dt>
              <dd className="mt-0.5 font-mono text-xs">{org.org_slug}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Plan</dt>
              <dd className="mt-0.5 capitalize">{org.plan}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Your role</dt>
              <dd className="mt-0.5">
                <Badge variant={org.role === "owner" ? "accent" : "default"}>{ROLE_LABELS[org.role]}</Badge>
              </dd>
            </div>
            {detail.data && (
              <div>
                <dt className="text-xs text-muted-foreground">Created</dt>
                <dd className="mt-0.5">{shortDate(detail.data.created_at)}</dd>
              </div>
            )}
          </dl>
          {hasRole("admin") ? (
            <RenameForm key={org.org_id} current={org.org_name} />
          ) : (
            <p className="text-xs text-muted-foreground">Only admins and owners can rename the workspace.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-start justify-between gap-3">
          <div>
            <CardTitle>Your workspaces</CardTitle>
            <CardDescription>Switch between organizations you belong to.</CardDescription>
          </div>
          <Button size="sm" variant="outline" onClick={() => setCreateOpen(true)}>
            <Plus /> New
          </Button>
        </CardHeader>
        <CardContent>
          <ul className="divide-y rounded-md border">
            {me.memberships.map((m) => {
              const current = m.org_id === org.org_id;
              return (
                <li key={m.org_id} className="flex items-center gap-3 px-3 py-2.5 text-sm">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{m.org_name}</div>
                    <div className="text-xs text-muted-foreground">
                      {ROLE_LABELS[m.role]} · <span className="capitalize">{m.plan}</span>
                    </div>
                  </div>
                  {current ? (
                    <Badge variant="outline">
                      <Check className="size-3" /> Current
                    </Badge>
                  ) : (
                    <Button size="sm" variant="ghost" onClick={() => switchOrg(m.org_id)}>
                      Switch
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        </CardContent>
      </Card>
      <CreateWorkspaceDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}

function RenameForm({ current }: { current: string }) {
  const { reload } = useAuth();
  const qc = useQueryClient();
  const orgKey = useOrgKey();
  const [name, setName] = useState(current);
  const rename = useMutation({
    mutationFn: () => api("/api/org", { method: "PATCH", body: { name: name.trim() } }),
    onSuccess: async () => {
      await reload();
      qc.invalidateQueries({ queryKey: [orgKey] });
      toast.success("Workspace renamed");
    },
    onError: (e) => toast.error(e.message),
  });
  const trimmed = name.trim();
  return (
    <form
      className="flex flex-col gap-2 sm:flex-row sm:items-end"
      onSubmit={(e) => {
        e.preventDefault();
        rename.mutate();
      }}
    >
      <div className="flex-1 space-y-1.5">
        <Label htmlFor="org-name">Workspace name</Label>
        <Input id="org-name" value={name} onChange={(e) => setName(e.target.value)} minLength={2} maxLength={200} required />
      </div>
      <Button type="submit" loading={rename.isPending} disabled={trimmed.length < 2 || trimmed === current}>
        Save name
      </Button>
    </form>
  );
}

function CreateWorkspaceDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { reload, switchOrg } = useAuth();
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => api<{ id: string; name: string }>("/api/orgs", { body: { name: name.trim() } }),
    onSuccess: async (o) => {
      await reload();
      toast.success(`Workspace “${o.name}” created`, {
        description: "You are its owner. It starts empty on the Starter plan.",
        action: { label: "Switch", onClick: () => switchOrg(o.id) },
      });
      setName("");
      onOpenChange(false);
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Create a workspace" description="A separate organization with its own deals, members and plan.">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="new-org-name">Workspace name</Label>
            <Input
              id="new-org-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Harbor Capital Partners"
              minLength={2}
              maxLength={200}
              required
              autoFocus
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending} disabled={name.trim().length < 2}>
              Create workspace
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ----------------------------------------------------------------- members
function MembersTab() {
  const { me, org, hasRole, reload } = useAuth();
  const qc = useQueryClient();
  const orgKey = useOrgKey();
  const isAdmin = hasRole("admin");
  const isOwner = hasRole("owner");
  const members = useQuery({ queryKey: [orgKey, "members"], queryFn: () => api<Member[]>("/api/org/members") });
  const billing = useBilling();
  const [removing, setRemoving] = useState<Member | null>(null);

  const changeRole = useMutation({
    mutationFn: ({ user_id, role }: { user_id: string; role: Role }) =>
      api<Member>(`/api/org/members/${user_id}`, { method: "PATCH", body: { role } }),
    onSuccess: async (m) => {
      toast.success(`${m.name} is now ${ROLE_LABELS[m.role].toLowerCase()}`);
      if (m.user_id === me?.user.id) await reload();
      qc.invalidateQueries({ queryKey: [orgKey] });
    },
    onError: (e) => toast.error(e.message),
  });

  const remove = useMutation({
    mutationFn: (m: Member) => api(`/api/org/members/${m.user_id}`, { method: "DELETE" }),
    onSuccess: (_, m) => {
      toast.success(`${m.name} was removed from the workspace`);
      setRemoving(null);
      qc.invalidateQueries({ queryKey: [orgKey] });
    },
    onError: (e) => toast.error(e.message),
  });

  if (!org || !me) return null;
  const myRole = org.role;

  /** Mirrors the obvious server rules; the API remains the authority. */
  const canEditRole = (m: Member) => {
    if (!isAdmin) return false;
    if (m.user_id === me.user.id) return isOwner; // owners may step down (server keeps ≥1 owner)
    if (m.role === "owner") return isOwner;
    return isOwner || RANK[m.role] < RANK[myRole];
  };
  const canRemove = (m: Member) => {
    if (!isAdmin || m.user_id === me.user.id) return false;
    if (m.role === "owner") return isOwner;
    if (m.role === "admin") return isOwner;
    return true;
  };
  const roleOptions: Role[] = isOwner ? ["owner", "admin", "analyst", "viewer"] : ["admin", "analyst", "viewer"];
  const plan = billing.data ? billing.data.plans[billing.data.plan] : undefined;

  return (
    <div className="space-y-4">
      {!isAdmin && (
        <Callout>You have read-only access to the member list. Ask an admin or owner to change roles or invite people.</Callout>
      )}
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-3">
          <div>
            <CardTitle>Members</CardTitle>
            <CardDescription>
              Owners manage billing and ownership; admins manage members; analysts edit deals; viewers read only.
            </CardDescription>
          </div>
          {billing.data && plan && (
            <span className="shrink-0 text-xs tabular text-muted-foreground">
              {billing.data.usage.members} / {limitText(plan.max_members)} seats
            </span>
          )}
        </CardHeader>
        {members.isLoading && <LoadingBlock rows={3} className="px-5 pb-5" />}
        {members.error && (
          <CardContent>
            <ErrorBlock error={members.error} />
          </CardContent>
        )}
        {members.data && (
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Name</TH>
                <TH>Email</TH>
                <TH>Role</TH>
                <TH>Joined</TH>
                {isAdmin && (
                  <TH className="w-12">
                    <span className="sr-only">Actions</span>
                  </TH>
                )}
              </TR>
            </THead>
            <TBody>
              {members.data.map((m) => {
                const self = m.user_id === me.user.id;
                const pending = changeRole.isPending && changeRole.variables?.user_id === m.user_id;
                return (
                  <TR key={m.user_id}>
                    <TD>
                      <span className="font-medium">{m.name}</span>
                      {self && (
                        <Badge variant="outline" className="ml-2">
                          You
                        </Badge>
                      )}
                    </TD>
                    <TD className="text-muted-foreground">{m.email}</TD>
                    <TD>
                      {canEditRole(m) ? (
                        <Select
                          value={m.role}
                          disabled={pending}
                          onChange={(e) => changeRole.mutate({ user_id: m.user_id, role: e.target.value as Role })}
                          className="h-8 w-32"
                          aria-label={`Role for ${m.name}`}
                        >
                          {(roleOptions.includes(m.role) ? roleOptions : [m.role, ...roleOptions]).map((r) => (
                            <option key={r} value={r}>
                              {ROLE_LABELS[r]}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <Badge variant={m.role === "owner" ? "accent" : "default"}>{ROLE_LABELS[m.role]}</Badge>
                      )}
                    </TD>
                    <TD className="whitespace-nowrap text-muted-foreground">{shortDate(m.joined_at)}</TD>
                    {isAdmin && (
                      <TD className="text-right">
                        {canRemove(m) && (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => setRemoving(m)}
                            aria-label={`Remove ${m.name}`}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 />
                          </Button>
                        )}
                      </TD>
                    )}
                  </TR>
                );
              })}
            </TBody>
          </Table>
        )}
      </Card>

      {isAdmin && <InvitationsCard canInviteAdmin={isOwner} />}

      <Dialog open={!!removing} onOpenChange={(o) => !o && setRemoving(null)}>
        <DialogContent
          title="Remove member?"
          description={
            removing
              ? `${removing.name} (${removing.email}) will immediately lose access to this workspace. Deals they own stay in the workspace.`
              : undefined
          }
        >
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setRemoving(null)}>
              Cancel
            </Button>
            <Button variant="destructive" loading={remove.isPending} onClick={() => removing && remove.mutate(removing)}>
              Remove member
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function InvitationsCard({ canInviteAdmin }: { canInviteAdmin: boolean }) {
  const qc = useQueryClient();
  const orgKey = useOrgKey();
  const invitations = useQuery({
    queryKey: [orgKey, "invitations"],
    queryFn: () => api<Invitation[]>("/api/org/invitations"),
  });
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("analyst");
  const [created, setCreated] = useState<InvitationCreated | null>(null);
  const [now] = useState(() => Date.now());

  const invite = useMutation({
    mutationFn: () => api<InvitationCreated>("/api/org/invitations", { body: { email: email.trim(), role } }),
    onSuccess: (inv) => {
      setCreated(inv);
      setEmail("");
      toast.success(`Invitation created for ${inv.email}`);
      qc.invalidateQueries({ queryKey: [orgKey, "invitations"] });
      qc.invalidateQueries({ queryKey: [orgKey, "audit"] });
    },
    onError: (e) => toast.error(e.message),
  });

  const revoke = useMutation({
    mutationFn: (id: string) => api(`/api/org/invitations/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Invitation revoked");
      qc.invalidateQueries({ queryKey: [orgKey, "invitations"] });
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Invitations</CardTitle>
        <CardDescription>Invite colleagues by email. Links expire after 7 days.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="grid gap-3 sm:grid-cols-[1fr_10rem_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            invite.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="invite-email">Email</Label>
            <Input
              id="invite-email"
              type="email"
              required
              autoComplete="off"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="colleague@firm.com"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="invite-role">Role</Label>
            <Select id="invite-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
              <option value="analyst">Analyst</option>
              <option value="viewer">Viewer</option>
              <option value="admin" disabled={!canInviteAdmin}>
                Admin{canInviteAdmin ? "" : " (owners only)"}
              </option>
            </Select>
          </div>
          <Button type="submit" loading={invite.isPending}>
            <Mail /> Send invite
          </Button>
        </form>

        {created && <InviteLink invitation={created} onDismiss={() => setCreated(null)} />}

        {invitations.isLoading && <LoadingBlock rows={2} />}
        {invitations.error && <ErrorBlock error={invitations.error} />}
        {invitations.data && invitations.data.length === 0 && (
          <p className="text-sm text-muted-foreground">No invitations yet.</p>
        )}
        {invitations.data && invitations.data.length > 0 && (
          <div className="rounded-md border">
            <Table>
              <THead>
                <TR className="hover:bg-transparent">
                  <TH>Email</TH>
                  <TH>Role</TH>
                  <TH>Status</TH>
                  <TH>Sent</TH>
                  <TH>Expires</TH>
                  <TH className="w-20">
                    <span className="sr-only">Actions</span>
                  </TH>
                </TR>
              </THead>
              <TBody>
                {invitations.data.map((inv) => {
                  const status = inviteStatus(inv, now);
                  return (
                    <TR key={inv.id}>
                      <TD className="font-medium">{inv.email}</TD>
                      <TD className="text-muted-foreground">{ROLE_LABELS[inv.role] ?? inv.role}</TD>
                      <TD>
                        <Badge variant={INVITE_TONE[status]} className="capitalize">
                          {status}
                        </Badge>
                      </TD>
                      <TD className="whitespace-nowrap text-muted-foreground">{shortDate(inv.created_at)}</TD>
                      <TD className="whitespace-nowrap text-muted-foreground">
                        {status === "pending" ? shortDate(inv.expires_at) : "—"}
                      </TD>
                      <TD className="text-right">
                        {status === "pending" && (
                          <Button
                            variant="ghost"
                            size="sm"
                            loading={revoke.isPending && revoke.variables === inv.id}
                            onClick={() => revoke.mutate(inv.id)}
                            aria-label={`Revoke invitation for ${inv.email}`}
                          >
                            Revoke
                          </Button>
                        )}
                      </TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function InviteLink({ invitation, onDismiss }: { invitation: InvitationCreated; onDismiss: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(invitation.accept_url);
      setCopied(true);
      toast.success("Invitation link copied");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      ref.current?.select();
      toast.message("Press Ctrl/Cmd + C to copy the selected link");
    }
  };
  return (
    <div className="space-y-2 rounded-md border border-accent/40 bg-accent/5 p-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="text-sm">
          <span className="font-medium">Invitation link for {invitation.email}</span>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Email delivery is not configured in this environment; share this link. It works once and expires{" "}
            {shortDate(invitation.expires_at)}.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
      <div className="flex gap-2">
        <Label htmlFor="invite-link" className="sr-only">
          Invitation link
        </Label>
        <Input
          id="invite-link"
          ref={ref}
          readOnly
          value={invitation.accept_url}
          onFocus={(e) => e.currentTarget.select()}
          className="font-mono text-xs"
        />
        <Button variant="outline" onClick={copy} aria-label="Copy invitation link">
          {copied ? <Check /> : <Copy />}
          <span className="hidden sm:inline">{copied ? "Copied" : "Copy"}</span>
        </Button>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- billing
function BillingTab() {
  const { hasRole, reload } = useAuth();
  const qc = useQueryClient();
  const orgKey = useOrgKey();
  const billing = useBilling();
  const features = useFeatures();
  const isOwner = hasRole("owner");
  const [target, setTarget] = useState<string | null>(null);

  const change = useMutation({
    mutationFn: (plan: string) => api<{ plan?: string; checkout_url?: string }>("/api/billing/plan", { body: { plan } }),
    onSuccess: async (res, plan) => {
      if (res.checkout_url) {
        toast.message("Redirecting to secure checkout…");
        window.location.assign(res.checkout_url);
        return;
      }
      setTarget(null);
      await reload();
      qc.invalidateQueries({ queryKey: [orgKey] });
      toast.success(`Plan changed to ${billing.data?.plans[plan]?.label ?? plan}`);
    },
    onError: (e) => toast.error(e.message),
  });

  if (billing.isLoading) return <LoadingBlock rows={5} />;
  if (billing.error) return <ErrorBlock error={billing.error} />;
  if (!billing.data) return null;
  const b = billing.data;
  const current = b.plans[b.plan];
  const keys = [...PLAN_ORDER.filter((k) => k in b.plans), ...Object.keys(b.plans).filter((k) => !PLAN_ORDER.includes(k))];
  const featureLabel = (k: string) => features.data?.[k]?.label ?? k;
  const targetPlan = target ? b.plans[target] : undefined;
  const overLimits = (p: Plan) =>
    [
      p.max_deals !== null && b.usage.deals > p.max_deals ? `${b.usage.deals} deals (limit ${p.max_deals})` : null,
      p.max_members !== null && b.usage.members > p.max_members ? `${b.usage.members} members (limit ${p.max_members})` : null,
    ].filter(Boolean) as string[];

  return (
    <div className="space-y-4">
      {b.billing_mode === "manual" && (
        <Callout title="Manual billing mode">
          Stripe-ready: billing runs in manual mode until STRIPE keys are configured. Plan changes apply immediately and are
          recorded in the audit log.
        </Callout>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <UsageCard label="Deals" used={b.usage.deals} max={current?.max_deals ?? null} />
        <UsageCard label="Members" used={b.usage.members} max={current?.max_members ?? null} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        {keys.map((k) => {
          const p = b.plans[k];
          const isCurrent = k === b.plan;
          return (
            <Card key={k} className={cn("flex flex-col", isCurrent && "border-accent ring-1 ring-accent/40")}>
              <CardHeader>
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-base">{p.label}</CardTitle>
                  {isCurrent && <Badge variant="accent">Current plan</Badge>}
                </div>
                <div className="mt-1 flex items-baseline gap-1">
                  {isNum(p.price_monthly) ? (
                    <>
                      <span className="text-2xl font-semibold tabular tracking-tight">${num(p.price_monthly)}</span>
                      <span className="text-xs text-muted-foreground">/ month</span>
                    </>
                  ) : (
                    <span className="text-2xl font-semibold tracking-tight">Custom</span>
                  )}
                </div>
              </CardHeader>
              <CardContent className="flex flex-1 flex-col gap-4">
                <dl className="grid grid-cols-2 gap-2 text-sm">
                  <div className="rounded-md bg-muted/60 px-2.5 py-2">
                    <dt className="text-xs text-muted-foreground">Deals</dt>
                    <dd className="font-medium tabular">{limitText(p.max_deals)}</dd>
                  </div>
                  <div className="rounded-md bg-muted/60 px-2.5 py-2">
                    <dt className="text-xs text-muted-foreground">Members</dt>
                    <dd className="font-medium tabular">{limitText(p.max_members)}</dd>
                  </div>
                </dl>
                <ul className="flex-1 space-y-1.5 text-sm" aria-label={`${p.label} features`}>
                  {p.features.map((f) => (
                    <li key={f} className="flex items-start gap-2">
                      <Check className="mt-0.5 size-3.5 shrink-0 text-success" aria-hidden />
                      <span>{featureLabel(f)}</span>
                    </li>
                  ))}
                </ul>
                {!isCurrent &&
                  (isOwner ? (
                    <Button variant={k === "enterprise" ? "outline" : "default"} onClick={() => setTarget(k)}>
                      Switch to {p.label}
                    </Button>
                  ) : (
                    <p className="text-xs text-muted-foreground">Only owners can change the plan.</p>
                  ))}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Dialog open={!!target} onOpenChange={(o) => !o && setTarget(null)}>
        <DialogContent
          title={`Switch to ${targetPlan?.label ?? ""}?`}
          description={
            b.billing_mode === "stripe"
              ? "You will be redirected to Stripe Checkout to confirm the subscription."
              : "In manual billing mode the change takes effect immediately."
          }
        >
          {targetPlan && overLimits(targetPlan).length > 0 && (
            <Callout tone="warn" title="Usage exceeds this plan">
              You currently have {overLimits(targetPlan).join(" and ")}. Existing data is kept, but you won&apos;t be able
              to add more until usage is within the limit.
            </Callout>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setTarget(null)}>
              Cancel
            </Button>
            <Button loading={change.isPending} onClick={() => target && change.mutate(target)}>
              Confirm change
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function UsageCard({ label, used, max }: { label: string; used: number; max: number | null }) {
  const ratio = max ? Math.min(1, used / max) : 0;
  const over = max !== null && used >= max;
  return (
    <Card className="px-4 py-3.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
        <span className="text-xs text-muted-foreground tabular">
          {max === null ? "Unlimited" : `${num(max - Math.min(used, max))} remaining`}
        </span>
      </div>
      <div className="mt-1 text-xl font-semibold tabular tracking-tight">
        {num(used)}
        <span className="text-sm font-normal text-muted-foreground"> / {limitText(max)}</span>
      </div>
      {max !== null && (
        <div
          className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-label={`${label} usage`}
          aria-valuemin={0}
          aria-valuemax={max}
          aria-valuenow={used}
        >
          <div className={cn("h-full rounded-full", over ? "bg-warning" : "bg-primary")} style={{ width: `${ratio * 100}%` }} />
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- features
function FeaturesTab() {
  const { hasRole } = useAuth();
  const qc = useQueryClient();
  const orgKey = useOrgKey();
  const features = useFeatures();
  const detail = useOrgDetail();
  const billing = useBilling();
  const isOwner = hasRole("owner");

  const save = useMutation({
    mutationFn: ({ overrides }: { overrides: Record<string, boolean>; key: string }) =>
      api("/api/org", { method: "PATCH", body: { feature_overrides: overrides } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [orgKey] });
      toast.success("Feature settings saved");
    },
    onError: (e) => toast.error(e.message),
  });

  if (features.isLoading || detail.isLoading) return <LoadingBlock rows={6} />;
  if (features.error) return <ErrorBlock error={features.error} />;
  if (detail.error) return <ErrorBlock error={detail.error} />;
  if (!features.data || !detail.data) return null;

  const overrides = detail.data.feature_overrides ?? {};
  const planFeatures = billing.data ? new Set(billing.data.plans[billing.data.plan]?.features ?? []) : null;
  const entries = Object.entries(features.data).sort((a, b) => a[1].phase - b[1].phase || a[1].label.localeCompare(b[1].label));

  const setOverride = (key: string, value: boolean | null) => {
    const next = { ...overrides };
    if (value === null) delete next[key];
    else next[key] = value;
    save.mutate({ overrides: next, key });
  };

  return (
    <div className="space-y-4">
      <Callout title="How feature flags work">
        Flags gate incomplete or plan-restricted modules. Each feature resolves as platform default → plan entitlement →
        workspace override. Phase badges show delivery maturity: <strong className="font-medium">Phase 1</strong> core and
        production-ready, <strong className="font-medium">Phase 2</strong> advanced analytics,{" "}
        <strong className="font-medium">Phase 3</strong> beta or early-access modules that may be incomplete.
        {!isOwner && " Only owners can change overrides."}
      </Callout>
      <Card>
        <ul className="divide-y">
          {entries.map(([key, f]) => {
            const overridden = key in overrides;
            const planDefault = planFeatures ? f.default && planFeatures.has(key) : null;
            const id = `feature-${key}`;
            const pending = save.isPending && save.variables?.key === key;
            return (
              <li key={key} className="flex flex-col gap-3 px-5 py-3.5 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Label htmlFor={id} className="text-sm font-medium text-foreground">
                      {f.label}
                    </Label>
                    <Badge variant={f.phase === 1 ? "success" : f.phase === 2 ? "accent" : "warning"}>Phase {f.phase}</Badge>
                    {overridden && (
                      <Tooltip content="This workspace overrides the plan default.">
                        <Badge variant="outline" tabIndex={0}>
                          Override
                        </Badge>
                      </Tooltip>
                    )}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    <span className="font-mono">{key}</span>
                    {planDefault !== null && <> · Plan default: {planDefault ? "on" : "off"}</>}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {isOwner && overridden && (
                    <Button variant="ghost" size="sm" disabled={save.isPending} onClick={() => setOverride(key, null)}>
                      Reset to default
                    </Button>
                  )}
                  <span className={cn("w-7 text-right text-xs", f.enabled ? "text-foreground" : "text-muted-foreground")}>
                    {f.enabled ? "On" : "Off"}
                  </span>
                  <Switch
                    id={id}
                    checked={f.enabled}
                    disabled={!isOwner || save.isPending}
                    aria-busy={pending || undefined}
                    onCheckedChange={(v) => setOverride(key, v)}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------- audit
function fmtValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? num(v) : Math.abs(v) < 1 ? String(+v.toFixed(4)) : num(v, 2);
  if (typeof v === "string") return v.length > 48 ? `${v.slice(0, 45)}…` : v;
  if (typeof v === "boolean") return v ? "true" : "false";
  if (Array.isArray(v)) return v.every((x) => typeof x !== "object") && v.length <= 4 ? v.map(fmtValue).join(", ") : `[${v.length} items]`;
  if (typeof v === "object") {
    const e = Object.entries(v as Record<string, unknown>);
    const inner = e
      .slice(0, 3)
      .map(([k, x]) => `${k}: ${typeof x === "object" && x !== null ? "…" : fmtValue(x)}`)
      .join(", ");
    return `{${inner}${e.length > 3 ? ", …" : ""}}`;
  }
  return String(v);
}

function summarise(details: Record<string, unknown> | null | undefined): string {
  return Object.entries(details ?? {})
    .map(([k, v]) => `${k}: ${fmtValue(v)}`)
    .join(" · ");
}

function AuditTab() {
  const audit = useAudit();
  const [q, setQ] = useState("");
  const rows = useMemo(
    () => (audit.data ?? []).map((a) => ({ ...a, summary: summarise(a.details) })),
    [audit.data],
  );
  const needle = q.trim().toLowerCase();
  const filtered = needle
    ? rows.filter((a) =>
        [a.action, a.entity_type, a.entity_id ?? "", a.user_name ?? "System", a.summary].some((s) => s.toLowerCase().includes(needle)),
      )
    : rows;

  return (
    <Card>
      <CardHeader className="gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <CardTitle>Audit log</CardTitle>
          <CardDescription>The 200 most recent actions in this workspace. Entries are immutable.</CardDescription>
        </div>
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter by user, action, details…"
            className="pl-8"
            aria-label="Filter audit log"
            type="search"
          />
        </div>
      </CardHeader>
      {audit.isLoading && <LoadingBlock rows={6} className="px-5 pb-5" />}
      {audit.error && (
        <CardContent>
          <ErrorBlock error={audit.error} />
        </CardContent>
      )}
      {audit.data && rows.length === 0 && (
        <CardContent>
          <EmptyState icon={History} title="No activity yet" description="Actions such as underwriting runs and exports appear here." />
        </CardContent>
      )}
      {audit.data && rows.length > 0 && (
        <>
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Time</TH>
                <TH>User</TH>
                <TH>Action</TH>
                <TH>Entity</TH>
                <TH>Details</TH>
              </TR>
            </THead>
            <TBody>
              {filtered.map((a: AuditEntry & { summary: string }) => (
                <TR key={a.id}>
                  <TD className="whitespace-nowrap">
                    <time dateTime={a.created_at} title={new Date(a.created_at).toLocaleString()}>
                      {dateTime(a.created_at)}
                    </time>
                    <div className="text-[11px] text-muted-foreground">{relativeTime(a.created_at)}</div>
                  </TD>
                  <TD className="whitespace-nowrap">{a.user_name ?? <span className="text-muted-foreground">System</span>}</TD>
                  <TD>
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">{a.action}</code>
                  </TD>
                  <TD className="whitespace-nowrap text-muted-foreground">
                    {a.entity_type}
                    {a.entity_id && <span className="ml-1 font-mono text-[11px]">{a.entity_id.slice(0, 8)}</span>}
                  </TD>
                  <TD className="max-w-md">
                    <div className="truncate text-xs text-muted-foreground" title={a.summary || undefined}>
                      {a.summary || "—"}
                    </div>
                  </TD>
                </TR>
              ))}
              {filtered.length === 0 && (
                <TR className="hover:bg-transparent">
                  <TD colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                    No entries match “{q}”.
                  </TD>
                </TR>
              )}
            </TBody>
          </Table>
          <div className="border-t px-5 py-2.5 text-xs text-muted-foreground" aria-live="polite">
            Showing {filtered.length} of {rows.length} entries
          </div>
        </>
      )}
    </Card>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <SettingsInner />
    </Suspense>
  );
}
