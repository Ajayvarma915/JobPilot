import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Bell,
  BriefcaseBusiness,
  Building2,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Command,
  Download,
  ExternalLink,
  FileCheck2,
  FileText,
  Filter,
  Gauge,
  Globe2,
  LayoutDashboard,
  LoaderCircle,
  MapPin,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  WandSparkles,
  Zap,
  type LucideIcon,
} from "lucide-react";

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

type Screen = "overview" | "jobs" | "resume";
type ApiStatus = "checking" | "connected" | "offline";
type CareerLevelFilter = "early" | "all";

interface Company {
  id: number;
  name: string;
}

interface JobFilters {
  company: string;
  location: string;
  source: string;
  career_level: CareerLevelFilter;
}

interface JobMatch {
  score: number;
  recommendation: "strong_match" | "good_match" | "review" | "low_match";
  recommendation_label: string;
  role_family: string;
  seniority: string;
  required_years: number | null;
  analysis_confidence: string;
  score_breakdown: {
    role: number;
    seniority: number;
    experience: number;
    skills: number;
    education: number;
    location: number;
  };
  matched_required_skills: string[];
  missing_required_skills: string[];
  required_skills: string[];
  matched_preferred_skills: string[];
  preferred_skills: string[];
  required_education: string[];
  hard_constraints: string[];
  reasons: string[];
  concerns: string[];
}

interface Job {
  id: number;
  external_id: string | null;
  title: string;
  company: Company;
  location: string | null;
  url: string;
  description: string;
  source: string;
  experience_level: string | null;
  employment_type: string | null;
  posted_at: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  is_active: boolean;
  match?: JobMatch;
}

interface DashboardStats {
  total_jobs: number;
  active_jobs: number;
  inactive_jobs: number;
  total_companies: number;
  jobs_by_source: Array<{ source: string; count: number }>;
  jobs_by_experience_level: Array<{
    experience_level: string;
    count: number;
  }>;
}

interface EvidenceSummary {
  status: "ready" | "not_ready";
  record_count: number;
  verified_count: number;
  pending_count: number;
  counts_by_category: Record<string, number>;
  source_resume?: {
    file?: string | null;
    sha256?: string | null;
  };
}

interface JobListResponse {
  items: Job[];
  pagination: {
    limit: number;
    offset: number;
    total: number;
    has_more: boolean;
  };
}

interface SelectedEvidence {
  evidence_id: string;
  category: string;
  title: string;
  statement: string;
  score: number;
  reason: string[];
  matched_required_skills: string[];
  matched_preferred_skills: string[];
  user_verified: boolean;
  source: {
    file?: string;
    section?: string;
    text?: string;
  };
}

interface EvidenceSelection {
  job: { title: string };
  signals: {
    required_skills: string[];
    preferred_skills: string[];
    inferred_job_technologies: string[];
  };
  coverage: {
    required_skills: number;
    verified_covered: string[];
    awaiting_evidence_review: string[];
    not_found_in_evidence: string[];
  };
  selected_evidence: SelectedEvidence[];
  review_queue: SelectedEvidence[];
  counts: {
    verified_selected: number;
    unverified_relevant_for_review: number;
  };
  safety: {
    only_user_verified_records_selected: boolean;
    unverified_records_are_suggestions_only: boolean;
    generated_claims: boolean;
  };
}

interface GeneratedResume {
  status: string;
  job_title: string;
  resume_filename: string;
  resume_path: string;
  audit_path: string;
  selected_evidence_count: number;
  download_url: string;
  safety: {
    verified_evidence_required: boolean;
    claims_invented: boolean;
  };
}

interface ApiError {
  detail?: string;
}

const NAV_ITEMS: Array<{
  id: Screen;
  label: string;
  description: string;
  icon: LucideIcon;
}> = [
  {
    id: "overview",
    label: "Overview",
    description: "Your workspace",
    icon: LayoutDashboard,
  },
  {
    id: "jobs",
    label: "Discover jobs",
    description: "Explore opportunities",
    icon: BriefcaseBusiness,
  },
  {
    id: "resume",
    label: "Resume studio",
    description: "Tailor your resume",
    icon: FileCheck2,
  },
];

const numberFormat = new Intl.NumberFormat("en-IN");

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }

  return numberFormat.format(value);
}

function compactText(value: string | null | undefined): string {
  return (value || "").replace(/\s+/g, " ").trim();
}

function parseSkills(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

function errorText(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "An unexpected error occurred.";
}

async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);

  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;

  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
    });
  } catch {
    throw new Error(
      `Unable to reach the JobPilot API at ${API_BASE}. Check that the backend is running.`,
    );
  }

  const rawText = await response.text();
  let data: unknown = {};

  if (rawText) {
    try {
      data = JSON.parse(rawText);
    } catch {
      data = { detail: rawText };
    }
  }

  if (!response.ok) {
    const detail = (data as ApiError)?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : `API request failed with HTTP ${response.status}.`,
    );
  }

  return data as T;
}

function categoryLabel(category: string): string {
  return category.replaceAll("_", " ");
}

function makeResumeRequest(
  jobTitle: string,
  jobDescription: string,
  requiredSkills: string,
  preferredSkills: string,
) {
  return {
    job_title: jobTitle.trim(),
    job_description: jobDescription.trim(),
    required_skills: parseSkills(requiredSkills),
    preferred_skills: parseSkills(preferredSkills),
    max_projects: 3,
  };
}

function recommendationTone(
  recommendation: JobMatch["recommendation"],
): string {
  switch (recommendation) {
    case "strong_match":
      return "border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-200";
    case "good_match":
      return "border-blue-400/20 bg-blue-400/[0.08] text-blue-200";
    case "review":
      return "border-amber-300/20 bg-amber-300/[0.08] text-amber-100";
    default:
      return "border-rose-400/20 bg-rose-400/[0.08] text-rose-200";
  }
}

