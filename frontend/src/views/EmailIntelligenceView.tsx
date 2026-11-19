import { CheckCircle2, ExternalLink, LoaderCircle, Mail, RefreshCw, ShieldCheck } from "lucide-react";
import { formatNumber } from "../lib";
import { EmailSuggestions } from "./EmailSuggestions";
import { type ApplicationStatus, type TrackedApplication } from "../types";

export interface EmailConnectionStatus {
  provider: "gmail";
  oauth_configured: boolean;
  connected: boolean;
  email_address: string | null;
  connected_at: string | null;
  last_sync_at: string | null;
  last_sync_imported: number;
  last_sync_scanned: number;
  last_error: string | null;
  requested_scope: string;
  stores_full_email_body: boolean;
}

export type EmailReviewFilter = "pending" | "approved" | "ignored";

type EmailEventType =
  | "application_confirmation"
  | "assessment_invitation"
  | "interview_invitation"
  | "offer"
  | "rejection";

export interface ApplicationEmailEvent {
  id: number;
  gmail_message_id: string;
  gmail_thread_id: string | null;
  received_at: string | null;
  sender: string;
  subject: string;
  snippet: string;
  event_type: EmailEventType;
  classification_confidence: number;
  matched_application_id: number | null;
  match_confidence: number;
  proposed_status: ApplicationStatus;
  review_status: "pending" | "approved" | "ignored";
  review_note: string | null;
  before_status: string | null;
  after_status: string | null;
  reviewed_at: string | null;
  created_at: string;
  matched_job: {
    application_id: number;
    company: string;
    title: string;
    current_status: ApplicationStatus;
  } | null;
}

