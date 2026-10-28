const API_BASE = "http://127.0.0.1:8000";

const elements = {
  select: document.getElementById("applicationSelect"),
  jobMeta: document.getElementById("jobMeta"),
  blockerSummary: document.getElementById("blockerSummary"),
  refreshBtn: document.getElementById("refreshBtn"),
  openPostingBtn: document.getElementById("openPostingBtn"),
  overwriteExisting: document.getElementById("overwriteExisting"),
  fillBtn: document.getElementById("fillBtn"),
  actionStatus: document.getElementById("actionStatus"),
  questionCount: document.getElementById("questionCount"),
  questionsList: document.getElementById("questionsList"),
};

let applications = [];
let selectedPreparation = null;
let selectedApplication = null;

function setStatus(message, type = "") {
  elements.actionStatus.textContent = message;
  elements.actionStatus.className = `status ${type}`.trim();
}

function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:"
      ? url.href
      : null;
  } catch {
    return null;
  }
}

async function apiRequest(path) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });

  const body = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : JSON.stringify(
            body.detail || body || `HTTP ${response.status}`
          );

    throw new Error(detail);
  }

  return body;
}

function createOption(value, text) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = text;
  return option;
}

function renderQuestions(questions) {
  elements.questionsList.replaceChildren();

  const validQuestions = Array.isArray(questions) ? questions : [];
  elements.questionCount.textContent = String(validQuestions.length);

  if (validQuestions.length === 0) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent =
      "No custom questions saved for this application.";

    elements.questionsList.append(empty);
    return;
  }

  validQuestions.forEach((item, index) => {
    const card = document.createElement("div");
    card.className = "question";

    const title = document.createElement("div");
    title.className = "question-title";
    title.textContent = `${index + 1}. ${
      item.question || "Question not specified"
    }`;

    const answer = document.createElement("div");
    answer.className = "question-answer";
    answer.textContent = item.answer || "No answer saved yet.";

    const copyButton = document.createElement("button");
    copyButton.className = "copy-answer";
    copyButton.textContent = "Copy answer";
    copyButton.disabled = !(item.answer || "").trim();

    copyButton.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(item.answer);

        setStatus(
          "Answer copied. Review it before pasting into the employer form.",
          "success"
        );
      } catch {
        setStatus(
          "Could not copy the answer. Select and copy it manually.",
          "error"
        );
      }
    });

    card.append(title, answer, copyButton);
    elements.questionsList.append(card);
  });
}

function renderPreparation(prep) {
  selectedPreparation = prep;

  const job = prep?.job || {};

  const title = `${
    job.title || selectedApplication?.job?.title || "Role"
  } — ${
    job.company || selectedApplication?.job?.company || "Company"
  }`;

  elements.jobMeta.textContent =
    `${title}\n` +
    `${
      job.location ||
      selectedApplication?.job?.location ||
      "Location not specified"
    }\n` +
    `Status: ${
      prep.application_status ||
      selectedApplication?.status ||
      "unknown"
    }` +
    (
      prep.resume_filename
        ? `\nResume selected: ${prep.resume_filename}`
        : "\nNo resume selected yet"
    );

  const blockers = Array.isArray(prep.blockers)
    ? prep.blockers
    : [];

  elements.blockerSummary.classList.toggle(
    "hidden",
    blockers.length === 0
  );

  elements.blockerSummary.textContent = blockers.length
    ? `${blockers.length} preparation item(s) to resolve:\n• ${blockers.join("\n• ")}`
    : "Preparation packet checks passed. Review the values on the employer page before continuing.";

  const postingUrl = safeHttpUrl(
    job.url || selectedApplication?.job?.url
  );

  elements.openPostingBtn.disabled = !postingUrl;
  elements.fillBtn.disabled = !prep || !selectedApplication;

  renderQuestions(prep.custom_questions);
}

async function loadPreparation(applicationId) {
  selectedPreparation = null;

  selectedApplication =
    applications.find(
      (item) => String(item.id) === String(applicationId)
    ) || null;

  elements.fillBtn.disabled = true;
  elements.openPostingBtn.disabled = true;
  elements.blockerSummary.classList.add("hidden");
  elements.jobMeta.textContent = "Loading preparation packet…";

  renderQuestions([]);

  if (!selectedApplication) return;

  try {
    const prep = await apiRequest(
      `/api/applications/${Number(applicationId)}/preparation`
    );

    renderPreparation(prep);

    setStatus(
      "Preparation packet loaded from your local JobPilot API.",
      "success"
    );
  } catch (error) {
    elements.jobMeta.textContent =
      "Could not load this preparation packet.";

    setStatus(`API error: ${error.message}`, "error");
  }
}

