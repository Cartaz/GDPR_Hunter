const statusNode = document.getElementById("status");
const milestoneNode = document.getElementById("milestone");
const investigationCountNode = document.getElementById("investigation-count");
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
const investigationForm = document.getElementById("investigation-form");
const investigationTitleNode = document.getElementById("investigation-title");
const investigationListNode = document.getElementById("investigation-list");
const investigationDetailNode = document.getElementById("investigation-detail");
const investigationDetailEmptyNode = document.getElementById("investigation-detail-empty");
const investigationDetailTitleNode = document.getElementById("investigation-detail-title");
const investigationDetailListNode = document.getElementById("investigation-detail-list");
const artifactForm = document.getElementById("artifact-form");
const artifactKindNode = document.getElementById("artifact-kind");
const artifactTextNode = document.getElementById("artifact-text");
const evidenceForm = document.getElementById("evidence-form");
const evidenceValueNode = document.getElementById("evidence-value");
const evidenceLocatorNode = document.getElementById("evidence-locator");
const claimForm = document.getElementById("claim-form");
const claimStatementNode = document.getElementById("claim-statement");

let backend = null;
let currentState = null;
let selectedInvestigationId = null;
let selectedInvestigationDetail = null;
let activeResearchArtifactId = null;

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

function renderInvestigations(investigations) {
  clearNode(investigationListNode);
  if (!investigations.length) {
    const empty = document.createElement("p");
    empty.className = "muted empty-state";
    empty.textContent = "No investigations created yet.";
    investigationListNode.appendChild(empty);
    return;
  }
  for (const investigation of investigations) {
    const row = document.createElement("div");
    row.className = "record";
    const info = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = investigation.title ?? `Investigation #${investigation.id}`;
    const detail = document.createElement("small");
    detail.textContent = `#${investigation.id} · ${investigation.status}`;
    info.append(title, detail);
    row.append(info, makeButton("Inspect", () => loadInvestigation(investigation.id)));
    investigationListNode.appendChild(row);
  }
}

function analyzeArtifact(artifactId) {
  if (!backend || !selectedInvestigationId) return;
  backend.analyzeArtifact(selectedInvestigationId, artifactId, (response) => {
    if (response?.ok) {
      const count = response.result?.createdCount ?? 0;
      setStatus(count ? `${count} deterministic evidence item(s) extracted.` : "Artifact already fully analyzed or no supported findings found.");
      loadInvestigation(selectedInvestigationId);
    } else if (response?.error?.message) {
      setStatus(response.error.message, true);
    }
  });
}

function researchArtifactUrls(artifactId) {
  if (!backend || !selectedInvestigationId || activeResearchArtifactId !== null) return;
  const approved = window.confirm(
    "Fetch the public URLs deterministically extracted from this artifact? Network access will be restricted by the research policy.",
  );
  if (!approved) return;
  backend.researchArtifactUrls(selectedInvestigationId, artifactId, approved, (response) => {
    if (response?.ok) setStatus("Public research started in the background.");
    else if (response?.error?.message) setStatus(response.error.message, true);
  });
}

function renderInvestigationDetail(detail) {
  selectedInvestigationDetail = detail;
  investigationDetailEmptyNode.hidden = true;
  investigationDetailNode.hidden = false;
  investigationDetailTitleNode.textContent = detail.investigation.title ?? `Investigation #${detail.investigation.id}`;
  clearNode(investigationDetailListNode);

  const summary = document.createElement("div");
  summary.className = "timeline-event";
  const summaryTitle = document.createElement("strong");
  summaryTitle.textContent = `${detail.artifacts.length} artifact(s) · ${detail.evidence.length} evidence item(s) · ${detail.claims.length} claim(s)`;
  const summaryStatus = document.createElement("small");
  summaryStatus.textContent = `State: ${detail.investigation.status}`;
  summary.append(summaryTitle, summaryStatus);
  investigationDetailListNode.appendChild(summary);

  for (const artifact of detail.artifacts) {
    const row = document.createElement("div");
    row.className = "record";
    const info = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = `Artifact #${artifact.id} · ${artifact.kind}`;
    const value = document.createElement("small");
    value.textContent = `${artifact.mediaType} · ${artifact.byteSize} bytes`;
    info.append(title, value);
    const actions = document.createElement("div");
    actions.className = "record-actions";
    actions.appendChild(makeButton("Analyze", () => analyzeArtifact(artifact.id)));
    const researchButton = makeButton("Research URLs", () => researchArtifactUrls(artifact.id));
    researchButton.disabled = activeResearchArtifactId !== null;
    actions.appendChild(researchButton);
    row.append(info, actions);
    investigationDetailListNode.appendChild(row);
  }

  for (const evidence of detail.evidence) {
    const row = document.createElement("div");
    row.className = "timeline-event";
    const title = document.createElement("strong");
    title.textContent = `Evidence #${evidence.id} · ${evidence.kind}`;
    const value = document.createElement("small");
    value.textContent = `${evidence.provenance} · ${evidence.value ?? evidence.sourceLocator ?? "No display value"}`;
    row.append(title, value);
    investigationDetailListNode.appendChild(row);
  }

  for (const claim of detail.claims) {
    const row = document.createElement("div");
    row.className = "timeline-event";
    const title = document.createElement("strong");
    title.textContent = `Claim #${claim.id} · ${claim.status}`;
    const statement = document.createElement("small");
    statement.textContent = `${claim.provenance} · ${claim.statement}`;
    row.append(title, statement);
    investigationDetailListNode.appendChild(row);
  }
}

