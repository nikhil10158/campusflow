"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useAuth } from "@/lib/store";

import { cx } from "./ui";

interface Item {
  id: number;
  kind: string;
  title: string;
  body: string;
  booking_id: number | null;
  read: boolean;
  created_at: string;
}

interface Feed {
  items: Item[];
  unread: number;
}

const HOME: Record<string, string> = { admin: "/approvals", approver: "/approvals", faculty: "/faculty", student: "/student" };

export function NotificationBell() {
  const user = useAuth((state) => state.user);
  const router = useRouter();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const feed = useQuery({ queryKey: ["notifications"], queryFn: () => api<Feed>("/notifications", { params: { limit: 30 } }), refetchInterval: 15000, enabled: !!user });
  const refresh = () => client.invalidateQueries({ queryKey: ["notifications"] });
  const read = useMutation({ mutationFn: (id: number) => api(`/notifications/${id}/read`, { method: "POST" }), onSuccess: refresh });
  const readAll = useMutation({ mutationFn: () => api("/notifications/read-all", { method: "POST" }), onSuccess: refresh });
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent && event.key === "Escape") setOpen(false);
      if (event instanceof MouseEvent && box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", close);
    };
  }, [open]);
  const unread = feed.data?.unread ?? 0;
  const items = feed.data?.items ?? [];

  function openItem(item: Item) {
    if (!item.read) read.mutate(item.id);
    setOpen(false);
    router.push(item.kind === "new_request" ? "/approvals" : HOME[user?.role ?? ""] ?? "/");
  }

  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        title="Notifications"
        className="relative grid h-9 w-9 place-items-center rounded-full border border-line bg-surface text-ink transition duration-200 hover:border-primary hover:bg-surface2 active:scale-90"
      >
        <Bell className="h-[18px] w-[18px]" aria-hidden />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 grid min-w-[18px] place-items-center rounded-full bg-accent px-1 text-[11px] font-bold leading-[18px] text-[#04121f]">{unread > 99 ? "99+" : unread}</span>
        )}
      </button>
      {open && (
        <div className="pop absolute right-0 top-full z-40 mt-2 w-96 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-line bg-surface shadow-lift">
          <div className="flex items-center justify-between border-b border-line px-3 py-2.5">
            <p className="font-semibold">Notifications {unread > 0 && <span className="text-sm font-normal text-muted">({unread} unread)</span>}</p>
            <button onClick={() => readAll.mutate()} disabled={unread === 0 || readAll.isPending} className="flex items-center gap-1 rounded-lg px-2 py-1 text-sm font-medium text-link hover:bg-surface2 disabled:opacity-40 disabled:hover:bg-transparent">
              <CheckCheck className="h-4 w-4" aria-hidden /> Mark all as read
            </button>
          </div>
          <ul className="max-h-[min(26rem,70vh)] overflow-y-auto p-1.5">
            {feed.isPending && <li className="p-3 text-sm text-muted">Loading…</li>}
            {!feed.isPending && items.length === 0 && <li className="p-4 text-center text-sm text-muted">No notifications yet.</li>}
            {items.map((item) => (
              <li key={item.id} className={cx("flex items-start gap-2 rounded-lg px-2.5 py-2 hover:bg-surface2", !item.read && "bg-tint")}>
                <button onClick={() => openItem(item)} className="min-w-0 flex-1 text-left">
                  <span className="flex items-center gap-1.5 text-[15px] font-medium">
                    {!item.read && <span className="h-2 w-2 shrink-0 rounded-full bg-accent" aria-hidden />}
                    <span className="truncate">{item.title}</span>
                  </span>
                  {item.body && <span className="mt-0.5 line-clamp-2 block text-sm text-muted">{item.body}</span>}
                  <span className="mt-0.5 block text-xs text-muted">{fmtDateTime(item.created_at)}</span>
                </button>
                {!item.read && (
                  <button onClick={() => read.mutate(item.id)} className="mt-0.5 shrink-0 rounded-lg px-1.5 py-0.5 text-xs font-medium text-link hover:underline">
                    Mark as read
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
