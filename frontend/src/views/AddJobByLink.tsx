import { useState, type FormEvent } from "react";
import { Link2, LoaderCircle } from "lucide-react";
import { apiRequest, errorText } from "../lib";

interface Imported {
  job_id: number;
  created: boolean;
  title: string;
  company: string;
  location: string[];
  url: string;
}

// For a job at a company with no public job list (for example a referral): paste the job's link.
// Only that one page is read. You can then track it right away.
export function AddJobByLink({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imported, setImported] = useState<Imported | null>(null);
  const [tracked, setTracked] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setImported(null);
    setTracked(false);
    apiRequest<Imported>("/api/jobs/import-link", { method: "POST", body: JSON.stringify({ url: url.trim() }) })
      .then((result) => {
        setImported(result);
        onAdded();
      })
      .catch((caught: unknown) => setError(errorText(caught)))
      .finally(() => setBusy(false));
  };

  const track = () => {
    if (!imported) return;
    apiRequest("/api/applications", { method: "POST", body: JSON.stringify({ job_id: imported.job_id }) })
      .then(() => setTracked(true))
      .catch((caught: unknown) => setError(errorText(caught)));
  };

  return (
    <div className="panel rounded-2xl p-4">
      <button className="secondary-button !px-3 !py-2" onClick={() => setOpen(!open)} aria-expanded={open}>
        <Link2 size={13} />
        {open ? "Hide" : "Add a job by link"}
      </button>
      {open && (
        <form onSubmit={submit} className="mt-3 space-y-2">
          <p className="text-[11px] text-slate-400">
            Use this for a job at a company that has no public job list (for example a referral). Paste the link to the job posting; only that page is read.
          </p>
          <div className="flex flex-wrap gap-2">
            <input className="field min-w-64 flex-1" placeholder="https://..." value={url} onChange={(event) => setUrl(event.target.value)} aria-label="Job link" />
            <button className="primary-button" type="submit" disabled={busy || url.trim().length < 8}>
              {busy ? <LoaderCircle size={14} className="loading-ring" /> : null}
              Add job
            </button>
          </div>
          {error && <p className="text-[11px] text-rose-300">{error}</p>}
          {imported && (
            <div className="rounded-xl border border-emerald-300/20 bg-emerald-300/[0.04] p-3 text-xs text-slate-300">
              <p>
                <span className="font-semibold text-emerald-300">{imported.created ? "Added" : "Already saved"}:</span> {imported.title} at {imported.company}
                {imported.location.length > 0 ? ` (${imported.location.join("; ")})` : ""}
              </p>
              <button className="secondary-button mt-2 !px-3 !py-2" onClick={track} disabled={tracked} type="button">
                {tracked ? "Tracked" : "Track this job"}
              </button>
            </div>
          )}
        </form>
      )}
    </div>
  );
}
