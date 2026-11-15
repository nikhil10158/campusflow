"use client";

import { useQuery } from "@tanstack/react-query";
import { use } from "react";

import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

interface Verdict {
  result: string;
  pass: { type: string; plate: string | null; valid_from: string; valid_to: string } | null;
}

const COLOR: Record<string, string> = { VALID: "var(--good)", EXPIRED: "var(--bad)", NOT_FOUND: "var(--bad)", WRONG_LOT: "var(--warn)", REVOKED: "var(--bad)", NOT_YET_VALID: "var(--warn)" };

export default function PassPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const { data, isPending, isError } = useQuery({ queryKey: ["verify", token], queryFn: () => api<Verdict>(`/verify/pass/${encodeURIComponent(token)}`) });
  const result = isError ? "NOT_FOUND" : data?.result;
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm rounded-2xl border border-line bg-surface p-8 text-center shadow-lg">
        <p className="mb-2 text-xs uppercase tracking-widest text-muted">CampusFlow pass check · synthetic data</p>
        {isPending ? <div className="skeleton mx-auto h-16 w-40" /> : <div className="text-5xl font-bold" style={{ color: COLOR[result ?? "NOT_FOUND"] }}>{(result ?? "").replace(/_/g, " ")}</div>}
        {data?.pass && (
          <div className="mt-4 text-sm">
            <p className="font-medium">{data.pass.plate ?? data.pass.type}</p>
            <p className="text-muted">{fmtDateTime(data.pass.valid_from)} → {fmtDateTime(data.pass.valid_to)}</p>
          </div>
        )}
        <p className="mt-6 text-xs text-muted">This public page only verifies a pass. Gate staff mark it scanned from the Security page.</p>
      </div>
    </div>
  );
}
