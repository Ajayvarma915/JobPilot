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
  CalendarDays,
  ClipboardList,
  ChevronDown,
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
  Plus,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  Trash2,
  AlertTriangle,
  WandSparkles,
  Zap,
  type LucideIcon,
} from "lucide-react";

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

// Default the workspace to roles based in India and remote roles not tied to another country.
const DEFAULT_JOB_LOCATION = "India";

type Screen = "overview" | "jobs" | "applications" | "resume";
type ApiStatus = "checking" | "connected" | "offline";
type CareerLevelFilter = "early" | "all";

interface Company {
  id: number;
  name: string;
}

interface CompanyOption extends Company {
  website: string | null;
  careers_url: string | null;
  job_count: number;
  active_job_count: number;
  source_types: string[];
}

interface LocationOption {
  city: string;
  value: string;
  job_count: number;
}

interface JobTitleSuggestion {
  title: string;
  count: number;
  companies: string[];
  matched_by: Array<"title" | "company">;
}

interface FilterOption {
  value: string;
  label: string;
  meta?: string;
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
  all_locations?: string | null;
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

interface CompanyDirectoryResponse {
  items: CompanyOption[];
  total: number;
  limit: number;
  active_only: boolean;
}

interface LocationDirectoryResponse {
  items: LocationOption[];
  total: number;
  active_only: boolean;
}

interface JobSuggestionResponse {
  query: string;
  items: JobTitleSuggestion[];
}

type ApplicationStatus =
  | "saved"
  | "preparing"
  | "ready_to_apply"
  | "applied"
  | "assessment"
  | "interview"
  | "offer"
  | "rejected"
  | "withdrawn";

interface TrackedApplication {
  id: number;
  job_id: number;
  status: ApplicationStatus;
  notes: string | null;
  resume_filename: string | null;
  cover_letter_filename: string | null;
  applied_at: string | null;
  next_action: string | null;
  follow_up_date: string | null;
  created_at: string;
  updated_at: string;
  job: {
    id: number;
    title: string;
    company: string;
    location: string | null;
    url: string;
    source: string;
    is_active: boolean;
  };
  job_reviewed: boolean;
  eligibility_confirmed: boolean;
  resume_reviewed: boolean;
  application_details_reviewed: boolean;
}

interface ApplicationListResponse {
  items: TrackedApplication[];
  total: number;
  limit: number;
  offset: number;
}

interface ApplicationStats {
  total: number;
  needs_action: number;
  by_status: Record<ApplicationStatus, number>;
}

interface TrackedJobIdsResponse {
  job_ids: number[];
}

interface ApplicationDeleteResponse {
  deleted: boolean;
  application_id: number;
  job_id: number;
}

interface ApplicationUpdatePayload {
  status: ApplicationStatus;
  notes: string | null;
  next_action: string | null;
  follow_up_date: string | null;
  resume_filename?: string | null;
  job_reviewed?: boolean;
  eligibility_confirmed?: boolean;
  resume_reviewed?: boolean;
  application_details_reviewed?: boolean;
}

interface ApplicationReadinessCheck {
  id: string;
  label: string;
  passed: boolean;
  blocking: boolean;
  detail: string;
}

interface ApplicationResumeOption {
  filename: string;
  format: "pdf" | "docx";
  modified_at: string;
  size_bytes: number;
}

interface ApplicationReadinessResponse {
  application_id: number;
  status: ApplicationStatus;
  ready: boolean;
  readiness_label: string;
  completed_checks: number;
  total_checks: number;
  checks: ApplicationReadinessCheck[];
  blockers: string[];
  review: {
    job_reviewed: boolean;
    eligibility_confirmed: boolean;
    resume_reviewed: boolean;
    application_details_reviewed: boolean;
  };
  resume_filename: string | null;
  resume_options: ApplicationResumeOption[];
  submission_note: string;
  job: { title: string; company: string };
}

const APPLICATION_STATUSES: Array<{
  value: ApplicationStatus;
  label: string;
}> = [
  { value: "saved", label: "Saved" },
  { value: "preparing", label: "Preparing" },
  { value: "ready_to_apply", label: "Ready to apply" },
  { value: "applied", label: "Applied" },
  { value: "assessment", label: "Assessment" },
  { value: "interview", label: "Interview" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Rejected" },
  { value: "withdrawn", label: "Withdrawn" },
];

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

interface ResumeScoreCheck {
  label: string;
  passed: boolean;
  points: number;
  detail: string;
}

interface ResumeEvaluation {
  readiness_label: string;
  readiness_passes_local_checks: boolean;
  global_disclaimer: string;
  ats_readability: {
    score: number;
    label: string;
    checks: ResumeScoreCheck[];
    issues: string[];
    pdf_page_count: number;
    pdf_extractable_word_count: number;
    disclaimer: string;
  };
  job_relevance: {
    score: number;
    label: string;
    required_skill_coverage: {
      score: number | null;
      matched: string[];
      missing: string[];
      awaiting_review: string[];
    };
    preferred_skill_coverage: {
      score: number | null;
      matched: string[];
      missing: string[];
    };
    job_technology_coverage: {
      score: number | null;
      matched: string[];
      missing: string[];
    };
    verified_evidence_categories: string[];
    blockers: string[];
    disclaimer: string;
  };
  achievement_quality: {
    score: number;
    label: string;
    sample_size: number;
    checks: Array<{ label: string; passed_count: number; sample_size: number }>;
    recommendation: string;
  };
  recommendations: string[];
}

interface GeneratedResume {
  status: string;
  job_title: string;
  resume_filename: string;
  resume_path: string;
  audit_path: string;
  selected_evidence_count: number;
  download_url: string;
  pdf_filename?: string;
  pdf_download_url?: string;
  evaluation?: ResumeEvaluation;
  safety: {
    verified_evidence_required: boolean;
    claims_invented: boolean;
  };
}

interface ApiError {
  detail?: string | { message?: string; blockers?: string[] };
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
    id: "applications",
    label: "Applications",
    description: "Track your pipeline",
    icon: ClipboardList,
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

async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);

  if (init?.body && !headers.has("Content-Type")) {
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
    let message = `API request failed with HTTP ${response.status}.`;

    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object") {
      const summary = detail.message || message;
      message = detail.blockers?.length
        ? `${summary} ${detail.blockers.join("; ")}`
        : summary;
    }

    throw new Error(message);
  }

  return data as T;
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

  const components: Array<{
    label: string;
    value: number;
    max: number;
  }> = [
    { label: "Role fit", value: match.score_breakdown.role, max: 25 },
    { label: "Seniority", value: match.score_breakdown.seniority, max: 20 },
    { label: "Experience", value: match.score_breakdown.experience, max: 20 },
    { label: "Skills", value: match.score_breakdown.skills, max: 20 },
    { label: "Education", value: match.score_breakdown.education, max: 10 },
    { label: "Location", value: match.score_breakdown.location, max: 5 },
  ];

