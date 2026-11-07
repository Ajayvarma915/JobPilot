import { useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  Copy,
  ExternalLink,
  FileText,
  LoaderCircle,
  Plus,
  Save,
  Sparkles,
  Trash2,
} from "lucide-react";

type Sponsorship = "yes" | "no" | "unknown";

type PreparationProfile = {
  contact_name: string;
  email: string;
  phone: string;
  current_location: string;
  linkedin_url: string;
  github_url: string;
  portfolio_url: string;
  current_employer: string;
  current_title: string;
  years_experience: string;
  notice_period: string;
  work_authorization: string;
  requires_sponsorship: Sponsorship | "";
  salary_expectation: string;
};

type CustomQuestion = { question: string; answer: string };
type ResumeOption = {
  filename: string;
  format: "pdf" | "docx";
  modified_at: string;
  size_bytes: number;
};
type PreparationResponse = {
  application_id: number;
  application_status: string;
  resume_filename: string | null;
  cover_letter_filename: string | null;
  profile: Partial<Record<keyof PreparationProfile, string | null>>;
  cover_letter_draft: string;
  custom_questions: CustomQuestion[];
  prepared: boolean;
  blockers: string[];
  resume_options: ResumeOption[];
  prepared_at: string | null;
  updated_at: string | null;
  job: {
    id: number;
    title: string;
    company: string;
    location: string | null;
    url: string;
    description_available: boolean;
    is_active: boolean;
  };
  submission_note: string;
};
type ReviewKey =
  | "job_reviewed"
  | "eligibility_confirmed"
  | "resume_reviewed"
  | "application_details_reviewed";
type ReadinessResponse = {
  ready: boolean;
  readiness_label: string;
  completed_checks: number;
  total_checks: number;
  checks: Array<{
    id: string;
    label: string;
    passed: boolean;
    blocking: boolean;
    detail: string;
  }>;
  blockers: string[];
  review: Record<ReviewKey, boolean>;
  resume_options: ResumeOption[];
  submission_note: string;
};

type Props = {
  applicationId: number;
  jobId: number;
  jobTitle: string;
  company: string;
  onTailorResume: (jobId: number) => Promise<void> | void;
  onRefresh: () => void;
};

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const EMPTY_PROFILE: PreparationProfile = {
  contact_name: "",
  email: "",
  phone: "",
  current_location: "",
  linkedin_url: "",
  github_url: "",
  portfolio_url: "",
  current_employer: "",
  current_title: "",
  years_experience: "",
  notice_period: "",
  work_authorization: "",
  requires_sponsorship: "",
  salary_expectation: "",
};

