import { useEffect, useState } from "react";
import { CheckCircle2, Circle } from "lucide-react";
import { apiRequest } from "../lib";
import { type Screen } from "../types";

interface Step {
  id: string;
  title: string;
  detail: string;
  done: boolean;
  screen: Screen;
  action: string;
}

interface Progress {
  steps: Step[];
}

async function safe<T>(path: string): Promise<T | null> {
  try {
    return await apiRequest<T>(path);
  } catch {
    return null; // one unavailable service must not hide the whole checklist
  }
}

// A short "what to do next" list for a new setup. Each step is marked done from real data,
// and its button opens the screen where you do it.
export function OnboardingChecklist({ onNavigate }: { onNavigate: (screen: Screen) => void }) {
  const [progress, setProgress] = useState<Progress | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      safe<{ status: string; record_count: number; pending_count: number }>("/api/evidence/summary"),
      safe<{ total_companies: number; active_jobs: number }>("/api/dashboard/stats"),
      safe<{ connected: boolean }>("/api/email/status"),
      safe<{ total: number }>("/api/applications/stats"),
    ]).then(([evidence, stats, email, applications]) => {
      if (cancelled) return;
      const evidenceReady = !!evidence && evidence.record_count > 0 && evidence.pending_count === 0;
      setProgress({
        steps: [
          {
            id: "evidence",
            title: "Confirm your resume statements",
            detail: !evidence || evidence.record_count === 0
              ? "No resume was read yet. Put your PDF in data/master_resume and build the evidence store."
              : evidenceReady
                ? `All ${evidence.record_count} statements are confirmed.`
                : `${evidence.pending_count} of ${evidence.record_count} statements wait for you. Tailored resumes use only confirmed ones.`,
            done: evidenceReady,
            screen: "resume",
            action: "Open Resume studio",
          },
          {
            id: "jobs",
            title: "Read jobs from the companies",
            detail: stats && stats.total_companies >= 5
              ? `${stats.total_companies} companies have jobs saved.`
              : "Press Update jobs now on the Discover screen. It reads every company career page and the remote boards.",
            done: !!stats && stats.total_companies >= 5,
            screen: "jobs",
            action: "Open Discover",
          },
          {
            id: "gmail",
            title: "Connect Gmail (read-only)",
            detail: email?.connected ? "Connected. Application emails are matched to your tracker." : "Lets JobPilot notice assessments, interviews and replies. It never sends or deletes mail.",
            done: !!email?.connected,
            screen: "email",
            action: "Open Email",
          },
          {
            id: "track",
            title: "Track your first application",
            detail: applications && applications.total > 0 ? `${applications.total} application(s) tracked.` : "Press Track on a job you like, or save a job with the browser extension.",
            done: !!applications && applications.total > 0,
            screen: "applications",
            action: "Open Applications",
          },
        ],
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!progress) return null;
  const remaining = progress.steps.filter((step) => !step.done);
  if (remaining.length === 0) {
    return (
      <p className="flex items-center gap-2 text-[11px] text-emerald-300">
        <CheckCircle2 size={14} /> Setup complete: resume confirmed, jobs read, Gmail connected, first application tracked.
      </p>
    );
  }
  return (
    <section className="panel rounded-2xl p-4 sm:p-5" aria-label="Getting started">
      <h3 className="text-sm font-semibold text-slate-100">
        Getting started: {progress.steps.length - remaining.length} of {progress.steps.length} done
      </h3>
      <ul className="mt-3 space-y-2.5">
        {progress.steps.map((step) => (
          <li key={step.id} className="flex flex-wrap items-start justify-between gap-2">
            <div className="flex min-w-0 items-start gap-2">
              {step.done ? <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-300" /> : <Circle size={15} className="mt-0.5 shrink-0 text-slate-500" />}
              <div className="min-w-0">
                <p className={`text-xs font-medium ${step.done ? "text-slate-400 line-through" : "text-slate-100"}`}>{step.title}</p>
                <p className="text-[11px] text-slate-500">{step.detail}</p>
              </div>
            </div>
            {!step.done && (
              <button className="secondary-button !px-3 !py-1.5 text-[11px]" onClick={() => onNavigate(step.screen)}>
                {step.action}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
