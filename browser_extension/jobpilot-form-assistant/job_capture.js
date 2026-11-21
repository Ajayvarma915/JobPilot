// Reads ONE job posting from the page you are looking at, so it can be saved in JobPilot.
//
// Pure rules (no clicking, no typing, no submitting, no network): extractJobPosting() works on plain
// values and is tested in Node. captureFromDocument() only reads what the page already shows
// (its structured "JobPosting" data, headings and visible text) and hands the result back to the popup.
(function (root) {
  "use strict";

  const MAX_DESCRIPTION = 12000;

  function clean(value) {
    return String(value == null ? "" : value).replace(/\s+/g, " ").trim();
  }

  function htmlToText(html) {
    return String(html || "")
      .replace(/<(br|\/p|\/div|\/li|\/h[1-6]|\/tr)\s*\/?>/gi, "\n")
      .replace(/<[^>]+>/g, " ")
      .replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/[ \t]+/g, " ")
      .replace(/\n\s*\n\s*\n+/g, "\n\n")
      .trim();
  }

  function* walk(node) {
    if (Array.isArray(node)) {
      for (const item of node) yield* walk(item);
    } else if (node && typeof node === "object") {
      yield node;
      if (Array.isArray(node["@graph"])) yield* walk(node["@graph"]);
    }
  }

  function typeIncludes(node, wanted) {
    const type = node && node["@type"];
    return Array.isArray(type) ? type.includes(wanted) : type === wanted;
  }

  function jobPostingFromJsonLd(blocks) {
    for (const block of blocks || []) {
      let data;
      try {
        data = typeof block === "string" ? JSON.parse(block) : block;
      } catch (error) {
        continue;
      }
      for (const node of walk(data)) {
        if (!typeIncludes(node, "JobPosting")) continue;
        const org = node.hiringOrganization;
        const places = [].concat(node.jobLocation || []);
        const locations = places
          .map((place) => {
            const address = (place && place.address) || {};
            return typeof address === "string"
              ? address
              : [address.addressLocality, address.addressRegion, address.addressCountry].filter(Boolean).join(", ");
          })
          .filter(Boolean);
        if (String(node.jobLocationType || "").toUpperCase() === "TELECOMMUTE") locations.push("Remote");
        const identifier = node.identifier;
        return {
          title: clean(node.title),
          company: clean(org && typeof org === "object" ? org.name : org),
          location: locations,
          description: htmlToText(node.description).slice(0, MAX_DESCRIPTION),
          external_id: clean(identifier && typeof identifier === "object" ? identifier.value : identifier),
        };
      }
    }
    return null;
  }

  function companyFromTitle(pageTitle) {
    // "Software Engineer | Acme", "Software Engineer - Acme Careers", "Acme Careers: Software Engineer"
    const parts = clean(pageTitle).split(/\s+[|\-–—]\s+/).map((part) => part.replace(/\b(careers?|jobs?)\b/gi, "").trim()).filter(Boolean);
    return parts.length > 1 ? parts[parts.length - 1] : "";
  }

  function companyFromHost(hostname) {
    const labels = String(hostname || "").toLowerCase().replace(/^www\./, "").split(".");
    const generic = new Set(["greenhouse", "lever", "ashbyhq", "myworkdayjobs", "smartrecruiters", "icims", "workable", "jobs", "careers"]);
    const label = labels.length >= 2 ? labels[labels.length - 2] : labels[0];
    if (!label || generic.has(label)) return "";
    return label.charAt(0).toUpperCase() + label.slice(1);
  }

  // input: { url, jsonLd: [string|object], title, heading, siteName, text }
  function extractJobPosting(input) {
    const url = clean(input && input.url);
    const structured = jobPostingFromJsonLd(input && input.jsonLd);
    if (structured && structured.title && structured.company) {
      return { ok: true, confidence: "structured", job: { ...structured, url } };
    }
    const title = clean((structured && structured.title) || (input && input.heading) || clean(input && input.title).split(/\s+[|\-–—]\s+/)[0]);
    let host = "";
    try {
      host = new URL(url).hostname;
    } catch (error) {
      host = "";
    }
    const company = clean(
      (structured && structured.company) || (input && input.siteName) || companyFromTitle(input && input.title) || companyFromHost(host),
    );
    if (!title || !company) {
      return { ok: false, reason: "This page does not show a job title and a company clearly. Open the job's own page and try again." };
    }
    return {
      ok: true,
      confidence: "page_text",
      job: {
        title,
        company,
        location: (structured && structured.location) || [],
        description: clean((structured && structured.description) || (input && input.text)).slice(0, MAX_DESCRIPTION) || title,
        external_id: (structured && structured.external_id) || "",
        url,
      },
    };
  }

  // Runs inside the page (injected by the popup). Reads only; changes nothing.
  function captureFromDocument() {
    const meta = (name) => {
      const node = document.querySelector(`meta[property="${name}"], meta[name="${name}"]`);
      return node ? node.getAttribute("content") || "" : "";
    };
    const jsonLd = Array.from(document.querySelectorAll('script[type="application/ld+json"]')).map((node) => node.textContent || "");
    const heading = document.querySelector("h1");
    return extractJobPosting({
      url: location.href,
      jsonLd,
      title: document.title,
      heading: heading ? heading.innerText : "",
      siteName: meta("og:site_name"),
      text: (document.body && document.body.innerText ? document.body.innerText : "").slice(0, MAX_DESCRIPTION),
    });
  }

  const api = { extractJobPosting, captureFromDocument, jobPostingFromJsonLd, htmlToText };
  root.JobPilotJobCapture = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
