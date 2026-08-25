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
const caseRightNode = document.getElementById("case-right");
const rightSummaryNode = document.getElementById("right-summary");
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

function localDateString() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function targetName(targetId) {
  const target = currentState?.targets?.find((item) => item.id === targetId);
  return target?.name ?? `Target #${targetId}`;
}

function renderRights(rights) {
  const selected = caseRightNode.value;
  clearNode(caseRightNode);
  for (const right of rights) {
    const option = document.createElement("option");
    option.value = right.id;
    option.textContent = `${right.article} · ${right.title}`;
    caseRightNode.appendChild(option);
  }
  if (rights.some((right) => right.id === selected)) caseRightNode.value = selected;
  renderRightSummary();
}

function renderRightSummary() {
  const right = currentState?.rights?.find((item) => item.id === caseRightNode.value);
  rightSummaryNode.textContent = right?.summary ?? "";
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

function makeDateAction(label, action) {
  const wrapper = document.createElement("div");
  wrapper.className = "date-action";
  const input = document.createElement("input");
  input.type = "date";
  input.value = localDateString();
  const button = makeButton(label, () => action(input.value));
  wrapper.append(input, button);
  return wrapper;
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
    detail.textContent = `Case #${caseItem.id} · ${caseItem.article ?? "Legacy"} · ${caseItem.rightTitle} · ${caseItem.status}`;
    info.append(title, detail);

    if (caseItem.effectiveDueOn) {
      const due = document.createElement("small");
      due.textContent = `Tracked deadline: ${caseItem.effectiveDueOn}${caseItem.extensionNotifiedOn ? " · extension recorded" : ""}`;
      info.appendChild(due);
    }

    const actions = document.createElement("div");
    actions.className = "record-actions";
    actions.appendChild(makeButton("Timeline", () => loadTimeline(caseItem.id)));

    if (caseItem.status === "DRAFT" && caseItem.right !== "UNSPECIFIED") {
      actions.appendChild(
        makeDateAction("Record submission", (value) => submitCase(caseItem.id, value)),
      );
      actions.appendChild(makeButton("Cancel", () => transitionCase(caseItem.id, "CANCELLED")));
    } else if (caseItem.status === "AWAITING_RESPONSE") {
      if (!caseItem.extensionNotifiedOn) {
        actions.appendChild(
          makeDateAction("Record extension", (value) => recordExtension(caseItem.id, value)),
        );
      }
      actions.appendChild(makeButton("Complete", () => transitionCase(caseItem.id, "COMPLETED")));
      actions.appendChild(makeButton("Cancel", () => transitionCase(caseItem.id, "CANCELLED")));
    }

    row.append(info, actions);
    caseListNode.appendChild(row);
  }
}

function renderState(state) {
  currentState = state;
  milestoneNode.textContent = state.milestone ?? "M3";
  identifierCountNode.textContent = String(state.identity?.identifierCount ?? 0);
  targetCountNode.textContent = String(state.targets?.length ?? 0);
  caseCountNode.textContent = String(state.cases?.length ?? 0);
  displayNameNode.value = state.identity?.displayName ?? "";
  renderRights(state.rights ?? []);
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
  if (!backend || !caseRightNode.value) return;
  backend.createCase(targetId, caseRightNode.value, (response) => {
    handleMutation(response, "Draft GDPR case created locally.");
  });
}

function submitCase(caseId, receivedOn) {
  if (!backend || !receivedOn) return;
  backend.submitCase(caseId, receivedOn, (response) => {
    handleMutation(response, "Submission recorded and deadline calculated.");
    if (response?.ok) loadTimeline(caseId);
  });
}

function recordExtension(caseId, notifiedOn) {
  if (!backend || !notifiedOn) return;
  backend.recordCaseExtension(caseId, notifiedOn, (response) => {
    handleMutation(response, "Extension notice recorded.");
    if (response?.ok) loadTimeline(caseId);
  });
}

function transitionCase(caseId, targetStatus) {
  if (!backend) return;
  backend.transitionCase(caseId, targetStatus, (response) => {
    handleMutation(response, `Case moved to ${targetStatus}.`);
    if (response?.ok) loadTimeline(caseId);
  });
}

function eventTitle(event) {
  if (event.type === "CREATED") return "Case created";
  if (event.type === "REQUEST_SUBMITTED") return "Request submission recorded";
  if (event.type === "EXTENSION_RECORDED") return "Deadline extension recorded";
  return `${event.fromStatus} → ${event.toStatus}`;
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
      title.textContent = eventTitle(event);
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

caseRightNode.addEventListener("change", renderRightSummary);

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
