import { useState } from "react";
import { History } from "lucide-react";
import { apiRequest, errorText } from "../lib";
import { APPLICATION_STATUSES } from "../types";

interface HistoryItem {
  from_status: string | null;
  to_status: string;
  changed_at: string;
}

const label = (value: string | null) => (value ? (APPLICATION_STATUSES.find((item) => item.value === value)?.label ?? value) : "Created");

// Every status this application has had, oldest first, read from the tracker's own history table.
export function ApplicationHistory({ applicationId, status }: { applicationId: number; status: string }) {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next) {
      setError(null);
      apiRequest<{ items: HistoryItem[] }>(`/api/applications/${applicationId}/history`)
        .then((result) => setItems(result.items))
        .catch((caught: unknown) => setError(errorText(caught)));
    }
  };

  return (
    <div className="mt-3 border-t border-slate-800/70 pt-3" data-status={status}>
      <button className="secondary-button !px-3 !py-1.5 text-[11px]" onClick={toggle}>
        <History size={13} />
        {open ? "Hide history" : "Show history"}
      </button>
      {open && error && <p className="mt-2 text-[11px] text-rose-300">{error}</p>}
      {open && !error && items && (
        <ol className="mt-2 space-y-1 text-[11px] text-slate-400">
          {items.length === 0 && <li>No history recorded yet.</li>}
          {items.map((item, index) => (
            <li key={`${item.changed_at}-${index}`}>
              <span className="text-slate-300">{label(item.to_status)}</span>
              {item.from_status ? <span className="text-slate-500"> (from {label(item.from_status)})</span> : null}
              <span className="text-slate-500"> — {new Date(item.changed_at).toLocaleString()}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
