"use client";

import { useMutation } from "@tanstack/react-query";
import { Camera, ScanLine } from "lucide-react";
import { useRef, useState } from "react";

import { Button, Card, ErrorBox, Field, Input, PageHeader, Select, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { useParkingLots } from "@/lib/hooks";
import { extractToken, fmtDateTime } from "@/lib/format";

interface ScanResult {
  result: "VALID" | "EXPIRED" | "WRONG_LOT" | "NOT_FOUND" | "REVOKED" | "NOT_YET_VALID";
  pass: { type: string; plate: string | null; valid_from: string; valid_to: string } | null;
}

const LOOK: Record<string, string> = {
  VALID: "bg-good text-[#07101f]",
  EXPIRED: "bg-bad text-[#07101f]",
  WRONG_LOT: "bg-warn text-[#07101f]",
  NOT_FOUND: "bg-bad text-[#07101f]",
  REVOKED: "bg-bad text-[#07101f]",
  NOT_YET_VALID: "bg-warn text-[#07101f]",
};

export default function SecurityPage() {
  const { data: lots } = useParkingLots();
  const [token, setToken] = useState("");
  const [lot, setLot] = useState("");
  const [camera, setCamera] = useState(false);
  const video = useRef<HTMLVideoElement>(null);

  const scan = useMutation({ mutationFn: (value: string) => api<ScanResult>("/passes/scan", { body: { token: extractToken(value), lot_id: lot ? Number(lot) : null } }) });

  async function startCamera() {
    const detectorClass = (window as unknown as { BarcodeDetector?: new (options: { formats: string[] }) => { detect: (source: HTMLVideoElement) => Promise<{ rawValue: string }[]> } }).BarcodeDetector;
    if (!detectorClass || !navigator.mediaDevices?.getUserMedia) {
      setCamera(false);
      alert("Camera scanning is not supported in this browser. Paste the token instead.");
      return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    setCamera(true);
    if (video.current) {
      video.current.srcObject = stream;
      await video.current.play();
    }
    const detector = new detectorClass({ formats: ["qr_code"] });
    const timer = setInterval(async () => {
      if (!video.current) return;
      const found = await detector.detect(video.current).catch(() => []);
      if (found.length) {
        clearInterval(timer);
        stream.getTracks().forEach((track) => track.stop());
        setCamera(false);
        setToken(found[0].rawValue);
        scan.mutate(found[0].rawValue);
      }
    }, 500);
  }

  return (
    <>
      <PageHeader title="Gate scan" subtitle="Scan or paste a pass. The result is the signed token checked against its booking window and lot." />
      <div className="mx-auto max-w-xl space-y-4">
        <Card>
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); scan.mutate(token); }}>
            <Field label="Pass token or link"><Input value={token} onChange={(e) => setToken(e.target.value)} placeholder="12.ab34cd… or https://…/pass/12.ab34…" autoFocus /></Field>
            <Field label="This gate belongs to lot"><Select value={lot} onChange={(e) => setLot(e.target.value)}><option value="">Any lot</option>{lots?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select></Field>
            <div className="flex gap-2">
              <Button type="submit" busy={scan.isPending} className="flex-1"><ScanLine className="h-4 w-4" /> Check pass</Button>
              <Button type="button" variant="outline" onClick={startCamera}><Camera className="h-4 w-4" /> Camera</Button>
            </div>
          </form>
          {camera && <video ref={video} className="mt-3 w-full rounded-lg" muted playsInline />}
        </Card>
        {scan.isError && <ErrorBox error={scan.error} />}
        {scan.data && (
          <div role="status" className={cx("rounded-2xl p-8 text-center", LOOK[scan.data.result])}>
            <div className="text-5xl font-bold tracking-tight">{scan.data.result === "VALID" ? "VALID" : scan.data.result.replace(/_/g, " ")}</div>
            {scan.data.pass && (
              <p className="mt-3 text-lg">{scan.data.pass.plate ?? scan.data.pass.type} · {fmtDateTime(scan.data.pass.valid_from)} → {fmtDateTime(scan.data.pass.valid_to)}</p>
            )}
          </div>
        )}
      </div>
    </>
  );
}

