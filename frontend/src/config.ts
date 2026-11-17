export const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

// Optional API token for a protected deployment (backend variable JOBPILOT_API_TOKEN).
// A VITE_ value is compiled into the public JavaScript, so use it only for a private,
// single-user deployment. Browser download links cannot carry the token.
const API_TOKEN = import.meta.env.VITE_API_TOKEN as string | undefined;

if (API_TOKEN) {
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url.startsWith(API_BASE)) {
      const headers = new Headers(init?.headers);
      headers.set("Authorization", `Bearer ${API_TOKEN}`);
      return originalFetch(input, { ...init, headers });
    }
    return originalFetch(input, init);
  };
}
