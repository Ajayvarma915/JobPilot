import { useState, type ReactNode } from "react";
import { motion } from "motion/react";
import { ArrowRight, Building2, CheckCircle2, ChevronDown, Clock3, Command, LoaderCircle, MapPin, Search, Target, type LucideIcon } from "lucide-react";
import { recommendationTone } from "./lib";
import { type ApiStatus, type FilterOption, type Job, type JobCompensation, type JobMatch } from "./types";

export function MatchBadge({ match }: { match?: JobMatch }) {
  if (!match) {
    return (
      <span className="inline-flex items-center rounded-full border border-slate-700/60 bg-slate-800/40 px-2.5 py-1 text-[10px] text-slate-500">
        Match unavailable
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold ${recommendationTone(match.recommendation)}`}
      title={`Structured candidate match score: ${match.score}/100`}
    >
      <Target size={11} />
      {Math.round(match.score)}/100 · {match.recommendation_label}
    </span>
  );
}

export function MatchDetails({ match }: { match?: JobMatch }) {
  if (!match) {
    return (
      <p className="mt-3 text-[11px] text-slate-500">
        Match details are unavailable for this job.
      </p>
    );
  }

  const components: Array<{
    label: string;
    value: number;
    max: number;
  }> = [
    { label: "Role fit", value: match.score_breakdown.role, max: 25 },
    { label: "Seniority", value: match.score_breakdown.seniority, max: 20 },
    { label: "Experience", value: match.score_breakdown.experience, max: 20 },
    { label: "Skills", value: match.score_breakdown.skills, max: 20 },
    { label: "Education", value: match.score_breakdown.education, max: 10 },
    { label: "Location", value: match.score_breakdown.location, max: 5 },
  ];

  return (
    <div className="mt-4 grid grid-cols-1 gap-4 border-t border-slate-700/50 pt-4 xl:grid-cols-2">
      <div>
        <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">
          Score breakdown
        </p>

        <div className="space-y-2.5">
          {components.map((component) => (
            <div key={component.label}>
              <div className="mb-1 flex items-center justify-between gap-3 text-[10px]">
                <span className="text-slate-400">{component.label}</span>
                <span className="tabular-nums text-slate-300">
                  {component.value.toFixed(1)} / {component.max}
                </span>
              </div>

              <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-400"
                  style={{
                    width: `${Math.max(
                      0,
                      Math.min(100, (component.value / component.max) * 100),
                    )}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>

        <p className="mt-3 text-[10px] text-slate-500">
          JD analysis confidence: {match.analysis_confidence}
          {match.required_years != null
            ? ` · Minimum experience detected: ${match.required_years}+ years`
            : " · No explicit minimum years detected"}
        </p>
      </div>

      <div className="space-y-3">
        <div>
          <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">
            Why it matches
          </p>

          {match.reasons.length > 0 ? (
            <ul className="space-y-1.5">
              {match.reasons.map((reason, index) => (
                <li
                  key={`${index}-${reason}`}
                  className="flex gap-2 text-[11px] leading-4 text-slate-300"
                >
                  <CheckCircle2
                    size={12}
                    className="mt-0.5 shrink-0 text-emerald-300"
                  />
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[11px] text-slate-500">
              No positive match signals were identified.
            </p>
          )}
        </div>

        {match.matched_required_skills.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-semibold text-emerald-300">
              Required skills matched
            </p>
            <p className="text-[11px] leading-4 text-slate-300">
              {match.matched_required_skills.join(", ")}
            </p>
          </div>
        )}

        {match.matched_preferred_skills.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-semibold text-blue-300">
              Preferred skills matched
            </p>
            <p className="text-[11px] leading-4 text-slate-300">
              {match.matched_preferred_skills.join(", ")}
            </p>
          </div>
        )}

        {match.missing_required_skills.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-semibold text-amber-200">
              Required skills not found in profile
            </p>
            <p className="text-[11px] leading-4 text-slate-300">
              {match.missing_required_skills.join(", ")}
            </p>
          </div>
        )}

        {match.hard_constraints.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-semibold text-rose-200">
              Potential hard constraints
            </p>
            <p className="text-[11px] leading-4 text-slate-300">
              {match.hard_constraints.join(" · ")}
            </p>
          </div>
        )}

        {match.concerns.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-semibold text-amber-200">
              Things to check
            </p>
            <ul className="space-y-1">
              {match.concerns.map((concern, index) => (
                <li
                  key={`${index}-${concern}`}
                  className="text-[11px] leading-4 text-slate-400"
                >
                  {concern}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

export function SearchableFilter({
  label,
  value,
  placeholder,
  options,
  allOptionLabel,
  onChange,
}: {
  label: string;
  value: string;
  placeholder: string;
  options: FilterOption[];
  allOptionLabel: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);

  const normalizedValue = value.trim().toLocaleLowerCase();
  const exactOptionExists = options.some(
    (option) => option.value.toLocaleLowerCase() === normalizedValue,
  );

  // Typing narrows the list. But once a value is chosen (or the box is empty) show every option,
  // otherwise the list would only ever show the company that is already selected.
  const filteredOptions =
    !normalizedValue || exactOptionExists
      ? options
      : options.filter(
          (option) =>
            option.label.toLocaleLowerCase().includes(normalizedValue) ||
            option.value.toLocaleLowerCase().includes(normalizedValue),
        );

  return (
    <div className="relative min-w-0">
      <label className="sr-only">{label}</label>

      <div className="relative">
        <input
          className="field pr-9"
          value={value}
          placeholder={placeholder}
          autoComplete="off"
          aria-label={label}
          aria-autocomplete="list"
          aria-expanded={open}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            window.setTimeout(() => setOpen(false), 140);
          }}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
          }}
        />

        <button
          type="button"
          className="absolute inset-y-0 right-0 grid w-9 place-items-center text-slate-500 hover:text-slate-200"
          aria-label={`Show ${label.toLowerCase()} options`}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => setOpen((current) => !current)}
        >
          <ChevronDown size={15} />
        </button>
      </div>

      {open && (
        <div
          role="listbox"
          className="absolute left-0 top-[calc(100%+6px)] z-50 max-h-64 w-full min-w-[240px] overflow-y-auto rounded-xl border border-slate-700 bg-[#0d1423] p-1.5 shadow-2xl"
        >
          <button
            type="button"
            role="option"
            aria-selected={value === ""}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              onChange("");
              setOpen(false);
            }}
            className={`flex w-full items-start justify-between gap-2 rounded-lg px-3 py-2.5 text-left text-[11px] transition ${
              value === ""
                ? "bg-blue-400/[0.1] text-blue-200"
                : "text-slate-300 hover:bg-white/[0.05]"
            }`}
          >
            <span>{allOptionLabel}</span>
            <span className="text-[10px] text-slate-500">Clear filter</span>
          </button>

          {filteredOptions.map((option) => (
            <button
              type="button"
              role="option"
              aria-selected={value === option.value}
              key={option.value}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
              className={`flex w-full items-start justify-between gap-3 rounded-lg px-3 py-2.5 text-left transition ${
                value === option.value
                  ? "bg-blue-400/[0.1] text-blue-200"
                  : "text-slate-300 hover:bg-white/[0.05]"
              }`}
            >
              <span className="min-w-0 flex-1 truncate">
                {option.label}
              </span>
              {option.meta && (
                <span className="shrink-0 text-[10px] text-slate-500">
                  {option.meta}
                </span>
              )}
            </button>
          ))}

          {value.trim() && !exactOptionExists && (
            <button
              type="button"
              role="option"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => setOpen(false)}
              className="mt-1 flex w-full items-center gap-2 rounded-lg border-t border-slate-700/60 px-3 py-2.5 text-left text-[10px] text-blue-200 hover:bg-white/[0.04]"
            >
              <Search size={12} />
              Use typed filter: “{value.trim()}”
            </button>
          )}

          {filteredOptions.length === 0 && !value.trim() && (
            <p className="px-3 py-3 text-[11px] text-slate-500">
              No options available yet.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div className="relative grid h-10 w-10 place-items-center overflow-hidden rounded-[14px] border border-blue-300/25 bg-gradient-to-br from-blue-500 via-indigo-500 to-violet-600 shadow-[0_7px_25px_rgba(73,105,241,0.28)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_25%_10%,rgba(255,255,255,0.42),transparent_55%)]" />
        <Command className="relative h-5 w-5 text-white" strokeWidth={2.3} />
      </div>

      <div>
        <p className="text-[16px] font-bold tracking-[-0.035em] text-white">
          JobPilot<span className="text-blue-400">.</span>
        </p>
        <p className="mt-0.5 text-[9px] font-semibold tracking-[0.21em] text-slate-500">
          CAREER INTELLIGENCE
        </p>
      </div>
    </div>
  );
}

export function StatusPill({ status }: { status: ApiStatus }) {
  const connected = status === "connected";
  const checking = status === "checking";

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-medium ${
        connected
          ? "border-emerald-400/15 bg-emerald-400/[0.07] text-emerald-300"
          : checking
            ? "border-amber-300/15 bg-amber-300/[0.06] text-amber-200"
            : "border-rose-400/20 bg-rose-400/[0.07] text-rose-300"
      }`}
    >
      {checking ? (
        <LoaderCircle className="loading-ring h-3 w-3" />
      ) : (
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            connected ? "bg-emerald-400" : "bg-rose-400"
          }`}
        />
      )}
      {connected ? "API connected" : checking ? "Connecting" : "API offline"}
    </span>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  right,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  right?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && (
          <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-blue-300">
            {eyebrow}
          </p>
        )}
        <h2 className="text-xl font-semibold tracking-[-0.04em] text-slate-100">
          {title}
        </h2>
        {description && (
          <p className="mt-1.5 max-w-2xl text-[12px] leading-5 text-slate-400">
            {description}
          </p>
        )}
      </div>
      {right}
    </div>
  );
}

