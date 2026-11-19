export type Screen = "overview" | "jobs" | "recommended" | "applications" | "documents" | "resume" | "email" | "coverage" | "insights" | "network";
export type ApiStatus = "checking" | "connected" | "offline";
export type CareerLevelFilter = "early" | "all";
export type RoleScopeFilter = "software_engineering" | "all";
export type CompensationFilter = "target_or_unknown" | "target_only" | "all";
export type ReviewScope = "main" | "remote" | "review" | "dismissed";

export interface Company {
  id: number;
  name: string;
}

export interface CompanyOption extends Company {
  website: string | null;
  careers_url: string | null;
  job_count: number;
  active_job_count: number;
  source_types: string[];
}

// One line per company JobPilot knows, so no company silently disappears from the Company filter.
export interface CompanyCoverage {
  name: string;
  shown: number;
  review: number;
  state: string | null;
  in_registry: boolean;
  note: string;
}

export interface LocationOption {
  city: string;
  value: string;
  job_count: number;
}

export interface JobTitleSuggestion {
  title: string;
  count: number;
  companies: string[];
  matched_by: Array<"title" | "company">;
}

export interface FilterOption {
  value: string;
  label: string;
  meta?: string;
}

export interface JobFilters {
  company: string;
  location: string;
  source: string;
  career_level: CareerLevelFilter;
  role_scope: RoleScopeFilter;
  compensation_filter: CompensationFilter;
  review_scope: ReviewScope;
}

// Why a stored job is waiting for your decision (only present on jobs the sync held for review).
export interface JobReviewInfo {
  status: "pending" | "accepted" | "dismissed";
  flags: string[];
  reasons: string[];
  decided_at: string | null;
}

export interface JobMatch {
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

export interface JobCompensation {
  min_lpa: number | null;
  max_lpa: number | null;
  status: "target_30_plus" | "target_25_plus" | "target_possible" | "below_target" | "not_disclosed";
  target_floor_lpa: number;
}

export interface Job {
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
  compensation?: JobCompensation;
  posted_at: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  is_active: boolean;
  match?: JobMatch;
  review?: JobReviewInfo | null;
}

export interface DashboardStats {
  total_jobs: number;
  active_jobs: number;
  needs_review_jobs?: number;
  inactive_jobs: number;
  total_companies: number;
  jobs_by_source: Array<{ source: string; count: number }>;
  jobs_by_experience_level: Array<{
    experience_level: string;
    count: number;
  }>;
}

export interface EvidenceSummary {
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

export interface JobListResponse {
  items: Job[];
  pagination: {
    limit: number;
    offset: number;
    total: number;
    has_more: boolean;
  };
}

export interface CompanyDirectoryResponse {
  items: CompanyOption[];
  total: number;
  limit: number;
  active_only: boolean;
}

export interface LocationDirectoryResponse {
  items: LocationOption[];
  total: number;
  active_only: boolean;
}

export interface JobSuggestionResponse {
  query: string;
  items: JobTitleSuggestion[];
}

export type ApplicationStatus =
  | "saved"
  | "preparing"
  | "ready_to_apply"
  | "applied"
  | "assessment"
  | "interview"
  | "offer"
  | "rejected"
  | "withdrawn";

export interface TrackedApplication {
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
  };
}

export interface ApplicationListResponse {
  items: TrackedApplication[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApplicationStats {
  total: number;
  needs_action: number;
  by_status: Record<ApplicationStatus, number>;
}

export interface ApplicationUpdatePayload {
  status: ApplicationStatus;
  notes: string | null;
  next_action: string | null;
  follow_up_date: string | null;
}

export const APPLICATION_STATUSES: Array<{
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

export interface EvidenceSelection {
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
    preferred_skills?: number;
    preferred_verified_covered?: string[];
    preferred_awaiting_evidence_review?: string[];
    preferred_not_found_in_evidence?: string[];
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

export interface GeneratedResume {
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

export interface ApiError {
  detail?: string;
}

export interface SourceHealthItem {
  id: string;
  name: string | null;
  priority: number | null;
  provider: string | null;
  careers_url: string | null;
  configured_state: string;
  state: string;
  state_detail: string;
  auto_sync_allowed: boolean;
  never_fetched: boolean;
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error: string | null;
  consecutive_failures: number;
  raw_jobs: number | null;
  unique_jobs: number | null;
  eligible_jobs: number | null;
  review_jobs: number | null;
  jobs_with_description: number | null;
  detail_attempted: number | null;
  detail_succeeded: number | null;
  last_enrichment_success_at: string | null;
  pagination_status: string;
}

export interface SourceHealthResponse {
  items: SourceHealthItem[];
  summary: {
    total: number;
    by_state: Record<string, number>;
    auto_sync_allowed: number;
    never_fetched: number;
  };
}

export interface RecommendationItem {
  id: number;
  title: string;
  company: string;
  location: string | null;
  url: string;
  posted_at: string | null;
  first_seen_at: string | null;
  match_score: number | null;
  match_recommendation: string | null;
  required_years: number | null;
  missing_required_skills: string[];
  matched_required_skills: string[];
  mismatches: Record<string, string[]>;
  opportunity_score: number;
  action: "apply_now" | "review_first" | "prepare_missing_skills" | "skip";
  action_label: string;
  reasons: string[];
  signals: string[];
  components: Record<string, number>;
  compensation: { status: string; min_lpa: number | null; max_lpa: number | null };
}

export interface SkillGapReport {
  jobs_considered: number;
  small_sample: boolean;
  note: string;
  gaps: Array<{ skill: string; jobs_requiring: number; share_of_jobs: number; example_titles: string[]; companies: string[] }>;
  learning_plan: Array<{ skill: string; step: string }>;
}

export interface RecommendationResponse {
  items: RecommendationItem[];
  sort: string;
  summary: { considered: number; by_action: Record<string, number>; shown: number };
  skill_gap: SkillGapReport;
}

export interface ComparisonRow {
  id: number;
  title: string | null;
  company: string | null;
  location: string | null;
  url: string | null;
  score: number | null;
  recommendation: string | null;
  required_years: number | null;
  blockers: string[];
  experience_mismatch: string[];
  location_mismatch: string[];
  preferred_missing: string[];
}

export interface ComparisonResponse {
  jobs: ComparisonRow[];
  highlights: {
    best_overall_job_id: number | null;
    best_overall_score: number | null;
    skill_matrix: Array<{ skill: string; jobs: Record<string, string>; required_by: number; covered_by_profile: number }>;
    skills_missing_everywhere: string[];
    jobs_with_blockers: number[];
  };
}
