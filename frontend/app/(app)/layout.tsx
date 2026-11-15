"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Shell } from "@/components/Shell";
import { LoadingRows } from "@/components/ui";
import { useAuth } from "@/lib/store";

export default function AppLayout({ children }: { children: ReactNode }) {
  const { token, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (ready && !token) router.replace("/login");
  }, [ready, token, router]);
  if (!ready || !token) {
    return (
      <div className="mx-auto max-w-xl p-8">
        <LoadingRows />
      </div>
    );
  }
  return <Shell>{children}</Shell>;
}