export function MetricCard({
  label,
  value,
  caption,
  icon: Icon,
  iconStyle,
  delay = 0,
}: {
  label: string;
  value: string | number;
  caption: string;
  icon: LucideIcon;
  iconStyle: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.36, delay }}
      whileHover={{ y: -3 }}
      className="panel panel-hover rounded-2xl p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-[12px] font-medium text-slate-400">{label}</p>
        <div className={`grid h-9 w-9 place-items-center rounded-xl ${iconStyle}`}>
          <Icon size={17} strokeWidth={1.8} />
        </div>
      </div>
      <p className="mt-5 text-[29px] font-semibold tracking-[-0.055em] text-white">
        {value}
      </p>
      <p className="mt-1.5 text-[11px] text-slate-500">{caption}</p>
    </motion.div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  message,
}: {
  icon: LucideIcon;
  title: string;
  message: string;
}) {
  return (
    <div className="flex min-h-44 flex-col items-center justify-center px-6 py-8 text-center">
      <div className="mb-3 grid h-11 w-11 place-items-center rounded-2xl border border-slate-700/70 bg-slate-800/50 text-slate-400">
        <Icon size={19} />
      </div>
      <p className="text-sm font-medium text-slate-200">{title}</p>
      <p className="mt-1.5 max-w-sm text-xs leading-5 text-slate-500">
        {message}
      </p>
    </div>
  );
}

