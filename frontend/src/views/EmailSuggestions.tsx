import { useCallback, useEffect, useState } from "react";
import { LoaderCircle, MailQuestion } from "lucide-react";
import { apiRequest, errorText } from "../lib";

interface Suggestion {
  id: number;
  company_guess: string;
  title_guess: string;
  subject: string;
  sender: string;
  received_at: string | null;
  already_tracked_titles?: string[];
}

// Application confirmations found in your mail for jobs you are not tracking (for example one you
// applied to through a referral). Nothing is added until you press Add; fix the company and role first.
export function EmailSuggestions({ onAdded, refreshKey = 0 }: { onAdded?: () => void; refreshKey?: number }) {
  const [items, setItems] = useState<Suggestion[] | null>(null);
  const [edits, setEdits] = useState<Record<number, { company: string; title: string }>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    apiRequest<{ items: Suggestion[] }>("/api/email/suggestions")
      .then((result) => {
        if (!cancelled) setItems(result.items);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorText(caught));
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken, refreshKey]);

  const value = (item: Suggestion) => edits[item.id] ?? { company: item.company_guess, title: item.title_guess };
  const change = (item: Suggestion, patch: Partial<{ company: string; title: string }>) =>
    setEdits((current) => ({ ...current, [item.id]: { ...value(item), ...patch } }));

  const act = (item: Suggestion, path: "add" | "dismiss") => {
    setBusyId(item.id);
    setError(null);
    const body = path === "add" ? JSON.stringify(value(item)) : undefined;
    apiRequest(`/api/email/suggestions/${item.id}/${path}`, { method: "POST", body })
      .then(() => {
        reload();
        if (path === "add") onAdded?.();
      })
      .catch((caught: unknown) => setError(errorText(caught)))
      .finally(() => setBusyId(null));
  };

  if (!items || items.length === 0) {
    return error ? <p className="text-xs text-rose-300">{error}</p> : null;
  }

  return (
    <section className="panel rounded-2xl border border-sky-300/20 p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <MailQuestion size={18} className="mt-0.5 shrink-0 text-sky-300" />
        <div>
          <h3 className="text-sm font-semibold text-slate-100">Applications found in your email that you are not tracking</h3>
          <p className="mt-1 text-[11px] text-slate-400">
            These confirmation emails are for jobs that are not in your tracker (for example a referral you applied through). Check the company and role, then add
            them as Applied. Nothing is added unless you press Add.
          </p>
        </div>
      </div>
      <ul className="mt-3 space-y-3">
        {items.map((item) => (
          <li key={item.id} className="rounded-xl border border-slate-700/60 bg-slate-900/40 p-3">
            <p className="text-[11px] text-slate-500">
              {item.subject}
              {item.received_at ? ` · ${new Date(item.received_at).toLocaleDateString()}` : ""}
            </p>
            {(item.already_tracked_titles?.length ?? 0) > 0 && (
              <p className="mt-1 text-[11px] text-amber-200">
                You already track {item.already_tracked_titles?.join(", ")} at this company. If this email is about that job, press "Not mine" instead of adding it twice.
              </p>
            )}
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <input className="field" aria-label="Company" placeholder="Company" value={value(item).company} onChange={(event) => change(item, { company: event.target.value })} />
              <input className="field" aria-label="Role" placeholder="Role" value={value(item).title} onChange={(event) => change(item, { title: event.target.value })} />
            </div>
            <div className="mt-2 flex gap-2">
              <button
                className="primary-button !px-3 !py-2"
                disabled={busyId === item.id || !value(item).company.trim() || !value(item).title.trim()}
                onClick={() => act(item, "add")}
              >
                {busyId === item.id ? <LoaderCircle size={13} className="loading-ring" /> : null}
                Add to tracker as Applied
              </button>
              <button className="secondary-button !px-3 !py-2" disabled={busyId === item.id} onClick={() => act(item, "dismiss")}>
                Not mine
              </button>
            </div>
          </li>
        ))}
      </ul>
      {error && <p className="mt-2 text-[11px] text-rose-300">{error}</p>}
    </section>
  );
}
