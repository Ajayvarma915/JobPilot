import { useCallback, useEffect, useState, type FormEvent } from "react";
import { LoaderCircle, Mail, Plus, Trash2, Users } from "lucide-react";
import { EmptyState, SectionHeading } from "../components";
import { apiRequest, errorText } from "../lib";

interface Contact {
  id: number;
  name: string;
  kind: "recruiter" | "referral" | "other";
  role_title: string | null;
  company_name: string | null;
  email: string | null;
  linkedin_url: string | null;
  referral_status: string;
  follow_up_date: string | null;
  notes: string | null;
}

interface Draft {
  id: number;
  body: string;
  warnings: string[];
  note: string;
  status: string;
}

const EMPTY = { name: "", kind: "recruiter", role_title: "", company_name: "", email: "", linkedin_url: "", notes: "" };

// Contacts you track (recruiters and referrals). JobPilot only drafts a message; you send it yourself.
export function NetworkView() {
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [reloadToken, setReloadToken] = useState(0);

  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    apiRequest<{ items: Contact[] }>("/api/contacts")
      .then((result) => {
        if (!cancelled) {
          setContacts(result.items);
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorText(caught));
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const addContact = (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    const body = Object.fromEntries(Object.entries(form).map(([key, value]) => [key, value.trim() || null]));
    apiRequest("/api/contacts", { method: "POST", body: JSON.stringify(body) })
      .then(() => {
        setForm(EMPTY);
        reload();
      })
      .catch((caught: unknown) => setError(errorText(caught)))
      .finally(() => setSaving(false));
  };

  const draftFor = (contact: Contact) =>
    apiRequest<Draft>(`/api/contacts/${contact.id}/outreach-draft`, { method: "POST", body: JSON.stringify({}) })
      .then((draft) => setDrafts((current) => ({ ...current, [contact.id]: draft })))
      .catch((caught: unknown) => setError(errorText(caught)));

  const markSent = (contact: Contact, draft: Draft) =>
    apiRequest(`/api/interactions/${draft.id}/mark-sent`, { method: "POST" })
      .then(() => setDrafts((current) => ({ ...current, [contact.id]: { ...draft, status: "sent_by_user" } })))
      .catch((caught: unknown) => setError(errorText(caught)));

  const remove = (contact: Contact) =>
    apiRequest(`/api/contacts/${contact.id}`, { method: "DELETE" })
      .then(reload)
      .catch((caught: unknown) => setError(errorText(caught)));

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Network"
        title="Recruiters and referrals"
        description="Keep track of the people who can help. JobPilot can draft a message from your verified facts, but it never sends anything: you copy it, edit it and send it yourself."
      />

      <form onSubmit={addContact} className="panel grid gap-3 rounded-2xl p-4 sm:grid-cols-2 sm:p-5">
        <input className="field" placeholder="Name" required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
        <select className="field" value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value })} aria-label="Kind">
          <option value="recruiter">Recruiter</option>
          <option value="referral">Referral</option>
          <option value="other">Other</option>
        </select>
        <input className="field" placeholder="Company" value={form.company_name} onChange={(event) => setForm({ ...form, company_name: event.target.value })} />
        <input className="field" placeholder="Role" value={form.role_title} onChange={(event) => setForm({ ...form, role_title: event.target.value })} />
        <input className="field" placeholder="Email (optional)" type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
        <input className="field" placeholder="LinkedIn link (optional)" value={form.linkedin_url} onChange={(event) => setForm({ ...form, linkedin_url: event.target.value })} />
        <textarea className="field sm:col-span-2" rows={2} placeholder="Notes" value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />
        <div className="sm:col-span-2">
          <button className="primary-button" type="submit" disabled={saving || !form.name.trim()}>
            {saving ? <LoaderCircle size={14} className="loading-ring" /> : <Plus size={14} />}
            Add contact
          </button>
        </div>
      </form>

      {error && <p className="text-xs text-rose-300">{error}</p>}

      {contacts && contacts.length === 0 && (
        <EmptyState icon={Users} title="No contacts yet" message="Add a recruiter or someone who can refer you above." />
      )}

      {contacts?.map((contact) => {
        const draft = drafts[contact.id];
        return (
          <article key={contact.id} className="panel rounded-2xl p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-slate-100">{contact.name}</h3>
                <p className="mt-1 text-[11px] text-slate-400">
                  {[contact.kind, contact.role_title, contact.company_name].filter(Boolean).join(" · ")}
                </p>
                {contact.notes && <p className="mt-2 text-[11px] text-slate-500">{contact.notes}</p>}
              </div>
              <div className="flex gap-2">
                <button className="secondary-button !px-3 !py-2" onClick={() => void draftFor(contact)}>
                  <Mail size={13} /> Draft message
                </button>
                <button className="secondary-button !px-3 !py-2" onClick={() => void remove(contact)} aria-label={`Delete ${contact.name}`}>
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
            {draft && (
              <div className="mt-3 rounded-xl border border-slate-700/60 bg-slate-900/40 p-3 text-xs text-slate-300">
                <p className="text-[11px] text-amber-200">{draft.note}</p>
                <textarea className="field mt-2 w-full" rows={7} readOnly value={draft.body} />
                {draft.warnings.map((warning) => (
                  <p key={warning} className="mt-1 text-[11px] text-amber-200">• {warning}</p>
                ))}
                <button className="secondary-button mt-2 !px-3 !py-2" disabled={draft.status === "sent_by_user"} onClick={() => void markSent(contact, draft)}>
                  {draft.status === "sent_by_user" ? "Marked as sent by you" : "I sent this myself"}
                </button>
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
