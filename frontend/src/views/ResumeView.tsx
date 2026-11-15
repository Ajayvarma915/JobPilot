import { type FormEvent } from "react";
import { ArrowRight, CheckCircle2, Download, FileCheck2, FileText, Gauge, LoaderCircle, ShieldCheck, Target, WandSparkles } from "lucide-react";
import { EmptyState, SectionHeading } from "../components";
import { API_BASE } from "../config";
import { categoryLabel, compactText } from "../lib";
import { type EvidenceSelection, type GeneratedResume } from "../types";

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

export function ResumeView({
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
