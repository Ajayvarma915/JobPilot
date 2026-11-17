import { useEffect, useState } from "react";
import { LoaderCircle, RefreshCw, TrendingUp } from "lucide-react";
import { API_BASE } from "../config";
import { EmptyState, MetricCard, SectionHeading } from "../components";
import { errorText } from "../lib";

interface Funnel {
  counts: Record<string, number>;
  rates: Record<string, number | null> | null;
  rates_hidden_reason: string | null;
  min_applied_for_rates: number;
  by_company: Array<{ company: string; applied: number; responded: number; interviews: number; offers: number }>;
  by_source: Array<{ source: string; applied: number; responded: number }>;
  upcoming_follow_ups: Array<{
    application_id: number;
    title: string;
    company: string;
    status: string;
    follow_up_date: string;
    next_action: string | null;
    overdue: boolean;
  }>;
  note?: string;
}

const STAGES: Array<{ key: string; label: string; caption: string }> = [
  { key: "tracked", label: "Tracked", caption: "Jobs in your pipeline" },
  { key: "applied", label: "Applied", caption: "Submissions you confirmed" },
  { key: "responded", label: "Responses", caption: "Assessment, interview, offer or rejection" },
  { key: "interviews", label: "Interviews", caption: "Reached an interview" },
  { key: "offers", label: "Offers", caption: "Reached an offer" },
  { key: "rejections", label: "Rejections", caption: "Told no" },
];

export function InsightsView() {
  const [data, setData] = useState<Funnel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/analytics/funnel`)
      .then((response) => {
        if (!response.ok) throw new Error(`Analytics request failed (${response.status}).`);
        return response.json() as Promise<Funnel>;
      })
      .then((payload) => {
        if (!cancelled) {
          setData(payload);
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorText(caught));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const refresh = () => {
    setLoading(true);
    setReloadToken((value) => value + 1);
  };

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Insights"
        title="Your application funnel"
        description="Counted from your own tracked applications. Nothing is estimated, and percentages stay hidden until there are enough applications for them to mean something."
        right={
          <button type="button" onClick={refresh} disabled={loading} className="inline-flex items-center gap-2 rounded-xl border border-slate-700/70 bg-slate-800/50 px-3 py-2 text-xs font-medium text-slate-200 disabled:opacity-60">
            {loading ? <LoaderCircle className="loading-ring h-3.5 w-3.5" /> : <RefreshCw size={14} />}
            Refresh
          </button>
        }
      />
      {error && <p role="alert" className="text-sm text-rose-300">{error} Start the backend and press Refresh.</p>}

      {!data && !error && (
        <p className="flex items-center text-sm text-slate-400">
          <LoaderCircle className="loading-ring mr-2 h-4 w-4" /> Loading…
        </p>
      )}

      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {STAGES.map((stage) => (
              <MetricCard key={stage.key} label={stage.label} value={data.counts[stage.key] ?? 0} caption={stage.caption} icon={TrendingUp} iconStyle="text-blue-300" />
            ))}
          </div>

          <section className="panel rounded-2xl p-5">
            <h3 className="text-sm font-semibold text-slate-100">Rates</h3>
            {data.rates ? (
              <ul className="mt-3 grid gap-2 text-xs text-slate-300 sm:grid-cols-2">
                {Object.entries(data.rates).map(([name, value]) => (
                  <li key={name} className="flex justify-between rounded-xl border border-slate-800/80 px-3 py-2">
                    <span>{name.replace(/_/g, " ")}</span>
                    <span className="tabular-nums text-slate-100">{value === null ? "—" : `${value}%`}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-xs text-slate-400">{data.rates_hidden_reason}</p>
            )}
          </section>

          <section className="panel rounded-2xl p-5">
            <h3 className="text-sm font-semibold text-slate-100">Upcoming follow-ups</h3>
            {data.upcoming_follow_ups.length === 0 ? (
              <EmptyState icon={TrendingUp} title="No follow-ups scheduled" message="Set a follow-up date on an application and it will appear here." />
            ) : (
              <ul className="mt-3 grid gap-2 text-xs text-slate-300">
                {data.upcoming_follow_ups.map((item) => (
                  <li key={item.application_id} className="flex flex-wrap justify-between gap-2 rounded-xl border border-slate-800/80 px-3 py-2">
                    <span>
                      <span className="font-medium text-slate-100">{item.title}</span> · {item.company} · {item.status}
                      {item.next_action && <span className="text-slate-500"> — {item.next_action}</span>}
                    </span>
                    <span className={item.overdue ? "text-rose-300" : "text-slate-400"}>
                      {item.follow_up_date}
                      {item.overdue && " (overdue)"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {data.by_company.length > 0 && (
            <section className="panel rounded-2xl p-5">
              <h3 className="text-sm font-semibold text-slate-100">By company</h3>
              <table className="mt-3 w-full border-collapse text-left text-xs text-slate-300">
                <thead>
                  <tr className="border-b border-slate-700/60 text-[10px] uppercase tracking-[0.14em] text-slate-500">
                    <th className="py-2 pr-3 font-semibold">Company</th>
                    <th className="py-2 pr-3 text-right font-semibold">Applied</th>
                    <th className="py-2 pr-3 text-right font-semibold">Responses</th>
                    <th className="py-2 pr-3 text-right font-semibold">Interviews</th>
                    <th className="py-2 text-right font-semibold">Offers</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_company.map((row) => (
                    <tr key={row.company} className="border-b border-slate-800/70">
                      <td className="py-2 pr-3 text-slate-100">{row.company}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{row.applied}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{row.responded}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{row.interviews}</td>
                      <td className="py-2 text-right tabular-nums">{row.offers}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}
    </div>
  );
}