export interface EmailEventListResponse {
  items: ApplicationEmailEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface EmailSyncResult {
  status: string;
  query_days_back: number;
  scanned: number;
  imported: number;
  duplicates: number;
  unclassified: number;
  errors: number;
  review_required: number;
  more_pages_pending: boolean;
  full_email_bodies_stored: boolean;
  note: string;
}

function emailEventLabel(eventType: EmailEventType): string {
  const labels: Record<EmailEventType, string> = {
    application_confirmation: "Application confirmation",
    assessment_invitation: "Online assessment",
    interview_invitation: "Interview invitation",
    offer: "Offer",
    rejection: "Rejection",
  };
  return labels[eventType];
}

function emailDateLabel(value: string | null): string {
  if (!value) return "Date unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

export function EmailIntelligenceView({
  connection,
  events,
  applications,
  loading,
  syncing,
  suggestionsKey,
  error,
  notice,
  selectedApplicationIds,
  eventFilter,
  pendingTotal,
  eventTotal,
  onFilterChange,
  onRefresh,
  onConnect,
  onSync,
  onDisconnect,
  onReview,
  onSelectApplication,
}: {
  connection: EmailConnectionStatus | null;
  events: ApplicationEmailEvent[];
  applications: TrackedApplication[];
  loading: boolean;
  syncing: boolean;
  suggestionsKey?: number;
  error: string | null;
  notice: string | null;
  selectedApplicationIds: Record<number, string>;
  eventFilter: EmailReviewFilter;
  pendingTotal: number;
  eventTotal: number;
  onFilterChange: (filter: EmailReviewFilter) => void;
  onRefresh: () => void;
  onConnect: () => void;
  onSync: () => void;
  onDisconnect: () => void;
  onReview: (
    eventId: number,
    decision: "approve" | "ignore",
    applicationId?: number,
  ) => void;
  onSelectApplication: (eventId: number, applicationId: string) => void;
}) {
  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-blue-300/80">
            Inbox intelligence
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-white sm:text-3xl">
            Employer email events
          </h1>
          <p className="mt-2 max-w-2xl text-xs leading-6 text-slate-400 sm:text-sm">
            Detect application confirmations, assessments, interviews, offers and rejections, then review each proposed tracker update.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="secondary-button" onClick={onRefresh} disabled={loading}>
            <RefreshCw size={13} className={loading ? "loading-ring" : ""} />
            Refresh
          </button>
          <button
            className="primary-button"
            onClick={onSync}
            disabled={!connection?.connected || syncing}
            title={!connection?.connected ? "Connect Gmail before syncing" : "Read recent recruiting-related email"}
          >
            {syncing ? <LoaderCircle size={14} className="loading-ring" /> : <Mail size={14} />}
            {syncing ? "Syncing inbox…" : "Sync Gmail"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-400/20 bg-rose-400/[0.06] px-4 py-3 text-xs leading-5 text-rose-200">
          {error}
        </div>
      )}
      {notice && (
        <div className="rounded-xl border border-emerald-400/20 bg-emerald-400/[0.06] px-4 py-3 text-xs leading-5 text-emerald-200">
          {notice}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-slate-800/80 bg-[#101827]/70 p-4">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-500">Gmail connection</span>
            <span className={`h-2 w-2 rounded-full ${connection?.connected ? "bg-emerald-400" : "bg-amber-300"}`} />
          </div>
          <p className="mt-3 truncate text-sm font-semibold text-slate-100">
            {connection?.connected ? connection.email_address || "Connected" : "Not connected"}
          </p>
          <p className="mt-1 text-[10px] leading-4 text-slate-500">
            {connection?.connected ? "Read-only access" : "Connect your own Google account"}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-800/80 bg-[#101827]/70 p-4">
          <span className="text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-500">Pending review</span>
          <p className="mt-3 text-2xl font-semibold tabular-nums text-slate-100">{formatNumber(pendingTotal)}</p>
          <p className="mt-1 text-[10px] leading-4 text-slate-500">No tracker changes until approval</p>
        </div>
        <div className="rounded-2xl border border-slate-800/80 bg-[#101827]/70 p-4">
          <span className="text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-500">Last successful sync</span>
          <p className="mt-3 text-sm font-semibold text-slate-100">
            {connection?.last_sync_at ? emailDateLabel(connection.last_sync_at) : "Not synced yet"}
          </p>
          <p className="mt-1 text-[10px] leading-4 text-slate-500">
            {connection?.last_sync_at
              ? `${formatNumber(connection.last_sync_imported)} events imported from ${formatNumber(connection.last_sync_scanned)} messages scanned`
              : "Run a sync after connecting Gmail"}
          </p>
        </div>
      </div>

      {!connection?.oauth_configured && (
        <section className="rounded-2xl border border-amber-300/20 bg-amber-300/[0.045] p-5">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-lg bg-amber-300/10 p-2 text-amber-200"><ShieldCheck size={17} /></div>
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold text-amber-100">Google OAuth setup required</h2>
              <p className="mt-2 text-xs leading-5 text-slate-300">
                Create a Google OAuth Web application client, enable the Gmail API, and save its downloaded JSON file at:
              </p>
              <code className="mt-2 block overflow-x-auto rounded-lg border border-slate-700/70 bg-black/20 px-3 py-2 text-[11px] text-slate-200">
                credentials/gmail_oauth_client.json
              </code>
              <p className="mt-2 text-[10px] leading-5 text-slate-400">
                Authorized redirect URI: <code className="text-slate-200">http://127.0.0.1:8000/api/email/oauth/callback</code>
              </p>
              <p className="mt-2 text-[10px] leading-5 text-slate-400">
                JobPilot requests only Gmail read-only access. For personal development, configure your Google account as a test user when the OAuth app is in testing mode.
              </p>
            </div>
          </div>
        </section>
      )}

      {connection?.connected && (
        <section className="rounded-2xl border border-slate-800/80 bg-[#101827]/50 p-4 sm:p-5">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 rounded-lg bg-emerald-400/[0.08] p-2 text-emerald-200"><CheckCircle2 size={17} /></div>
              <div>
                <p className="text-xs font-semibold text-slate-100">Gmail is connected</p>
                <p className="mt-1 text-[10px] leading-5 text-slate-400">
                  Last sync imported {formatNumber(connection.last_sync_imported)} events. Use Refresh to reload pending reviews.
                </p>
                {connection.last_error && <p className="mt-1 text-[10px] text-amber-200">Last sync warning: {connection.last_error}</p>}
              </div>
            </div>
            <button className="secondary-button self-start !border-rose-300/15 !text-rose-200 sm:self-center" onClick={onDisconnect}>
              Disconnect Gmail
            </button>
          </div>
        </section>
      )}

      {!connection?.connected && connection?.oauth_configured && (
        <section className="rounded-2xl border border-slate-800/80 bg-[#101827]/50 p-5">
          <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
            <div>
              <h2 className="text-sm font-semibold text-slate-100">Connect your Gmail account</h2>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-400">
                Google will ask you to grant read-only permission. Authorization opens in a separate tab so you can return here afterwards.
              </p>
            </div>
            <button className="primary-button self-start" onClick={onConnect}>
              <ExternalLink size={14} /> Connect Gmail
            </button>
          </div>
        </section>
      )}

      <section className="space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-100">{eventFilter === "pending" ? "Needs your review" : "Review history"}</h2>
            <p className="mt-1 text-[10px] text-slate-500">Each message is deduplicated by Gmail message ID and stored without its full body.</p>
          </div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filter email events">
            {(["pending", "approved", "ignored"] as const).map((filter) => {
              const active = eventFilter === filter;
              const label = filter === "pending" ? `Pending · ${formatNumber(pendingTotal)}` : filter === "approved" ? "Approved" : "Ignored";
              return (
                <button
                  key={filter}
                  type="button"
                  className={active ? "primary-button" : "secondary-button"}
                  aria-pressed={active}
                  onClick={() => onFilterChange(filter)}
                >
                  {label}
                </button>
              );
            })}
            <span className="self-center text-[10px] text-slate-500">{formatNumber(eventTotal)} total</span>
          </div>
        </div>

        {loading ? (
          <div className="rounded-2xl border border-slate-800/80 bg-[#101827]/40 p-8 text-center text-xs text-slate-400">
            <LoaderCircle size={18} className="loading-ring mx-auto mb-3" />
            Loading email events…
          </div>
        ) : events.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-700/70 bg-white/[0.015] p-8 text-center">
            <Mail size={22} className="mx-auto text-slate-600" />
            <p className="mt-3 text-xs font-semibold text-slate-300">
              {eventFilter === "pending" ? "No pending email events" : `No ${eventFilter} email events yet`}
            </p>
            <p className="mt-1 text-[10px] leading-5 text-slate-500">
              {eventFilter === "pending"
                ? connection?.connected
                  ? "Sync Gmail to look for recent assessment, interview, offer and application messages."
                  : "Connect Gmail first, then sync your inbox."
                : "Reviewed messages will appear here after you approve or ignore them."}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {events.map((event) => {
              const chosenValue = selectedApplicationIds[event.id] ?? (event.matched_application_id ? String(event.matched_application_id) : "");
              const selectedApplicationId = chosenValue ? Number(chosenValue) : null;
              const selectedApplication = selectedApplicationId
                ? applications.find((application) => application.id === selectedApplicationId)
                : null;
              const autoMatched = event.matched_application_id !== null && event.matched_job !== null;
              const hasManualOverride = selectedApplicationId !== null && selectedApplicationId !== event.matched_application_id;
              const canApprove = selectedApplicationId !== null;
              return (
                <article key={event.id} className="rounded-2xl border border-slate-800/80 bg-[#101827]/55 p-4 sm:p-5">
                  <div className="flex flex-col justify-between gap-3 md:flex-row md:items-start">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full border border-blue-300/20 bg-blue-300/[0.07] px-2.5 py-1 text-[9px] font-semibold text-blue-200">{emailEventLabel(event.event_type)}</span>
                        <span className="rounded-full border border-slate-700 px-2 py-1 text-[9px] text-slate-400">{Math.round(event.classification_confidence * 100)}% classification confidence</span>
                      </div>
                      <h3 className="mt-3 break-words text-sm font-semibold text-slate-100">{event.subject || "(No subject)"}</h3>
                      <p className="mt-1 break-words text-[10px] leading-5 text-slate-400">{event.sender} · {emailDateLabel(event.received_at)}</p>
                      {event.snippet && <p className="mt-3 rounded-xl bg-black/15 px-3 py-2 text-[11px] leading-5 text-slate-300">{event.snippet}</p>}
                    </div>
                    <div className="flex shrink-0 flex-col items-start gap-2 md:items-end">
                      <span className="text-[9px] uppercase tracking-[0.15em] text-slate-500">Proposed status</span>
                      <span className="rounded-lg border border-amber-300/15 bg-amber-300/[0.06] px-2.5 py-1.5 text-[10px] font-semibold text-amber-100">{event.proposed_status.replaceAll("_", " ")}</span>
                      {event.gmail_thread_id && (
                        <a className="inline-flex items-center gap-1 text-[10px] text-blue-300 hover:text-blue-200" href={`https://mail.google.com/mail/u/0/#all/${encodeURIComponent(event.gmail_thread_id)}`} target="_blank" rel="noreferrer">
                          Open in Gmail <ExternalLink size={11} />
                        </a>
                      )}
                    </div>
                  </div>

                  {eventFilter === "pending" ? (
                    <>
                      <div className="mt-4 rounded-xl border border-slate-800 bg-black/10 p-3">
                        <div className="flex items-center justify-between gap-3">
                      <p className="text-[10px] font-semibold text-slate-300">Match this email to an application</p>
                      {autoMatched && !hasManualOverride && (
                        <span className="text-[9px] text-emerald-200">Suggested match · {Math.round(event.match_confidence * 100)}%</span>
                      )}
                    </div>
                    <select
                      className="mt-2 w-full rounded-xl border border-slate-700 bg-[#0b1220] px-3 py-2.5 text-xs text-slate-200 outline-none focus:border-blue-400/50"
                      value={chosenValue}
                      onChange={(changeEvent) => onSelectApplication(event.id, changeEvent.target.value)}
                    >
                      <option value="">Choose an application…</option>
                      {applications.map((application) => (
                        <option key={application.id} value={String(application.id)}>
                          {application.job.company} — {application.job.title} ({application.status.replaceAll("_", " ")})
                        </option>
                      ))}
                    </select>
                    {selectedApplication && (
                      <p className="mt-2 text-[10px] leading-4 text-slate-500">
                        Selected: {selectedApplication.job.company} · {selectedApplication.job.title}. Current tracker status: {selectedApplication.status.replaceAll("_", " ")}.
                      </p>
                    )}
                    {!autoMatched && (
                      <p className="mt-2 text-[10px] leading-4 text-amber-200/80">JobPilot did not guess a specific application. Choose the correct one before approving.</p>
                    )}
                  </div>

                      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
                        <p className="text-[9px] leading-4 text-slate-500">No status changes occur until you approve this event.</p>
                        <div className="flex gap-2">
                          <button className="secondary-button" onClick={() => onReview(event.id, "ignore")}>
                            Ignore
                          </button>
                          <button
                            className="primary-button"
                            disabled={!canApprove}
                            onClick={() => onReview(event.id, "approve", hasManualOverride ? selectedApplicationId! : undefined)}
                            title={!canApprove ? "Choose an application first" : "Approve the proposed status update"}
                          >
                            <CheckCircle2 size={13} /> Approve update
                          </button>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="mt-4 rounded-xl border border-slate-800 bg-black/10 p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded-full border px-2.5 py-1 text-[9px] font-semibold ${event.review_status === "approved" ? "border-emerald-300/20 bg-emerald-300/[0.06] text-emerald-200" : "border-slate-600/40 bg-slate-700/20 text-slate-300"}`}>
                          {event.review_status === "approved" ? "Approved by you" : "Ignored by you"}
                        </span>
                        {event.reviewed_at && <span className="text-[9px] text-slate-500">Reviewed {emailDateLabel(event.reviewed_at)}</span>}
                      </div>
                      {event.matched_job && (
                        <p className="mt-3 text-[10px] text-slate-300">
                          Linked application: <span className="font-semibold">{event.matched_job.company}</span> · {event.matched_job.title}
                        </p>
                      )}
                      {event.review_status === "approved" && (
                        <p className="mt-2 text-[10px] text-slate-400">
                          Tracker status: {event.before_status || "unknown"} → {event.after_status || "unchanged"}
                        </p>
                      )}
                      {event.review_note && <p className="mt-2 text-[10px] leading-5 text-slate-500">Review note: {event.review_note}</p>}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>

      <EmailSuggestions refreshKey={suggestionsKey} />

      <section className="rounded-2xl border border-slate-800/70 bg-white/[0.015] p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck size={16} className="mt-0.5 shrink-0 text-slate-400" />
          <div>
            <p className="text-[10px] font-semibold text-slate-300">Privacy and control</p>
            <p className="mt-1 text-[10px] leading-5 text-slate-500">
              This integration requests Gmail read-only access, does not send or delete mail, does not download attachments, and stores event metadata/snippets rather than full email bodies. Disconnecting removes the local token but keeps previously imported event history.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
