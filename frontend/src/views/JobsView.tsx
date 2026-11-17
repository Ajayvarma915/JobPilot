import { VerifyOpenButton } from "./VerifyOpenButton";
import { type FormEvent } from "react";
import { AnimatePresence, motion } from "motion/react";
import { BriefcaseBusiness, Building2, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, Clock3, ExternalLink, Filter, Globe2, LoaderCircle, MapPin, Plus, RefreshCw, Search, Sparkles, Target } from "lucide-react";
import { CompensationBadge, EmptyState, MatchBadge, MatchDetails, SearchableFilter, SectionHeading } from "../components";
import { compactText, formatNumber } from "../lib";
import { type CareerLevelFilter, type CompensationFilter, type FilterOption, type Job, type JobFilters, type JobTitleSuggestion, type ReviewScope, type RoleScopeFilter } from "../types";

export function JobsView({
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
  reviewScope,
  onReviewScope,
  onReviewDecision,
  onPrevious,
  onNext,
  onRefresh,
  onTrack,
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
  reviewScope: ReviewScope;
  onReviewScope: (scope: ReviewScope) => void;
  onReviewDecision: (jobId: number, decision: "accept" | "dismiss" | "reset") => void;
  onPrevious: () => void;
  onNext: () => void;
  onRefresh: () => void;
  onTrack: (job: Job) => void;
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
        description="Default feed: software-engineering roles in India/India-eligible remote locations, early-career suitable, prioritizing disclosed compensation of ₹25 LPA or more."
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

      <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Job lists">
        {([
          ["main", "Jobs"],
          ["review", "Needs your review"],
          ["dismissed", "Dismissed"],
        ] as Array<[ReviewScope, string]>).map(([scope, label]) => (
          <button
            key={scope}
            role="tab"
            aria-selected={reviewScope === scope}
            className={reviewScope === scope ? "primary-button !px-3 !py-2" : "secondary-button !px-3 !py-2"}
            onClick={() => onReviewScope(scope)}
          >
            {label}
          </button>
        ))}
        {reviewScope === "review" && (
          <p className="text-[11px] text-slate-400">
            These roles fit your location and role rules, but something is unclear (often the years of experience). Accept the ones that look right.
          </p>
        )}
      </div>

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

        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
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
            aria-label="Experience level filter"
            onChange={(event) =>
              setFilterDraft({
                ...filterDraft,
                career_level: event.target.value as CareerLevelFilter,
              })
            }
          >
            <option value="early">Up to 2 years required</option>
            <option value="all">All experience levels</option>
          </select>

          <select
            className="field"
            value={filterDraft.role_scope}
            aria-label="Role family filter"
            onChange={(event) =>
              setFilterDraft({
                ...filterDraft,
                role_scope: event.target.value as RoleScopeFilter,
              })
            }
          >
            <option value="software_engineering">Software engineering roles</option>
            <option value="all">All job functions</option>
          </select>

          <select
            className="field"
            value={filterDraft.compensation_filter}
            aria-label="Compensation target filter"
            onChange={(event) =>
              setFilterDraft({
                ...filterDraft,
                compensation_filter: event.target.value as CompensationFilter,
              })
            }
          >
            <option value="target_or_unknown">₹25+ LPA or undisclosed</option>
            <option value="target_only">Confirmed ₹25+ LPA only</option>
            <option value="all">All salary levels</option>
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

                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <MatchBadge match={job.match} />
                      <CompensationBadge compensation={job.compensation} />
                      {job.review?.status === "pending" && (
                        <span className="rounded-full border border-amber-300/30 bg-amber-300/10 px-2 py-0.5 text-[10px] font-semibold text-amber-200">
                          Needs your review
                        </span>
                      )}
                    </div>

                    {job.review && job.review.status !== "accepted" && job.review.reasons.length > 0 && (
                      <ul className="mt-2 space-y-0.5 text-[11px] text-amber-200/90">
                        {job.review.reasons.map((reason) => (
                          <li key={reason}>• {reason}</li>
                        ))}
                      </ul>
                    )}

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

                <div className="flex shrink-0 flex-wrap items-start gap-2 lg:justify-end">
                  {job.review?.status === "pending" && (
                    <>
                      <button className="primary-button !px-3 !py-2" onClick={() => onReviewDecision(job.id, "accept")} title="Show this job with your normal jobs">
                        Accept
                      </button>
                      <button className="secondary-button !px-3 !py-2" onClick={() => onReviewDecision(job.id, "dismiss")} title="Hide this job">
                        Dismiss
                      </button>
                    </>
                  )}
                  {job.review?.status === "dismissed" && (
                    <button className="secondary-button !px-3 !py-2" onClick={() => onReviewDecision(job.id, "reset")} title="Put this job back in your review list">
                      Restore
                    </button>
                  )}
                  <VerifyOpenButton jobId={job.id} lastSeenAt={job.last_seen_at} />
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
                    className="secondary-button !px-3 !py-2"
                    onClick={() => onTrack(job)}
                    disabled={isTracked(job.id) || trackingJobIds.has(job.id)}
                    title={isTracked(job.id) ? "Already tracked" : "Add this job to your application pipeline"}
                  >
                    {trackingJobIds.has(job.id) ? (
                      <LoaderCircle size={13} className="loading-ring" />
                    ) : isTracked(job.id) ? (
                      <CheckCircle2 size={13} />
                    ) : (
                      <Plus size={13} />
                    )}
                    {trackingJobIds.has(job.id)
                      ? "Saving..."
                      : isTracked(job.id)
                        ? "Tracked"
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