export function CompensationBadge({ compensation }: { compensation?: JobCompensation }) {
  if (!compensation) return null;
  const formatRange = () => {
    if (compensation.min_lpa === null || compensation.max_lpa === null) return "Pay not disclosed";
    if (compensation.min_lpa === compensation.max_lpa) return `₹${compensation.min_lpa} LPA`;
    return `₹${compensation.min_lpa}–${compensation.max_lpa} LPA`;
  };
  const label = compensation.status === "target_30_plus"
    ? `₹30+ LPA listed · ${formatRange()}`
    : compensation.status === "target_25_plus"
      ? `₹25+ LPA listed · ${formatRange()}`
      : compensation.status === "target_possible"
        ? `Range overlaps ₹25+ · ${formatRange()}`
        : compensation.status === "below_target"
          ? `Below ₹${compensation.target_floor_lpa}+ target`
          : "Pay not disclosed · verify";
  const tone = compensation.status === "target_30_plus"
    ? "border-emerald-400/25 bg-emerald-400/[0.09] text-emerald-200"
    : compensation.status === "target_25_plus"
      ? "border-emerald-400/15 bg-emerald-400/[0.04] text-emerald-100"
      : compensation.status === "target_possible"
        ? "border-amber-300/20 bg-amber-300/[0.06] text-amber-100"
        : "border-slate-700 bg-slate-800/50 text-slate-400";
  return <span className={`inline-flex rounded-full border px-2 py-1 text-[9px] ${tone}`}>{label}</span>;
}


export function JobMiniCard({
  job,
  onTailor,
}: {
  job: Job;
  onTailor: (job: Job) => void;
}) {
  return (
    <div className="group flex flex-wrap items-center justify-between gap-3 border-b border-slate-700/40 py-4 last:border-0">
      <div className="flex min-w-0 items-start gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-slate-700/60 bg-slate-800/70 text-slate-300">
          <Building2 size={17} />
        </div>
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold text-slate-100">
            {job.title}
          </p>
          <p className="mt-1 text-[11px] text-slate-400">
            {job.company?.name || "Unknown company"}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-500">
            {job.location && (
              <span className="inline-flex items-center gap-1">
                <MapPin size={11} />
                {job.location}
              </span>
            )}
            {job.experience_level && (
              <span className="inline-flex items-center gap-1">
                <Clock3 size={11} />
                {job.experience_level}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <CompensationBadge compensation={job.compensation} />
        <MatchBadge match={job.match} />
        <button
          className="secondary-button shrink-0 !px-3 !py-2"
          onClick={() => onTailor(job)}
        >
          Tailor resume
          <ArrowRight size={13} />
        </button>
      </div>
    </div>
  );
}