const PROFILE_FIELDS: Array<{
  key: keyof PreparationProfile;
  label: string;
  placeholder: string;
  type?: string;
}> = [
  { key: "contact_name", label: "Full name", placeholder: "Your full name" },
  { key: "email", label: "Email", placeholder: "you@example.com", type: "email" },
  { key: "phone", label: "Phone", placeholder: "+91 ..." },
  { key: "current_location", label: "Current location", placeholder: "Hyderabad, India" },
  { key: "linkedin_url", label: "LinkedIn URL", placeholder: "https://linkedin.com/in/..." },
  { key: "github_url", label: "GitHub URL", placeholder: "https://github.com/..." },
  { key: "portfolio_url", label: "Portfolio URL", placeholder: "https://..." },
  { key: "current_employer", label: "Current employer", placeholder: "Company" },
  { key: "current_title", label: "Current title", placeholder: "Systems Engineer" },
  { key: "years_experience", label: "Experience", placeholder: "e.g. 1 year" },
  { key: "notice_period", label: "Notice period", placeholder: "e.g. 30 days" },
  { key: "work_authorization", label: "Work authorization", placeholder: "e.g. Authorized to work in India" },
  { key: "salary_expectation", label: "Salary expectation", placeholder: "e.g. ₹25–30 LPA" },
];

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new Error(`Cannot reach JobPilot API at ${API_BASE}. Start the backend and retry.`);
  }

  const body = await response.text();
  let payload: any = {};
  if (body) {
    try { payload = JSON.parse(body); } catch { payload = { detail: body }; }
  }
  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}).`);
  }
  return payload as T;
}

function inputClass(): string {
  return "field mt-1.5";
}

export default function ApplicationPreparationPanel({
  applicationId,
  jobId,
  jobTitle,
  company,
  onTailorResume,
  onRefresh,
}: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reviewSaving, setReviewSaving] = useState<ReviewKey | null>(null);
  const [preparation, setPreparation] = useState<PreparationResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [profile, setProfile] = useState<PreparationProfile>(EMPTY_PROFILE);
  const [resumeFilename, setResumeFilename] = useState("");
  const [coverLetter, setCoverLetter] = useState("");
  const [questions, setQuestions] = useState<CustomQuestion[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const reload = async () => {
    setLoading(true);
    setError("");
    try {
      const [prep, checks] = await Promise.all([
        apiRequest<PreparationResponse>(`/api/applications/${applicationId}/preparation`),
        apiRequest<ReadinessResponse>(`/api/applications/${applicationId}/readiness`),
      ]);
      setPreparation(prep);
      setReadiness(checks);
      setProfile({
        ...EMPTY_PROFILE,
        ...Object.fromEntries(
          Object.entries(prep.profile || {}).map(([key, value]) => [key, value ?? ""]),
        ),
      } as PreparationProfile);
      setResumeFilename(prep.resume_filename || "");
      setCoverLetter(prep.cover_letter_draft || "");
      setQuestions(Array.isArray(prep.custom_questions) ? prep.custom_questions : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load application preparation.");
    } finally {
      setLoading(false);
    }
  };

  const toggleOpen = () => {
    const next = !open;
    setOpen(next);
    if (next && !preparation && !loading) void reload();
  };

  const updateProfile = (key: keyof PreparationProfile, value: string) => {
    setProfile((current) => ({ ...current, [key]: value }));
  };

  const savePreparation = async () => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payload = await apiRequest<PreparationResponse>(
        `/api/applications/${applicationId}/preparation`,
        {
          method: "PATCH",
          body: JSON.stringify({
            ...profile,
            requires_sponsorship: profile.requires_sponsorship || null,
            resume_filename: resumeFilename || null,
            cover_letter_draft: coverLetter,
            custom_questions: questions,
          }),
        },
      );
      setPreparation(payload);
      setNotice(payload.prepared
        ? "Preparation details saved. Complete the review checklist below."
        : "Saved. Resolve the preparation blockers shown below.");
      const checks = await apiRequest<ReadinessResponse>(`/api/applications/${applicationId}/readiness`);
      setReadiness(checks);
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save preparation.");
    } finally {
      setSaving(false);
    }
  };

  const updateReview = async (key: ReviewKey, checked: boolean) => {
    setReviewSaving(key);
    setError("");
    try {
      await apiRequest(`/api/applications/${applicationId}`, {
        method: "PATCH",
        body: JSON.stringify({ [key]: checked }),
      });
      const checks = await apiRequest<ReadinessResponse>(`/api/applications/${applicationId}/readiness`);
      setReadiness(checks);
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the review confirmation.");
    } finally {
      setReviewSaving(null);
    }
  };

  const markReady = async () => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await apiRequest(`/api/applications/${applicationId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "ready_to_apply" }),
      });
      setNotice("Marked Ready to apply. Open the employer site and submit manually; JobPilot does not submit it for you.");
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The application is not ready yet.");
    } finally {
      setSaving(false);
    }
  };

  const copyCoverLetter = async () => {
    try {
      await navigator.clipboard.writeText(coverLetter);
      setNotice("Cover letter copied to clipboard.");
    } catch {
      setError("Clipboard access was blocked by the browser. Select and copy the text manually.");
    }
  };

  const reviewItems: Array<{ key: ReviewKey; label: string }> = [
    { key: "job_reviewed", label: "I reviewed the job responsibilities and requirements." },
    { key: "eligibility_confirmed", label: "I confirmed location, experience, education and work eligibility." },
    { key: "resume_reviewed", label: "I opened and reviewed the tailored resume for accuracy." },
    { key: "application_details_reviewed", label: "I reviewed the application details and employer questions." },
  ];

  return (
    <section className="mt-4 border-t border-slate-700/40 pt-3">
      <button
        type="button"
        onClick={toggleOpen}
        className="flex w-full items-center justify-between gap-3 rounded-xl border border-blue-300/15 bg-blue-400/[0.04] px-3.5 py-3 text-left hover:bg-blue-400/[0.07]"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 text-[11px] font-semibold text-blue-100">
          <ClipboardCheck size={14} /> Prepare application
          {preparation?.prepared && <span className="rounded-full border border-emerald-400/20 px-2 py-0.5 text-[9px] text-emerald-300">Profile ready</span>}
        </span>
        <ChevronDown size={14} className={`text-slate-400 transition ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="mt-3 space-y-4 rounded-xl border border-slate-700/50 bg-slate-950/30 p-4">
          <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start">
            <div>
              <p className="text-xs font-semibold text-slate-100">{jobTitle} · {company}</p>
              <p className="mt-1 text-[10px] text-slate-500">Reusable profile details are stored locally and can be edited for this application.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="secondary-button !px-3 !py-2" onClick={() => void onTailorResume(jobId)}>
                <Sparkles size={12} /> Tailor resume
              </button>
              {preparation?.job?.url && (
                <a className="secondary-button !px-3 !py-2" href={preparation.job.url} target="_blank" rel="noreferrer">
                  Employer site <ExternalLink size={12} />
                </a>
              )}
            </div>
          </div>

          {loading && (
            <div className="flex items-center gap-2 py-4 text-xs text-slate-400"><LoaderCircle size={14} className="loading-ring" /> Loading preparation details...</div>
          )}
          {!loading && error && <p className="rounded-lg border border-rose-400/20 bg-rose-400/[0.06] p-3 text-[11px] text-rose-200">{error}</p>}
          {!loading && preparation && (
            <>
              <div>
                <h4 className="mb-2 text-[11px] font-semibold text-slate-200">Application profile</h4>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {PROFILE_FIELDS.map((field) => (
                    <label key={field.key} className="block text-[10px] font-medium text-slate-400">
                      {field.label}
                      <input
                        className={inputClass()}
                        type={field.type || "text"}
                        value={profile[field.key]}
                        placeholder={field.placeholder}
                        maxLength={field.key === "email" ? 320 : 500}
                        onChange={(event) => updateProfile(field.key, event.target.value)}
                      />
                    </label>
                  ))}
                  <label className="block text-[10px] font-medium text-slate-400">
                    Requires sponsorship?
                    <select className={inputClass()} value={profile.requires_sponsorship} onChange={(event) => updateProfile("requires_sponsorship", event.target.value)}>
                      <option value="">Not specified</option>
                      <option value="no">No</option>
                      <option value="yes">Yes</option>
                      <option value="unknown">Not sure</option>
                    </select>
                  </label>
                </div>
              </div>

              <div>
                <h4 className="mb-2 text-[11px] font-semibold text-slate-200">Tailored resume</h4>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                  <select className="field" value={resumeFilename} onChange={(event) => setResumeFilename(event.target.value)}>
                    <option value="">Select a generated PDF or DOCX resume</option>
                    {preparation.resume_options.map((item) => (
                      <option key={item.filename} value={item.filename}>{item.filename} · {item.format.toUpperCase()}</option>
                    ))}
                  </select>
                  {resumeFilename && (
                    <a className="secondary-button !px-3 !py-2" href={`${API_BASE}/api/resumes/${encodeURIComponent(resumeFilename)}/download`} target="_blank" rel="noreferrer">
                      <FileText size={12} /> Review resume
                    </a>
                  )}
                </div>
                {preparation.resume_options.length === 0 && <p className="mt-1 text-[10px] text-amber-200">No generated resume found. Use Tailor resume to open Resume Studio.</p>}
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h4 className="text-[11px] font-semibold text-slate-200">Cover letter draft</h4>
                  <button type="button" className="secondary-button !px-2.5 !py-1.5" disabled={!coverLetter.trim()} onClick={() => void copyCoverLetter()}><Copy size={11} /> Copy</button>
                </div>
                <textarea className="field min-h-32 resize-y" maxLength={16000} value={coverLetter} onChange={(event) => setCoverLetter(event.target.value)} placeholder="Paste or write a truthful, role-specific cover letter. Verify every claim before using it." />
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h4 className="text-[11px] font-semibold text-slate-200">Employer-specific questions</h4>
                  <button type="button" className="secondary-button !px-2.5 !py-1.5" disabled={questions.length >= 15} onClick={() => setQuestions((items) => [...items, { question: "", answer: "" }])}><Plus size={11} /> Add question</button>
                </div>
                {questions.length === 0 ? <p className="text-[10px] text-slate-500">Add questions from the employer form and prepare accurate answers here.</p> : (
                  <div className="space-y-2">
                    {questions.map((item, index) => (
                      <div key={index} className="grid grid-cols-1 gap-2 rounded-lg border border-slate-700/40 p-3 sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)_auto]">
                        <input className="field" value={item.question} maxLength={500} placeholder={`Question ${index + 1}`} onChange={(event) => setQuestions((items) => items.map((entry, i) => i === index ? { ...entry, question: event.target.value } : entry))} />
                        <textarea className="field min-h-16 resize-y" value={item.answer} maxLength={6000} placeholder="Your truthful answer" onChange={(event) => setQuestions((items) => items.map((entry, i) => i === index ? { ...entry, answer: event.target.value } : entry))} />
                        <button type="button" className="secondary-button self-start !px-2.5 !py-2" aria-label={`Remove question ${index + 1}`} onClick={() => setQuestions((items) => items.filter((_, i) => i !== index))}><Trash2 size={12} /></button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-700/40 pt-3">
                <div className="text-[10px] text-slate-400">
                  {preparation.prepared ? <span className="text-emerald-300">Preparation profile checks passed.</span> : `${preparation.blockers.length} preparation item(s) still need attention.`}
                </div>
                <button type="button" className="primary-button !px-3 !py-2" disabled={saving} onClick={() => void savePreparation()}>
                  {saving ? <LoaderCircle size={12} className="loading-ring" /> : <Save size={12} />} Save preparation
                </button>
              </div>

              {!preparation.prepared && preparation.blockers.length > 0 && (
                <ul className="list-disc space-y-1 pl-5 text-[10px] text-amber-200">{preparation.blockers.map((item) => <li key={item}>{item}</li>)}</ul>
              )}

              {readiness && (
                <div className="space-y-3 rounded-xl border border-slate-700/50 p-3.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h4 className="text-[11px] font-semibold text-slate-100">Application readiness</h4>
                      <p className="mt-1 text-[10px] text-slate-500">{readiness.completed_checks}/{readiness.total_checks} checks passed · {readiness.readiness_label}</p>
                    </div>
                    <span className={`rounded-full border px-2.5 py-1 text-[9px] ${readiness.ready ? "border-emerald-400/20 text-emerald-300" : "border-amber-300/20 text-amber-200"}`}>{readiness.ready ? "Checklist complete" : "Review required"}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-emerald-400 transition-all" style={{ width: `${Math.round((readiness.completed_checks / Math.max(readiness.total_checks, 1)) * 100)}%` }} /></div>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {reviewItems.map((item) => (
                      <label key={item.key} className="flex cursor-pointer items-start gap-2 rounded-lg bg-slate-900/50 p-2.5 text-[10px] text-slate-300">
                        <input type="checkbox" className="mt-0.5 accent-emerald-400" checked={Boolean(readiness.review[item.key])} disabled={reviewSaving === item.key} onChange={(event) => void updateReview(item.key, event.target.checked)} />
                        <span>{item.label}</span>
                      </label>
                    ))}
                  </div>
                  <div className="space-y-1.5">
                    {readiness.checks.filter((item) => item.blocking && !item.passed).map((item) => (
                      <p key={item.id} className="flex items-start gap-2 text-[10px] text-amber-200"><span className="mt-0.5">•</span><span>{item.label}: {item.detail}</span></p>
                    ))}
                  </div>
                  <button type="button" className="primary-button w-full" disabled={saving || !readiness.ready || !preparation.prepared || preparation.application_status === "ready_to_apply"} onClick={() => void markReady()}>
                    {saving ? <LoaderCircle size={13} className="loading-ring" /> : <CheckCircle2 size={13} />}
                    {preparation.application_status === "ready_to_apply" ? "Ready to apply" : "Mark ready to apply"}
                  </button>
                  <p className="text-[10px] leading-4 text-slate-500">{readiness.submission_note}</p>
                </div>
              )}
            </>
          )}
          {notice && <p className="rounded-lg border border-emerald-400/15 bg-emerald-400/[0.05] p-2.5 text-[10px] text-emerald-200">{notice}</p>}
          <p className="text-[10px] text-slate-600">JobPilot stores preparation data locally. It does not autofill or submit an employer application.</p>
        </div>
      )}
    </section>
  );
}
