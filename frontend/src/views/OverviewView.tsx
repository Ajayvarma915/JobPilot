import { motion } from "motion/react";
import { Activity, ArrowRight, ArrowUpRight, BriefcaseBusiness, Building2, CheckCircle2, Command, FileCheck2, FileText, Globe2, RefreshCw, Search, ShieldCheck, Sparkles, TrendingUp, WandSparkles, Zap } from "lucide-react";
import { EmptyState, JobMiniCard, MetricCard, SectionHeading } from "../components";
import { categoryLabel, formatNumber } from "../lib";
import { type DashboardStats, type EvidenceSummary, type Job } from "../types";

export function OverviewView({
  stats,
  jobs,
  evidence,
  loading,
  onExplore,
  onRefresh,
  onTailor,
  onBuild,
}: {
  stats: DashboardStats | null;
  jobs: Job[];
  evidence: EvidenceSummary | null;
  loading: boolean;
  onExplore: () => void;
  onRefresh: () => void;
  onTailor: (job: Job) => void;
  onBuild: () => void;
}) {
  const verifiedPercent =
    evidence && evidence.record_count > 0
      ? Math.round((evidence.verified_count / evidence.record_count) * 100)
      : 0;

  return (
    <div className="space-y-7">
      <section className="relative isolate overflow-hidden rounded-[24px] border border-blue-300/15 bg-[#101a31] p-6 sm:p-8 lg:p-9">
        <div className="soft-grid pointer-events-none absolute inset-0 -z-10 opacity-65" />
        <motion.div
          className="pointer-events-none absolute -right-10 -top-24 -z-10 h-80 w-80 rounded-full bg-blue-500/15 blur-3xl"
          animate={{ x: [0, 15, 0], y: [0, 10, 0] }}
          transition={{ duration: 9, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          className="pointer-events-none absolute -bottom-32 right-[28%] -z-10 h-64 w-64 rounded-full bg-violet-500/10 blur-3xl"
          animate={{ x: [0, -14, 0] }}
          transition={{ duration: 11, repeat: Infinity, ease: "easeInOut" }}
        />

        <div className="relative max-w-3xl">
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-blue-300/20 bg-blue-400/[0.08] px-3 py-1.5 text-[10px] font-semibold tracking-wide text-blue-200">
            <Sparkles size={13} />
            YOUR CAREER WORKSPACE
          </div>

          <h1 className="max-w-2xl text-3xl font-semibold leading-[1.16] tracking-[-0.055em] text-white sm:text-[42px]">
            Your next opportunity,
            <span className="block bg-gradient-to-r from-blue-300 via-indigo-300 to-violet-300 bg-clip-text text-transparent">
              with a smarter workflow.
            </span>
          </h1>

          <p className="mt-4 max-w-xl text-[13px] leading-6 text-slate-400 sm:text-sm">
            Discover relevant software roles, explore their requirements,
            and build evidence-backed resumes from your verified experience.
          </p>

          <div className="mt-7 flex flex-wrap gap-3">
            <button className="primary-button" onClick={onExplore}>
              <Search size={15} />
              Explore opportunities
              <ArrowRight size={15} />
            </button>
            <button className="secondary-button" onClick={onBuild}>
              <WandSparkles size={15} />
              Resume studio
            </button>
            <button
              className="secondary-button"
              onClick={onRefresh}
              disabled={loading}
              title="Refresh dashboard data"
            >
              <RefreshCw
                size={15}
                className={loading ? "loading-ring" : ""}
              />
              Refresh data
            </button>
          </div>

          <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 text-[10px] text-slate-400">
            <span className="inline-flex items-center gap-2">
              <ShieldCheck size={13} className="text-emerald-300" />
              Verified-evidence workflow
            </span>
            <span className="inline-flex items-center gap-2">
              <Zap size={13} className="text-blue-300" />
              Local-first processing
            </span>
            <span className="inline-flex items-center gap-2">
              <Activity size={13} className="text-violet-300" />
              Live API data
            </span>
          </div>
        </div>

        <div className="pointer-events-none absolute right-7 top-8 hidden h-36 w-36 items-center justify-center rounded-full border border-white/[0.055] lg:flex">
          <div className="absolute inset-4 rounded-full border border-blue-200/[0.09]" />
          <div className="absolute inset-8 rounded-full border border-violet-200/[0.12]" />
          <motion.div
            className="absolute inset-0 rounded-full border border-blue-300/20"
            animate={{ rotate: 360 }}
            transition={{ duration: 26, repeat: Infinity, ease: "linear" }}
          >
            <span className="absolute -top-1 left-1/2 h-2 w-2 rounded-full bg-blue-300 shadow-[0_0_14px_rgba(125,170,255,0.8)]" />
          </motion.div>
          <div className="grid h-14 w-14 place-items-center rounded-2xl border border-blue-200/20 bg-blue-400/[0.08] text-blue-200">
            <Command size={25} />
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-4">
        <MetricCard
          label="Jobs discovered"
          value={loading ? "…" : formatNumber(stats?.total_jobs)}
          caption="Stored in your job database"
          icon={BriefcaseBusiness}
          iconStyle="bg-blue-400/[0.1] text-blue-300"
          delay={0.03}
        />
        <MetricCard
          label="Active listings"
          value={loading ? "…" : formatNumber(stats?.active_jobs)}
          caption="Currently marked active"
          icon={TrendingUp}
          iconStyle="bg-emerald-400/[0.09] text-emerald-300"
          delay={0.08}
        />
        <MetricCard
          label="Companies"
          value={loading ? "…" : formatNumber(stats?.total_companies)}
          caption="Represented in your database"
          icon={Building2}
          iconStyle="bg-violet-400/[0.1] text-violet-300"
          delay={0.13}
        />
        <MetricCard
          label="Verified evidence"
          value={
            evidence
              ? `${evidence.verified_count}/${evidence.record_count}`
              : "—"
          }
          caption={`${evidence?.pending_count ?? "—"} awaiting review`}
          icon={FileCheck2}
          iconStyle="bg-amber-400/[0.1] text-amber-200"
          delay={0.18}
        />
      </section>

      <section className="grid grid-cols-1 gap-5 2xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.85fr)]">
        <div className="panel rounded-2xl p-5 sm:p-6">
          <SectionHeading
            eyebrow="Opportunity feed"
            title="Recently collected jobs"
            description="India-based and India-eligible remote software-engineering roles from configured target companies. Listed pay appears when available; undisclosed pay is retained for verification."
            right={
              <button
                className="secondary-button !px-3 !py-2"
                onClick={onExplore}
              >
                View all
                <ArrowUpRight size={14} />
              </button>
            }
          />
          {jobs.length > 0 ? (
            <div>
              {jobs.map((job) => (
                <JobMiniCard key={job.id} job={job} onTailor={onTailor} />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={BriefcaseBusiness}
              title={loading ? "Loading jobs" : "No jobs to display"}
              message={
                loading
                  ? "Fetching job records from your API."
                  : "Check that the API is connected and your database has jobs."
              }
            />
          )}
        </div>

        <div className="space-y-5">
          <div className="panel rounded-2xl p-5 sm:p-6">
            <SectionHeading
              eyebrow="Resume foundation"
              title="Evidence readiness"
              description="Only records you have verified can be used in a generated resume."
            />

            <div className="mt-6 flex items-end justify-between gap-4">
              <div>
                <p className="text-3xl font-semibold tracking-tight text-white">
                  {evidence ? `${verifiedPercent}%` : "—"}
                </p>
                <p className="mt-1 text-[11px] text-slate-500">
                  evidence verified
                </p>
              </div>
              <div className="mb-1 flex items-center gap-1.5 text-[11px] text-emerald-300">
                <CheckCircle2 size={14} />
                {evidence?.pending_count === 0
                  ? "All reviewed"
                  : `${evidence?.pending_count ?? "—"} to review`}
              </div>
            </div>

            <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-800">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-blue-500 to-emerald-400"
                initial={{ width: 0 }}
                animate={{ width: `${verifiedPercent}%` }}
                transition={{ duration: 0.75, ease: "easeOut" }}
              />
            </div>

            <div className="mt-5 space-y-3">
              {Object.entries(evidence?.counts_by_category ?? {})
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([category, count]) => (
                  <div
                    key={category}
                    className="flex items-center justify-between text-[11px]"
                  >
                    <span className="capitalize text-slate-400">
                      {categoryLabel(category)}
                    </span>
                    <span className="font-semibold tabular-nums text-slate-200">
                      {count}
                    </span>
                  </div>
                ))}
            </div>

            <button
              className="secondary-button mt-6 w-full"
              onClick={onBuild}
            >
              <FileText size={14} />
              Open resume studio
              <ArrowRight size={14} />
            </button>
          </div>

          <div className="panel rounded-2xl p-5">
            <div className="mb-4 flex items-center gap-2">
              <div className="grid h-8 w-8 place-items-center rounded-xl bg-cyan-400/[0.09] text-cyan-300">
                <Globe2 size={16} />
              </div>
              <div>
                <p className="text-[12px] font-semibold text-slate-100">
                  Collector sources
                </p>
                <p className="mt-0.5 text-[10px] text-slate-500">
                  Sources represented in your database
                </p>
              </div>
            </div>

            {(stats?.jobs_by_source ?? []).length > 0 ? (
              stats!.jobs_by_source.map((item) => (
                <div
                  key={item.source}
                  className="flex items-center justify-between border-t border-slate-700/40 py-3 first:border-0"
                >
                  <div className="flex items-center gap-2">
                    <span className="status-dot" />
                    <span className="text-[11px] capitalize text-slate-300">
                      {item.source.replaceAll("_", " ")}
                    </span>
                  </div>
                  <span className="text-[11px] font-semibold text-slate-200">
                    {formatNumber(item.count)} jobs
                  </span>
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-500">
                Source statistics are not available yet.
              </p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
