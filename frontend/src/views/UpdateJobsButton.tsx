import { useCallback, useEffect, useRef, useState } from "react";
import { CloudDownload, LoaderCircle } from "lucide-react";
import { apiRequest, errorText } from "../lib";

interface Step {
  name: string;
  state: "running" | "done" | "failed";
  summary: string[];
  error: string | null;
  sources_done?: number;
}

interface UpdateStatus {
  state: "idle" | "running" | "finished" | "failed";
  started_at: string | null;
  finished_at: string | null;
  current: string | null;
  progress?: string | null;
  interrupted?: boolean;
  steps: Step[];
}

// Reads every company career page (closing jobs that were taken down) and the remote job boards.
// It takes a few minutes; the list refreshes when it is done.
export function UpdateJobsButton({ onFinished }: { onFinished: () => void }) {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wasRunning = useRef(false);

  const poll = useCallback(() => {
    apiRequest<UpdateStatus>("/api/sync/status")
      .then((next) => {
        setStatus(next);
        if (wasRunning.current && next.state !== "running") onFinished();
        wasRunning.current = next.state === "running";
      })
      .catch((caught: unknown) => setError(errorText(caught)));
  }, [onFinished]);

  useEffect(() => {
    poll();
  }, [poll]);

  useEffect(() => {
    if (status?.state !== "running") return;
    const timer = window.setInterval(poll, 4000);
    return () => window.clearInterval(timer);
  }, [status?.state, poll]);

  const start = () => {
    setError(null);
    apiRequest<UpdateStatus>("/api/sync/start", { method: "POST" })
      .then((next) => {
        wasRunning.current = true;
        setStatus(next);
      })
      .catch((caught: unknown) => setError(errorText(caught)));
  };

  const running = status?.state === "running";
  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <button className="primary-button" onClick={start} disabled={running} title="Read every company career page and the remote job boards, and close jobs that were taken down">
        {running ? <LoaderCircle size={14} className="loading-ring" /> : <CloudDownload size={14} />}
        {running ? `Updating: ${status?.current ?? "starting"}...` : "Update jobs now"}
      </button>
      {running && (
        <div className="max-w-72 space-y-0.5 text-[10px] text-slate-500">
          <p>
            {status?.steps.find((step) => step.state === "running")?.sources_done ?? 0} sources read so far.
            {status?.progress ? ` Now: ${status.progress}` : ""}
          </p>
          <p>This takes a few minutes. You can keep using JobPilot or restart it; the list refreshes when the update is done.</p>
        </div>
      )}
      {!running && status?.interrupted && (
        <p className="max-w-72 text-[10px] text-amber-200">The last update was stopped before it finished. What it had already saved is kept; press Update jobs now to run it again.</p>
      )}
      {!running && status && status.steps.length > 0 && (
        <ul className="max-w-80 space-y-0.5 text-[10px] text-slate-400">
          {status.steps.map((step) => (
            <li key={step.name} className={step.state === "failed" ? "text-amber-200" : ""}>
              <span className="font-semibold">{step.name}:</span>{" "}
              {step.summary.length > 0 ? step.summary.join(" · ") : step.error ?? step.state}
              {step.state === "failed" && step.summary.length > 0 && step.error ? ` (${step.error})` : ""}
            </li>
          ))}
        </ul>
      )}
      {error && <p className="text-[10px] text-rose-300">{error}</p>}
    </div>
  );
}