function MatchBadge({ match }: { match?: JobMatch }) {
  if (!match) {
    return (
      <span className="inline-flex items-center rounded-full border border-slate-700/60 bg-slate-800/40 px-2.5 py-1 text-[10px] text-slate-500">
        Match unavailable
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold ${recommendationTone(match.recommendation)}`}
      title={`Structured candidate match score: ${match.score}/100`}
    >
      <Target size={11} />
      {Math.round(match.score)}/100 · {match.recommendation_label}
    </span>
  );
}

function MatchDetails({ match }: { match?: JobMatch }) {
  if (!match) {
    return (
      <p className="mt-3 text-[11px] text-slate-500">
        Match details are unavailable for this job.
      </p>
    );
  }

  const components: Array<{ label: string; value: number; max: number }> = [
    { label: "Role fit", value: match.score_breakdown.role, max: 25 },
    { label: "Seniority", value: match.score_breakdown.seniority, max: 20 },
    { label: "Experience", value: match.score_breakdown.experience, max: 20 },
    { label: "Skills", value: match.score_breakdown.skills, max: 20 },
    { label: "Education", value: match.score_breakdown.education, max: 10 },
    { label: "Location", value: match.score_breakdown.location, max: 5 },
  ];

  return (
    <div className="mt-4 grid grid-cols-1 gap-4 border-t border-slate-700/50 pt-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div>
        <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">
          Score breakdown
        </p>

        <div className="space-y-2.5">
          {components.map((component) => (
            <div key={component.label}>
              <div className="mb-1 flex items-center justify-between gap-3 text-[10px]">
                <span className="text-slate-400">{component.label}</span>
                <span className="tabular-nums text-slate-300">
                  {component.value.toFixed(1)} / {component.max}
                </span>
              </div>

              <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-400"
                  style={{
                    width: `${Math.max(
                      0,
                      Math.min(100, (component.value / component.max) * 100),
                    )}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>

        <p className="mt-3 text-[10px] text-slate-500">
          JD analysis confidence: {match.analysis_confidence}
          {match.required_years != null
            ? ` · Minimum experience detected: ${match.required_years}+ years`
            : " · No explicit minimum years detected"}
        </p>
      </div>

      <div className="space-y-3">
        <div>
          <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">
            Why it matches
          </p>

          {match.reasons.length > 0 ? (
            <ul className="space-y-1.5">
              {match.reasons.map((reason, index) => (
                <li
                  key={`${index}-${reason}`}
                  className="flex gap-2 text-[11px] leading-4 text-slate-300"
                >
                  <CheckCircle2
                    size={12}
                    className="mt-0.5 shrink-0 text-emerald-300"
                  />
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[11px] text-slate-500">
              No positive match signals were identified.
            </p>
          )}
        </div>

        {match.matched_required_skills.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-semibold text-emerald-300">
              Required skills matched
            </p>
            <p className="text-[11px] leading-4 text-slate-300">
              {match.matched_required_skills.join(", ")}
            </p>
          </div>
        )}

        {match.matched_preferred_skills.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-semibold text-blue-300">
              Preferred skills matched
            </p>
            <p className="text-[11px] leading-4 text-slate-300">
              {match.matched_preferred_skills.join(", ")}
            </p>
          </div>
        )}

        {match.missing_required_skills.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-semibold text-amber-200">
              Required skills not found in profile
            </p>
            <p className="text-[11px] leading-4 text-slate-300">
              {match.missing_required_skills.join(", ")}
            </p>
          </div>
        )}

        {match.hard_constraints.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-semibold text-rose-200">
              Potential hard constraints
            </p>
            <p className="text-[11px] leading-4 text-slate-300">
              {match.hard_constraints.join(" · ")}
            </p>
          </div>
        )}

        {match.concerns.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-semibold text-amber-200">
              Things to check
            </p>
            <ul className="space-y-1">
              {match.concerns.map((concern, index) => (
                <li
                  key={`${index}-${concern}`}
                  className="text-[11px] leading-4 text-slate-400"
                >
                  {concern}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div className="relative grid h-10 w-10 place-items-center overflow-hidden rounded-[14px] border border-blue-300/25 bg-gradient-to-br from-blue-500 via-indigo-500 to-violet-600 shadow-[0_7px_25px_rgba(73,105,241,0.28)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_25%_10%,rgba(255,255,255,0.42),transparent_55%)]" />
        <Command className="relative h-5 w-5 text-white" strokeWidth={2.3} />
      </div>

      <div>
        <p className="text-[16px] font-bold tracking-[-0.035em] text-white">
          JobPilot<span className="text-blue-400">.</span>
        </p>
        <p className="mt-0.5 text-[9px] font-semibold tracking-[0.21em] text-slate-500">
          CAREER INTELLIGENCE
        </p>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: ApiStatus }) {
  const connected = status === "connected";
  const checking = status === "checking";

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-medium ${
        connected
          ? "border-emerald-400/15 bg-emerald-400/[0.07] text-emerald-300"
          : checking
            ? "border-amber-300/15 bg-amber-300/[0.06] text-amber-200"
            : "border-rose-400/20 bg-rose-400/[0.07] text-rose-300"
      }`}
    >
      {checking ? (
        <LoaderCircle className="loading-ring h-3 w-3" />
      ) : (
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            connected ? "bg-emerald-400" : "bg-rose-400"
          }`}
        />
      )}

      {connected ? "API connected" : checking ? "Connecting" : "API offline"}
    </span>
  );
}

function SectionHeading({
  eyebrow,
  title,
  description,
  right,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  right?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && (
          <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-blue-300">
            {eyebrow}
          </p>
        )}

        <h2 className="text-xl font-semibold tracking-[-0.04em] text-slate-100">
          {title}
        </h2>

        {description && (
          <p className="mt-1.5 max-w-2xl text-[12px] leading-5 text-slate-400">
            {description}
          </p>
        )}
      </div>

      {right}
    </div>
  );
}