async function loadApplications(preferredId = "") {
  elements.refreshBtn.disabled = true;
  elements.select.disabled = true;

  setStatus("Connecting to local JobPilot API…");

  try {
    const result = await apiRequest(
      "/api/applications?limit=100&offset=0"
    );

    applications = Array.isArray(result.items)
      ? result.items
      : [];

    elements.select.replaceChildren();

    if (applications.length === 0) {
      elements.select.append(
        createOption("", "No tracked applications found")
      );

      selectedPreparation = null;
      selectedApplication = null;

      elements.jobMeta.textContent =
        "Track a job in JobPilot before preparing an employer application.";

      elements.fillBtn.disabled = true;
      elements.openPostingBtn.disabled = true;

      renderQuestions([]);
      setStatus("No tracked applications found.");

      return;
    }

    applications.forEach((application) => {
      const job = application.job || {};

      const label = `${
        job.company || "Company"
      } — ${
        job.title || "Untitled role"
      } (${application.status || "saved"})`;

      elements.select.append(
        createOption(String(application.id), label)
      );
    });

    const chosen =
      applications.find(
        (item) => String(item.id) === String(preferredId)
      ) || applications[0];

    elements.select.value = String(chosen.id);

    await loadPreparation(chosen.id);
  } catch (error) {
    elements.select.replaceChildren(
      createOption("", "JobPilot API unavailable")
    );

    elements.jobMeta.textContent =
      "Start the local FastAPI server and refresh this extension.";

    elements.fillBtn.disabled = true;
    elements.openPostingBtn.disabled = true;

    setStatus(
      `Can't reach ${API_BASE}: ${error.message}`,
      "error"
    );
  } finally {
    elements.refreshBtn.disabled = false;
    elements.select.disabled = false;
  }
}

