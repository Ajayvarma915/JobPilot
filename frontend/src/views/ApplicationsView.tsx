import { useState } from "react";
import { motion } from "motion/react";
import { Building2, CheckCircle2, CalendarDays, ClipboardList, Clock3, ExternalLink, LoaderCircle, MapPin, Plus, RefreshCw, Save, Search, Zap } from "lucide-react";
import ApplicationPreparationPanel from "../components/ApplicationPreparationPanel";
import { EmptyState, SectionHeading } from "../components";
import { errorText, formatNumber } from "../lib";
import { APPLICATION_STATUSES, type ApplicationStats, type ApplicationStatus, type ApplicationUpdatePayload, type TrackedApplication } from "../types";

function ApplicationCard({
  application,
  onUpdate,
  onTailorResume,
  onRefresh,
}: {
  application: TrackedApplication;
  onUpdate: (
    applicationId: number,
    update: ApplicationUpdatePayload,
  ) => Promise<TrackedApplication>;
  onTailorResume: (jobId: number) => Promise<void>;
  onRefresh: () => void;
}) {
  const [draftStatus, setDraftStatus] = useState<ApplicationStatus>(application.status);
  const [notes, setNotes] = useState(application.notes ?? "");
  const [nextAction, setNextAction] = useState(application.next_action ?? "");
  const [followUpDate, setFollowUpDate] = useState(application.follow_up_date ?? "");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState(false);

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
        <a
          className="secondary-button shrink-0 !px-3 !py-2"
          href={application.job.url}
          target="_blank"
          rel="noreferrer"
        >
          Original posting <ExternalLink size={13} />
        </a>
      </div>

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

      <ApplicationPreparationPanel
        applicationId={application.id}
        jobId={application.job_id}
        jobTitle={application.job.title}
        company={application.job.company}
        onTailorResume={onTailorResume}
        onRefresh={onRefresh}
      />
    </motion.article>
  );
}

export function ApplicationsView({
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
  onDiscoverJobs,
  onTailorResume,
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
  onDiscoverJobs: () => void;
  onTailorResume: (jobId: number) => Promise<void>;
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
              onTailorResume={onTailorResume}
              onRefresh={onRefresh}
            />
          ))}
        </div>
      )}
    </div>
  );
}
