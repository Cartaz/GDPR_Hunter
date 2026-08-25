const statusNode = document.getElementById("status");
const milestoneNode = document.getElementById("milestone");
const identifierCountNode = document.getElementById("identifier-count");
const targetCountNode = document.getElementById("target-count");
const caseCountNode = document.getElementById("case-count");
const displayNameNode = document.getElementById("display-name");
const nameForm = document.getElementById("name-form");
const targetForm = document.getElementById("target-form");
const targetNameNode = document.getElementById("target-name");
const targetDomainNode = document.getElementById("target-domain");
const privacyEmailNode = document.getElementById("privacy-email");
const targetListNode = document.getElementById("target-list");
const caseListNode = document.getElementById("case-list");
const timelineTitleNode = document.getElementById("timeline-title");
const timelineListNode = document.getElementById("timeline-list");

let backend = null;
let currentState = null;

function setStatus(message, isError = false) {
  statusNode.textContent = message;
  statusNode.classList.toggle("error", isError);
}

function clearNode(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function makeButton(label, action) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "action-button";
  button.textContent = label;
  button.addEventListener("click", action);
  return button;
}

function targetName(targetId) {
  const target = currentState?.targets?.find((item) => item.id === targetId);
  return target?.name ?? `Target #${targetId}`;
}

function renderTargets(targets) {
  clearNode(targetListNode);
  if (!targets.length) {
    const empty = document.createElement("p");
    empty.className = "muted empty-state";
    empty.textContent = "No targets registered yet.";
    targetListNode.appendChild(empty);
    return;
  }

  for (const target of targets) {
    const row = document.createElement("div");
    row.className = "record";

    const info = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = target.name;
    const detail = document.createElement("small");
    detail.textContent = target.domain ?? target.privacyEmail ?? "No public contact recorded";
    info.append(title, detail);

    row.append(info, makeButton("New case", () => createCase(target.id)));
    targetListNode.appendChild(row);
  }
}

function nextCaseActions(caseItem) {
  if (caseItem.status === "DRAFT") return [["Open", "OPEN"], ["Cancel", "CANCELLED"]];
  if (caseItem.status === "OPEN") return [["Complete", "COMPLETED"], ["Cancel", "CANCELLED"]];
  return [];
}

function renderCases(cases) {
  clearNode(caseListNode);
  if (!cases.length) {
    const empty = document.createElement("p");
    empty.className = "muted empty-state";
    empty.textContent = "No cases created yet.";
    caseListNode.appendChild(empty);
    return;
  }

  for (const caseItem of cases) {
    const row = document.createElement("div");
    row.className = "record case-record";

    const info = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = targetName(caseItem.targetId);
    const detail = document.createElement("small");
    detail.textContent = `Case #${caseItem.id} · ${caseItem.status}`;
    info.append(title, detail);

    const actions = document.createElement("div");
    actions.className = "record-actions";
    actions.appendChild(makeButton("Timeline", () => loadTimeline(caseItem.id)));
    for (const [label, status] of nextCaseActions(caseItem)) {
      actions.appendChild(makeButton(label, () => transitionCase(caseItem.id, status)));
    }

    row.append(info, actions);
    caseListNode.appendChild(row);
  }
}

function renderState(state) {
  currentState = state;
  milestoneNode.textContent = state.milestone ?? "M2";
  identifierCountNode.textContent = String(state.identity?.identifierCount ?? 0);
  targetCountNode.textContent = String(state.targets?.length ?? 0);
  caseCountNode.textContent = String(state.cases?.length ?? 0);
  displayNameNode.value = state.identity?.displayName ?? "";
  renderTargets(state.targets ?? []);
  renderCases(state.cases ?? []);
}

function handleMutation(response, successMessage) {
  if (response?.ok) {
    setStatus(successMessage);
  } else if (response?.error?.message) {
    setStatus(response.error.message, true);
  }
}

function createCase(targetId) {
  if (!backend) return;
  backend.createCase(targetId, (response) => handleMutation(response, "Draft case created locally."));
}

function transitionCase(caseId, targetStatus) {
  if (!backend) return;
  backend.transitionCase(caseId, targetStatus, (response) => {
    handleMutation(response, `Case moved to ${targetStatus}.`);
    if (response?.ok) loadTimeline(caseId);
  });
}

function loadTimeline(caseId) {
  if (!backend) return;
  backend.getCaseTimeline(caseId, (response) => {
    if (response?.error) {
      setStatus(response.error.message, true);
      return;
    }
    timelineTitleNode.textContent = `Case #${caseId}`;
    clearNode(timelineListNode);
    for (const event of response) {
      const row = document.createElement("div");
      row.className = "timeline-event";
      const title = document.createElement("strong");
      title.textContent = event.type === "CREATED" ? "Case created" : `${event.fromStatus} → ${event.toStatus}`;
      const time = document.createElement("small");
      time.textContent = event.createdAt;
      row.append(title, time);
      timelineListNode.appendChild(row);
    }
  });
}

function connectBackend() {
  if (typeof qt === "undefined" || typeof QWebChannel === "undefined") {
    setStatus("Native backend is unavailable.", true);
    return;
  }

  new QWebChannel(qt.webChannelTransport, (channel) => {
    backend = channel.objects.backend;
    backend.getBootstrapState((state) => renderState(state));
    backend.stateChanged.connect((state) => renderState(state));
    backend.operationFailed.connect((_code, message) => setStatus(message, true));
  });
}

nameForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!backend) return;
  backend.setDisplayName(displayNameNode.value, (response) => handleMutation(response, "Profile saved locally."));
});

targetForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!backend) return;
  backend.createTarget(targetNameNode.value, targetDomainNode.value, privacyEmailNode.value, (response) => {
    handleMutation(response, "Target added locally.");
    if (response?.ok) targetForm.reset();
  });
});

connectBackend();