function MetricCard({
  label,
  value,
  caption,
  icon: Icon,
  iconStyle,
  delay = 0,
}: {
  label: string;
  value: string | number;
  caption: string;
  icon: LucideIcon;
  iconStyle: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.36, delay }}
      whileHover={{ y: -3 }}
      className="panel panel-hover rounded-2xl p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-[12px] font-medium text-slate-400">{label}</p>
        <div className={`grid h-9 w-9 place-items-center rounded-xl ${iconStyle}`}>
          <Icon size={17} strokeWidth={1.8} />
        </div>
      </div>

      <p className="mt-5 text-[29px] font-semibold tracking-[-0.055em] text-white">
        {value}
      </p>

      <p className="mt-1.5 text-[11px] text-slate-500">{caption}</p>
    </motion.div>
  );
}

function EmptyState({
  icon: Icon,
  title,
  message,
}: {
  icon: LucideIcon;
  title: string;
  message: string;
}) {
  return (
    <div className="flex min-h-44 flex-col items-center justify-center px-6 py-8 text-center">
      <div className="mb-3 grid h-11 w-11 place-items-center rounded-2xl border border-slate-700/70 bg-slate-800/50 text-slate-400">
        <Icon size={19} />
      </div>
      <p className="text-sm font-medium text-slate-200">{title}</p>
      <p className="mt-1.5 max-w-sm text-xs leading-5 text-slate-500">
        {message}
      </p>
    </div>
  );
}

function JobMiniCard({
  job,
  onTailor,
}: {
  job: Job;
  onTailor: (job: Job) => void;
}) {
  return (
    <div className="group flex flex-wrap items-center justify-between gap-3 border-b border-slate-700/40 py-4 last:border-0">
      <div className="flex min-w-0 items-start gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-slate-700/60 bg-slate-800/70 text-slate-300">
          <Building2 size={17} />
        </div>

        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold text-slate-100">
            {job.title}
          </p>
          <p className="mt-1 text-[11px] text-slate-400">
            {job.company?.name || "Unknown company"}
          </p>

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-500">
            {job.location && (
              <span className="inline-flex items-center gap-1">
                <MapPin size={11} />
                {job.location}
              </span>
            )}

            {job.experience_level && (
              <span className="inline-flex items-center gap-1">
                <Clock3 size={11} />
                {job.experience_level}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <MatchBadge match={job.match} />
        <button
          className="secondary-button shrink-0 !px-3 !py-2"
          onClick={() => onTailor(job)}
        >
          Tailor resume
          <ArrowRight size={13} />
        </button>
      </div>
    </div>
  );
}

function OverviewView({
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
            description="Open a role to inspect its original description or prepare a tailored resume."
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

      <div className="flex justify-end">
        <button
          className="secondary-button"
          onClick={onRefresh}
          disabled={loading}
        >
          <RefreshCw size={13} />
          Refresh dashboard
        </button>
      </div>
    </div>
  );
}

function JobsView({
  jobs,
  total,
  hasMore,
  page,
  loading,
  error,
  query,
  setQuery,
  filterDraft,
  setFilterDraft,
  sourceOptions,
  onApplyFilters,
  onPrevious,
  onNext,
  onRefresh,
  onTailor,
}: {
  jobs: Job[];
  total: number;
  hasMore: boolean;
  page: number;
  loading: boolean;
  error: string | null;
  query: string;
  setQuery: (value: string) => void;
  filterDraft: JobFilters;
  setFilterDraft: (value: JobFilters) => void;
  sourceOptions: string[];
  onApplyFilters: (event: FormEvent<HTMLFormElement>) => void;
  onPrevious: () => void;
  onNext: () => void;
  onRefresh: () => void;
  onTailor: (job: Job) => void;
}) {
  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Discover"
        title="Explore opportunities"
        description="Search your collected jobs by title, company, description, or location."
        right={
          <button
            className="secondary-button"
            onClick={onRefresh}
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? "loading-ring" : ""} />
            Refresh
          </button>
        }
      />

      <form
        onSubmit={onApplyFilters}
        className="panel rounded-2xl p-4 sm:p-5"
      >
        <div className="flex flex-col gap-3 lg:flex-row">
          <div className="relative min-w-0 flex-1">
            <Search
              size={16}
              className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500"
            />
            <input
              className="field !pl-10"
              placeholder="Search jobs, skills, companies..."
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>

          <button className="primary-button shrink-0" type="submit">
            <Search size={14} />
            Search jobs
          </button>
        </div>

        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <input
            className="field"
            placeholder="Company"
            value={filterDraft.company}
            onChange={(event) =>
              setFilterDraft({
                ...filterDraft,
                company: event.target.value,
              })
            }
          />

          <input
            className="field"
            placeholder="Location"
            value={filterDraft.location}
            onChange={(event) =>
              setFilterDraft({
                ...filterDraft,
                location: event.target.value,
              })
            }
          />

          <select
            className="field"
            value={filterDraft.source}
            onChange={(event) =>
              setFilterDraft({
                ...filterDraft,
                source: event.target.value,
              })
            }
          >
            <option value="">All sources</option>
            {sourceOptions.map((source) => (
              <option key={source} value={source}>
                {source.replaceAll("_", " ")}
              </option>
            ))}
          </select>

          <select
            className="field"
            value={filterDraft.career_level}
            onChange={(event) =>
              setFilterDraft({
                ...filterDraft,
                career_level: event.target.value as CareerLevelFilter,
              })
            }
            aria-label="Role level filter"
          >
            <option value="early">Early-career suitable</option>
            <option value="all">All role levels</option>
          </select>

          <button className="secondary-button" type="submit">
            <Filter size={14} />
            Apply filters
          </button>
        </div>
      </form>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[12px] text-slate-400">
          <BriefcaseBusiness size={15} />
          <span>
            <span className="font-semibold text-slate-200">
              {formatNumber(total)}
            </span>{" "}
            jobs found
          </span>
        </div>

        <span className="text-[10px] text-slate-500">
          Page {page + 1} · 10 jobs per page
        </span>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-4 text-sm text-rose-200">
          {error}
        </div>
      )}

      {loading ? (
        <div className="panel flex min-h-56 items-center justify-center rounded-2xl">
          <div className="flex items-center gap-3 text-sm text-slate-400">
            <LoaderCircle className="loading-ring" size={18} />
            Loading jobs from the API...
          </div>
        </div>
      ) : jobs.length === 0 ? (
        <div className="panel rounded-2xl">
          <EmptyState
            icon={Search}
            title="No matching opportunities"
            message={
              filterDraft.career_level === "early"
                ? "No jobs matched all current filters and the early-career suitability rules. Choose ‘All role levels’ to inspect other jobs and their match concerns."
                : "Try another keyword, company, or location filter."
            }
          />
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job, index) => (
            <motion.article
              key={job.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(index * 0.035, 0.2) }}
              className="panel panel-hover rounded-2xl p-4 sm:p-5"
            >
              <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
                <div className="flex min-w-0 gap-3.5">
                  <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-slate-700/60 bg-slate-800/60 text-slate-300">
                    <Building2 size={18} />
                  </div>

                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold leading-5 text-slate-100">
                      {job.title}
                    </h3>
                    <p className="mt-1 text-[11px] text-slate-400">
                      {job.company?.name || "Unknown company"}
                    </p>

                    <div className="mt-2">
                      <MatchBadge match={job.match} />
                    </div>

                    <div className="mt-3 flex flex-wrap gap-x-3 gap-y-2 text-[10px] text-slate-500">
                      {job.location && (
                        <span className="inline-flex items-center gap-1">
                          <MapPin size={12} />
                          {job.location}
                        </span>
                      )}
                      {job.experience_level && (
                        <span className="inline-flex items-center gap-1">
                          <Clock3 size={12} />
                          {job.experience_level}
                        </span>
                      )}
                      <span className="inline-flex items-center gap-1">
                        <Globe2 size={12} />
                        {job.source.replaceAll("_", " ")}
                      </span>
                    </div>

                    <p className="mt-3 max-w-3xl text-[11px] leading-5 text-slate-400">
                      {compactText(job.description).slice(0, 270)}
                      {compactText(job.description).length > 270 ? "…" : ""}
                    </p>
                  </div>
                </div>

                <div className="flex shrink-0 flex-wrap items-center gap-2 lg:justify-end">
                  <a
                    className="secondary-button !px-3 !py-2"
                    href={job.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Original posting
                    <ExternalLink size={13} />
                  </a>

                  <button
                    className="primary-button !px-3 !py-2"
                    onClick={() => onTailor(job)}
                  >
                    <Sparkles size={13} />
                    Tailor
                  </button>
                </div>
              </div>

              <details className="group mt-4 rounded-xl border border-slate-700/45 bg-slate-950/20 px-3.5 py-3">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-[11px] font-semibold text-slate-300 marker:hidden">
                  <span className="inline-flex items-center gap-2">
                    <Target size={13} className="text-blue-300" />
                    Why this match score?
                  </span>
                  <span className="text-[10px] font-normal text-slate-500 transition group-open:rotate-180">
                    ⌄
                  </span>
                </summary>
                <MatchDetails match={job.match} />
              </details>
            </motion.article>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between gap-3 border-t border-slate-700/40 pt-4">
        <button
          className="secondary-button"
          onClick={onPrevious}
          disabled={page === 0 || loading}
        >
          <ChevronLeft size={15} />
          Previous
        </button>

        <button
          className="secondary-button"
          onClick={onNext}
          disabled={!hasMore || loading}
        >
          Next
          <ChevronRight size={15} />
        </button>
      </div>
    </div>
  );
}

