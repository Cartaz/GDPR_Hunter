// Case-owned, ephemeral form drafts. Persisted correspondence remains Python-owned.
export function createResponsePanel({ getBackend, getState, targetName, setStatus, handleMutation, localDateString, makeButton, clearNode }) {
  const node = (id) => document.getElementById(id);
  const form = node("response-form");
  const fields = ["channel", "received-on", "sender", "subject", "body"];
  const drafts = new Map();
  const pending = new Set();
  let selectedCaseId = null;
  let listGeneration = 0;
  let detailGeneration = 0;

  const readDraft = () => Object.fromEntries(fields.map((name) => [name, node(`response-${name}`).value]));
  function restoreDraft(caseId) {
    const draft = drafts.get(caseId) ?? { channel: "EMAIL", "received-on": localDateString() };
    for (const field of fields) node(`response-${field}`).value = draft[field] ?? "";
    form.querySelector("button[type='submit']").disabled = pending.has(caseId);
  }

  function clearDetail() {
    detailGeneration += 1;
    node("response-detail-title").textContent = "No response selected";
    node("response-detail-empty").hidden = false;
    node("response-detail").hidden = true;
    node("response-detail-meta").textContent = "";
    for (const field of ["sender", "subject", "body"]) node(`response-detail-${field}`).value = "";
  }

  function openResponse(caseId, responseId) {
    if (selectedCaseId !== caseId) return;
    clearDetail();
    const generation = detailGeneration;
    getBackend().getCaseResponse(responseId, (response) => {
      if (selectedCaseId !== caseId || generation !== detailGeneration) return;
      if (response?.error) return setStatus(response.error.message, true);
      if (response.caseId !== caseId || response.id !== responseId) return;
      node("response-detail-title").textContent = `Case #${caseId} · Response #${response.id}`;
      node("response-detail-empty").hidden = true;
      node("response-detail").hidden = false;
      node("response-detail-meta").textContent = `${response.channel} · received ${response.receivedOn} · recorded ${response.recordedAt}`;
      for (const field of ["sender", "subject", "body"]) node(`response-detail-${field}`).value = response[field] ?? "";
    });
  }

  function open(caseId) {
    const backend = getBackend();
    if (!backend) return;
    const caseItem = getState()?.cases?.find((item) => item.id === caseId);
    const nextId = caseItem?.receivedOn ? caseId : null;
    if (selectedCaseId !== nextId) {
      if (selectedCaseId !== null) drafts.set(selectedCaseId, readDraft());
      selectedCaseId = nextId;
      clearDetail();
      clearNode(node("response-list"));
      restoreDraft(nextId);
    }
    const generation = ++listGeneration;
    node("response-panel-title").textContent = nextId ? `Case #${caseId} · ${targetName(caseItem.targetId)}` : "Select a submitted case";
    node("response-panel-empty").hidden = nextId !== null;
    node("response-panel").hidden = nextId === null;
    if (nextId === null) return;
    form.hidden = caseItem.status !== "AWAITING_RESPONSE";
    backend.listCaseResponses(caseId, (response) => {
      if (generation !== listGeneration || selectedCaseId !== caseId) return;
      if (response?.error) return setStatus(response.error.message, true);
      const list = node("response-list");
      clearNode(list);
      if (!response.length) {
        const empty = document.createElement("p");
        empty.textContent = "No controller responses recorded for this Case.";
        empty.className = "muted empty-state";
        list.appendChild(empty);
      }
      for (const summary of response) {
        const row = document.createElement("div");
        row.className = "record";
        const info = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = `Response #${summary.id} · ${summary.channel}`;
        const detail = document.createElement("small");
        detail.textContent = `Received ${summary.receivedOn} · recorded ${summary.recordedAt}`;
        info.append(title, detail);
        row.append(info, makeButton("Open", () => openResponse(caseId, summary.id)));
        list.appendChild(row);
      }
    });
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const backend = getBackend();
    const caseId = selectedCaseId;
    if (!backend || !caseId || pending.has(caseId)) return;
    const draft = readDraft();
    const confirmed = window.confirm(`Record this response against Case #${caseId} exactly as entered? This encrypts it locally; it does not classify compliance, change deadlines, or complete the Case.`);
    if (!confirmed) return;
    pending.add(caseId);
    drafts.set(caseId, draft);
    form.querySelector("button[type='submit']").disabled = true;
    backend.recordCaseResponse(caseId, draft.channel, draft["received-on"], draft.sender, draft.subject, draft.body, true, (response) => {
      pending.delete(caseId);
      handleMutation(response, `Response for Case #${caseId} encrypted and recorded locally.`);
      const latest = selectedCaseId === caseId ? readDraft() : drafts.get(caseId);
      if (response?.ok && JSON.stringify(latest) === JSON.stringify(draft)) {
        drafts.delete(caseId);
        if (selectedCaseId === caseId) {
          restoreDraft(caseId);
          clearDetail();
        }
      }
      if (selectedCaseId === caseId) {
        form.querySelector("button[type='submit']").disabled = false;
        open(caseId);
      }
    });
  });

  return { open, refresh: () => { if (selectedCaseId !== null) open(selectedCaseId); } };
}
