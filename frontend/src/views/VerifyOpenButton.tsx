import { useState } from "react";
import { LoaderCircle, RefreshCw } from "lucide-react";
import { API_BASE } from "../config";
import { errorText } from "../lib";

interface VerifyResult {
  status: "open" | "closed" | "unknown";
  reason: string;
  checked_at: string;
}

const TONES: Record<string, string> = {
  open: "text-emerald-300",
  closed: "text-rose-300",
  unknown: "text-amber-200",
};

const LABELS: Record<string, string> = {
  open: "Still open",
  closed: "Closed: no longer on the employer's site",
  unknown: "Could not confirm",
};

// Asks the API to re-read the job's own career source. It only ever marks a job closed when the
// source answered normally and no longer lists it; failures and doubtful answers change nothing.
export function VerifyOpenButton({ jobId, lastSeenAt }: { jobId: number; lastSeenAt: string | null }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const verify = () => {
    setBusy(true);
    setError(null);
    fetch(`${API_BASE}/api/jobs/${jobId}/verify-open`, { method: "POST" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Check failed (${response.status}).`);
        return (await response.json()) as VerifyResult;
      })
      .then(setResult)
      .catch((caught: unknown) => setError(errorText(caught)))
      .finally(() => setBusy(false));
  };

  return (
    <div className="flex flex-col items-start gap-1 lg:items-end">
      <button className="secondary-button !px-3 !py-2" onClick={verify} disabled={busy} title="Re-read the employer's career source to see whether this job is still listed">
        {busy ? <LoaderCircle size={13} className="loading-ring" /> : <RefreshCw size={13} />}
        {busy ? "Checking..." : "Check if still open"}
      </button>
      {result && (
        <p className={`max-w-64 text-[11px] leading-4 ${TONES[result.status]}`}>
          <span className="font-semibold">{LABELS[result.status]}.</span> {result.reason}
        </p>
      )}
      {error && <p className="text-[11px] text-rose-300">{error}</p>}
      {!result && !error && lastSeenAt && (
        <p className="text-[10px] text-slate-500">Last seen listed: {new Date(lastSeenAt).toLocaleDateString()}</p>
      )}
    </div>
  );
}
