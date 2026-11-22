"use client";

import Link from "next/link";
import { brand } from "@/lib/brand";
import { usePathname, useRouter } from "next/navigation";
import { Fragment, useEffect, useRef, useState } from "react";
import { Bell, ChevronDown, LogOut, Menu, Search, X } from "lucide-react";
import { Logo } from "../Logo";
import { DASH_NAV, QUICK_ACTIONS } from "./nav";
import { logout } from "@/app/(auth)/actions";

interface Props {
  user: { name: string; email: string; workspace: string; role: string };
  children: React.ReactNode;
}

interface Note { id: string; title: string; created_at: string; read: boolean }
interface Team { id: string; name: string }

function useOutside(ref: React.RefObject<HTMLElement | null>, close: () => void) {
  useEffect(() => {
    const click = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && close();
    const key = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", click);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", click);
      document.removeEventListener("keydown", key);
    };
  }, [ref, close]);
}

/** Unread notification count: refreshed every minute, when the tab regains focus, and when the Notifications page changes something. */
function useUnread() {
  const [n, setN] = useState(0);
  useEffect(() => {
    let live = true;
    const pull = () => fetch("/app-api/notifications/count").then((r) => (r.ok ? r.json() : null)).then((j) => { if (live && j) setN(j.unread); }).catch(() => undefined);
    const first = setTimeout(pull, 0);
    const iv = setInterval(pull, 60000);
    window.addEventListener("notifications-changed", pull);
    window.addEventListener("focus", pull);
    return () => { live = false; clearTimeout(first); clearInterval(iv); window.removeEventListener("notifications-changed", pull); window.removeEventListener("focus", pull); };
  }, []);
  return n;
}

function GlobalSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [teams, setTeams] = useState<(Team & { league: string })[] | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useOutside(box, () => setOpen(false));

  async function loadTeams() {
    if (teams) return;
    try {
      const out: (Team & { league: string })[] = [];
      for (const l of ["nfl-fict", "csd-fict"]) {
        const r = await fetch(`/app-api/sports/teams?league_id=${l}`);
        if (r.ok) out.push(...((await r.json()).teams as Team[]).map((t) => ({ ...t, league: l })));
      }
      setTeams(out);
    } catch {
      setTeams([]);
    }
  }

  const needle = q.trim().toLowerCase();
  const pages = needle ? DASH_NAV.filter((n) => (n.label + " " + n.keywords).toLowerCase().includes(needle)) : [];
  const actions = needle ? QUICK_ACTIONS.filter((a) => (a.label + " " + a.keywords).toLowerCase().includes(needle)).slice(0, 4) : [];
  const teamHits = needle && teams ? teams.filter((t) => t.name.toLowerCase().includes(needle)).slice(0, 6) : [];
  const go = (href: string) => {
    setOpen(false);
    setQ("");
    router.push(href);
  };

  return (
    <div ref={box} className="relative w-full max-w-md" role="search">
      <label htmlFor="global-search" className="sr-only">Search {brand.name}</label>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden="true" />
      <input
        id="global-search"
        value={q}
        onFocus={() => { setOpen(true); loadTeams(); }}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        placeholder="Search pages, actions and teams…"
        autoComplete="off"
        className="w-full rounded-xl border border-line bg-bg/60 py-2 pl-9 pr-3 text-sm placeholder:text-muted/70 focus:border-violet focus:outline-none focus:ring-2 focus:ring-violet/40"
      />
      {open && needle && (
        <ul className="glass absolute left-0 right-0 top-full z-50 mt-2 max-h-80 overflow-auto rounded-xl p-1.5 shadow-2xl">
          {pages.map((p) => (
            <li key={p.href}>
              <button type="button" onClick={() => go(p.href)} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-white/5">
                <p.icon className="h-4 w-4 text-violet" aria-hidden="true" /> {p.label}
              </button>
            </li>
          ))}
          {actions.map((a) => (
            <li key={a.label}>
              <button type="button" onClick={() => go(a.href)} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-white/5">
                <span className="rounded bg-violet/15 px-1.5 text-[10px] font-semibold text-violet">ACTION</span> {a.label}
              </button>
            </li>
          ))}
          {teamHits.map((t) => (
            <li key={t.id}>
              <button type="button" onClick={() => go(`/dashboard/sports?league=${t.league}&team=${encodeURIComponent(t.id)}`)} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-white/5">
                <span className="rounded bg-cyan/15 px-1.5 text-[10px] font-semibold text-cyan">TEAM</span> {t.name}
                <span className="ml-auto text-[10px] text-muted">fictional</span>
              </button>
            </li>
          ))}
          {!pages.length && !teamHits.length && !actions.length && <li className="px-3 py-2 text-sm text-muted">{teams ? "No results." : "Searching…"}</li>}
        </ul>
      )}
    </div>
  );
}

function Notifications({ unread }: { unread: number }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Note[] | null>(null);
  const [err, setErr] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useOutside(ref, () => setOpen(false));

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next) {
      setErr(false);
      try {
        const r = await fetch("/app-api/notifications?limit=5");
        if (!r.ok) throw new Error();
        setItems((await r.json()).notifications);
      } catch {
        setErr(true);
      }
    }
  }
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={toggle} aria-expanded={open} aria-haspopup="true" aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"} className="relative rounded-lg p-2 text-muted hover:bg-white/5 hover:text-ink">
        <Bell className="h-5 w-5" />
        {unread > 0 && <span aria-hidden="true" className="absolute right-0.5 top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-cyan px-1 text-[10px] font-bold text-bg">{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && (
        <div className="glass absolute right-0 top-full z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl p-3 shadow-2xl">
          <h2 className="mb-2 text-sm font-semibold">Notifications</h2>
          {err ? <p role="alert" className="text-sm text-red-300">Could not load notifications.</p>
            : items === null ? <p className="text-sm text-muted">Loading…</p>
            : items.length === 0 ? <p className="text-sm text-muted">Nothing yet. Notifications appear here only for the alerts you switch on.</p>
            : <ul className="space-y-2">{items.map((a) => (
                <li key={a.id} className="text-sm">
                  <span className={a.read ? "text-muted" : "font-semibold"}>{a.title}</span>
                  <div className="text-[11px] text-muted">{new Date(a.created_at).toLocaleString()}</div>
                </li>))}</ul>}
          <Link href="/dashboard/notifications" onClick={() => setOpen(false)} className="mt-3 block text-xs text-violet underline">Open all notifications and alert rules</Link>
        </div>
      )}
    </div>
  );
}

