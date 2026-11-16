import { useEffect, useState } from "react";
import { ExternalLink, LoaderCircle, RefreshCw, Target } from "lucide-react";
import { API_BASE } from "../config";
import { EmptyState, SectionHeading } from "../components";
import { errorText } from "../lib";
import {
  type ComparisonResponse,
  type RecommendationItem,
  type RecommendationResponse,
} from "../types";

const SORTS: Array<{ value: string; label: string }> = [
  { value: "opportunity", label: "Best opportunity" },
  { value: "score", label: "Highest match score" },
  { value: "newest", label: "Newest" },
  { value: "company", label: "Company" },
  { value: "location", label: "Location" },
  { value: "experience", label: "Experience required" },
  { value: "salary", label: "Disclosed salary" },
];

const ACTION_TONES: Record<string, string> = {
  apply_now: "border-emerald-400/25 bg-emerald-400/[0.1] text-emerald-300",
  review_first: "border-amber-300/25 bg-amber-300/[0.1] text-amber-200",
  prepare_missing_skills: "border-sky-400/25 bg-sky-400/[0.1] text-sky-300",
  skip: "border-slate-500/30 bg-slate-500/[0.1] text-slate-300",
};

function ActionBadge({ item }: { item: RecommendationItem }) {
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold ${ACTION_TONES[item.action]}`}>
      {item.action_label}
    </span>
  );
}

function salaryLabel(item: RecommendationItem): string {
  const pay = item.compensation;
  if (pay.min_lpa === null) return "Pay not disclosed";
  return pay.max_lpa && pay.max_lpa !== pay.min_lpa ? `${pay.min_lpa}-${pay.max_lpa} LPA` : `${pay.min_lpa} LPA`;
}

function ComparisonTable({ data, onClose }: { data: ComparisonResponse; onClose: () => void }) {
  const best = data.highlights.best_overall_job_id;
  return (
    <div className="panel mb-5 rounded-2xl p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-100">Side-by-side comparison</h3>
        <button type="button" onClick={onClose} className="text-xs text-slate-400 hover:text-slate-200">
          Close
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-left text-xs text-slate-300">
          <thead>
            <tr className="border-b border-slate-700/60 text-[10px] uppercase tracking-[0.14em] text-slate-500">
              <th className="py-2 pr-3 font-semibold">&nbsp;</th>
              {data.jobs.map((job) => (
                <th key={job.id} className="py-2 pr-3 font-semibold normal-case tracking-normal text-slate-200">
                  {job.title}
                  <div className="text-[11px] font-normal text-slate-500">{job.company}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-slate-800/70">
              <td className="py-2 pr-3 text-slate-500">Match score</td>
              {data.jobs.map((job) => (
                <td key={job.id} className="py-2 pr-3 tabular-nums">
                  {job.score ?? "—"}
                  {job.id === best && <span className="ml-2 text-emerald-300">best</span>}
                </td>
              ))}
            </tr>
            <tr className="border-b border-slate-800/70">
              <td className="py-2 pr-3 text-slate-500">Experience asked</td>
              {data.jobs.map((job) => (
                <td key={job.id} className="py-2 pr-3">{job.required_years === null ? "not stated" : `${job.required_years} yr`}</td>
              ))}
            </tr>
            <tr className="border-b border-slate-800/70 align-top">
              <td className="py-2 pr-3 text-slate-500">Blockers</td>
              {data.jobs.map((job) => (
                <td key={job.id} className="py-2 pr-3 text-rose-300/90">
                  {job.blockers.length ? job.blockers.join("; ") : <span className="text-slate-600">none</span>}
                </td>
              ))}
            </tr>
            {data.highlights.skill_matrix.map((row) => (
              <tr key={row.skill} className="border-b border-slate-800/70">
                <td className="py-2 pr-3 text-slate-400">{row.skill}</td>
                {data.jobs.map((job) => {
                  const status = row.jobs[String(job.id)];
                  return (
                    <td key={job.id} className="py-2 pr-3">
                      {status === "matched" ? (
                        <span className="text-emerald-300">you have it</span>
                      ) : status === "missing" ? (
                        <span className="text-amber-200">missing</span>
                      ) : (
                        <span className="text-slate-600">not required</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.highlights.skills_missing_everywhere.length > 0 && (
        <p className="mt-3 text-xs text-slate-400">
          Missing in every job that asks for it: {data.highlights.skills_missing_everywhere.join(", ")}
        </p>
      )}
    </div>
  );
}

export function RecommendedView() {
  const [data, setData] = useState<RecommendationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState("opportunity");
  const [includeSkip, setIncludeSkip] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [selected, setSelected] = useState<number[]>([]);
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const query = new URLSearchParams({ sort, limit: "20", include_skip: String(includeSkip) });
    fetch(`${API_BASE}/api/recommendations?${query.toString()}`)
      .then((response) => {
        if (!response.ok) throw new Error(`Recommendations request failed (${response.status}).`);
        return response.json() as Promise<RecommendationResponse>;
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
  }, [sort, includeSkip, reloadToken]);

  const refresh = () => {
    setLoading(true);
    setReloadToken((token) => token + 1);
  };

  const toggle = (id: number) => {
    setSelected((current) => {
      if (current.includes(id)) return current.filter((value) => value !== id);
      return current.length >= 4 ? current : [...current, id];
    });
  };

  const compare = () => {
    setCompareError(null);
    fetch(`${API_BASE}/api/jobs/compare?ids=${selected.join(",")}`)
      .then((response) => {
        if (!response.ok) throw new Error(`Comparison request failed (${response.status}).`);
        return response.json() as Promise<ComparisonResponse>;
      })
      .then(setComparison)
      .catch((caught: unknown) => setCompareError(errorText(caught)));
  };

  const summary = data?.summary;

  return (
    <div>
      <SectionHeading
        eyebrow="Recommended"
        title="Best next actions"
        description="Software jobs in India that fit your early-career profile, each with a clear next step. The rule-based match and eligibility decide the action; freshness, company priority and disclosed pay only rank."
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
        <div className="mb-5 flex flex-wrap gap-2 text-xs">
          {Object.entries(summary.by_action).map(([action, count]) => (
            <span key={action} className={`rounded-full border px-3 py-1.5 ${ACTION_TONES[action]}`}>
              {action.replace(/_/g, " ")}: {count}
            </span>
          ))}
          <span className="rounded-full border border-slate-700/70 px-3 py-1.5 text-slate-400">
            {summary.considered} jobs considered
          </span>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort recommendations" className="field w-auto">
          {SORTS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-xs text-slate-400">
          <input type="checkbox" checked={includeSkip} onChange={(event) => setIncludeSkip(event.target.checked)} />
          Also show jobs to skip
        </label>
        <button
          type="button"
          onClick={compare}
          disabled={selected.length < 2}
          className="rounded-xl border border-blue-400/30 bg-blue-500/10 px-3 py-2 text-xs font-medium text-blue-200 disabled:opacity-40"
        >
          Compare selected ({selected.length}/4)
        </button>
        {selected.length < 2 && <span className="text-[11px] text-slate-500">Tick 2 to 4 jobs to compare them.</span>}
      </div>

      {compareError && <p className="mb-3 text-xs text-rose-300">{compareError}</p>}
      {comparison && <ComparisonTable data={comparison} onClose={() => setComparison(null)} />}

      {loading && !data ? (
        <div className="flex min-h-44 items-center justify-center text-sm text-slate-400">
          <LoaderCircle className="loading-ring mr-2 h-4 w-4" /> Finding your best opportunities…
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="panel rounded-2xl">
          <EmptyState
            icon={Target}
            title="Nothing to recommend yet"
            message={
              data
                ? "No stored job passes your early-career and India filters with a viable next step. Run a sync of the active sources to bring in more jobs."
                : "Recommendations could not be loaded. Check that the backend is running."
            }
          />
        </div>
      ) : (
        <div className="grid gap-4">
          {data.items.map((item) => (
            <article key={item.id} className="panel rounded-2xl p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <label className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={selected.includes(item.id)}
                      onChange={() => toggle(item.id)}
                      aria-label={`Select ${item.title} to compare`}
                      className="mt-1"
                    />
                    <span>
                      <span className="block text-sm font-semibold text-slate-100">{item.title}</span>
                      <span className="block text-xs text-slate-400">
                        {item.company} · {item.location ?? "Location not stated"} · {salaryLabel(item)}
                      </span>
                    </span>
                  </label>
                </div>
                <div className="flex items-center gap-3">
                  <ActionBadge item={item} />
                  <div className="text-right text-[11px] text-slate-400">
                    <div>
                      Opportunity <span className="text-sm font-semibold text-slate-100">{item.opportunity_score}</span>
                    </div>
                    <div>Match {item.match_score ?? "—"}</div>
                  </div>
                </div>
              </div>

              <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-300">
                {item.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
              {item.missing_required_skills.length > 0 && (
                <p className="mt-2 text-xs text-amber-200">
                  Missing required skills: {item.missing_required_skills.join(", ")}
                </p>
              )}
              <p className="mt-2 text-[11px] text-slate-500">{item.signals.join(" · ")}</p>
              <a
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="mt-3 inline-flex items-center gap-1 text-xs text-blue-300 hover:underline"
              >
                Open original posting <ExternalLink size={11} />
              </a>
            </article>
          ))}
        </div>
      )}

      {data && data.skill_gap.gaps.length > 0 && (
        <section className="panel mt-6 rounded-2xl p-5">
          <h3 className="text-sm font-semibold text-slate-100">Skills worth building</h3>
          <p className="mt-1 text-xs text-slate-400">{data.skill_gap.note}</p>
          <ul className="mt-3 grid gap-2 text-xs text-slate-300">
            {data.skill_gap.gaps.map((gap) => (
              <li key={gap.skill} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-800/80 px-3 py-2">
                <span className="font-medium text-slate-100">{gap.skill}</span>
                <span className="text-slate-400">
                  required in {gap.jobs_requiring} of {data.skill_gap.jobs_considered} jobs
                  {gap.companies.length > 0 && ` · ${gap.companies.join(", ")}`}
                </span>
              </li>
            ))}
          </ul>
          {data.skill_gap.learning_plan.length > 0 && (
            <ol className="mt-4 list-decimal space-y-1.5 pl-5 text-xs text-slate-400">
              {data.skill_gap.learning_plan.map((step) => (
                <li key={step.skill}>{step.step}</li>
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
  );
}
