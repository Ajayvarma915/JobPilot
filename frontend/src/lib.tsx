import { API_BASE } from "./config";
import { type ApiError, type JobMatch } from "./types";

const numberFormat = new Intl.NumberFormat("en-IN");

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }

  return numberFormat.format(value);
}

export function compactText(value: string | null | undefined): string {
  return (value || "").replace(/\s+/g, " ").trim();
}

function parseSkills(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

export function errorText(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "An unexpected error occurred.";
}

export function categoryLabel(category: string): string {
  return category.replaceAll("_", " ");
}

export function makeResumeRequest(
  jobTitle: string,
  jobDescription: string,
  requiredSkills: string,
  preferredSkills: string,
) {
  return {
    job_title: jobTitle.trim(),
    job_description: jobDescription.trim(),
    required_skills: parseSkills(requiredSkills),
    preferred_skills: parseSkills(preferredSkills),
    max_projects: 3,
  };
}

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);

  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;

  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
    });
  } catch {
    throw new Error(
      `Unable to reach the JobPilot API at ${API_BASE}. Check that the backend is running.`,
    );
  }

  const rawText = await response.text();
  let data: unknown = {};

  if (rawText) {
    try {
      data = JSON.parse(rawText);
    } catch {
      data = { detail: rawText };
    }
  }

  if (!response.ok) {
    const detail = (data as ApiError)?.detail;

    throw new Error(
      typeof detail === "string"
        ? detail
        : `API request failed with HTTP ${response.status}.`,
    );
  }

  return data as T;
}

export function recommendationTone(
  recommendation: JobMatch["recommendation"],
): string {
  switch (recommendation) {
    case "strong_match":
      return "border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-200";
    case "good_match":
      return "border-blue-400/20 bg-blue-400/[0.08] text-blue-200";
    case "review":
      return "border-amber-300/20 bg-amber-300/[0.08] text-amber-100";
    default:
      return "border-rose-400/20 bg-rose-400/[0.08] text-rose-200";
  }
}