function Profile({ user }: { user: Props["user"] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useOutside(ref, () => setOpen(false));
  const initials = user.name.split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-haspopup="true" aria-label="Account menu" className="flex items-center gap-2 rounded-xl p-1 pr-2 hover:bg-white/5">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/30 text-xs font-bold">{initials}</span>
        <ChevronDown className="hidden h-4 w-4 text-muted sm:block" aria-hidden="true" />
      </button>
      {open && (
        <div className="glass absolute right-0 top-full z-50 mt-2 w-64 rounded-xl p-2 shadow-2xl">
          <div className="border-b border-line px-3 pb-2 pt-1">
            <div className="truncate text-sm font-semibold">{user.name}</div>
            <div className="truncate text-xs text-muted">{user.email}</div>
            <div className="mt-1 text-[11px] text-muted">{user.workspace} · {user.role}</div>
          </div>
          <Link href="/dashboard/workspace" onClick={() => setOpen(false)} className="mt-1 block rounded-lg px-3 py-2 text-sm hover:bg-white/5">Workspaces &amp; library</Link>
          <Link href="/dashboard/settings" onClick={() => setOpen(false)} className="block rounded-lg px-3 py-2 text-sm hover:bg-white/5">Settings</Link>
          <form action={logout}>
            <button className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-white/5"><LogOut className="h-4 w-4" aria-hidden="true" /> Sign out</button>
          </form>
        </div>
      )}
    </div>
  );
}

function SideNav({ onNavigate, unread }: { onNavigate?: () => void; unread: number }) {
  const path = usePathname();
  // the most specific entry wins, so a child page (Live Predictions) does not also light up its parent (Sports)
  const current = DASH_NAV.filter((n) => (n.href === "/dashboard" ? path === n.href : path === n.href || path.startsWith(n.href + "/"))).sort((a, b) => b.href.length - a.href.length)[0]?.href;
  return (
    <nav aria-label="Dashboard" className="flex flex-col gap-0.5 p-3">
      {DASH_NAV.map((n) => {
        const active = n.href === current;
        return (
          <Fragment key={n.href}>
          {n.href === "/dashboard/history" && <p className="mt-3 px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted">Workspace tools</p>}
          <Link
            href={n.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors ${active ? "bg-primary/20 text-ink" : "text-muted hover:bg-white/5 hover:text-ink"}`}
          >
            <n.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="flex-1">{n.label}</span>
            {n.href === "/dashboard/notifications" && unread > 0 && <span className="rounded-full bg-cyan px-1.5 text-[10px] font-bold text-bg"><span className="sr-only">{unread} unread </span><span aria-hidden="true">{unread > 99 ? "99+" : unread}</span></span>}
            {n.status === "soon" && <span className="rounded-full border border-line px-1.5 text-[9px] uppercase tracking-wide text-muted">Soon</span>}
          </Link>
          </Fragment>
        );
      })}
    </nav>
  );
}

export function Shell({ user, children }: Props) {
  const [drawer, setDrawer] = useState(false);
  const unread = useUnread();
  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(false);
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);
  return (
    <div className="flex min-h-screen">
      <a href="#dash-main" className="skip-link">Skip to content</a>
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-line bg-bg2/60 lg:flex">
        <div className="flex h-16 items-center px-5"><Logo /></div>
        <div className="flex-1 overflow-y-auto"><SideNav unread={unread} /></div>
        <div className="border-t border-line p-4 text-[11px] leading-relaxed text-muted">
          Dev data is <strong className="text-cyan">fictional</strong>. Nothing here is a live prediction.
        </div>
      </aside>

      {drawer && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <button className="absolute inset-0 bg-black/60" aria-label="Close menu" onClick={() => setDrawer(false)} />
          <div className="relative h-full w-72 max-w-[85vw] overflow-y-auto border-r border-line bg-bg2">
            <div className="flex h-16 items-center justify-between px-5">
              <Logo />
              <button type="button" onClick={() => setDrawer(false)} aria-label="Close menu" className="rounded-lg p-2"><X className="h-5 w-5" /></button>
            </div>
            <SideNav unread={unread} onNavigate={() => setDrawer(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 flex h-16 items-center gap-2 border-b border-line bg-bg/85 px-3 backdrop-blur-xl sm:gap-4 sm:px-6">
          <button type="button" onClick={() => setDrawer(true)} aria-label="Open menu" aria-expanded={drawer} className="rounded-lg p-2 lg:hidden"><Menu className="h-6 w-6" /></button>
          <GlobalSearch />
          <div className="ml-auto flex items-center gap-1">
            <Notifications unread={unread} />
            <Profile user={user} />
          </div>
        </header>
        <main id="dash-main" className="mx-auto w-full max-w-7xl flex-1 px-3 py-6 sm:px-6">{children}</main>
      </div>
    </div>
  );
}
