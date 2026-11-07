import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const popupPath = path.join(here, 'browser_extension', 'jobpilot-form-assistant', 'popup.js');
const source = fs.readFileSync(popupPath, 'utf8');

class FakeElement {
  constructor(id = '') {
    this.id = id;
    this.value = '';
    this.textContent = '';
    this.className = '';
    this.disabled = false;
    this.checked = false;
    this.options = [];
    this.children = [];
    this.listeners = {};
    this.classList = {
      add: (...names) => { this._classes = new Set([...(this._classes || []), ...names]); },
      remove: (...names) => { for (const name of names) this._classes?.delete(name); },
      toggle: (name, force) => {
        this._classes ||= new Set();
        if (force === undefined ? !this._classes.has(name) : force) this._classes.add(name);
        else this._classes.delete(name);
      },
    };
  }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  replaceChildren(...children) { this.children = [...children]; }
  append(...children) { this.children.push(...children); }
}

async function runCase(initialStatus, shouldConfirm) {
  const ids = [
    'applicationSelect', 'jobMeta', 'blockerSummary', 'refreshBtn',
    'openPostingBtn', 'overwriteExisting', 'fillBtn', 'markAppliedBtn',
    'actionStatus', 'questionCount', 'questionsList',
  ];
  const elements = Object.fromEntries(ids.map((id) => [id, new FakeElement(id)]));
  const calls = [];
  let confirmCalls = 0;
  let currentStatus = initialStatus;

  const app = {
    id: 42,
    status: currentStatus,
    applied_at: null,
    job: {
      id: 7,
      title: 'Software Engineer',
      company: 'Example Co',
      location: 'Hyderabad',
      url: 'https://jobs.example.com/role/7',
    },
  };

  const preparation = () => ({
    application_id: 42,
    application_status: currentStatus,
    profile: {},
    cover_letter_draft: '',
    custom_questions: [],
    blockers: [],
    job: { ...app.job, description_available: true, is_active: true },
  });

  const fetch = async (url, options = {}) => {
    calls.push({ url, options });
    let body;
    if (url.endsWith('/api/applications?limit=100&offset=0')) {
      body = { items: [{ ...app, status: currentStatus }], total: 1 };
    } else if (url.endsWith('/api/applications/42/preparation')) {
      body = preparation();
    } else if (url.endsWith('/api/applications/42') && options.method === 'PATCH') {
      assert.equal(JSON.parse(options.body).status, 'applied');
      currentStatus = 'applied';
      app.status = 'applied';
      app.applied_at = '2026-11-06T03:00:00Z';
      body = { ...app };
    } else {
      throw new Error(`Unexpected fetch: ${url} ${options.method || 'GET'}`);
    }
    return { ok: true, status: 200, json: async () => body };
  };

  const document = {
    getElementById: (id) => elements[id],
    createElement: () => new FakeElement(),
  };
  const sandbox = {
    document,
    fetch,
    URL,
    window: { confirm: () => { confirmCalls += 1; return shouldConfirm; } },
    chrome: { tabs: { query: async () => [], create: async () => ({}) }, scripting: { executeScript: async () => [] } },
    navigator: { clipboard: { writeText: async () => {} } },
    console,
  };

  vm.runInNewContext(source, sandbox, { filename: popupPath });
  await new Promise((resolve) => setTimeout(resolve, 0));

  const button = elements.markAppliedBtn;
  if (initialStatus === 'ready_to_apply') {
    assert.equal(button.disabled, false, 'ready application should enable confirmation');
  } else {
    assert.equal(button.disabled, true, 'non-ready application must not enable confirmation');
  }

  await button.listeners.click();
  const patchCalls = calls.filter((call) => call.options.method === 'PATCH');

  if (initialStatus === 'ready_to_apply' && shouldConfirm) {
    assert.equal(confirmCalls, 1);
    assert.equal(patchCalls.length, 1);
    assert.equal(currentStatus, 'applied');
    assert.equal(button.disabled, true, 'button must disable after recording');
    assert.match(elements.actionStatus.textContent, /Submission recorded as Applied/);
    return 'PASS - explicit confirmation records applied status and timestamp';
  }

  assert.equal(patchCalls.length, 0, 'no PATCH should occur without readiness and explicit confirmation');
  if (initialStatus === 'ready_to_apply' && !shouldConfirm) {
    assert.equal(confirmCalls, 1);
    return 'PASS - cancelled confirmation makes no application status change';
  }
  assert.equal(confirmCalls, 0, 'non-ready application must be rejected before confirmation dialog');
  return 'PASS - non-ready application cannot be marked applied from extension';
}

console.log(await runCase('ready_to_apply', true));
console.log(await runCase('ready_to_apply', false));
console.log(await runCase('preparing', true));