  return (
    <div className="mt-4 grid grid-cols-1 gap-4 border-t border-slate-700/50 pt-4 xl:grid-cols-2">
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

function SearchableFilter({
  label,
  value,
  placeholder,
  options,
  allOptionLabel,
  onChange,
}: {
  label: string;
  value: string;
  placeholder: string;
  options: FilterOption[];
  allOptionLabel: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);

  const normalizedValue = value.trim().toLocaleLowerCase();
  const filteredOptions = options
    .filter(
      (option) =>
        !normalizedValue ||
        option.label.toLocaleLowerCase().includes(normalizedValue) ||
        option.value.toLocaleLowerCase().includes(normalizedValue),
    )
    .slice(0, 10);

  const exactOptionExists = options.some(
    (option) => option.value.toLocaleLowerCase() === normalizedValue,
  );

  return (
    <div className="relative min-w-0">
      <label className="sr-only">{label}</label>

      <div className="relative">
        <input
          className="field pr-9"
          value={value}
          placeholder={placeholder}
          autoComplete="off"
          aria-label={label}
          aria-autocomplete="list"
          aria-expanded={open}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            window.setTimeout(() => setOpen(false), 140);
          }}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
          }}
        />

        <button
          type="button"
          className="absolute inset-y-0 right-0 grid w-9 place-items-center text-slate-500 hover:text-slate-200"
          aria-label={`Show ${label.toLowerCase()} options`}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => setOpen((current) => !current)}
        >
          <ChevronDown size={15} />
        </button>
      </div>

      {open && (
        <div
          role="listbox"
          className="absolute left-0 top-[calc(100%+6px)] z-50 max-h-64 w-full min-w-[240px] overflow-y-auto rounded-xl border border-slate-700 bg-[#0d1423] p-1.5 shadow-2xl"
        >
          <button
            type="button"
            role="option"
            aria-selected={value === ""}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              onChange("");
              setOpen(false);
            }}
            className={`flex w-full items-start justify-between gap-2 rounded-lg px-3 py-2.5 text-left text-[11px] transition ${
              value === ""
                ? "bg-blue-400/[0.1] text-blue-200"
                : "text-slate-300 hover:bg-white/[0.05]"
            }`}
          >
            <span>{allOptionLabel}</span>
            <span className="text-[10px] text-slate-500">Clear filter</span>
          </button>

          {filteredOptions.map((option) => (
            <button
              type="button"
              role="option"
              aria-selected={value === option.value}
              key={option.value}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
              className={`flex w-full items-start justify-between gap-3 rounded-lg px-3 py-2.5 text-left transition ${
                value === option.value
                  ? "bg-blue-400/[0.1] text-blue-200"
                  : "text-slate-300 hover:bg-white/[0.05]"
              }`}
            >
              <span className="min-w-0 flex-1 truncate">
                {option.label}
              </span>
              {option.meta && (
                <span className="shrink-0 text-[10px] text-slate-500">
                  {option.meta}
                </span>
              )}
            </button>
          ))}

          {value.trim() && !exactOptionExists && (
            <button
              type="button"
              role="option"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => setOpen(false)}
              className="mt-1 flex w-full items-center gap-2 rounded-lg border-t border-slate-700/60 px-3 py-2.5 text-left text-[10px] text-blue-200 hover:bg-white/[0.04]"
            >
              <Search size={12} />
              Use typed filter: “{value.trim()}”
            </button>
          )}

          {filteredOptions.length === 0 && !value.trim() && (
            <p className="px-3 py-3 text-[11px] text-slate-500">
              No options available yet.
            </p>
          )}
        </div>
      )}
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
  suggestions,
  suggestionsLoading,
  suggestionsOpen,
  onQueryFocus,
  onQueryBlur,
  onSelectSuggestion,
  filterDraft,
  setFilterDraft,
  companyOptions,
  locationOptions,
  sourceOptions,
  onApplyFilters,
  onPrevious,
  onNext,
  onRefresh,
  onTrack,
  onUntrack,
  isTracked,
  trackingJobIds,
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
  suggestions: JobTitleSuggestion[];
  suggestionsLoading: boolean;
  suggestionsOpen: boolean;
  onQueryFocus: () => void;
  onQueryBlur: () => void;
  onSelectSuggestion: (suggestion: JobTitleSuggestion) => void;
  filterDraft: JobFilters;
  setFilterDraft: (value: JobFilters) => void;
  companyOptions: FilterOption[];
  locationOptions: FilterOption[];
  sourceOptions: string[];
  onApplyFilters: (event: FormEvent<HTMLFormElement>) => void;
  onPrevious: () => void;
  onNext: () => void;
  onRefresh: () => void;
  onTrack: (job: Job) => void;
  onUntrack: (job: Job) => void;
  isTracked: (jobId: number) => boolean;
  trackingJobIds: Set<number>;
  onTailor: (job: Job) => void;
}) {
  const showSuggestions = suggestionsOpen && query.trim().length >= 2;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Discover"
        title="Explore opportunities"
        description="Search job titles, skills or keywords, then narrow the results by company, location and experience."
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

      <form onSubmit={onApplyFilters} className="panel rounded-2xl p-4 sm:p-5">
        <div className="flex flex-col gap-3 lg:flex-row">
          <div className="relative z-30 min-w-0 flex-1">
            <Search
              size={16}
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500"
            />
            <input
              className="field !pl-10"
              placeholder="Search job titles, skills or keywords..."
              value={query}
              autoComplete="off"
              aria-label="Search jobs"
              aria-autocomplete="list"
              aria-expanded={showSuggestions}
              onFocus={onQueryFocus}
              onBlur={onQueryBlur}
              onChange={(event) => setQuery(event.target.value)}
            />

            <AnimatePresence>
              {showSuggestions && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  className="absolute left-0 right-0 top-[calc(100%+7px)] max-h-72 overflow-y-auto rounded-xl border border-slate-700 bg-[#0d1423] p-2 shadow-2xl"
                >
                  <div className="flex items-center justify-between px-2 py-1.5">
                    <p className="text-[9px] font-bold uppercase tracking-[0.16em] text-slate-500">
                      Suggested job titles
                    </p>
                    {suggestionsLoading && (
                      <LoaderCircle size={12} className="loading-ring text-blue-300" />
                    )}
                  </div>

                  {!suggestionsLoading && suggestions.length === 0 ? (
                    <p className="px-2 py-3 text-[11px] leading-5 text-slate-400">
                      No title suggestions. Press Search jobs to search the
                      descriptions and keywords too.
                    </p>
                  ) : (
                    suggestions.map((suggestion) => (
                      <button
                        type="button"
                        key={suggestion.title}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => onSelectSuggestion(suggestion)}
                        className="flex w-full items-start gap-3 rounded-lg px-2.5 py-2.5 text-left hover:bg-white/[0.05]"
                      >
                        <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-blue-400/[0.08] text-blue-300">
                          <BriefcaseBusiness size={13} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-[11px] font-medium text-slate-100">
                            {suggestion.title}
                          </p>
                          <p className="mt-1 truncate text-[10px] text-slate-500">
                            {suggestion.companies.join(", ")}
                          </p>
                        </div>
                        <span className="shrink-0 pt-1 text-[9px] text-slate-500">
                          {suggestion.count} listing
                          {suggestion.count === 1 ? "" : "s"}
                        </span>
                      </button>
                    ))
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <button className="primary-button shrink-0" type="submit">
            <Search size={14} />
            Search jobs
          </button>
        </div>

        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <SearchableFilter
            label="Company"
            value={filterDraft.company}
            placeholder="All companies · search"
            allOptionLabel="All companies"
            options={companyOptions}
            onChange={(value) =>
              setFilterDraft({ ...filterDraft, company: value })
            }
          />

          <SearchableFilter
            label="Location"
            value={filterDraft.location}
            placeholder="All locations · search"
            allOptionLabel="All locations"
            options={locationOptions}
            onChange={(value) =>
              setFilterDraft({ ...filterDraft, location: value })
            }
          />

          <select
            className="field"
            value={filterDraft.source}
            aria-label="Job source"
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
            aria-label="Role level filter"
            onChange={(event) =>
              setFilterDraft({
                ...filterDraft,
                career_level: event.target.value as CareerLevelFilter,
              })
            }
          >
            <option value="early">Early-career suitable</option>
            <option value="all">All role levels</option>
          </select>

          <button className="secondary-button" type="submit">
            <Filter size={14} />
            Apply filters
          </button>
        </div>

        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-slate-500">
          <span>
            {companyOptions.length} companies with active jobs
          </span>
          <span>
            {locationOptions.length} locations in collected listings
          </span>
          <span>Keyword search also searches job descriptions</span>
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
                ? "No jobs matched all filters and the early-career rules. Choose All role levels to inspect other jobs."
                : "Try another keyword, company, location or source."
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
                        <span
                          className="inline-flex items-center gap-1"
                          title={
                            job.all_locations && job.all_locations !== job.location
                              ? `All listed locations: ${job.all_locations}`
                              : undefined
                          }
                        >
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
                    className={`secondary-button !px-3 !py-2 ${isTracked(job.id) ? "!border-rose-400/25 !text-rose-200 hover:!bg-rose-400/[0.08]" : ""}`}
                    onClick={() => isTracked(job.id) ? onUntrack(job) : onTrack(job)}
                    disabled={trackingJobIds.has(job.id)}
                    title={isTracked(job.id) ? "Remove this job from your application pipeline" : "Add this job to your application pipeline"}
                    aria-label={isTracked(job.id) ? `Untrack ${job.title} at ${job.company?.name || "this company"}` : `Track ${job.title} at ${job.company?.name || "this company"}`}
                  >
                    {trackingJobIds.has(job.id) ? (
                      <LoaderCircle size={13} className="loading-ring" />
                    ) : isTracked(job.id) ? (
                      <Trash2 size={13} />
                    ) : (
                      <Plus size={13} />
                    )}
                    {trackingJobIds.has(job.id)
                      ? "Saving..."
                      : isTracked(job.id)
                        ? "Untrack"
                        : "Track"}
                  </button>
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
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-[11px] font-semibold text-slate-300">
                  <span className="inline-flex items-center gap-2">
                    <Target size={13} className="text-blue-300" />
                    Why this match score?
                  </span>
                  <ChevronDown
                    size={13}
                    className="text-slate-500 transition group-open:rotate-180"
                  />
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

function ApplicationCard({
  application,
  onUpdate,
  onRequestRemove,
}: {
  application: TrackedApplication;
  onUpdate: (
    applicationId: number,
    update: ApplicationUpdatePayload,
  ) => Promise<TrackedApplication>;
  onRequestRemove: (application: TrackedApplication) => void;
}) {
  const [draftStatus, setDraftStatus] = useState<ApplicationStatus>(application.status);
  const [notes, setNotes] = useState(application.notes ?? "");
  const [nextAction, setNextAction] = useState(application.next_action ?? "");
  const [followUpDate, setFollowUpDate] = useState(application.follow_up_date ?? "");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState(false);
  const [readinessOpen, setReadinessOpen] = useState(false);
  const [readiness, setReadiness] = useState<ApplicationReadinessResponse | null>(null);
  const [readinessLoading, setReadinessLoading] = useState(false);
  const [readinessSaving, setReadinessSaving] = useState(false);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const [readinessSavedMessage, setReadinessSavedMessage] = useState<string | null>(null);
  const [selectedResumeFilename, setSelectedResumeFilename] = useState(
    application.resume_filename ?? "",
  );

  const loadReadiness = async () => {
    setReadinessLoading(true);
    setReadinessError(null);
    try {
      const response = await apiRequest<ApplicationReadinessResponse>(
        `/api/applications/${application.id}/readiness`,
      );
      setReadiness(response);
      setSelectedResumeFilename(response.resume_filename ?? "");
    } catch (error) {
      setReadinessError(errorText(error));
    } finally {
      setReadinessLoading(false);
    }
  };

  const visibleReadinessChecks = (readiness?.checks ?? []).map((check) => {
    if (!readiness) return check;
    const reviewValueById: Record<string, boolean> = {
      job_reviewed: readiness.review.job_reviewed,
      eligibility_confirmed: readiness.review.eligibility_confirmed,
      resume_reviewed: readiness.review.resume_reviewed,
      application_details_reviewed: readiness.review.application_details_reviewed,
      resume_selected: Boolean(
        selectedResumeFilename && readiness.resume_options.some(
          (option) => option.filename === selectedResumeFilename,
        ),
      ),
    };
    return Object.prototype.hasOwnProperty.call(reviewValueById, check.id)
      ? { ...check, passed: reviewValueById[check.id] }
      : check;
  });
  const readinessIsComplete = Boolean(
    readiness && visibleReadinessChecks
      .filter((check) => check.blocking)
      .every((check) => check.passed),
  );

  const toggleReadiness = async () => {
    const nextOpen = !readinessOpen;
    setReadinessOpen(nextOpen);
    if (nextOpen) {
      // Always refresh on open so newly generated files and changed job status appear.
      await loadReadiness();
    }
  };

  const updateReadinessReview = (
    field: keyof ApplicationReadinessResponse["review"],
    value: boolean,
  ) => {
    setReadiness((current) => current ? {
      ...current,
      review: { ...current.review, [field]: value },
    } : current);
    setReadinessSavedMessage(null);
    setReadinessError(null);
  };

  const saveReadinessReview = async (targetStatus: ApplicationStatus = draftStatus) => {
    if (!readiness || readinessSaving) return;
    setReadinessSaving(true);
    setReadinessError(null);
    setReadinessSavedMessage(null);
    try {
      const updated = await onUpdate(application.id, {
        status: targetStatus,
        notes: notes.trim() || null,
        next_action: nextAction.trim() || null,
        follow_up_date: followUpDate || null,
        resume_filename: selectedResumeFilename || null,
        job_reviewed: readiness.review.job_reviewed,
        eligibility_confirmed: readiness.review.eligibility_confirmed,
        resume_reviewed: readiness.review.resume_reviewed,
        application_details_reviewed: readiness.review.application_details_reviewed,
      });
      setDraftStatus(updated.status);
      setNotes(updated.notes ?? "");
      setNextAction(updated.next_action ?? "");
      setFollowUpDate(updated.follow_up_date ?? "");
      const refreshed = await apiRequest<ApplicationReadinessResponse>(
        `/api/applications/${application.id}/readiness`,
      );
      setReadiness(refreshed);
      setSelectedResumeFilename(refreshed.resume_filename ?? "");
      setReadinessSavedMessage(
        targetStatus === "ready_to_apply"
          ? "Readiness checks passed. This application is marked Ready to apply; submission is still manual."
          : "Review checklist saved.",
      );
    } catch (error) {
      setReadinessError(errorText(error));
    } finally {
      setReadinessSaving(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    setSavedMessage(false);

    try {
      const updated = await onUpdate(application.id, {
        status: draftStatus,
        notes: notes.trim() || null,
        next_action: nextAction.trim() || null,
        follow_up_date: followUpDate || null,
      });
      setDraftStatus(updated.status);
      setNotes(updated.notes ?? "");
      setNextAction(updated.next_action ?? "");
      setFollowUpDate(updated.follow_up_date ?? "");
      setSavedMessage(true);
    } catch (error) {
      setSaveError(errorText(error));
    } finally {
      setSaving(false);
    }
  };

  const statusLabel =
    APPLICATION_STATUSES.find((item) => item.value === application.status)?.label ??
    application.status;

  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="panel rounded-2xl p-4 sm:p-5"
    >
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
        <div className="flex min-w-0 gap-3">
          <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-slate-700/60 bg-slate-800/60 text-slate-300">
            <Building2 size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-slate-100">
              {application.job.title}
            </h3>
            <p className="mt-1 text-[11px] text-slate-400">
              {application.job.company}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-500">
              {application.job.location && (
                <span className="inline-flex items-center gap-1">
                  <MapPin size={11} /> {application.job.location}
                </span>
              )}
              <span className="inline-flex items-center gap-1">
                <Clock3 size={11} />
                {application.applied_at
                  ? `Applied ${new Date(application.applied_at).toLocaleDateString()}`
                  : `Added ${new Date(application.created_at).toLocaleDateString()}`}
              </span>
              <span className="rounded-full border border-slate-700 px-2 py-0.5">
                {statusLabel}
              </span>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <a
            className="secondary-button !px-3 !py-2"
            href={application.job.url}
            target="_blank"
            rel="noreferrer"
          >
            Original posting <ExternalLink size={13} />
          </a>
          <button
            type="button"
            className={`secondary-button !px-3 !py-2 ${readiness?.ready ? "!border-emerald-400/25 !text-emerald-200" : ""}`}
            onClick={() => void toggleReadiness()}
            aria-expanded={readinessOpen}
            aria-controls={`readiness-${application.id}`}
            title="Review application readiness before proceeding"
          >
            <FileCheck2 size={13} /> {readiness?.ready ? "Ready checks passed" : "Readiness review"}
          </button>
          <button
            type="button"
            className="secondary-button !border-rose-400/25 !px-3 !py-2 !text-rose-200 hover:!bg-rose-400/[0.08]"
            onClick={() => onRequestRemove(application)}
            disabled={saving}
            title="Remove this entry from your JobPilot tracker"
          >
            <Trash2 size={13} /> Remove
          </button>
        </div>
      </div>

      {readinessOpen && (
        <section
          id={`readiness-${application.id}`}
          className="mt-4 rounded-xl border border-blue-400/20 bg-blue-400/[0.035] p-4"
          aria-label="Application readiness review"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-[12px] font-semibold text-slate-100">Application readiness review</p>
              <p className="mt-1 text-[10px] text-slate-400">
                Review the posting, confirm eligibility, and select the exact document you intend to upload.
              </p>
            </div>
            <button
              type="button"
              className="secondary-button !px-3 !py-2"
              onClick={() => void loadReadiness()}
              disabled={readinessLoading}
            >
              <RefreshCw size={12} className={readinessLoading ? "loading-ring" : ""} /> Refresh checks
            </button>
          </div>

          {readinessLoading && (
            <div className="mt-4 flex items-center gap-2 text-[11px] text-slate-400">
              <LoaderCircle size={14} className="loading-ring" /> Checking posting and available resume files...
            </div>
          )}
          {readinessError && (
            <div role="alert" className="mt-3 rounded-lg border border-rose-400/20 bg-rose-400/[0.06] p-3 text-[11px] text-rose-200">
              {readinessError}
            </div>
          )}

          {readiness && !readinessLoading && (
            <>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className={`inline-flex rounded-full border px-2.5 py-1 text-[10px] font-semibold ${readinessIsComplete ? "border-emerald-400/20 bg-emerald-400/[0.07] text-emerald-200" : "border-amber-300/20 bg-amber-300/[0.06] text-amber-100"}`}>
                    {readinessIsComplete ? "Ready for your review" : "More review required"}
                  </span>
                  <span className="ml-2 text-[10px] text-slate-500">
                    {visibleReadinessChecks.filter((check) => check.passed).length}/{visibleReadinessChecks.length} checks passed
                  </span>
                </div>
                <div className="h-1.5 w-36 overflow-hidden rounded-full bg-slate-800">
                  <div
                    className={`h-full rounded-full ${readinessIsComplete ? "bg-emerald-400" : "bg-blue-400"}`}
                    style={{ width: `${visibleReadinessChecks.length ? (visibleReadinessChecks.filter((check) => check.passed).length / visibleReadinessChecks.length) * 100 : 0}%` }}
                  />
                </div>
              </div>

              <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-2">
                {visibleReadinessChecks.map((check) => (
                  <div key={check.id} className="flex gap-2 rounded-lg border border-slate-700/50 bg-slate-950/30 p-3">
                    {check.passed ? (
                      <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-emerald-300" />
                    ) : (
                      <AlertTriangle size={14} className={`mt-0.5 shrink-0 ${check.blocking ? "text-amber-200" : "text-slate-500"}`} />
                    )}
                    <div className="min-w-0">
                      <p className="text-[10px] font-semibold text-slate-200">{check.label}</p>
                      <p className="mt-1 text-[10px] leading-4 text-slate-500">{check.detail}</p>
                      {!check.blocking && !check.passed && <p className="mt-1 text-[9px] text-slate-500">Recommendation, not a blocker</p>}
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                <label className="block text-[10px] font-medium text-slate-400">
                  Tailored resume to attach
                  <select
                    className="field mt-1.5"
                    value={selectedResumeFilename}
                    onChange={(event) => {
                      setSelectedResumeFilename(event.target.value);
                      setReadinessSavedMessage(null);
                      setReadinessError(null);
                    }}
                    aria-label={`Select tailored resume for ${application.job.title}`}
                  >
                    <option value="">Select a generated PDF or DOCX...</option>
                    {readiness.resume_options.map((option) => (
                      <option key={option.filename} value={option.filename}>
                        {option.filename} · {option.format.toUpperCase()} · {new Date(option.modified_at).toLocaleDateString()}
                      </option>
                    ))}
                  </select>
                  {readiness.resume_options.length === 0 && (
                    <span className="mt-1.5 block text-[10px] text-amber-100">
                      No generated resumes found. Generate one in Resume Studio, then refresh these checks.
                    </span>
                  )}
                </label>

                <div className="space-y-2">
                  {([
                    ["job_reviewed", "I reviewed the job description and required qualifications."],
                    ["eligibility_confirmed", "I confirmed location, experience, education, and work-authorization eligibility."],
                    ["resume_reviewed", "I reviewed the selected resume's content, dates, links, and PDF layout."],
                    ["application_details_reviewed", "I can answer the employer's application questions accurately and have required materials ready."],
                  ] as const).map(([key, label]) => (
                    <label key={key} className="flex cursor-pointer items-start gap-2 text-[10px] leading-4 text-slate-300">
                      <input
                        className="mt-0.5 accent-blue-400"
                        type="checkbox"
                        checked={readiness.review[key]}
                        onChange={(event) => updateReadinessReview(key, event.target.checked)}
                      />
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
              </div>

              <p className="mt-3 text-[10px] text-slate-500">{readiness.submission_note}</p>
              {readinessSavedMessage && (
                <p role="status" className="mt-3 inline-flex items-center gap-1.5 text-[10px] text-emerald-300">
                  <CheckCircle2 size={12} /> {readinessSavedMessage}
                </p>
              )}
              <div className="mt-4 flex flex-wrap justify-end gap-2 border-t border-slate-700/50 pt-3">
                <button
                  type="button"
                  className="secondary-button !px-3 !py-2"
                  onClick={() => void saveReadinessReview(draftStatus)}
                  disabled={readinessSaving || readinessLoading}
                >
                  {readinessSaving ? <LoaderCircle size={12} className="loading-ring" /> : <Save size={12} />}
                  {readinessSaving ? "Saving..." : "Save review"}
                </button>
                <button
                  type="button"
                  className="primary-button !px-3 !py-2"
                  onClick={() => void saveReadinessReview("ready_to_apply")}
                  disabled={!readinessIsComplete || readinessSaving || readinessLoading || application.status === "applied"}
                  title={!readinessIsComplete ? "Complete all required checks first" : "Mark this application ready to apply; this does not submit it"}
                >
                  <ShieldCheck size={13} /> Mark Ready to Apply
                </button>
              </div>
            </>
          )}
        </section>
      )}

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <label className="block text-[10px] font-medium text-slate-400">
          Application status
          <select
            className="field mt-1.5"
            value={draftStatus}
            onChange={(event) => setDraftStatus(event.target.value as ApplicationStatus)}
          >
            {APPLICATION_STATUSES.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>
        <label className="block text-[10px] font-medium text-slate-400">
          Follow-up date
          <input
            className="field mt-1.5"
            type="date"
            value={followUpDate}
            onChange={(event) => setFollowUpDate(event.target.value)}
          />
        </label>
        <label className="block text-[10px] font-medium text-slate-400 sm:col-span-2">
          Next action
          <input
            className="field mt-1.5"
            placeholder="e.g. Review job requirements, follow up with recruiter"
            maxLength={500}
            value={nextAction}
            onChange={(event) => setNextAction(event.target.value)}
          />
        </label>
      </div>

      <label className="mt-3 block text-[10px] font-medium text-slate-400">
        Notes
        <textarea
          className="field mt-1.5 min-h-20 resize-y"
          placeholder="Interview notes, referral contact, assessment details..."
          maxLength={5000}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          rows={2}
        />
      </label>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-slate-700/40 pt-3">
        <div className="min-w-0 text-[10px]">
          {saveError && <span className="text-rose-300">{saveError}</span>}
          {!saveError && savedMessage && (
            <span className="inline-flex items-center gap-1 text-emerald-300">
              <CheckCircle2 size={12} /> Changes saved
            </span>
          )}
          {!saveError && !savedMessage && (
            <span className="text-slate-600">Save changes to persist your status and notes.</span>
          )}
        </div>
        <button className="primary-button !px-3 !py-2" onClick={() => void handleSave()} disabled={saving}>
          {saving ? <LoaderCircle size={13} className="loading-ring" /> : <Save size={13} />}
          {saving ? "Saving..." : "Save changes"}
        </button>
      </div>
    </motion.article>
  );
}

function ApplicationsView({
  applications,
  total,
  stats,
  loading,
  error,
  search,
  setSearch,
  statusFilter,
  setStatusFilter,
  onRefresh,
  onUpdate,
  onRequestRemove,
  onDiscoverJobs,
}: {
  applications: TrackedApplication[];
  total: number;
  stats: ApplicationStats | null;
  loading: boolean;
  error: string | null;
  search: string;
  setSearch: (value: string) => void;
  statusFilter: ApplicationStatus | "all";
  setStatusFilter: (value: ApplicationStatus | "all") => void;
  onRefresh: () => void;
  onUpdate: (
    applicationId: number,
    update: ApplicationUpdatePayload,
  ) => Promise<TrackedApplication>;
  onRequestRemove: (application: TrackedApplication) => void;
  onDiscoverJobs: () => void;
}) {
  const visibleApplications = applications.filter((application) => {
    const matchesStatus = statusFilter === "all" || application.status === statusFilter;
    const searchText = `${application.job.title} ${application.job.company} ${application.notes ?? ""}`.toLowerCase();
    const matchesSearch = !search.trim() || searchText.includes(search.trim().toLowerCase());
    return matchesStatus && matchesSearch;
  });

  const metricCards = [
    { label: "Tracked", value: stats?.total ?? total, note: "Jobs in your pipeline", icon: ClipboardList },
    { label: "Needs action", value: stats?.needs_action ?? 0, note: "Saved or being prepared", icon: Zap },
    { label: "Applied", value: stats?.by_status.applied ?? 0, note: "Submitted applications", icon: CheckCircle2 },
    { label: "Interviews", value: stats?.by_status.interview ?? 0, note: "Interview stage", icon: CalendarDays },
  ];

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Application pipeline"
        title="Track your applications"
        description="Keep each opportunity organized from saved job to interview and outcome. JobPilot records progress; it does not submit applications automatically."
        right={
          <div className="flex flex-wrap gap-2">
            <button className="secondary-button" onClick={onRefresh} disabled={loading}>
              <RefreshCw size={14} className={loading ? "loading-ring" : ""} /> Refresh
            </button>
            <button className="primary-button" onClick={onDiscoverJobs}>
              <Plus size={14} /> Discover jobs
            </button>
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metricCards.map((metric) => {
          const Icon = metric.icon;
          return (
            <div key={metric.label} className="panel rounded-2xl p-4">
              <div className="flex items-start justify-between gap-3">
                <p className="text-[11px] font-medium text-slate-400">{metric.label}</p>
                <div className="grid h-8 w-8 place-items-center rounded-xl border border-slate-700/60 bg-slate-800/70 text-blue-300">
                  <Icon size={15} />
                </div>
              </div>
              <p className="mt-4 text-2xl font-semibold tracking-tight text-slate-100">{formatNumber(metric.value)}</p>
              <p className="mt-1 text-[10px] text-slate-500">{metric.note}</p>
            </div>
          );
        })}
      </div>

      <div className="panel rounded-2xl p-4 sm:p-5">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_240px]">
          <label className="relative block">
            <Search size={15} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <input className="field !pl-10" placeholder="Search company, role, or notes..." value={search} onChange={(event) => setSearch(event.target.value)} aria-label="Search applications" />
          </label>
          <select className="field" aria-label="Filter applications by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as ApplicationStatus | "all")}>
            <option value="all">All statuses</option>
            {APPLICATION_STATUSES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[10px] text-slate-500">
          <span>{formatNumber(visibleApplications.length)} shown · {formatNumber(total)} tracked in total</span>
          {total > applications.length && <span>Showing the 100 most recently updated records.</span>}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-4 text-[12px] text-rose-200">
          {error}
        </div>
      )}

      {loading ? (
        <div className="panel flex min-h-56 items-center justify-center rounded-2xl">
          <div className="flex items-center gap-3 text-sm text-slate-400">
            <LoaderCircle className="loading-ring" size={18} /> Loading your applications...
          </div>
        </div>
      ) : visibleApplications.length === 0 ? (
        <div className="panel rounded-2xl">
          <EmptyState
            icon={ClipboardList}
            title={applications.length === 0 ? "Your pipeline is ready" : "No matching applications"}
            message={applications.length === 0 ? "Save a job from Discover Jobs to start tracking your progress, follow-ups, assessments and interviews." : "Try a different search or status filter."}
          />
          {applications.length === 0 && (
            <div className="pb-5 text-center">
              <button className="primary-button" onClick={onDiscoverJobs}><Plus size={14} /> Discover jobs</button>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {visibleApplications.map((application) => (
            <ApplicationCard
              key={`${application.id}-${application.updated_at}`}
              application={application}
              onUpdate={onUpdate}
              onRequestRemove={onRequestRemove}
            />
          ))}
        </div>
      )}
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
                    <div className="mt-3 flex flex-wrap gap-2">
                      {generated.pdf_download_url && (
                        <a
                          className="primary-button !py-2"
                          href={`${API_BASE}${generated.pdf_download_url}`}
                          download={generated.pdf_filename || undefined}
                        >
                          <Download size={14} />
                          Download PDF
                        </a>
                      )}
                      <a
                        className="secondary-button !py-2"
                        href={`${API_BASE}${generated.download_url}`}
                        download={generated.resume_filename}
                      >
                        <Download size={14} />
                        Download DOCX
                      </a>
                    </div>
                  </div>
                </div>

                {generated.evaluation && (
                  <div className="mt-4 border-t border-emerald-300/10 pt-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-[12px] font-semibold text-slate-100">
                          Resume quality review
                        </p>
                        <p className="mt-1 text-[10px] text-slate-400">
                          {generated.evaluation.readiness_label}
                        </p>
                      </div>
                      <span className={`rounded-full border px-2.5 py-1 text-[10px] ${
                        generated.evaluation.readiness_passes_local_checks
                          ? "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-200"
                          : "border-amber-400/20 bg-amber-400/[0.06] text-amber-200"
                      }`}>
                        {generated.evaluation.readiness_passes_local_checks
                          ? "Local checks passed"
                          : "Review recommended"}
                      </span>
                    </div>

                    <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
                      {[
                        {
                          label: "ATS readability",
                          score: generated.evaluation.ats_readability.score,
                          detail: generated.evaluation.ats_readability.label,
                        },
                        {
                          label: "Job relevance",
                          score: generated.evaluation.job_relevance.score,
                          detail: generated.evaluation.job_relevance.label,
                        },
                        {
                          label: "Achievement quality",
                          score: generated.evaluation.achievement_quality.score,
                          detail: generated.evaluation.achievement_quality.label,
                        },
                      ].map((item) => (
                        <div key={item.label} className="rounded-xl border border-slate-700/60 bg-slate-950/40 p-3">
                          <p className="text-[10px] text-slate-400">{item.label}</p>
                          <div className="mt-1 flex items-baseline gap-1">
                            <span className="text-xl font-semibold text-slate-100">{item.score}</span>
                            <span className="text-[10px] text-slate-500">/100</span>
                          </div>
                          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
                            <div
                              className={`h-full rounded-full ${item.score >= 90 ? "bg-emerald-400" : item.score >= 75 ? "bg-amber-400" : "bg-rose-400"}`}
                              style={{ width: `${Math.max(0, Math.min(100, item.score))}%` }}
                            />
                          </div>
                          <p className="mt-2 text-[10px] leading-4 text-slate-400">{item.detail}</p>
                        </div>
                      ))}
                    </div>

                    <p className="mt-3 text-[10px] leading-4 text-slate-500">
                      {generated.evaluation.global_disclaimer}
                    </p>

                    {(generated.evaluation.job_relevance.required_skill_coverage.missing.length > 0 ||
                      generated.evaluation.job_relevance.required_skill_coverage.awaiting_review.length > 0) && (
                      <div className="mt-3 rounded-lg border border-amber-400/20 bg-amber-400/[0.05] p-3">
                        <p className="text-[11px] font-semibold text-amber-100">Required-skill gaps</p>
                        {generated.evaluation.job_relevance.required_skill_coverage.missing.length > 0 && (
                          <p className="mt-1 text-[10px] leading-4 text-slate-300">
                            No matching verified evidence: {generated.evaluation.job_relevance.required_skill_coverage.missing.join(", ")}
                          </p>
                        )}
                        {generated.evaluation.job_relevance.required_skill_coverage.awaiting_review.length > 0 && (
                          <p className="mt-1 text-[10px] leading-4 text-slate-300">
                            Awaiting your evidence review: {generated.evaluation.job_relevance.required_skill_coverage.awaiting_review.join(", ")}
                          </p>
                        )}
                      </div>
                    )}

                    {generated.evaluation.recommendations.length > 0 && (
                      <div className="mt-3">
                        <p className="text-[11px] font-semibold text-slate-200">Recommended review</p>
                        <ul className="mt-1 space-y-1">
                          {generated.evaluation.recommendations.map((recommendation, index) => (
                            <li key={`${index}-${recommendation}`} className="flex gap-2 text-[10px] leading-4 text-slate-400">
                              <span className="text-blue-300">•</span>
                              <span>{recommendation}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
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

  const [applications, setApplications] = useState<TrackedApplication[]>([]);
  const [applicationsTotal, setApplicationsTotal] = useState(0);
  const [applicationStats, setApplicationStats] = useState<ApplicationStats | null>(null);
  const [applicationsLoading, setApplicationsLoading] = useState(false);
  const [applicationsError, setApplicationsError] = useState<string | null>(null);
  const [applicationSearch, setApplicationSearch] = useState("");
  const [applicationStatusFilter, setApplicationStatusFilter] = useState<ApplicationStatus | "all">("all");
  const [trackingJobIds, setTrackingJobIds] = useState<Set<number>>(new Set());
  const [trackedApplicationJobIds, setTrackedApplicationJobIds] = useState<Set<number>>(new Set());
  const [applicationToRemove, setApplicationToRemove] = useState<TrackedApplication | null>(null);
  const [removeApplicationLoading, setRemoveApplicationLoading] = useState(false);
  const [removeApplicationError, setRemoveApplicationError] = useState<string | null>(null);

  const [companyOptions, setCompanyOptions] = useState<CompanyOption[]>([]);
  const [locationOptions, setLocationOptions] = useState<LocationOption[]>([]);

  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [jobsHasMore, setJobsHasMore] = useState(false);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [jobsPage, setJobsPage] = useState(0);

  const [queryInput, setQueryInput] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [jobSuggestions, setJobSuggestions] = useState<JobTitleSuggestion[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);

  const [filterDraft, setFilterDraft] = useState<JobFilters>({
    company: "",
    location: DEFAULT_JOB_LOCATION,
    source: "",
    career_level: "early",
  });

  const [appliedFilters, setAppliedFilters] = useState<JobFilters>({
    company: "",
    location: DEFAULT_JOB_LOCATION,
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
      const [
        health,
        dashboard,
        jobsResponse,
        evidenceSummary,
        companiesResponse,
        locationsResponse,
      ] = await Promise.all([
        apiRequest<{ status: string }>("/api/health"),
        apiRequest<DashboardStats>("/api/dashboard/stats"),
        apiRequest<JobListResponse>(`/api/jobs?limit=5&offset=0&location=${encodeURIComponent(DEFAULT_JOB_LOCATION)}`),
        apiRequest<EvidenceSummary>("/api/evidence/summary"),
        apiRequest<CompanyDirectoryResponse>("/api/companies?limit=1000"),
        apiRequest<LocationDirectoryResponse>("/api/locations?limit=1000"),
      ]);

      if (health.status !== "ok") {
        throw new Error("The API returned an unexpected health status.");
      }

      setStats(dashboard);
      setPreviewJobs(jobsResponse.items);
      setEvidence(evidenceSummary);
      setCompanyOptions(companiesResponse.items);
      setLocationOptions(locationsResponse.items);
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
        career_level: appliedFilters.career_level,
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

  const loadApplications = useCallback(async () => {
    setApplicationsLoading(true);
    setApplicationsError(null);

    try {
      const [list, summary, trackedJobs] = await Promise.all([
        apiRequest<ApplicationListResponse>("/api/applications?limit=100&offset=0"),
        apiRequest<ApplicationStats>("/api/applications/stats"),
        apiRequest<TrackedJobIdsResponse>("/api/applications/tracked-job-ids"),
      ]);
      setApplications(list.items);
      setApplicationsTotal(list.total);
      setApplicationStats(summary);
      setTrackedApplicationJobIds(new Set(trackedJobs.job_ids));
    } catch (error) {
      setApplicationsError(errorText(error));
    } finally {
      setApplicationsLoading(false);
    }
  }, []);

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

  useEffect(() => {
    if (screen !== "applications" && screen !== "jobs") {
      return;
    }

    const timerId = window.setTimeout(() => {
      void loadApplications();
    }, 0);

    return () => window.clearTimeout(timerId);
  }, [screen, loadApplications]);

  useEffect(() => {
    const query = queryInput.trim();
    let cancelled = false;

    const timerId = window.setTimeout(() => {
      if (query.length < 2) {
        setJobSuggestions([]);
        setSuggestionsLoading(false);
        return;
      }

      setSuggestionsLoading(true);

      const params = new URLSearchParams({
        q: query,
        limit: "8",
        career_level: filterDraft.career_level,
      });

      if (filterDraft.company.trim()) {
        params.set("company", filterDraft.company.trim());
      }
      if (filterDraft.location.trim()) {
        params.set("location", filterDraft.location.trim());
      }
      if (filterDraft.source.trim()) {
        params.set("source", filterDraft.source.trim());
      }

      void apiRequest<JobSuggestionResponse>(
        `/api/job-suggestions?${params.toString()}`,
      )
        .then((response) => {
          if (!cancelled) {
            setJobSuggestions(response.items);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setJobSuggestions([]);
          }
        })
        .finally(() => {
          if (!cancelled) {
            setSuggestionsLoading(false);
          }
        });
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [queryInput, filterDraft]);

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
    setSuggestionsOpen(false);
  };

  const selectSuggestedTitle = (suggestion: JobTitleSuggestion) => {
    const nextFilters: JobFilters = {
      company: filterDraft.company.trim(),
      location: filterDraft.location.trim(),
      source: filterDraft.source.trim(),
      career_level: filterDraft.career_level,
    };

    // When the query matched a company name rather than the title, and the
    // suggestion belongs to one company, keep that intended company selected.
    // Do not auto-select a company for an ordinary title match.
    if (
      !nextFilters.company &&
      suggestion.companies.length === 1 &&
      suggestion.matched_by.includes("company") &&
      !suggestion.matched_by.includes("title")
    ) {
      nextFilters.company = suggestion.companies[0];
    }

    setFilterDraft(nextFilters);
    setAppliedFilters(nextFilters);
    setQueryInput(suggestion.title);
    setAppliedQuery(suggestion.title);
    setJobsPage(0);
    setSuggestionsOpen(false);
  };

  const handlePreviousPage = () => {
    setJobsPage((value) => Math.max(0, value - 1));
  };

  const handleNextPage = () => {
    if (jobsHasMore) {
      setJobsPage((value) => value + 1);
    }
  };

  const handleTrackApplication = async (job: Job) => {
    setTrackingJobIds((current) => new Set(current).add(job.id));
    setJobsError(null);

    try {
      const created = await apiRequest<TrackedApplication>("/api/applications", {
        method: "POST",
        body: JSON.stringify({ job_id: job.id, status: "saved" }),
      });

      setApplications((current) => [
        created,
        ...current.filter((item) => item.id !== created.id && item.job_id !== job.id),
      ].slice(0, 100));
      setTrackedApplicationJobIds((current) => new Set(current).add(job.id));
      setApplicationsTotal((current) => current + 1);
      setApplicationStats((current) => current ? {
        ...current,
        total: current.total + 1,
        needs_action: current.needs_action + 1,
        by_status: {
          ...current.by_status,
          saved: (current.by_status.saved ?? 0) + 1,
        },
      } : current);
    } catch (error) {
      const message = errorText(error);
      if (message.toLowerCase().includes("already tracked")) {
        await loadApplications();
      } else {
        setJobsError(message);
      }
    } finally {
      setTrackingJobIds((current) => {
        const next = new Set(current);
        next.delete(job.id);
        return next;
      });
    }
  };

  const requestRemoveApplication = (application: TrackedApplication) => {
    setRemoveApplicationError(null);
    setApplicationToRemove(application);
  };

  const handleUntrackJob = async (job: Job) => {
    let application = applications.find((item) => item.job_id === job.id);

    if (!application) {
      try {
        application = await apiRequest<TrackedApplication>(
          `/api/applications/by-job/${job.id}`,
        );
      } catch (error) {
        setJobsError(errorText(error));
        await loadApplications();
        return;
      }
    }

    requestRemoveApplication(application);
  };

  const handleConfirmRemoveApplication = async () => {
    if (!applicationToRemove || removeApplicationLoading) return;

    const target = applicationToRemove;
    setRemoveApplicationLoading(true);
    setRemoveApplicationError(null);

    try {
      await apiRequest<ApplicationDeleteResponse>(
        `/api/applications/${target.id}`,
        { method: "DELETE" },
      );

      setApplications((current) => current.filter((item) => item.id !== target.id));
      setApplicationsTotal((current) => Math.max(0, current - 1));
      setTrackedApplicationJobIds((current) => {
        const next = new Set(current);
        next.delete(target.job_id);
        return next;
      });
      setApplicationStats((current) => {
        if (!current) return current;
        const counts = { ...current.by_status };
        counts[target.status] = Math.max(0, (counts[target.status] ?? 0) - 1);
        return {
          ...current,
          total: Math.max(0, current.total - 1),
          needs_action: counts.saved + counts.preparing + counts.ready_to_apply,
          by_status: counts,
        };
      });
      setApplicationToRemove(null);
    } catch (error) {
      setRemoveApplicationError(errorText(error));
    } finally {
      setRemoveApplicationLoading(false);
    }
  };

  const handleUpdateApplication = async (
    applicationId: number,
    update: ApplicationUpdatePayload,
  ): Promise<TrackedApplication> => {
    const updated = await apiRequest<TrackedApplication>(
      `/api/applications/${applicationId}`,
      {
        method: "PATCH",
        body: JSON.stringify(update),
      },
    );

    setApplications((current) => current.map((item) =>
      item.id === applicationId ? updated : item,
    ));

    setApplicationStats((current) => {
      if (!current) return current;
      const oldApplication = applications.find((item) => item.id === applicationId);
      if (!oldApplication || oldApplication.status === updated.status) return current;
      const counts = { ...current.by_status };
      counts[oldApplication.status] = Math.max(0, (counts[oldApplication.status] ?? 0) - 1);
      counts[updated.status] = (counts[updated.status] ?? 0) + 1;
      const needsAction = counts.saved + counts.preparing + counts.ready_to_apply;
      return { ...current, by_status: counts, needs_action: needsAction };
    });

    return updated;
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

  const companyFilterOptions: FilterOption[] = companyOptions.map((item) => ({
    value: item.name,
    label: item.name,
    meta: `${formatNumber(item.active_job_count)} active`,
  }));

  const locationFilterOptions: FilterOption[] = locationOptions.map((item) => ({
    value: item.value || item.city,
    label: item.city,
    meta: `${formatNumber(item.job_count)} jobs`,
  }));

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
                <p className="mt-0.5 text-[9px] text-slate-500">Python API</p>
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
                    setQuery={(value) => {
                      setQueryInput(value);
                      setSuggestionsOpen(true);
                    }}
                    suggestions={jobSuggestions}
                    suggestionsLoading={suggestionsLoading}
                    suggestionsOpen={suggestionsOpen}
                    onQueryFocus={() => setSuggestionsOpen(true)}
                    onQueryBlur={() => {
                      window.setTimeout(
                        () => setSuggestionsOpen(false),
                        140,
                      );
                    }}
                    onSelectSuggestion={selectSuggestedTitle}
                    filterDraft={filterDraft}
                    setFilterDraft={setFilterDraft}
                    companyOptions={companyFilterOptions}
                    locationOptions={locationFilterOptions}
                    sourceOptions={sourceOptions}
                    onApplyFilters={applyJobFilters}
                    onPrevious={handlePreviousPage}
                    onNext={handleNextPage}
                    onRefresh={() => {
                      void refreshOverview();
                      void loadJobs();
                      void loadApplications();
                    }}
                    onTrack={(job) => void handleTrackApplication(job)}
                    onUntrack={(job) => void handleUntrackJob(job)}
                    isTracked={(jobId) => trackedApplicationJobIds.has(jobId)}
                    trackingJobIds={trackingJobIds}
                    onTailor={openResumeForJob}
                  />
                )}

                {screen === "applications" && (
                  <ApplicationsView
                    applications={applications}
                    total={applicationsTotal}
                    stats={applicationStats}
                    loading={applicationsLoading}
                    error={applicationsError}
                    search={applicationSearch}
                    setSearch={setApplicationSearch}
                    statusFilter={applicationStatusFilter}
                    setStatusFilter={setApplicationStatusFilter}
                    onRefresh={() => void loadApplications()}
                    onUpdate={handleUpdateApplication}
                    onRequestRemove={requestRemoveApplication}
                    onDiscoverJobs={openJobs}
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

        <AnimatePresence>
          {applicationToRemove && (
            <motion.div
              className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              role="presentation"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget && !removeApplicationLoading) {
                  setApplicationToRemove(null);
                  setRemoveApplicationError(null);
                }
              }}
            >
              <motion.section
                initial={{ opacity: 0, y: 12, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 8, scale: 0.98 }}
                transition={{ duration: 0.16 }}
                className="panel w-full max-w-lg rounded-2xl border border-rose-400/20 p-5 shadow-2xl"
                role="alertdialog"
                aria-modal="true"
                aria-labelledby="remove-application-title"
                aria-describedby="remove-application-description"
              >
                <div className="flex items-start gap-3">
                  <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-rose-400/20 bg-rose-400/[0.08] text-rose-200">
                    <AlertTriangle size={18} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h2 id="remove-application-title" className="text-base font-semibold text-slate-100">
                      Remove from your tracker?
                    </h2>
                    <p className="mt-1 text-[11px] leading-5 text-slate-400">
                      {applicationToRemove.job.title} · {applicationToRemove.job.company}
                    </p>
                  </div>
                </div>
                <p id="remove-application-description" className="mt-4 text-[12px] leading-6 text-slate-300">
                  This removes the tracking entry, status, notes and follow-up details from JobPilot. It does not delete the original job listing or withdraw an application you already submitted. This action cannot be undone.
                </p>
                {applicationToRemove.status !== "saved" && applicationToRemove.status !== "preparing" && applicationToRemove.status !== "ready_to_apply" && (
                  <div className="mt-3 rounded-xl border border-amber-300/20 bg-amber-300/[0.05] p-3 text-[11px] leading-5 text-amber-100">
                    This record is marked as {APPLICATION_STATUSES.find((item) => item.value === applicationToRemove.status)?.label.toLowerCase()}. Removing it only changes JobPilot's records; it does not change the employer's application status.
                  </div>
                )}
                {removeApplicationError && (
                  <div className="mt-3 rounded-lg border border-rose-400/20 bg-rose-400/[0.06] p-3 text-[11px] text-rose-200" role="alert">
                    {removeApplicationError}
                  </div>
                )}
                <div className="mt-5 flex flex-wrap justify-end gap-2 border-t border-slate-700/50 pt-4">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => {
                      setApplicationToRemove(null);
                      setRemoveApplicationError(null);
                    }}
                    disabled={removeApplicationLoading}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="secondary-button !border-rose-400/30 !bg-rose-500/15 !text-rose-100 hover:!bg-rose-500/25"
                    onClick={() => void handleConfirmRemoveApplication()}
                    disabled={removeApplicationLoading}
                  >
                    {removeApplicationLoading ? (
                      <LoaderCircle size={14} className="loading-ring" />
                    ) : (
                      <Trash2 size={14} />
                    )}
                    {removeApplicationLoading ? "Removing..." : "Remove tracking"}
                  </button>
                </div>
              </motion.section>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

export default App;