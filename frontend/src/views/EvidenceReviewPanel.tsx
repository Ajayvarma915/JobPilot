import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, LoaderCircle, ShieldCheck } from "lucide-react";
import { apiRequest, errorText } from "../lib";

interface EvidenceRecord {
  evidence_id: string;
  category: string;
  title: string;
  statement: string;
  verified: boolean;
}

interface EvidenceRecords {
  items: EvidenceRecord[];
  pending_count: number;
  verified_count: number;
}

// Only statements you confirm here can appear in a tailored resume. After you replace your resume,
// everything that changed waits here until you have read it and ticked it.
export function EvidenceReviewPanel({ onChanged }: { onChanged?: () => void }) {
  const [data, setData] = useState<EvidenceRecords | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    apiRequest<EvidenceRecords>("/api/evidence/records?review=pending")
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setSelected((current) => current.filter((id) => result.items.some((item) => item.evidence_id === id)));
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorText(caught));
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const toggle = (id: string) => setSelected((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));

  const confirm = () => {
    if (selected.length === 0) return;
    if (!window.confirm(`You are confirming that ${selected.length} statement(s) from your resume are accurate and that you can speak to them in an interview. Continue?`)) return;
    setBusy(true);
    setError(null);
    apiRequest("/api/evidence/review", { method: "POST", body: JSON.stringify({ evidence_ids: selected, verified: true }) })
      .then(() => {
        setSelected([]);
        reload();
        onChanged?.();
      })
      .catch((caught: unknown) => setError(errorText(caught)))
      .finally(() => setBusy(false));
  };

  if (!data) return error ? <p className="text-xs text-rose-300">{error}</p> : null;
  if (data.pending_count === 0) {
    return (
      <p className="flex items-center gap-2 text-[11px] text-emerald-300">
        <ShieldCheck size={14} /> All {data.verified_count} statements from your resume are confirmed and can be used in tailored resumes.
      </p>
    );
  }

  const byCategory = data.items.reduce<Record<string, EvidenceRecord[]>>((groups, item) => {
    (groups[item.category] ??= []).push(item);
    return groups;
  }, {});

  return (
    <section className="panel rounded-2xl border border-amber-300/20 p-4 sm:p-5">
      <h3 className="text-sm font-semibold text-amber-200">
        {data.pending_count} statement(s) from your resume need your confirmation ({data.verified_count} already confirmed)
      </h3>
      <p className="mt-1 text-[11px] text-slate-400">
        Tailored resumes only use statements you confirm. Read each one; tick it only if it is accurate and you can talk about it in an interview.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="secondary-button !px-3 !py-2" onClick={() => setSelected(data.items.map((item) => item.evidence_id))}>
          Select all {data.items.length}
        </button>
        <button className="secondary-button !px-3 !py-2" onClick={() => setSelected([])} disabled={selected.length === 0}>
          Clear
        </button>
        <button className="primary-button !px-3 !py-2" onClick={confirm} disabled={busy || selected.length === 0}>
          {busy ? <LoaderCircle size={13} className="loading-ring" /> : <CheckCircle2 size={13} />}
          Confirm {selected.length} selected as accurate
        </button>
      </div>
      <div className="mt-4 space-y-4">
        {Object.entries(byCategory).map(([category, items]) => (
          <div key={category}>
            <p className="text-[11px] font-semibold capitalize text-slate-300">{category} ({items.length})</p>
            <ul className="mt-1.5 space-y-1.5">
              {items.map((item) => (
                <li key={item.evidence_id}>
                  <label className="flex items-start gap-2 text-[11px] text-slate-400">
                    <input type="checkbox" className="mt-0.5" checked={selected.includes(item.evidence_id)} onChange={() => toggle(item.evidence_id)} />
                    <span>
                      <span className="font-medium text-slate-200">{item.title}</span>
                      {item.statement && item.statement !== item.title ? <span className="block text-slate-500">{item.statement}</span> : null}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {error && <p className="mt-2 text-[11px] text-rose-300">{error}</p>}
    </section>
  );
}
