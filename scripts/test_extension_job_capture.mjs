// Tests for the extension's "Save this job" reader (pure rules) and static safety checks.
// Run from the project root:  node scripts/test_extension_job_capture.mjs
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const capture = require("../browser_extension/jobpilot-form-assistant/job_capture.js");
const source = readFileSync("browser_extension/jobpilot-form-assistant/job_capture.js", "utf8");
const popup = readFileSync("browser_extension/jobpilot-form-assistant/popup.js", "utf8");
const manifest = JSON.parse(readFileSync("browser_extension/jobpilot-form-assistant/manifest.json", "utf8"));

let failed = 0;
function test(name, fn) {
  try {
    fn();
    console.log(`PASS - ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL - ${name}: ${error.message}`);
  }
}
function equal(actual, expected, message) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

const posting = {
  "@context": "https://schema.org",
  "@type": "JobPosting",
  title: "Associate Engineer",
  description: "<p>Build <b>chips</b></p><ul><li>Python</li></ul>",
  hiringOrganization: { "@type": "Organization", name: "Qualcomm India Private Limited" },
  jobLocation: { "@type": "Place", address: { addressLocality: "Bangalore", addressRegion: "KA", addressCountry: "IN" } },
  identifier: { "@type": "PropertyValue", value: "3098178" },
};

test("structured JobPosting data is preferred and read completely", () => {
  const result = capture.extractJobPosting({ url: "https://careers.example.com/job/1", jsonLd: [JSON.stringify(posting)], title: "ignored", heading: "ignored" });
  equal(result.ok, true, "ok");
  equal(result.confidence, "structured", "confidence");
  equal(result.job.title, "Associate Engineer", "title");
  equal(result.job.company, "Qualcomm India Private Limited", "company is passed as written; the server tidies the name");
  equal(result.job.location, ["Bangalore, KA, IN"], "location");
  equal(result.job.external_id, "3098178", "id");
  equal(result.job.description.includes("Build chips") && result.job.description.includes("Python"), true, "description text");
});

test("JobPosting inside an @graph, an array, or marked remote is still found", () => {
  const graph = { "@graph": [{ "@type": "WebSite" }, { ...posting, "@type": ["JobPosting"], jobLocationType: "TELECOMMUTE" }] };
  const result = capture.extractJobPosting({ url: "https://x.example/job", jsonLd: [JSON.stringify([{ "@type": "Thing" }, graph])] });
  equal(result.ok && result.job.location.includes("Remote"), true, "remote flag read from the graph");
});

test("without structured data it falls back to the heading, site name and page text, and says so", () => {
  const result = capture.extractJobPosting({
    url: "https://jobs.acme.example/openings/42",
    jsonLd: ["not json at all", "{}"],
    title: "Backend Engineer | Acme Careers",
    heading: "Backend Engineer",
    siteName: "Acme",
    text: "We are hiring a backend engineer. Minimum 1 year of experience.",
  });
  equal(result.ok, true, "ok");
  equal(result.confidence, "page_text", "the popup warns the user to check it");
  equal([result.job.title, result.job.company], ["Backend Engineer", "Acme"], "title and company");
});

test("company comes from the page title or the host when the page does not name it", () => {
  const fromTitle = capture.extractJobPosting({ url: "https://careers.example.org/j/1", jsonLd: [], title: "Software Engineer - Initech Careers", heading: "Software Engineer", text: "x" });
  equal(fromTitle.job.company, "Initech", "title suffix");
  const fromHost = capture.extractJobPosting({ url: "https://www.globex.com/careers/7", jsonLd: [], title: "Platform Engineer", heading: "Platform Engineer", text: "x" });
  equal(fromHost.job.company, "Globex", "host name");
  const atsHost = capture.extractJobPosting({ url: "https://boards.greenhouse.io/x/jobs/1", jsonLd: [], title: "Engineer", heading: "Engineer", text: "x" });
  equal(atsHost.ok, false, "an ATS host says nothing about the company, so it asks for a clearer page");
});

test("a page with no job on it is refused with a readable reason", () => {
  const result = capture.extractJobPosting({ url: "https://news.example.com/", jsonLd: [], title: "", heading: "", text: "" });
  equal(result.ok, false, "refused");
  equal(typeof result.reason, "string", "reason");
});

test("long descriptions are cut to a safe size", () => {
  const result = capture.extractJobPosting({ url: "https://a.example/job", jsonLd: [JSON.stringify({ ...posting, description: "word ".repeat(10000) })] });
  equal(result.job.description.length <= 12000, true, "bounded");
});

test("the reader only reads: no clicks, typing, submitting or network calls", () => {
  for (const forbidden of [".click(", ".submit(", "dispatchEvent", "fetch(", "XMLHttpRequest", ".value =", "form.submit", "sendBeacon"]) {
    equal(source.includes(forbidden), false, `job_capture.js must not contain ${forbidden}`);
  }
});

test("the popup sends the job only to the local API and adds no extra permissions", () => {
  equal(popup.includes("/api/jobs/import-page"), true, "uses the local endpoint");
  equal(manifest.permissions, ["activeTab", "scripting"], "permissions unchanged");
  equal(manifest.host_permissions, ["http://127.0.0.1:8000/*"], "host permissions unchanged");
});

if (failed) {
  console.log(`\n${failed} test(s) failed`);
  process.exit(1);
}
console.log("\nAll extension job-capture tests passed.");