function CoverageChip({
  label,
  items,
  tone,
}: {
  label: string;
  items: string[];
  tone: "green" | "amber" | "rose";
}) {
  const tones = {
    green: "border-emerald-400/15 bg-emerald-400/[0.06] text-emerald-200",
    amber: "border-amber-300/15 bg-amber-300/[0.06] text-amber-100",
    rose: "border-rose-400/15 bg-rose-400/[0.06] text-rose-200",
  };

  return (
    <div className={`rounded-xl border p-3 ${tones[tone]}`}>
      <p className="text-[10px] font-semibold uppercase tracking-wide opacity-80">
        {label}
      </p>
      <p className="mt-2 text-[12px] font-medium">
        {items.length > 0 ? items.join(", ") : "None"}
      </p>
    </div>
  );
}

function ResumeView({
  jobTitle,
  setJobTitle,
  jobDescription,
  setJobDescription,
  requiredSkills,
  setRequiredSkills,
  preferredSkills,
  setPreferredSkills,
  selection,
  selectionLoading,
  selectionError,
  generated,
  generationLoading,
  generationError,
  onSelect,
  onGenerate,
}: {
  jobTitle: string;
  setJobTitle: (value: string) => void;
  jobDescription: string;
  setJobDescription: (value: string) => void;
  requiredSkills: string;
  setRequiredSkills: (value: string) => void;
  preferredSkills: string;
  setPreferredSkills: (value: string) => void;
  selection: EvidenceSelection | null;
  selectionLoading: boolean;
  selectionError: string | null;
  generated: GeneratedResume | null;
  generationLoading: boolean;
  generationError: string | null;
  onSelect: (event: FormEvent<HTMLFormElement>) => void;
  onGenerate: () => void;
}) {
  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Resume intelligence"
        title="Tailor your resume"
        description="Paste a real job description, identify its skills, and select evidence from your verified master resume."
      />

      <div className="grid grid-cols-1 gap-5 2xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
        <form
          onSubmit={onSelect}
          className="panel h-fit rounded-2xl p-5 sm:p-6"
        >
          <div className="mb-5 flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl border border-blue-300/15 bg-blue-400/[0.08] text-blue-300">
              <FileText size={18} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-100">
                Job requirements
              </h3>
              <p className="mt-1 text-[10px] text-slate-500">
                Submit the job description to the local API.
              </p>
            </div>
          </div>

          <label className="mb-2 block text-[11px] font-medium text-slate-300">
            Job title
          </label>
          <input
            className="field mb-4"
            value={jobTitle}
            onChange={(event) => setJobTitle(event.target.value)}
            placeholder="e.g. Frontend Software Engineer"
            maxLength={255}
            required
          />

          <label className="mb-2 block text-[11px] font-medium text-slate-300">
            Job description
          </label>
          <textarea
            className="field mb-4 min-h-44 resize-y leading-5"
            value={jobDescription}
            onChange={(event) => setJobDescription(event.target.value)}
            placeholder="Paste the complete job description, including qualifications and responsibilities..."
            minLength={20}
            maxLength={80000}
            required
          />

          <label className="mb-2 block text-[11px] font-medium text-slate-300">
            Required skills
          </label>
          <input
            className="field mb-4"
            value={requiredSkills}
            onChange={(event) => setRequiredSkills(event.target.value)}
            placeholder="JavaScript, React.js"
          />
          <p className="-mt-2 mb-4 text-[10px] text-slate-500">
            Comma-separated skills explicitly required by the employer.
          </p>

          <label className="mb-2 block text-[11px] font-medium text-slate-300">
            Preferred skills
          </label>
          <input
            className="field mb-5"
            value={preferredSkills}
            onChange={(event) => setPreferredSkills(event.target.value)}
            placeholder="Next.js, HTML, CSS"
          />

          {selectionError && (
            <div className="mb-4 rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-3 text-[11px] leading-5 text-rose-200">
              {selectionError}
            </div>
          )}

          <button
            className="primary-button w-full"
            type="submit"
            disabled={selectionLoading}
          >
            {selectionLoading ? (
              <LoaderCircle size={15} className="loading-ring" />
            ) : (
              <Target size={15} />
            )}
            {selectionLoading
              ? "Selecting evidence..."
              : "Analyze & select evidence"}
            {!selectionLoading && <ArrowRight size={15} />}
          </button>
        </form>

        <div className="space-y-5">
          <div className="panel min-h-52 rounded-2xl p-5 sm:p-6">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-xl border border-violet-300/15 bg-violet-400/[0.08] text-violet-300">
                  <Gauge size={18} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-100">
                    Requirement coverage
                  </h3>
                  <p className="mt-1 text-[10px] text-slate-500">
                    Based on the skills you supplied
                  </p>
                </div>
              </div>

              {selection && (
                <span className="rounded-full border border-emerald-400/15 bg-emerald-400/[0.06] px-2.5 py-1 text-[10px] text-emerald-300">
                  Analyzed
                </span>
              )}
            </div>

            {selection ? (
              <>
                <div className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
                  <CoverageChip
                    label="Verified covered"
                    items={selection.coverage.verified_covered}
                    tone="green"
                  />
                  <CoverageChip
                    label="Awaiting review"
                    items={selection.coverage.awaiting_evidence_review}
                    tone="amber"
                  />
                  <CoverageChip
                    label="Not found"
                    items={selection.coverage.not_found_in_evidence}
                    tone="rose"
                  />
                </div>

                <div className="flex items-center gap-2 text-[11px] text-slate-400">
                  <ShieldCheck size={14} className="text-emerald-300" />
                  Only user-verified evidence is eligible for resume generation.
                </div>
              </>
            ) : (
              <EmptyState
                icon={Target}
                title="Ready when you are"
                message="Submit a job description to see verified skill coverage, missing requirements, and the most relevant evidence."
              />
            )}
          </div>

          <div className="panel rounded-2xl p-5 sm:p-6">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-slate-100">
                  Selected evidence
                </h3>
                <p className="mt-1 text-[10px] text-slate-500">
                  Projects, skills, and experience relevant to this role.
                </p>
              </div>
              <span className="rounded-full border border-slate-700/70 bg-slate-800/50 px-2.5 py-1 text-[10px] text-slate-300">
                {selection?.selected_evidence.length ?? 0} records
              </span>
            </div>

            {!selection ? (
              <EmptyState
                icon={FileCheck2}
                title="No selection yet"
                message="The evidence list will appear after analysis."
              />
            ) : selection.selected_evidence.length === 0 ? (
              <EmptyState
                icon={ShieldCheck}
                title="No verified evidence selected"
                message="Review relevant evidence or try a different role. The generator will not invent qualifications."
              />
            ) : (
              <div className="space-y-3">
                {selection.selected_evidence.map((item) => (
                  <div
                    key={item.evidence_id}
                    className="rounded-xl border border-slate-700/50 bg-slate-950/30 p-3.5"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[12px] font-semibold text-slate-100">
                          {item.title}
                        </p>
                        <p className="mt-1 text-[10px] capitalize text-slate-500">
                          {categoryLabel(item.category)}
                          {item.source?.section
                            ? ` · ${categoryLabel(item.source.section)}`
                            : ""}
                        </p>
                      </div>
                      <span className="inline-flex shrink-0 items-center gap-1 text-[10px] text-emerald-300">
                        <CheckCircle2 size={12} />
                        Verified
                      </span>
                    </div>

                    <p className="mt-2 text-[11px] leading-5 text-slate-400">
                      {compactText(item.statement).slice(0, 240)}
                      {item.statement.length > 240 ? "…" : ""}
                    </p>

                    {item.reason.length > 0 && (
                      <p className="mt-2 text-[10px] text-blue-300/80">
                        {item.reason.join(" · ")}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}

            {generationError && (
              <div className="mt-4 rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-3 text-[11px] leading-5 text-rose-200">
                {generationError}
              </div>
            )}

            {generated && (
              <div className="mt-4 rounded-xl border border-emerald-400/20 bg-emerald-400/[0.055] p-4">
                <div className="flex items-start gap-2">
                  <CheckCircle2 size={16} className="mt-0.5 text-emerald-300" />
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] font-semibold text-emerald-100">
                      Resume generated successfully
                    </p>
                    <p className="mt-1 break-words text-[10px] leading-5 text-slate-400">
                      {generated.resume_filename}
                    </p>
                    <a
                      className="primary-button mt-3 !py-2"
                      href={`${API_BASE}${generated.download_url}`}
                    >
                      <Download size={14} />
                      Download DOCX
                    </a>
                  </div>
                </div>
              </div>
            )}

            <button
              className="primary-button mt-5 w-full"
              disabled={
                !selection?.selected_evidence.length || generationLoading
              }
              onClick={onGenerate}
            >
              {generationLoading ? (
                <LoaderCircle size={15} className="loading-ring" />
              ) : (
                <WandSparkles size={15} />
              )}
              {generationLoading
                ? "Generating document..."
                : "Generate tailored resume"}
              {!generationLoading && <ArrowRight size={15} />}
            </button>

            <p className="mt-3 text-center text-[10px] leading-4 text-slate-500">
              The API revalidates evidence before creating the Word document.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function App() {
  const [screen, setScreen] = useState<Screen>("overview");
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const [apiError, setApiError] = useState<string | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [previewJobs, setPreviewJobs] = useState<Job[]>([]);
  const [evidence, setEvidence] = useState<EvidenceSummary | null>(null);

  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [jobsHasMore, setJobsHasMore] = useState(false);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [jobsPage, setJobsPage] = useState(0);
  const [queryInput, setQueryInput] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");

  const [filterDraft, setFilterDraft] = useState<JobFilters>({
    company: "",
    location: "",
    source: "",
    career_level: "early",
  });

  const [appliedFilters, setAppliedFilters] = useState<JobFilters>({
    company: "",
    location: "",
    source: "",
    career_level: "early",
  });

  const [jobTitle, setJobTitle] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [requiredSkills, setRequiredSkills] = useState("");
  const [preferredSkills, setPreferredSkills] = useState("");

  const [selection, setSelection] = useState<EvidenceSelection | null>(null);
  const [selectionLoading, setSelectionLoading] = useState(false);
  const [selectionError, setSelectionError] = useState<string | null>(null);

  const [generated, setGenerated] = useState<GeneratedResume | null>(null);
  const [generationLoading, setGenerationLoading] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);

  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const refreshOverview = useCallback(async () => {
    setRefreshing(true);
    setApiError(null);

    try {
      const [health, dashboard, jobsResponse, evidenceSummary] =
        await Promise.all([
          apiRequest<{ status: string }>("/api/health"),
          apiRequest<DashboardStats>("/api/dashboard/stats"),
          apiRequest<JobListResponse>("/api/jobs?limit=5&offset=0"),
          apiRequest<EvidenceSummary>("/api/evidence/summary"),
        ]);

      if (health.status !== "ok") {
        throw new Error("The API returned an unexpected health status.");
      }

      setStats(dashboard);
      setPreviewJobs(jobsResponse.items);
      setEvidence(evidenceSummary);
      setApiStatus("connected");
    } catch (error) {
      setApiStatus("offline");
      setApiError(errorText(error));
    } finally {
      setOverviewLoading(false);
      setRefreshing(false);
    }
  }, []);

  const loadJobs = useCallback(async () => {
    setJobsLoading(true);
    setJobsError(null);

    try {
      const params = new URLSearchParams({
        limit: "10",
        offset: String(jobsPage * 10),
        active_only: "true",
      });

      if (appliedQuery) params.set("q", appliedQuery);

      if (appliedFilters.company) {
        params.set("company", appliedFilters.company);
      }

      if (appliedFilters.location) {
        params.set("location", appliedFilters.location);
      }

      if (appliedFilters.source) {
        params.set("source", appliedFilters.source);
      }

      params.set("career_level", appliedFilters.career_level);

      const result = await apiRequest<JobListResponse>(
        `/api/jobs?${params.toString()}`,
      );

      setJobs(result.items);
      setJobsTotal(result.pagination.total);
      setJobsHasMore(result.pagination.has_more);
    } catch (error) {
      setJobsError(errorText(error));
    } finally {
      setJobsLoading(false);
    }
  }, [appliedFilters, appliedQuery, jobsPage]);

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void refreshOverview();
    }, 0);

    return () => window.clearTimeout(timerId);
  }, [refreshOverview]);

  useEffect(() => {
    if (screen !== "jobs") {
      return;
    }

    const timerId = window.setTimeout(() => {
      void loadJobs();
    }, 0);

    return () => window.clearTimeout(timerId);
  }, [screen, loadJobs]);

  const openJobs = () => {
    setScreen("jobs");
    setMobileNavOpen(false);
  };

  const openResumeStudio = () => {
    setScreen("resume");
    setMobileNavOpen(false);
  };

  const openResumeForJob = (job: Job) => {
    setJobTitle(job.title);
    setJobDescription(job.description || "");
    setRequiredSkills("");
    setPreferredSkills("");
    setSelection(null);
    setSelectionError(null);
    setGenerated(null);
    setGenerationError(null);
    setScreen("resume");
    setMobileNavOpen(false);
  };

  const applyJobFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setJobsPage(0);
    setAppliedQuery(queryInput.trim());
    setAppliedFilters({
      company: filterDraft.company.trim(),
      location: filterDraft.location.trim(),
      source: filterDraft.source.trim(),
      career_level: filterDraft.career_level,
    });
  };

  const handlePreviousPage = () => {
    setJobsPage((value) => Math.max(0, value - 1));
  };

  const handleNextPage = () => {
    if (jobsHasMore) {
      setJobsPage((value) => value + 1);
    }
  };

  const handleSelectEvidence = async (
    event: FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();

    setSelectionLoading(true);
    setSelectionError(null);
    setGenerationError(null);
    setGenerated(null);

    try {
      const result = await apiRequest<EvidenceSelection>(
        "/api/evidence/select",
        {
          method: "POST",
          body: JSON.stringify(
            makeResumeRequest(
              jobTitle,
              jobDescription,
              requiredSkills,
              preferredSkills,
            ),
          ),
        },
      );

      setSelection(result);
    } catch (error) {
      setSelection(null);
      setSelectionError(errorText(error));
    } finally {
      setSelectionLoading(false);
    }
  };

  const handleGenerateResume = async () => {
    setGenerationLoading(true);
    setGenerationError(null);
    setGenerated(null);

    try {
      const result = await apiRequest<GeneratedResume>(
        "/api/resumes/generate",
        {
          method: "POST",
          body: JSON.stringify(
            makeResumeRequest(
              jobTitle,
              jobDescription,
              requiredSkills,
              preferredSkills,
            ),
          ),
        },
      );

      setGenerated(result);
    } catch (error) {
      setGenerationError(errorText(error));
    } finally {
      setGenerationLoading(false);
    }
  };

  const currentNavItem = NAV_ITEMS.find((item) => item.id === screen);
  const sourceOptions = (stats?.jobs_by_source ?? []).map(
    (item) => item.source,
  );

  return (
    <div className="min-h-screen text-slate-100">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-60 top-64 h-96 w-96 rounded-full bg-blue-500/[0.025] blur-3xl" />
        <div className="absolute -right-52 top-10 h-96 w-96 rounded-full bg-violet-500/[0.035] blur-3xl" />
      </div>

      <div className="relative flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-[246px] shrink-0 flex-col border-r border-slate-800/70 bg-[#090e19]/85 px-4 py-6 backdrop-blur-xl xl:flex">
          <div className="px-2">
            <Brand />
          </div>

          <div className="mt-10 px-3">
            <p className="text-[9px] font-bold uppercase tracking-[0.2em] text-slate-600">
              Workspace
            </p>
          </div>

          <nav className="mt-3 space-y-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const active = screen === item.id;

              return (
                <button
                  key={item.id}
                  onClick={() => setScreen(item.id)}
                  className={`group flex w-full items-center gap-3 rounded-xl border px-3 py-3 text-left transition ${
                    active
                      ? "border-blue-400/15 bg-blue-400/[0.085] text-blue-200"
                      : "border-transparent text-slate-400 hover:bg-white/[0.035] hover:text-slate-200"
                  }`}
                >
                  <Icon
                    size={17}
                    className={
                      active
                        ? "text-blue-300"
                        : "text-slate-500 group-hover:text-slate-300"
                    }
                  />

                  <span className="min-w-0 flex-1">
                    <span className="block text-[12px] font-semibold">
                      {item.label}
                    </span>

                    <span
                      className={`mt-0.5 block text-[10px] ${
                        active ? "text-blue-200/60" : "text-slate-600"
                      }`}
                    >
                      {item.description}
                    </span>
                  </span>

                  {active && (
                    <ChevronRight size={14} className="text-blue-300/70" />
                  )}
                </button>
              );
            })}
          </nav>

          <div className="mt-9 px-3">
            <p className="text-[9px] font-bold uppercase tracking-[0.2em] text-slate-600">
              System
            </p>
          </div>

          <div className="mt-3 rounded-xl border border-slate-700/40 bg-white/[0.02] p-3">
            <div className="flex items-center gap-2.5">
              <div className="grid h-8 w-8 place-items-center rounded-lg bg-emerald-400/[0.08] text-emerald-300">
                <Activity size={15} />
              </div>

              <div>
                <p className="text-[11px] font-semibold text-slate-200">
                  Local engine
                </p>
                <p className="mt-0.5 text-[9px] text-slate-500">
                  Python API
                </p>
              </div>
            </div>

            <div className="mt-3 flex items-center justify-between border-t border-slate-700/40 pt-3">
              <span className="text-[10px] text-slate-500">Connection</span>

              <span className="inline-flex items-center gap-1.5 text-[10px] text-slate-300">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    apiStatus === "connected"
                      ? "bg-emerald-400"
                      : apiStatus === "checking"
                        ? "bg-amber-300"
                        : "bg-rose-400"
                  }`}
                />

                {apiStatus === "connected"
                  ? "Online"
                  : apiStatus === "checking"
                    ? "Checking"
                    : "Offline"}
              </span>
            </div>
          </div>

          <div className="mt-auto rounded-2xl border border-blue-300/10 bg-gradient-to-br from-blue-400/[0.08] to-violet-400/[0.04] p-4">
            <div className="mb-3 grid h-8 w-8 place-items-center rounded-lg bg-blue-300/10 text-blue-300">
              <Sparkles size={16} />
            </div>

            <p className="text-[12px] font-semibold text-slate-100">
              Evidence-first AI
            </p>

            <p className="mt-1.5 text-[10px] leading-4 text-slate-500">
              Build resumes from reviewed evidence, not invented credentials.
            </p>
          </div>

          <div className="mt-5 flex items-center gap-3 border-t border-slate-800/80 px-2 pt-5">
            <div className="grid h-9 w-9 place-items-center rounded-xl border border-slate-700 bg-slate-800 text-[11px] font-bold text-slate-200">
              JP
            </div>

            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-medium text-slate-200">
                Local workspace
              </p>

              <p className="mt-0.5 text-[9px] text-slate-500">
                Personal job pipeline
              </p>
            </div>

            <ShieldCheck size={14} className="text-emerald-300/70" />
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-slate-800/70 bg-[#080c16]/85 backdrop-blur-2xl">
            <div className="flex h-[72px] items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
              <div className="flex min-w-0 items-center gap-3">
                <button
                  className="icon-button xl:hidden"
                  onClick={() => setMobileNavOpen((value) => !value)}
                  aria-label="Toggle navigation"
                >
                  <Command size={17} />
                </button>

                <div className="min-w-0">
                  <p className="truncate text-[13px] font-semibold text-slate-100">
                    {currentNavItem?.label ?? "Overview"}
                  </p>

                  <p className="mt-1 hidden text-[10px] text-slate-500 sm:block">
                    Your job search, organized.
                  </p>
                </div>
              </div>

              <div className="flex shrink-0 items-center gap-2 sm:gap-3">
                <StatusPill status={apiStatus} />

                <button
                  className="icon-button hidden sm:inline-flex"
                  onClick={() => void refreshOverview()}
                  aria-label="Refresh API data"
                  title="Refresh API data"
                  disabled={refreshing}
                >
                  <RefreshCw
                    size={15}
                    className={refreshing ? "loading-ring" : ""}
                  />
                </button>

                <div className="hidden h-7 w-px bg-slate-800 sm:block" />

                <button
                  className="icon-button relative"
                  onClick={openResumeStudio}
                  title="Open Resume Studio"
                  aria-label="Open Resume Studio"
                >
                  <Bell size={15} />

                  {evidence?.pending_count ? (
                    <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-amber-400 px-1 text-[8px] font-bold text-slate-950">
                      {evidence.pending_count}
                    </span>
                  ) : null}
                </button>
              </div>
            </div>

            <AnimatePresence>
              {mobileNavOpen && (
                <motion.nav
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden border-t border-slate-800/60 px-4 py-2 xl:hidden"
                >
                  {NAV_ITEMS.map((item) => {
                    const Icon = item.icon;

                    return (
                      <button
                        key={item.id}
                        onClick={() => {
                          setScreen(item.id);
                          setMobileNavOpen(false);
                        }}
                        className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-xs ${
                          screen === item.id
                            ? "bg-blue-400/[0.08] text-blue-200"
                            : "text-slate-400"
                        }`}
                      >
                        <Icon size={16} />
                        {item.label}
                      </button>
                    );
                  })}
                </motion.nav>
              )}
            </AnimatePresence>
          </header>

          <main className="mx-auto w-full max-w-[1640px] flex-1 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
            {apiError && (
              <div className="mb-6 flex flex-col justify-between gap-3 rounded-2xl border border-rose-400/20 bg-rose-400/[0.055] p-4 sm:flex-row sm:items-center">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 text-rose-300">
                    <Activity size={17} />
                  </div>

                  <div>
                    <p className="text-[12px] font-semibold text-rose-200">
                      The JobPilot API could not be reached
                    </p>

                    <p className="mt-1 text-[11px] leading-5 text-rose-200/70">
                      {apiError}
                    </p>

                    <p className="mt-1 text-[10px] text-slate-500">
                      Confirm that Uvicorn is running on {API_BASE}.
                    </p>
                  </div>
                </div>

                <button
                  className="secondary-button self-start !border-rose-300/15 sm:self-center"
                  onClick={() => void refreshOverview()}
                  disabled={refreshing}
                >
                  <RefreshCw size={13} />
                  Retry
                </button>
              </div>
            )}

            <AnimatePresence mode="wait">
              <motion.div
                key={screen}
                initial={{ opacity: 0, y: 7 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                {screen === "overview" && (
                  <OverviewView
                    stats={stats}
                    jobs={previewJobs}
                    evidence={evidence}
                    loading={overviewLoading}
                    onExplore={openJobs}
                    onRefresh={() => void refreshOverview()}
                    onTailor={openResumeForJob}
                    onBuild={openResumeStudio}
                  />
                )}

                {screen === "jobs" && (
                  <JobsView
                    jobs={jobs}
                    total={jobsTotal}
                    hasMore={jobsHasMore}
                    page={jobsPage}
                    loading={jobsLoading}
                    error={jobsError}
                    query={queryInput}
                    setQuery={setQueryInput}
                    filterDraft={filterDraft}
                    setFilterDraft={setFilterDraft}
                    sourceOptions={sourceOptions}
                    onApplyFilters={applyJobFilters}
                    onPrevious={handlePreviousPage}
                    onNext={handleNextPage}
                    onRefresh={() => void loadJobs()}
                    onTailor={openResumeForJob}
                  />
                )}

                {screen === "resume" && (
                  <ResumeView
                    jobTitle={jobTitle}
                    setJobTitle={setJobTitle}
                    jobDescription={jobDescription}
                    setJobDescription={setJobDescription}
                    requiredSkills={requiredSkills}
                    setRequiredSkills={setRequiredSkills}
                    preferredSkills={preferredSkills}
                    setPreferredSkills={setPreferredSkills}
                    selection={selection}
                    selectionLoading={selectionLoading}
                    selectionError={selectionError}
                    generated={generated}
                    generationLoading={generationLoading}
                    generationError={generationError}
                    onSelect={handleSelectEvidence}
                    onGenerate={() => void handleGenerateResume()}
                  />
                )}
              </motion.div>
            </AnimatePresence>

            <footer className="mt-12 flex flex-col justify-between gap-2 border-t border-slate-800/60 py-5 text-[10px] text-slate-600 sm:flex-row sm:items-center">
              <span>JobPilot · Personal career intelligence workspace</span>
              <span className="inline-flex items-center gap-1.5">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    apiStatus === "connected"
                      ? "bg-emerald-400"
                      : "bg-slate-600"
                  }`}
                />

                {apiStatus === "connected"
                  ? "Connected to your local API"
                  : "Waiting for the local API"}
              </span>
            </footer>
          </main>
        </div>
      </div>
    </div>
  );
}

export default App;