function loadInvestigation(investigationId) {
  if (!backend) return;
  backend.getInvestigationDetail(investigationId, (response) => {
    if (response?.error) {
      setStatus(response.error.message, true);
      return;
    }
    selectedInvestigationId = investigationId;
    renderInvestigationDetail(response);
  });
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
      actions.appendChild(makeDateAction("Record submission", (value) => submitCase(caseItem.id, value)));
      actions.appendChild(makeButton("Cancel", () => transitionCase(caseItem.id, "CANCELLED")));
    } else if (caseItem.status === "AWAITING_RESPONSE") {
      if (!caseItem.extensionNotifiedOn) {
        actions.appendChild(makeDateAction("Record extension", (value) => recordExtension(caseItem.id, value)));
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
  milestoneNode.textContent = state.milestone ?? "M7";
  investigationCountNode.textContent = String(state.investigations?.length ?? 0);
  targetCountNode.textContent = String(state.targets?.length ?? 0);
  caseCountNode.textContent = String(state.cases?.length ?? 0);
  displayNameNode.value = state.identity?.displayName ?? "";
  renderInvestigations(state.investigations ?? []);
  renderRights(state.rights ?? []);
  renderTargets(state.targets ?? []);
  renderCases(state.cases ?? []);
  if (selectedInvestigationId) loadInvestigation(selectedInvestigationId);
}

function handleMutation(response, successMessage) {
  if (response?.ok) setStatus(successMessage);
  else if (response?.error?.message) setStatus(response.error.message, true);
}

function createCase(targetId) {
  if (!backend || !caseRightNode.value) return;
  backend.createCase(targetId, caseRightNode.value, (response) => handleMutation(response, "Draft GDPR case created locally."));
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
    backend.researchStarted.connect((_investigationId, artifactId) => {
      activeResearchArtifactId = artifactId;
      setStatus(`Researching public URLs from artifact #${artifactId}…`);
      if (selectedInvestigationId) loadInvestigation(selectedInvestigationId);
    });
    backend.researchCompleted.connect((investigationId, artifactId, result) => {
      activeResearchArtifactId = null;
      const count = result?.createdCount ?? 0;
      setStatus(count ? `${count} research evidence item(s) recorded.` : "Research completed with no new evidence.");
      if (selectedInvestigationId === investigationId) loadInvestigation(investigationId);
    });
    backend.researchFailed.connect((investigationId, _artifactId, _code, message) => {
      activeResearchArtifactId = null;
      setStatus(message, true);
      if (selectedInvestigationId === investigationId) loadInvestigation(investigationId);
    });
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

investigationForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!backend) return;
  backend.createInvestigation(investigationTitleNode.value, (response) => {
    handleMutation(response, "Investigation created locally.");
    if (response?.ok) {
      investigationForm.reset();
      selectedInvestigationId = response.result.id;
      loadInvestigation(selectedInvestigationId);
    }
  });
});

artifactForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!backend || !selectedInvestigationId) return;
  backend.importTextArtifact(selectedInvestigationId, artifactKindNode.value, "TRIGGER", artifactTextNode.value, (response) => {
    handleMutation(response, "Artifact encrypted and attached.");
    if (response?.ok) {
      artifactForm.reset();
      loadInvestigation(selectedInvestigationId);
    }
  });
});

evidenceForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!backend || !selectedInvestigationId) return;
  const artifacts = selectedInvestigationDetail?.artifacts ?? [];
  const artifactId = artifacts.length ? artifacts[artifacts.length - 1].id : 0;
  backend.addUserEvidence(
    selectedInvestigationId,
    artifactId,
    evidenceValueNode.value,
    evidenceLocatorNode.value,
    (response) => {
      handleMutation(response, "User-observed evidence recorded with provenance.");
      if (response?.ok) {
        evidenceForm.reset();
        loadInvestigation(selectedInvestigationId);
      }
    },
  );
});

claimForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!backend || !selectedInvestigationId) return;
  backend.createUserClaim(selectedInvestigationId, claimStatementNode.value, (response) => {
    handleMutation(response, "User hypothesis recorded.");
    if (response?.ok) {
      claimForm.reset();
      loadInvestigation(selectedInvestigationId);
    }
  });
});

connectBackend();