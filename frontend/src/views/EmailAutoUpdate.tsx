import { useEffect, useState } from "react";
import { apiRequest, errorText } from "../lib";

// Switch for "update my applications from clear emails". On: an email that clearly names your job and company
// (an application confirmation, an interview or assessment invite, a rejection, an offer) updates the application
// by itself and is listed under Approved with the reason. Off: every match waits in Pending for you.
export function EmailAutoUpdate() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiRequest<{ auto_update: boolean }>("/api/email/settings")
      .then((result) => {
        if (!cancelled) setEnabled(result.auto_update);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorText(caught));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const change = (next: boolean) => {
    setEnabled(next);
    setError(null);
    apiRequest("/api/email/settings", { method: "PUT", body: JSON.stringify({ auto_update: next }) }).catch((caught: unknown) => {
      setEnabled(!next);
      setError(errorText(caught));
    });
  };

  if (enabled === null) return error ? <p className="text-xs text-rose-300">{error}</p> : null;
  return (
    <section className="panel rounded-2xl p-4 sm:p-5">
      <label className="flex items-start gap-3 text-xs text-slate-300">
        <input type="checkbox" className="mt-0.5" checked={enabled} onChange={(event) => change(event.target.checked)} />
        <span>
          <span className="font-semibold text-slate-100">Update my applications automatically when an email clearly matches</span>
          <span className="mt-1 block text-[11px] text-slate-500">
            When the company and the role are clearly in the email, JobPilot moves that application on its own: confirmation to Applied (even if you only
            saved the job), then Assessment or shortlisted, Interview, Offer or Rejected. Every automatic change appears under Approved with the reason, and
            unclear emails still wait for you in Pending. Switch this off to approve everything yourself.
          </span>
        </span>
      </label>
      {error && <p className="mt-2 text-[11px] text-rose-300">{error}</p>}
    </section>
  );
}
