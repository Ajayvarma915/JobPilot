import { useEffect, useState } from "react";
import { Download, LoaderCircle } from "lucide-react";
import { API_BASE } from "../config";
import { errorText } from "../lib";

interface VersionSummary {
  id: number;
  job_id: number | null;
  job_title: string;
  company_name: string | null;
  created_at: string;
  evidence_count: number;
  readiness_label: string | null;
  docx_filename: string;
  pdf_filename: string;
  download_url: string;
  pdf_download_url: string;
  files_present: { docx: boolean; pdf: boolean };
}

interface VersionDetail extends VersionSummary {
  report: {
    keywords_aligned: string[];
    evidence_reused: Array<{ evidence_id: string; category: string; title: string; matched_keywords: string[] }>;
    required_skills: {
      total: number;
      covered_with_verified_evidence: string[];
      awaiting_your_review: string[];
      no_evidence_found: string[];
    };
    sections_changed: Array<{ section: string; items_included: number; change: string }>;
    needs_review: Array<{ kind: string; title?: string; skill?: string; why: string }>;
    original_resume: { modified: boolean; note: string };
  };
  fabrication_check: { ok: boolean; bullets_checked: number; violations: string[] };
}

function ReportDetail({ detail }: { detail: VersionDetail }) {
  const { report } = detail;
  return (
    <div className="mt-3 space-y-3 rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 text-xs text-slate-300">
      <p className={detail.fabrication_check.ok ? "text-emerald-300" : "text-rose-300"}>
        {detail.fabrication_check.ok
          ? `Integrity check passed: all ${detail.fabrication_check.bullets_checked} bullets come from evidence you verified.`
          : "Integrity check failed."}
      </p>
      <div>
        <p className="font-semibold text-slate-200">Keywords aligned with the job</p>
        <p>{report.keywords_aligned.length ? report.keywords_aligned.join(", ") : "None of the job keywords matched verified evidence."}</p>
      </div>
      <div>
        <p className="font-semibold text-slate-200">Required skills ({report.required_skills.total})</p>
        <p>Covered with verified evidence: {report.required_skills.covered_with_verified_evidence.join(", ") || "none"}</p>
        <p>Waiting for your review: {report.required_skills.awaiting_your_review.join(", ") || "none"}</p>
        <p>No evidence found: {report.required_skills.no_evidence_found.join(", ") || "none"}</p>
      </div>
      <div>
        <p className="font-semibold text-slate-200">What changed from your master resume</p>
        <ul className="list-disc pl-5">
          {report.sections_changed.map((section) => (
            <li key={section.section}>
              {section.section} ({section.items_included}): {section.change}
            </li>
          ))}
        </ul>
        <p className="mt-1 text-slate-400">{report.original_resume.note}</p>
      </div>
      <div>
        <p className="font-semibold text-slate-200">Original details reused ({report.evidence_reused.length})</p>
        <ul className="list-disc pl-5">
          {report.evidence_reused.map((item) => (
            <li key={item.evidence_id}>
              {item.title} <span className="text-slate-500">({item.category})</span>
            </li>
          ))}
        </ul>
      </div>
      {report.needs_review.length > 0 && (
        <div>
          <p className="font-semibold text-amber-200">Needs your review</p>
          <ul className="list-disc pl-5">
            {report.needs_review.map((item, index) => (
              <li key={`${item.kind}-${index}`}>
                {item.title ?? item.skill}: {item.why}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function ResumeVersionsPanel({ refreshKey }: { refreshKey: string | null }) {
  const [versions, setVersions] = useState<VersionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [detail, setDetail] = useState<VersionDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/resume-versions`)
      .then((response) => {
        if (!response.ok) throw new Error(`Resume versions request failed (${response.status}).`);
        return response.json() as Promise<{ items: VersionSummary[] }>;
      })
      .then((payload) => {
        if (!cancelled) {
          setVersions(payload.items);
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorText(caught));
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const toggle = (id: number) => {
    if (openId === id) {
      setOpenId(null);
      setDetail(null);
      return;
    }
    setOpenId(id);
    setDetail(null);
    setDetailError(null);
    fetch(`${API_BASE}/api/resume-versions/${id}`)
      .then((response) => {
        if (!response.ok) throw new Error(`Report request failed (${response.status}).`);
        return response.json() as Promise<VersionDetail>;
      })
      .then(setDetail)
      .catch((caught: unknown) => setDetailError(errorText(caught)));
  };

  return (
    <section className="panel rounded-2xl p-5">
      <h3 className="text-sm font-semibold text-slate-100">Generated resume versions</h3>
      <p className="mt-1 text-xs text-slate-400">
        Every tailored resume is kept here with a report of what it reused. Your master resume is never changed.
      </p>
      {error && <p className="mt-3 text-xs text-rose-300">{error}</p>}
      {versions === null && !error && (
        <p className="mt-3 flex items-center text-xs text-slate-400">
          <LoaderCircle className="loading-ring mr-2 h-3.5 w-3.5" /> Loading versions…
        </p>
      )}
      {versions !== null && versions.length === 0 && (
        <p className="mt-3 text-xs text-slate-500">No tailored resume has been generated yet.</p>
      )}
      <ul className="mt-3 grid gap-3">
        {versions?.map((version) => (
          <li key={version.id} className="rounded-xl border border-slate-800/80 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm font-medium text-slate-100">
                  {version.job_title}
                  {version.company_name && <span className="text-slate-400"> · {version.company_name}</span>}
                </p>
                <p className="text-[11px] text-slate-500">
                  {new Date(version.created_at).toLocaleString()} · {version.evidence_count} verified items ·{" "}
                  {version.readiness_label ?? "no readiness label"}
                </p>
              </div>
              <div className="flex items-center gap-3 text-xs">
                {version.files_present.docx ? (
                  <a href={`${API_BASE}${version.download_url}`} download className="inline-flex items-center gap-1 text-blue-300 hover:underline">
                    <Download size={12} /> Word
                  </a>
                ) : (
                  <span className="text-slate-600">Word file missing</span>
                )}
                {version.files_present.pdf ? (
                  <a href={`${API_BASE}${version.pdf_download_url}`} download className="inline-flex items-center gap-1 text-blue-300 hover:underline">
                    <Download size={12} /> PDF
                  </a>
                ) : (
                  <span className="text-slate-600">PDF file missing</span>
                )}
                <button type="button" onClick={() => toggle(version.id)} className="text-slate-300 hover:text-white">
                  {openId === version.id ? "Hide report" : "View report"}
                </button>
              </div>
            </div>
            {openId === version.id && detailError && <p className="mt-2 text-xs text-rose-300">{detailError}</p>}
            {openId === version.id && !detail && !detailError && (
              <p className="mt-2 text-xs text-slate-500">Loading report…</p>
            )}
            {openId === version.id && detail && detail.id === version.id && <ReportDetail detail={detail} />}
          </li>
        ))}
      </ul>
    </section>
  );
}
