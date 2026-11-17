// Tests for the extension's pure field matcher and static safety checks on its source.
// Run from the project root:  node scripts/test_extension_field_matcher.mjs
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const matcher = require("../browser_extension/jobpilot-form-assistant/field_matcher.js");
const popupSource = readFileSync("browser_extension/jobpilot-form-assistant/popup.js", "utf8");
const matcherSource = readFileSync("browser_extension/jobpilot-form-assistant/field_matcher.js", "utf8");
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
const kind = (label, type = "", tag = "INPUT") =>
  matcher.classifyField(matcher.normalize(label), matcher.normalize(type), tag);

test("labels typical of Greenhouse, Lever and Workday forms map to the right profile field", () => {
  const cases = [
    // Greenhouse
    ["First Name", "first_name"], ["Last Name", "last_name"], ["Email", "email"], ["Phone", "phone"],
    ["LinkedIn Profile", "linkedin_url"], ["Website", null],
    ["Are you legally authorized to work in India?", "work_authorization"],
    ["Will you now or in the future require sponsorship?", "requires_sponsorship"],
    // Lever
    ["Full name", "full_name"], ["Current company", "current_employer"], ["LinkedIn URL", "linkedin_url"],
    ["GitHub URL", "github_url"], ["Portfolio URL", "portfolio_url"], ["Additional information", null],
    // Workday style
    ["Legal Name First Name", "first_name"], ["Mobile Phone Number", "phone"], ["City of residence", "current_location"],
    // Generic profile questions
    ["Notice period", "notice_period"], ["Total experience", "years_experience"],
    ["Expected salary", "salary_expectation"], ["Current job title", "current_title"],
  ];
  for (const [label, expected] of cases) equal(kind(label), expected, label);
});

test("sensitive and open-ended questions are never matched", () => {
  for (const label of [
    "Gender", "Race", "Ethnicity", "Disability status", "Veteran status", "Date of birth", "Pronouns",
    "Why do you want to work here?", "How did you hear about us?", "Referral", "Address line 1", "Postal code",
  ]) {
    equal(kind(label), null, label);
  }
});

test("the field type alone can identify email, phone and name, but ignored types never match", () => {
  equal(kind("", "email"), "email", "type=email");
  equal(kind("", "tel"), "phone", "type=tel");
  equal(kind("", "name"), "full_name", "type=name");
  for (const type of matcher.IGNORED_TYPES) equal(kind("Email address", type), null, `type=${type}`);
  equal(kind("Cover letter", "", "TEXTAREA"), "cover_letter", "cover letter textarea");
  equal(kind("Cover letter", "text", "INPUT"), null, "a cover letter text input is not a letter box");
});

test("names are split into first and last name", () => {
  equal(matcher.splitName("Asha Rao"), { full: "Asha Rao", first: "Asha", last: "Rao" }, "two parts");
  equal(matcher.splitName("  Asha Kumari Rao "), { full: "Asha Kumari Rao", first: "Asha Kumari", last: "Rao" }, "three parts");
  equal(matcher.splitName("Asha"), { full: "Asha", first: "Asha", last: "" }, "one part");
  equal(matcher.splitName(""), { full: "", first: "", last: "" }, "empty");
});

test("dropdown choice never picks the placeholder and maps sponsorship yes/no", () => {
  const options = [
    { value: "", text: "Select..." },
    { value: "y", text: "Yes, I will require sponsorship" },
    { value: "n", text: "No, I will not require sponsorship" },
  ];
  equal(matcher.pickSelectOption(options, "no", "requires_sponsorship"), "n", "no");
  equal(matcher.pickSelectOption(options, "yes", "requires_sponsorship"), "y", "yes");
  equal(matcher.pickSelectOption(options, "maybe", "requires_sponsorship"), null, "unknown answer");
  equal(matcher.pickSelectOption(options, "", "work_authorization"), null, "empty value must not select the placeholder");
  equal(matcher.pickSelectOption([{ value: "in", text: "India" }], "india", "current_location"), "in", "exact text match");
  equal(matcher.pickSelectOption([{ value: "in", text: "India" }], "Japan", "current_location"), null, "no match");
});

test("portals are recognised from the address and unknown ones are reported as such", () => {
  const urls = {
    "https://job-boards.greenhouse.io/acme/jobs/1": "greenhouse",
    "https://jobs.lever.co/acme/123/apply": "lever",
    "https://jobs.ashbyhq.com/acme/abc": "ashby",
    "https://jobs.smartrecruiters.com/Acme/1": "smartrecruiters",
    "https://acme.wd5.myworkdayjobs.com/External/job/x": "workday",
    "https://x.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience": "oracle",
  };
  for (const [url, id] of Object.entries(urls)) equal(matcher.detectPortal(url).id, id, url);
  const unknown = matcher.detectPortal("https://careers.example.com/apply");
  equal([unknown.id, unknown.recognised], ["unknown", false], "unknown portal");
  equal(matcher.detectPortal("https://evil-greenhouse.io.example.com/x").recognised, false, "look-alike hosts are not recognised");
  equal(matcher.detectPortal("not a url").recognised, false, "garbage input");
  if (!matcher.detectPortal("https://a.myworkdayjobs.com/x").note.includes("never does")) throw new Error("Workday note missing");
});

test("nothing in the extension code can click, submit or upload", () => {
  for (const [name, source] of [["popup.js", popupSource], ["field_matcher.js", matcherSource]]) {
    // Strip comments so documentation about the safety rules does not trigger the check.
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
    for (const forbidden of [/\.click\(\)/, /\.submit\(/, /requestSubmit/, /dispatchEvent\(new (Mouse|Pointer)Event/, /\.files\s*=/, /DataTransfer/]) {
      if (forbidden.test(code)) throw new Error(`${name} contains ${forbidden}`);
    }
  }
  if (/\b(fetch|XMLHttpRequest|WebSocket|sendBeacon)\b/.test(matcherSource.replace(/\/\*[\s\S]*?\*\//g, ""))) {
    throw new Error("field_matcher.js must not make network requests");
  }
  if (!/submitted:\s*false/.test(popupSource)) throw new Error("the fill result must report submitted: false");
  if (!/window\.confirm\(/.test(popupSource)) throw new Error("marking an application as applied must ask for confirmation");
});

test("the manifest stays minimal and the matcher is injected as a packaged file", () => {
  equal(manifest.manifest_version, 3, "manifest version");
  equal([...manifest.permissions].sort(), ["activeTab", "scripting"], "permissions");
  equal(manifest.host_permissions, ["http://127.0.0.1:8000/*"], "host permissions");
  if (!/files:\s*\["field_matcher\.js"\]/.test(popupSource)) throw new Error("popup.js must inject field_matcher.js");
});

console.log(`\nTests: ${failed === 0 ? "all passed" : `${failed} failed`}`);
process.exit(failed === 0 ? 0 : 1);
