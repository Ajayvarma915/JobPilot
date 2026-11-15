import { useEffect, useMemo, useState } from "react";
import { Building2, ExternalLink, LoaderCircle, RefreshCw, Search } from "lucide-react";
import { API_BASE } from "../config";
import { EmptyState, MetricCard, SectionHeading } from "../components";
import { errorText } from "../lib";
import { type SourceHealthItem, type SourceHealthResponse } from "../types";

const STATE_LABELS: Record<string, string> = {
  active: "Active",
  verified: "Verified",
  configured: "Configured",
  awaiting_validation: "Awaiting validation",
  discovered: "Discovered",
  temporarily_unavailable: "Temporarily unavailable",
  failed: "Failed",
  deprecated: "Deprecated",
};

const STATE_TONES: Record<string, string> = {
  active: "border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-300",
  verified: "border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-300",
  configured: "border-sky-400/20 bg-sky-400/[0.08] text-sky-300",
  awaiting_validation: "border-amber-300/20 bg-amber-300/[0.08] text-amber-200",
  discovered: "border-slate-500/30 bg-slate-500/[0.1] text-slate-300",
  temporarily_unavailable: "border-orange-400/20 bg-orange-400/[0.08] text-orange-300",
  failed: "border-rose-400/20 bg-rose-400/[0.08] text-rose-300",
  deprecated: "border-slate-600/30 bg-slate-600/[0.1] text-slate-400",
};

function formatWhen(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function count(value: number | null): string {
  return value === null || value === undefined ? "—" : String(value);
}

function StateBadge({ state }: { state: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium ${
        STATE_TONES[state] ?? STATE_TONES.discovered
      }`}
    >
      {STATE_LABELS[state] ?? state}
    </span>
  );
}

function enrichmentLabel(item: SourceHealthItem): string {
  if (item.detail_attempted === null) return "not reported";
  return `${item.detail_succeeded ?? 0}/${item.detail_attempted}`;
}

export function CoverageView() {
  const [data, setData] = useState<SourceHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stateFilter, setStateFilter] = useState("all");
  const [query, setQuery] = useState("");

  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/sources/health`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Source health request failed (${response.status}).`);
        }
        return response.json() as Promise<SourceHealthResponse>;
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
    setReloadToken((token) => token + 1);
  };

  const items = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (data?.items ?? []).filter((item) => {
      if (stateFilter !== "all" && item.state !== stateFilter) return false;
      if (!needle) return true;
      return (
        (item.name ?? "").toLowerCase().includes(needle) ||
        (item.provider ?? "").toLowerCase().includes(needle)
      );
    });
  }, [data, stateFilter, query]);

  const summary = data?.summary;

  return (
    <div>
      <SectionHeading
        eyebrow="Coverage"
        title="Company coverage"
        description="Every company in the source registry, with what is actually known about its job feed. States come from the registry; fetch history comes from recorded syncs."
        right={
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700/70 bg-slate-800/50 px-3 py-2 text-xs font-medium text-slate-200 transition hover:bg-slate-700/50 disabled:opacity-60"
          >
            {loading ? <LoaderCircle className="loading-ring h-3.5 w-3.5" /> : <RefreshCw size={14} />}
            Refresh
          </button>
        }
      />

      {error && (
        <div role="alert" className="mb-5 rounded-2xl border border-rose-400/20 bg-rose-400/[0.06] px-4 py-3 text-sm text-rose-200">
          {error} Start the backend and press Refresh.
        </div>
      )}

      {summary && (
        <div className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Companies" value={summary.total} caption="In the registry" icon={Building2} iconStyle="text-blue-300" />
          <MetricCard label="Active" value={summary.by_state.active ?? 0} caption="Verified; may enter automatic sync" icon={Building2} iconStyle="text-emerald-300" />
          <MetricCard
            label="Awaiting validation"
            value={summary.by_state.awaiting_validation ?? 0}
            caption="Mapped, not yet trusted"
            icon={Building2}
            iconStyle="text-amber-200"
          />
          <MetricCard label="Never fetched" value={summary.never_fetched} caption="No recorded sync yet" icon={Building2} iconStyle="text-slate-300" />
        </div>
      )}

      <div className="panel rounded-2xl p-4">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="relative min-w-52 flex-1">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search company or connector"
              aria-label="Search companies"
              className="field pl-9"
            />
          </div>
          <select
            value={stateFilter}
            onChange={(event) => setStateFilter(event.target.value)}
            aria-label="Filter by state"
            className="field w-auto"
          >
            <option value="all">All states</option>
            {Object.entries(STATE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <p className="text-xs text-slate-500">
            {items.length} of {data?.items.length ?? 0} shown
          </p>
        </div>

        {loading && !data ? (
          <div className="flex min-h-44 items-center justify-center text-sm text-slate-400">
            <LoaderCircle className="loading-ring mr-2 h-4 w-4" /> Loading source health…
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={Building2}
            title={data ? "No companies match" : "No data yet"}
            message={
              data
                ? "Try a different search or state filter."
                : "The registry could not be loaded. Check that the backend is running."
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px] border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-slate-700/60 text-[10px] uppercase tracking-[0.14em] text-slate-500">
                  <th className="py-2 pr-3 font-semibold">Company</th>
                  <th className="py-2 pr-3 font-semibold">Connector</th>
                  <th className="py-2 pr-3 font-semibold">State</th>
                  <th className="py-2 pr-3 font-semibold">Last success</th>
                  <th className="py-2 pr-3 text-right font-semibold">Raw / unique</th>
                  <th className="py-2 pr-3 text-right font-semibold">Eligible / review</th>
                  <th className="py-2 pr-3 text-right font-semibold">Descriptions</th>
                  <th className="py-2 pr-3 text-right font-semibold">Detail fetch</th>
                  <th className="py-2 font-semibold">Last problem</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-b border-slate-800/70 align-top text-slate-300">
                    <td className="py-3 pr-3">
                      <div className="font-medium text-slate-100">{item.name}</div>
                      {item.careers_url && (
                        <a
                          href={item.careers_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-blue-300 hover:underline"
                        >
                          Careers <ExternalLink size={10} />
                        </a>
                      )}
                    </td>
                    <td className="py-3 pr-3">{item.provider ?? "none"}</td>
                    <td className="py-3 pr-3">
                      <StateBadge state={item.state} />
                      {item.state_detail && (
                        <div className="mt-1 max-w-52 text-[10px] leading-4 text-slate-500">{item.state_detail}</div>
                      )}
                    </td>
                    <td className="py-3 pr-3">{item.never_fetched ? "No fetch yet" : formatWhen(item.last_success_at)}</td>
                    <td className="py-3 pr-3 text-right tabular-nums">
                      {count(item.raw_jobs)} / {count(item.unique_jobs)}
                    </td>
                    <td className="py-3 pr-3 text-right tabular-nums">
                      {count(item.eligible_jobs)} / {count(item.review_jobs)}
                    </td>
                    <td className="py-3 pr-3 text-right tabular-nums">{count(item.jobs_with_description)}</td>
                    <td className="py-3 pr-3 text-right tabular-nums">{enrichmentLabel(item)}</td>
                    <td className="py-3 text-[11px] text-rose-300/90">
                      {item.last_error ? (
                        <>
                          <div className="max-w-64 break-words">{item.last_error}</div>
                          <div className="mt-0.5 text-slate-500">{formatWhen(item.last_failure_at)}</div>
                        </>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