function fillSupportedFields(
  profile,
  coverLetterDraft,
  overwriteExisting
) {
  // This function runs on the employer page.
  // It only fills clearly identified, supported fields.
  // It never clicks buttons, submits forms, uploads files,
  // or answers employer-specific questions automatically.

  const normalize = (value) =>
    String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();

  const isVisible = (element) => {
    if (!(element instanceof HTMLElement)) return false;

    const style = window.getComputedStyle(element);

    return (
      style.display !== "none" &&
      style.visibility !== "hidden" &&
      Number(style.opacity || 1) !== 0 &&
      element.getClientRects().length > 0
    );
  };

  const labelFor = (element) => {
    const values = [
      element.getAttribute("aria-label"),
      element.getAttribute("placeholder"),
      element.getAttribute("name"),
      element.id,
      element.getAttribute("autocomplete"),
      element.getAttribute("data-testid"),
    ].filter(Boolean);

    if (element.id) {
      const safeId =
        window.CSS && CSS.escape
          ? CSS.escape(element.id)
          : element.id.replace(/[^a-zA-Z0-9_-]/g, "");

      const label = document.querySelector(
        `label[for="${safeId}"]`
      );

      if (label) values.push(label.textContent || "");
    }

    const parentLabel = element.closest("label");

    if (parentLabel) {
      values.push(parentLabel.textContent || "");
    }

    return normalize(values.join(" "));
  };

  const profileValue = (key) =>
    String(profile?.[key] || "").trim();

  const fullName = profileValue("contact_name");
  const nameParts = fullName.split(/\s+/).filter(Boolean);

  const firstName =
    nameParts.length > 1
      ? nameParts.slice(0, -1).join(" ")
      : fullName;

  const lastName =
    nameParts.length > 1
      ? nameParts[nameParts.length - 1]
      : "";

  const answers = {
    first_name: firstName,
    last_name: lastName,
    full_name: fullName,
    email: profileValue("email"),
    phone: profileValue("phone"),
    current_location: profileValue("current_location"),
    linkedin_url: profileValue("linkedin_url"),
    github_url: profileValue("github_url"),
    portfolio_url: profileValue("portfolio_url"),
    current_employer: profileValue("current_employer"),
    current_title: profileValue("current_title"),
    years_experience: profileValue("years_experience"),
    notice_period: profileValue("notice_period"),
    work_authorization: profileValue("work_authorization"),
    requires_sponsorship: profileValue("requires_sponsorship"),
    salary_expectation: profileValue("salary_expectation"),
    cover_letter: String(coverLetterDraft || "").trim(),
  };

  const controls = Array.from(
    document.querySelectorAll("input, textarea, select")
  );

  const ignoredTypes = [
    "hidden",
    "submit",
    "button",
    "reset",
    "file",
    "checkbox",
    "radio",
    "password",
  ];

  const visibleControls = controls.filter((element) => {
    const type = normalize(element.getAttribute("type"));

    return (
      isVisible(element) &&
      !element.disabled &&
      !element.readOnly &&
      !ignoredTypes.includes(type)
    );
  });

  const formCount = Array.from(document.forms).filter(isVisible).length;

  const filled = [];
  const skippedExisting = [];
  const skippedUnsupported = [];
  const missingProfileValues = [];

  let recognizedFieldCount = 0;

  const classify = (element) => {
    const text = labelFor(element);
    const type = normalize(element.getAttribute("type"));

    if (ignoredTypes.includes(type)) return null;

    if (/\b(first name|given name|forename)\b/.test(text)) {
      return "first_name";
    }

    if (/\b(last name|family name|surname)\b/.test(text)) {
      return "last_name";
    }

    if (
      /\b(full name|applicant name|your name|legal name)\b/.test(text) ||
      type === "name"
    ) {
      return "full_name";
    }

    if (
      type === "email" ||
      /\b(e mail|email address|email)\b/.test(text)
    ) {
      return "email";
    }

    if (
      type === "tel" ||
      /\b(phone number|mobile number|telephone number|phone|mobile)\b/.test(text)
    ) {
      return "phone";
    }

    if (/linkedin/.test(text)) return "linkedin_url";
    if (/github/.test(text)) return "github_url";

    if (
      /\b(portfolio|personal website|personal site)\b/.test(text)
    ) {
      return "portfolio_url";
    }

    if (
      /\b(current employer|current company|employer name)\b/.test(text)
    ) {
      return "current_employer";
    }

    if (
      /\b(current job title|current title|current position|current role)\b/.test(text)
    ) {
      return "current_title";
    }

    if (
      /\b(years of experience|years experience|total experience|relevant experience)\b/.test(text)
    ) {
      return "years_experience";
    }

    if (
      /\b(notice period|availability to start|when can you start)\b/.test(text)
    ) {
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
      /\b(salary expectation|expected salary|salary expectations|compensation expectation|desired compensation)\b/.test(text)
    ) {
      return "salary_expectation";
    }

    if (
      element.tagName === "TEXTAREA" &&
      /\bcover letter\b/.test(text)
    ) {
      return "cover_letter";
    }

    if (
      /\b(current location|city of residence|current city|city state country)\b/.test(text)
    ) {
      return "current_location";
    }

    return null;
  };

  const setControlValue = (element, value, kind) => {
    if (element.tagName === "SELECT") {
      const target = normalize(value);

      const options = Array.from(element.options).filter(
        (option) => option.value !== ""
      );

      let choice = options.find(
        (option) =>
          normalize(option.textContent) === target ||
          normalize(option.value) === target
      );

      if (!choice && kind === "requires_sponsorship") {
        const wantsYes = target === "yes";
        const wantsNo = target === "no";

        if (wantsYes || wantsNo) {
          choice = options.find((option) => {
            const optionText = normalize(
              `${option.textContent} ${option.value}`
            );

            if (wantsYes) {
              return (
                /\b(yes|i will require|require sponsorship)\b/.test(
                  optionText
                ) &&
                !/\b(no|not require|will not)\b/.test(optionText)
              );
            }

            return /\b(no|i will not require|do not require|not require sponsorship)\b/.test(
              optionText
            );
          });
        }
      }

      if (!choice) return false;

      element.value = choice.value;
    } else {
      const prototype =
        element.tagName === "TEXTAREA"
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype;

      const descriptor = Object.getOwnPropertyDescriptor(
        prototype,
        "value"
      );

      if (descriptor?.set) {
        descriptor.set.call(element, value);
      } else {
        element.value = value;
      }
    }

    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));

    return true;
  };

  for (const element of controls) {
    if (
      !isVisible(element) ||
      element.disabled ||
      element.readOnly
    ) {
      continue;
    }

    const kind = classify(element);

    if (!kind) continue;

    recognizedFieldCount += 1;

    const value = answers[kind];

    if (!value) {
      missingProfileValues.push(kind);
      continue;
    }

    if (
      element.value &&
      String(element.value).trim() &&
      !overwriteExisting
    ) {
      skippedExisting.push(labelFor(element) || kind);
      continue;
    }

    const didFill = setControlValue(element, value, kind);

    if (didFill) {
      filled.push(labelFor(element) || kind);
    } else {
      skippedUnsupported.push(labelFor(element) || kind);
    }
  }

  return {
    filledCount: filled.length,
    filled,
    skippedExistingCount: skippedExisting.length,
    skippedExisting,
    unsupportedCount: skippedUnsupported.length,
    skippedUnsupported,
    recognizedFieldCount,
    visibleControlCount: visibleControls.length,
    formCount,
    pageTitle: document.title || "Untitled page",
    pageUrl: location.href,
    missingProfileValues: [...new Set(missingProfileValues)],
    customQuestionsLeftForManualReview: true,
    resumeUploadLeftForManualReview: true,
    submitted: false,
    note:
      "No form was submitted. Review every populated field and attach the resume manually.",
  };
}

