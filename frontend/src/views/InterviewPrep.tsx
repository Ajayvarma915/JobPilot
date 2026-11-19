import { useState } from "react";
import { ListChecks } from "lucide-react";
import { apiRequest, errorText } from "../lib";

interface Prep {
  progress: unknown;
  categories: Record<string, Array<{ id: number; text: string; done: boolean }>>;
}

const progressText = (categories: Prep["categories"]) => {
  const items = Object.values(categories).flat();
  return `${items.filter((item) => item.done).length} of ${items.length} done`;
};

// A preparation plan built from the real job: topics for the required skills, and extra practice for
// the ones you are missing. Ticking items only records your own progress.
export function InterviewPrep({ applicationId }: { applicationId: number }) {
  const [prep, setPrep] = useState<Prep | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const build = () => {
    setBusy(true);
    setError(null);
    apiRequest<Prep>(`/api/applications/${applicationId}/interview-prep`, { method: "POST" })
      .then((result) => {
        setPrep(result);
        setOpen(true);
      })
      .catch((caught: unknown) => setError(errorText(caught)))
      .finally(() => setBusy(false));
  };

  const toggle = (itemId: number, done: boolean) =>
    apiRequest<Prep>(`/api/interview-prep/${itemId}`, { method: "PATCH", body: JSON.stringify({ done }) })
      .then(setPrep)
      .catch((caught: unknown) => setError(errorText(caught)));

  return (
    <div className="mt-3 border-t border-slate-800/70 pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <button className="secondary-button !px-3 !py-1.5 text-[11px]" onClick={prep && open ? () => setOpen(false) : prep ? () => setOpen(true) : build} disabled={busy}>
          <ListChecks size={13} />
          {busy ? "Building..." : prep ? (open ? "Hide interview prep" : "Show interview prep") : "Prepare for interviews"}
        </button>
        {prep && open && <span className="text-[11px] text-slate-500">{progressText(prep.categories)}</span>}
      </div>
      {error && <p className="mt-2 text-[11px] text-rose-300">{error}</p>}
      {prep && open && (
        <div className="mt-3 space-y-3">
          {Object.entries(prep.categories).map(([category, items]) => (
            <div key={category}>
              <p className="text-[11px] font-semibold capitalize text-slate-300">{category.replaceAll("_", " ")}</p>
              <ul className="mt-1 space-y-1">
                {items.map((item) => (
                  <li key={item.id}>
                    <label className="flex items-start gap-2 text-[11px] text-slate-400">
                      <input type="checkbox" className="mt-0.5" checked={item.done} onChange={(event) => void toggle(item.id, event.target.checked)} />
                      <span className={item.done ? "line-through opacity-60" : ""}>{item.text}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
