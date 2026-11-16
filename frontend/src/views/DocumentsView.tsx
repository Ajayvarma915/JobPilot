import { useEffect, useState } from "react";
import { Download, LoaderCircle, Trash2 } from "lucide-react";
import { API_BASE } from "../config";
import { EmptyState, SectionHeading } from "../components";
import { errorText } from "../lib";
import { type ApplicationListResponse, type TrackedApplication } from "../types";

interface CoverLetter {
  id: number;
  job_id: number;
  version_no: number;
  source: string;
  job_title: string;
  company_name: string | null;
  saved_filename: string | null;
  created_at: string;
  body?: string;
  report: { facts_used?: string[]; not_claimed?: string[]; warnings?: string[] };
}

interface EmployerAnswer {
  id: number;
  question_key: string;
  question: string;
  answer: string;
  status: "needs_input" | "draft" | "approved";
  sensitive: boolean;
  company_specific: boolean;
  company_name: string | null;
  message: string | null;
}

const STATUS_TONES: Record<string, string> = {
  approved: "border-emerald-400/25 bg-emerald-400/[0.1] text-emerald-300",
  draft: "border-sky-400/25 bg-sky-400/[0.1] text-sky-300",
  needs_input: "border-amber-300/25 bg-amber-300/[0.1] text-amber-200",
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch {
      /* keep the generic message */
    }
    throw new Error(detail);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

function CoverLetterSection({ applications }: { applications: TrackedApplication[] }) {
  const [jobId, setJobId] = useState<number | null>(applications[0]?.job_id ?? null);
  const [versions, setVersions] = useState<CoverLetter[]>([]);
  const [current, setCurrent] = useState<CoverLetter | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (jobId === null) return;
    let cancelled = false;
    api<{ items: CoverLetter[] }>(`/api/cover-letters?job_id=${jobId}`)
      .then((payload) => {
        if (!cancelled) setVersions(payload.items);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorText(caught));
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, reload]);

  const run = (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    work()
      .catch((caught: unknown) => setError(errorText(caught)))
      .finally(() => setBusy(false));
  };

  const open = (id: number) =>
    run(async () => {
      const letter = await api<CoverLetter>(`/api/cover-letters/${id}`);
      setCurrent(letter);
      setText(letter.body ?? "");
    });

  const generate = () =>
    run(async () => {
      if (jobId === null) return;
      const letter = await api<CoverLetter>("/api/cover-letters/generate", { method: "POST", body: JSON.stringify({ job_id: jobId }) });
      setCurrent(letter);
      setText(letter.body ?? "");
      setReload((value) => value + 1);
      setMessage("Draft created from your verified facts only. Read it and edit freely before using it.");
    });

  const saveEdit = () =>
    run(async () => {
      if (!current) return;
      const letter = await api<CoverLetter>(`/api/cover-letters/${current.id}/edit`, { method: "POST", body: JSON.stringify({ body: text }) });
      setCurrent(letter);
      setReload((value) => value + 1);
      setMessage(`Saved as version ${letter.version_no}. Earlier versions are kept.`);
    });

  const saveFile = () =>
    run(async () => {
      if (!current) return;
      const saved = await api<{ filename: string }>(`/api/cover-letters/${current.id}/save-file`, { method: "POST" });
      setMessage(`Saved as ${saved.filename}. You can attach it to the application in Applications.`);
    });

  return (
    <section className="panel rounded-2xl p-5">
      <h3 className="text-sm font-semibold text-slate-100">Cover letters</h3>
      <p className="mt-1 text-xs text-slate-400">
        Drafted only from your profile and the resume evidence you verified. Skills you cannot back up are left out and listed below the draft.
      </p>

      {applications.length === 0 ? (
        <EmptyState icon={Download} title="Track a job first" message="Cover letters are written for a tracked application. Track a job from Discover jobs or Recommended." />
      ) : (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <select
              value={jobId ?? ""}
              onChange={(event) => {
                setJobId(Number(event.target.value));
                setCurrent(null);
                setText("");
              }}
              aria-label="Choose a tracked job"
              className="field w-auto max-w-full"
            >
              {applications.map((application) => (
                <option key={application.id} value={application.job_id}>
                  {application.job.title} — {application.job.company}
                </option>
              ))}
            </select>
            <button type="button" onClick={generate} disabled={busy} className="rounded-xl border border-blue-400/30 bg-blue-500/10 px-3 py-2 text-xs font-medium text-blue-200 disabled:opacity-50">
              {busy ? "Working…" : "Draft a cover letter"}
            </button>
          </div>

          {error && <p role="alert" className="mt-3 text-xs text-rose-300">{error}</p>}
          {message && <p className="mt-3 text-xs text-emerald-300">{message}</p>}

          {versions.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2 text-xs">
              {versions.map((version) => (
                <button
                  key={version.id}
                  type="button"
                  onClick={() => open(version.id)}
                  className={`rounded-full border px-3 py-1.5 ${current?.id === version.id ? "border-blue-400/40 text-blue-200" : "border-slate-700/70 text-slate-400"}`}
                >
                  v{version.version_no} · {version.source === "user_edit" ? "your edit" : "draft"}
                </button>
              ))}
            </div>
          )}

          {current && (
            <div className="mt-4">
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                aria-label="Cover letter text"
                rows={14}
                className="field w-full font-mono text-xs leading-5"
              />
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
                <button type="button" onClick={saveEdit} disabled={busy || !text.trim()} className="rounded-xl border border-slate-600 px-3 py-2 text-slate-100 disabled:opacity-50">
                  Save as new version
                </button>
                <a href={`${API_BASE}/api/cover-letters/${current.id}/download?format=docx`} className="inline-flex items-center gap-1 text-blue-300 hover:underline">
                  <Download size={12} /> Word
                </a>
                <a href={`${API_BASE}/api/cover-letters/${current.id}/download?format=pdf`} className="inline-flex items-center gap-1 text-blue-300 hover:underline">
                  <Download size={12} /> PDF
                </a>
                <button type="button" onClick={saveFile} disabled={busy} className="text-slate-300 hover:text-white">
                  Save file for the application
                </button>
              </div>
              <div className="mt-3 space-y-1 text-[11px] text-slate-500">
                {current.report.not_claimed && current.report.not_claimed.length > 0 && (
                  <p className="text-amber-200">Not claimed (no verified evidence): {current.report.not_claimed.join(", ")}</p>
                )}
                {(current.report.warnings ?? []).map((warning) => (
                  <p key={warning}>{warning}</p>
                ))}
                <p>Edits to the text are yours: re-read the letter before sending, because JobPilot cannot check what you add.</p>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function AnswerSection({ applications }: { applications: TrackedApplication[] }) {
  const [answers, setAnswers] = useState<EmployerAnswer[]>([]);
  const [question, setQuestion] = useState("");
  const [technology, setTechnology] = useState("");
  const [jobId, setJobId] = useState<string>("");
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [confirms, setConfirms] = useState<Record<number, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api<{ items: EmployerAnswer[] }>("/api/answers")
      .then((payload) => {
        if (!cancelled) setAnswers(payload.items);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorText(caught));
      });
    return () => {
      cancelled = true;
    };
  }, [reload]);

  const run = (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    work()
      .then(() => setReload((value) => value + 1))
      .catch((caught: unknown) => setError(errorText(caught)))
      .finally(() => setBusy(false));
  };

  const draft = () =>
    run(async () => {
      await api("/api/answers/draft", {
        method: "POST",
        body: JSON.stringify({
          question,
          technology: technology.trim() || undefined,
          job_id: jobId ? Number(jobId) : undefined,
        }),
      });
      setQuestion("");
      setTechnology("");
    });

  return (
    <section className="panel rounded-2xl p-5">
      <h3 className="text-sm font-semibold text-slate-100">Answer library</h3>
      <p className="mt-1 text-xs text-slate-400">
        Answers to common employer questions, built from your saved profile and verified evidence. Missing facts are never filled in. Salary, work authorization and company-specific answers need your explicit confirmation.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Paste the employer's question"
          aria-label="Employer question"
          className="field sm:col-span-2"
        />
        <input value={technology} onChange={(event) => setTechnology(event.target.value)} placeholder="Technology (for experience questions)" aria-label="Technology" className="field" />
        <select value={jobId} onChange={(event) => setJobId(event.target.value)} aria-label="Company-specific job" className="field">
          <option value="">Reusable (not tied to one job)</option>
          {applications.map((application) => (
            <option key={application.id} value={application.job_id}>
              {application.job.title} — {application.job.company}
            </option>
          ))}
        </select>
      </div>
      <button type="button" onClick={draft} disabled={busy || !question.trim()} className="mt-3 rounded-xl border border-blue-400/30 bg-blue-500/10 px-3 py-2 text-xs font-medium text-blue-200 disabled:opacity-50">
        {busy ? <LoaderCircle className="loading-ring inline h-3.5 w-3.5" /> : "Draft an answer"}
      </button>
      {error && <p role="alert" className="mt-3 text-xs text-rose-300">{error}</p>}

      {answers.length === 0 ? (
        <p className="mt-4 text-xs text-slate-500">No answers yet.</p>
      ) : (
        <ul className="mt-4 grid gap-3">
          {answers.map((answer) => {
            const value = edits[answer.id] ?? answer.answer;
            const needsConfirm = answer.sensitive || answer.company_specific;
            return (
              <li key={answer.id} className="rounded-xl border border-slate-800/80 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-slate-100">{answer.question}</p>
                  <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${STATUS_TONES[answer.status]}`}>
                    {answer.status.replace("_", " ")}
                  </span>
                </div>
                {answer.message && <p className="mt-1 text-[11px] text-amber-200">{answer.message}</p>}
                <textarea
                  value={value}
                  onChange={(event) => setEdits((current) => ({ ...current, [answer.id]: event.target.value }))}
                  aria-label={`Answer to ${answer.question}`}
                  rows={3}
                  className="field mt-2 w-full text-xs"
                />
                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
                  <button
                    type="button"
                    disabled={busy || value === answer.answer}
                    onClick={() => run(async () => { await api(`/api/answers/${answer.id}`, { method: "PATCH", body: JSON.stringify({ answer: value }) }); setEdits((current) => { const next = { ...current }; delete next[answer.id]; return next; }); })}
                    className="rounded-lg border border-slate-600 px-2.5 py-1.5 text-slate-100 disabled:opacity-40"
                  >
                    Save edit
                  </button>
                  {needsConfirm && (
                    <label className="flex items-center gap-1.5 text-slate-400">
                      <input type="checkbox" checked={confirms[answer.id] ?? false} onChange={(event) => setConfirms((current) => ({ ...current, [answer.id]: event.target.checked }))} />
                      I confirm this is accurate ({answer.sensitive ? "sensitive" : "company-specific"})
                    </label>
                  )}
                  <button
                    type="button"
                    disabled={busy || answer.status === "approved" || value !== answer.answer}
                    onClick={() => run(async () => { await api(`/api/answers/${answer.id}/approve`, { method: "POST", body: JSON.stringify({ confirm: confirms[answer.id] ?? false }) }); })}
                    className="rounded-lg border border-emerald-400/30 px-2.5 py-1.5 text-emerald-300 disabled:opacity-40"
                  >
                    Approve
                  </button>
                  <button type="button" disabled={busy} onClick={() => run(async () => { await api(`/api/answers/${answer.id}`, { method: "DELETE" }); })} className="ml-auto text-slate-500 hover:text-rose-300" aria-label="Delete answer">
                    <Trash2 size={13} />
                  </button>
                </div>
                {value !== answer.answer && <p className="mt-1 text-[11px] text-slate-500">Save your edit before approving.</p>}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export function DocumentsView() {
  const [applications, setApplications] = useState<TrackedApplication[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<ApplicationListResponse>("/api/applications?limit=100")
      .then((payload) => {
        if (!cancelled) setApplications(payload.items);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorText(caught));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Documents"
        title="Cover letters and answers"
        description="Application writing that stays honest: everything is built from facts you verified, and nothing is sent anywhere."
      />
      {error && <p role="alert" className="text-sm text-rose-300">{error} Start the backend and reload.</p>}
      {applications === null && !error ? (
        <p className="flex items-center text-sm text-slate-400">
          <LoaderCircle className="loading-ring mr-2 h-4 w-4" /> Loading…
        </p>
      ) : (
        applications && (
          <>
            <CoverLetterSection applications={applications} />
            <AnswerSection applications={applications} />
          </>
        )
      )}
    </div>
  );
}
