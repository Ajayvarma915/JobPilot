import { useCallback, useEffect, useState, type FormEvent } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Activity, Bell, ChevronRight, Command, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import { Brand, StatusPill } from "./components";
import { API_BASE } from "./config";
import { apiRequest, errorText, formatNumber, makeResumeRequest } from "./lib";
import { NAV_ITEMS } from "./nav";
import { type ApiStatus, type ApplicationListResponse, type ApplicationStats, type ApplicationStatus, type ApplicationUpdatePayload, type CompanyDirectoryResponse, type CompanyOption, type DashboardStats, type EvidenceSelection, type EvidenceSummary, type FilterOption, type GeneratedResume, type Job, type JobFilters, type JobListResponse, type JobSuggestionResponse, type JobTitleSuggestion, type LocationDirectoryResponse, type LocationOption, type Screen, type TrackedApplication } from "./types";
import { ApplicationsView } from "./views/ApplicationsView";
import { CoverageView } from "./views/CoverageView";
import { RecommendedView } from "./views/RecommendedView";
import { DocumentsView } from "./views/DocumentsView";
import { EmailIntelligenceView, type ApplicationEmailEvent, type EmailConnectionStatus, type EmailEventListResponse, type EmailReviewFilter, type EmailSyncResult } from "./views/EmailIntelligenceView";
import { JobsView } from "./views/JobsView";
import { OverviewView } from "./views/OverviewView";
import { ResumeView } from "./views/ResumeView";

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

  const [emailConnection, setEmailConnection] = useState<EmailConnectionStatus | null>(null);
  const [emailEvents, setEmailEvents] = useState<ApplicationEmailEvent[]>([]);
  const [emailEventFilter, setEmailEventFilter] = useState<EmailReviewFilter>("pending");
  const [emailPendingTotal, setEmailPendingTotal] = useState(0);
  const [emailEventTotal, setEmailEventTotal] = useState(0);
  const [emailLoading, setEmailLoading] = useState(false);
  const [emailSyncing, setEmailSyncing] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [emailNotice, setEmailNotice] = useState<string | null>(null);
  const [emailSelectedApplicationIds, setEmailSelectedApplicationIds] = useState<Record<number, string>>({});

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
    location: "India",
    source: "",
    career_level: "early",
    role_scope: "software_engineering",
    compensation_filter: "target_or_unknown",
  });

  const [appliedFilters, setAppliedFilters] = useState<JobFilters>({
    company: "",
    location: "India",
    source: "",
    career_level: "early",
    role_scope: "software_engineering",
    compensation_filter: "target_or_unknown",
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
        apiRequest<JobListResponse>("/api/jobs?limit=5&offset=0&location=India&role_scope=software_engineering&compensation_filter=target_or_unknown"),
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
        role_scope: appliedFilters.role_scope,
        compensation_filter: appliedFilters.compensation_filter,
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
      const [list, summary] = await Promise.all([
        apiRequest<ApplicationListResponse>("/api/applications?limit=100&offset=0"),
        apiRequest<ApplicationStats>("/api/applications/stats"),
      ]);
      setApplications(list.items);
      setApplicationsTotal(list.total);
      setApplicationStats(summary);
    } catch (error) {
      setApplicationsError(errorText(error));
    } finally {
      setApplicationsLoading(false);
    }
  }, []);


  const loadEmailIntelligence = useCallback(async (filter: EmailReviewFilter = emailEventFilter) => {
    setEmailLoading(true);
    setEmailError(null);
    try {
      const eventParams = new URLSearchParams({ review_status: filter, limit: "100", offset: "0" });
      const [connection, eventList, pendingList] = await Promise.all([
        apiRequest<EmailConnectionStatus>("/api/email/status"),
        apiRequest<EmailEventListResponse>(`/api/email/events?${eventParams.toString()}`),
        filter === "pending"
          ? Promise.resolve<EmailEventListResponse | null>(null)
          : apiRequest<EmailEventListResponse>("/api/email/events?review_status=pending&limit=1&offset=0"),
      ]);
      setEmailConnection(connection);
      setEmailEvents(eventList.items);
      setEmailEventTotal(eventList.total);
      setEmailPendingTotal(filter === "pending" ? eventList.total : pendingList?.total ?? 0);
    } catch (error) {
      setEmailError(errorText(error));
    } finally {
      setEmailLoading(false);
    }
  }, [emailEventFilter]);

  const handleEmailConnect = useCallback(() => {
    window.open(`${API_BASE}/api/email/oauth/start`, "_blank", "noopener,noreferrer");
  }, []);

  const handleEmailSync = useCallback(async () => {
    setEmailSyncing(true);
    setEmailError(null);
    setEmailNotice(null);
    try {
      const result = await apiRequest<EmailSyncResult>("/api/email/sync", {
        method: "POST",
        body: JSON.stringify({ days_back: 180, max_messages: 100 }),
      });
      setEmailNotice(
        `Sync complete: scanned ${result.scanned}, imported ${result.imported}, skipped ${result.duplicates} duplicates, and left ${result.review_required} event(s) for review.${result.more_pages_pending ? " More pages remain; run Sync again to continue through older messages." : ""}`,
      );
      setEmailEventFilter("pending");
      await Promise.all([loadEmailIntelligence("pending"), loadApplications()]);
    } catch (error) {
      setEmailError(errorText(error));
    } finally {
      setEmailSyncing(false);
    }
  }, [loadApplications, loadEmailIntelligence]);

  const handleEmailDisconnect = useCallback(async () => {
    const confirmed = window.confirm(
      "Disconnect Gmail from JobPilot? Previously imported event history will remain in your local database.",
    );
    if (!confirmed) return;
    setEmailError(null);
    setEmailNotice(null);
    try {
      await apiRequest<{ connected: boolean; message: string }>("/api/email/disconnect", {
        method: "POST",
      });
      setEmailNotice("Gmail was disconnected. Previously imported event history was retained.");
      await loadEmailIntelligence();
    } catch (error) {
      setEmailError(errorText(error));
    }
  }, [loadEmailIntelligence]);

  const handleEmailEventReview = useCallback(async (
    eventId: number,
    decision: "approve" | "ignore",
    applicationId?: number,
  ) => {
    setEmailError(null);
    setEmailNotice(null);
    const payload: { decision: "approve" | "ignore"; application_id?: number; note?: string } = { decision };
    if (applicationId !== undefined) payload.application_id = applicationId;
    try {
      const result = await apiRequest<{
        review_status: string;
        before_status?: string;
        after_status?: string;
        application_status_changed?: boolean;
      }>(`/api/email/events/${eventId}/review`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (decision === "ignore") {
        setEmailNotice("Email event ignored. The application status was not changed.");
      } else if (result.application_status_changed) {
        setEmailNotice(`Email event approved. Application status changed from ${result.before_status} to ${result.after_status}.`);
      } else {
        setEmailNotice(`Email event approved. The application remains ${result.after_status || "at its existing status"}; no backward status change was made.`);
      }
      await Promise.all([loadEmailIntelligence(), loadApplications()]);
    } catch (error) {
      setEmailError(errorText(error));
    }
  }, [loadApplications, loadEmailIntelligence]);

  const handleEmailApplicationSelect = useCallback((eventId: number, applicationId: string) => {
    setEmailSelectedApplicationIds((current) => ({ ...current, [eventId]: applicationId }));
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
    if (screen !== "applications" && screen !== "jobs" && screen !== "email") {
      return;
    }

    const timerId = window.setTimeout(() => {
      void loadApplications();
    }, 0);

    return () => window.clearTimeout(timerId);
  }, [screen, loadApplications]);


  useEffect(() => {
    if (screen !== "email") return;
    const timerId = window.setTimeout(() => {
      void loadEmailIntelligence();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [screen, loadEmailIntelligence]);

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
        role_scope: filterDraft.role_scope,
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

  const handleTailorTrackedJob = async (jobId: number) => {
    try {
      const job = await apiRequest<Job>(`/api/jobs/${jobId}`);
      openResumeForJob(job);
    } catch (error) {
      setApplicationsError(errorText(error));
    }
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
      role_scope: filterDraft.role_scope,
      compensation_filter: filterDraft.compensation_filter,
    });
    setSuggestionsOpen(false);
  };

  const selectSuggestedTitle = (suggestion: JobTitleSuggestion) => {
    const nextFilters: JobFilters = {
      company: filterDraft.company.trim(),
      location: filterDraft.location.trim(),
      source: filterDraft.source.trim(),
      career_level: filterDraft.career_level,
      role_scope: filterDraft.role_scope,
      compensation_filter: filterDraft.compensation_filter,
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
                    isTracked={(jobId) => applications.some((item) => item.job_id === jobId)}
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
                    onDiscoverJobs={openJobs}
                    onTailorResume={handleTailorTrackedJob}
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


                {screen === "coverage" && <CoverageView />}

                {screen === "recommended" && <RecommendedView />}

                {screen === "documents" && <DocumentsView />}

                {screen === "email" && (
                  <EmailIntelligenceView
                    connection={emailConnection}
                    events={emailEvents}
                    applications={applications}
                    loading={emailLoading}
                    syncing={emailSyncing}
                    error={emailError}
                    notice={emailNotice}
                    selectedApplicationIds={emailSelectedApplicationIds}
                    eventFilter={emailEventFilter}
                    pendingTotal={emailPendingTotal}
                    eventTotal={emailEventTotal}
                    onFilterChange={setEmailEventFilter}
                    onRefresh={() => {
                      void loadEmailIntelligence();
                      void loadApplications();
                    }}
                    onConnect={handleEmailConnect}
                    onSync={handleEmailSync}
                    onDisconnect={handleEmailDisconnect}
                    onReview={handleEmailEventReview}
                    onSelectApplication={handleEmailApplicationSelect}
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
