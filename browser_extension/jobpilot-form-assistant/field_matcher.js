/*
 * JobPilot field matcher: the pure rules that decide which profile value (if any) belongs in
 * an application-form field. It has no DOM access, no network access and cannot click or
 * submit anything, so it can be tested in Node and is injected into the employer page before
 * the fill step runs.
 *
 * Only clearly labelled fields are matched. Sensitive demographic questions (gender, race,
 * disability, date of birth, ...) are deliberately NOT matched and are always left to you.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.JobPilotMatcher = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const IGNORED_TYPES = [
    "hidden",
    "submit",
    "button",
    "reset",
    "file",
    "checkbox",
    "radio",
    "password",
  ];

  function normalize(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  }

  // `text` is the already-normalized label text of the control, `type` its normalized
  // type attribute and `tagName` its upper-case tag name. Returns a profile key or null.
  function classifyField(text, type, tagName) {
    if (IGNORED_TYPES.includes(type)) return null;

    if (/\b(first name|given name|forename)\b/.test(text)) return "first_name";
    if (/\b(last name|family name|surname)\b/.test(text)) return "last_name";

    if (/\b(full name|applicant name|your name|legal name)\b/.test(text) || type === "name") {
      return "full_name";
    }

    if (type === "email" || /\b(e mail|email address|email)\b/.test(text)) return "email";

    if (
      type === "tel" ||
      /\b(phone number|mobile number|telephone number|phone|mobile)\b/.test(text)
    ) {
      return "phone";
    }

    if (/linkedin/.test(text)) return "linkedin_url";
    if (/github/.test(text)) return "github_url";

    if (/\b(portfolio|personal website|personal site)\b/.test(text)) return "portfolio_url";

    if (/\b(current employer|current company|employer name)\b/.test(text)) return "current_employer";

    if (/\b(current job title|current title|current position|current role)\b/.test(text)) {
      return "current_title";
    }

    if (
      /\b(years of experience|years experience|total experience|relevant experience)\b/.test(text)
    ) {
      return "years_experience";
    }

    if (/\b(notice period|availability to start|when can you start)\b/.test(text)) {
      return "notice_period";
    }

    if (
      /\b(work authorization|authorized to work|legally authorized|right to work)\b/.test(text)
    ) {
      return "work_authorization";
    }

    if (
      /\b(sponsorship|visa sponsorship)\b/.test(text) &&
      /\b(require|need|requirement|future|now or in the future|visa)\b/.test(text)
    ) {
      return "requires_sponsorship";
    }

    if (
      /\b(salary expectation|expected salary|salary expectations|compensation expectation|desired compensation)\b/.test(
        text
      )
    ) {
      return "salary_expectation";
    }

    if (tagName === "TEXTAREA" && /\bcover letter\b/.test(text)) return "cover_letter";

    if (/\b(current location|city of residence|current city|city state country)\b/.test(text)) {
      return "current_location";
    }

    return null;
  }

  // Splits a full name into first and last name ("A B C" -> "A B" and "C").
  function splitName(fullName) {
    const full = String(fullName || "").trim();
    const parts = full.split(/\s+/).filter(Boolean);
    return {
      full,
      first: parts.length > 1 ? parts.slice(0, -1).join(" ") : full,
      last: parts.length > 1 ? parts[parts.length - 1] : "",
    };
  }

  // Chooses the value of the dropdown option matching `value`, or null when none matches.
  // `options` is [{ value, text }]. The empty placeholder option is never chosen. A
  // sponsorship yes/no answer also matches wordings such as "I will not require sponsorship".
  function pickSelectOption(options, value, kind) {
    const target = normalize(value);
    const usable = (options || []).filter((option) => option.value !== "");

    let choice = usable.find(
      (option) => normalize(option.text) === target || normalize(option.value) === target
    );

    if (!choice && kind === "requires_sponsorship") {
      const wantsYes = target === "yes";
      const wantsNo = target === "no";
      if (wantsYes || wantsNo) {
        choice = usable.find((option) => {
          const optionText = normalize(`${option.text} ${option.value}`);
          if (wantsYes) {
            return (
              /\b(yes|i will require|require sponsorship)\b/.test(optionText) &&
              !/\b(no|not require|will not)\b/.test(optionText)
            );
          }
          return /\b(no|i will not require|do not require|not require sponsorship)\b/.test(optionText);
        });
      }
    }

    return choice ? choice.value : null;
  }

  // Recognises the portals JobPilot has a tested adapter for from the page address.
  // Anything else still works field-by-field, but is reported as an unrecognised portal.
  const PORTALS = [
    { id: "greenhouse", name: "Greenhouse", host: /(^|\.)greenhouse\.io$/ },
    { id: "lever", name: "Lever", host: /(^|\.)lever\.co$/ },
    { id: "ashby", name: "Ashby", host: /(^|\.)ashbyhq\.com$/ },
    { id: "smartrecruiters", name: "SmartRecruiters", host: /(^|\.)smartrecruiters\.com$/ },
    {
      id: "workday",
      name: "Workday",
      host: /(^|\.)myworkdayjobs\.com$/,
      note: "Workday asks you to sign in or create an account. Do that yourself; JobPilot never does.",
    },
    { id: "oracle", name: "Oracle Recruiting", host: /(^|\.)oraclecloud\.com$/ },
  ];

  function detectPortal(url) {
    let hostname = "";
    try {
      hostname = new URL(String(url)).hostname.toLowerCase();
    } catch {
      return { id: "unknown", name: "Unrecognised portal", recognised: false, note: null };
    }
    const match = PORTALS.find((portal) => portal.host.test(hostname));
    if (!match) {
      return {
        id: "unknown",
        name: "Unrecognised portal",
        recognised: false,
        note: "This site has no dedicated adapter; only clearly labelled fields are filled. Check everything.",
      };
    }
    return { id: match.id, name: match.name, recognised: true, note: match.note || null };
  }

  return { IGNORED_TYPES, normalize, classifyField, splitName, pickSelectOption, detectPortal };
});