async function fillCurrentTab() {
  if (!selectedPreparation || !selectedApplication) {
    setStatus("Select a tracked application first.", "error");
    return;
  }

  const [tab] = await chrome.tabs.query({
    active: true,
    lastFocusedWindow: true,
  });

  if (!tab?.id || !safeHttpUrl(tab.url)) {
    setStatus(
      "Open the employer's HTTP(S) application page in the active tab first.",
      "error"
    );
    return;
  }

  const currentUrl = new URL(tab.url);

  if (
    ["127.0.0.1", "localhost"].includes(currentUrl.hostname)
  ) {
    setStatus(
      "You're on the local JobPilot page. Open the employer application page in this tab, then click the extension again.",
      "error"
    );
    return;
  }

  elements.fillBtn.disabled = true;
  setStatus("Looking for clearly labelled fields…");

  try {
    const execution = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: fillSupportedFields,
      args: [
        selectedPreparation.profile || {},
        selectedPreparation.cover_letter_draft || "",
        elements.overwriteExisting.checked,
      ],
    });

    const result = execution?.[0]?.result;

    if (!result) {
      throw new Error("The page did not return a fill result.");
    }

    let message;
    let messageType = "success";

    if (result.filledCount > 0) {
      message =
        `${result.filledCount} field(s) filled. ` +
        `${result.skippedExistingCount} existing field(s) left unchanged. ` +
        `${result.unsupportedCount} field(s) could not be safely matched.\n` +
        result.note;
    } else if (
      result.recognizedFieldCount === 0 &&
      result.visibleControlCount === 0
    ) {
      message =
        "No editable form fields were found on this page. You're likely still on the job-description page. Click the employer's Apply button on the webpage, complete any sign-in step, and continue until the application form is visible. Then reopen this extension on that form page and try again. This extension will not submit the application.";

      messageType = "error";
    } else if (result.recognizedFieldCount === 0) {
      message =
        `Found ${result.visibleControlCount} visible form control(s), ` +
        "but none had labels the assistant can safely match. No fields were changed. " +
        "This employer may use custom controls or different labels; fill these fields manually for now.\n" +
        result.note;

      messageType = "error";
    } else if (
      result.skippedExistingCount > 0 &&
      result.skippedExistingCount === result.recognizedFieldCount
    ) {
      message =
        `The ${result.skippedExistingCount} supported field(s) found already contain values, so they were left unchanged. ` +
        "Enable “Overwrite fields that already contain text” only if you have checked that replacing them is appropriate.\n" +
        result.note;
    } else if (result.missingProfileValues?.length) {
      message =
        `Recognized ${result.recognizedFieldCount} supported field(s), but none could be filled. ` +
        "Add the missing value(s) to JobPilot Application prep and click Save preparation, then refresh this extension: " +
        `${result.missingProfileValues.join(", ")}.\n` +
        result.note;

      messageType = "error";
    } else {
      message =
        `Found ${result.recognizedFieldCount} potentially supported field(s), but couldn't safely fill them. ` +
        "No values were changed. Complete the remaining fields manually.\n" +
        result.note;

      messageType = "error";
    }

    setStatus(message, messageType);
  } catch (error) {
    setStatus(
      `Could not inspect this page: ${error.message}. Some portals block scripted field access; use the copy packet instead.`,
      "error"
    );
  } finally {
    elements.fillBtn.disabled = false;
  }
}

elements.select.addEventListener("change", () =>
  loadPreparation(elements.select.value)
);

elements.refreshBtn.addEventListener("click", () =>
  loadApplications(elements.select.value)
);

elements.openPostingBtn.addEventListener("click", async () => {
  const url = safeHttpUrl(
    selectedPreparation?.job?.url ||
    selectedApplication?.job?.url
  );

  if (!url) return;

  await chrome.tabs.create({ url });

  setStatus(
    "Employer posting opened. Navigate to its application form, then click the JobPilot extension icon in that tab.",
    "success"
  );
});

elements.fillBtn.addEventListener("click", fillCurrentTab);

loadApplications();