const statusNode = document.getElementById("status");
const milestoneNode = document.getElementById("milestone");
const investigationCountNode = document.getElementById("investigation-count");
const targetCountNode = document.getElementById("target-count");
const caseCountNode = document.getElementById("case-count");
const displayNameNode = document.getElementById("display-name");
const nameForm = document.getElementById("name-form");
const identifierForm = document.getElementById("identifier-form");
const identifierKindNode = document.getElementById("identifier-kind");
const identifierValueNode = document.getElementById("identifier-value");
const identifierLabelNode = document.getElementById("identifier-label");
const identifierListNode = document.getElementById("identifier-list");
const requestIdentifierOptionsNode = document.getElementById("request-identifier-options");
const targetForm = document.getElementById("target-form");
const targetNameNode = document.getElementById("target-name");
const targetDomainNode = document.getElementById("target-domain");
const privacyEmailNode = document.getElementById("privacy-email");
const targetListNode = document.getElementById("target-list");
const caseListNode = document.getElementById("case-list");
const caseRightNode = document.getElementById("case-right");
const caseErasureGroundNode = document.getElementById("case-erasure-ground");
const erasureGroundSummaryNode = document.getElementById("erasure-ground-summary");
const caseJurisdictionNode = document.getElementById("case-jurisdiction");
const rightSummaryNode = document.getElementById("right-summary");
const requestPreviewNode = document.getElementById("request-preview");
const requestPreviewTitleNode = document.getElementById("request-preview-title");
const requestPreviewRecipientNode = document.getElementById("request-preview-recipient");
const requestPreviewSubjectNode = document.getElementById("request-preview-subject");
const requestPreviewBodyNode = document.getElementById("request-preview-body");
const approveRequestButton = document.getElementById("approve-request-button");
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
const modelAnalysisButton = document.getElementById("model-analysis-button");
const modelProposalListNode = document.getElementById("model-proposal-list");

let backend = null;
let currentState = null;
let currentRequestPreviewContext = null;
let selectedInvestigationId = null;
let selectedInvestigationDetail = null;
let researchBusy = false;
let activeModelInvestigationId = null;
const proposalViews = new Map();

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

function selectedIdentifierIds() {
  const selected = [];
  for (const checkbox of requestIdentifierOptionsNode.querySelectorAll("input[type='checkbox']")) {
    if (checkbox.checked) selected.push(Number(checkbox.dataset.identifierId));
  }
  return selected.sort((left, right) => left - right);
}

function clearRequestPreview() {
  currentRequestPreviewContext = null;
  requestPreviewNode.hidden = true;
  requestPreviewTitleNode.textContent = "Request preview";
  requestPreviewRecipientNode.textContent = "";
  requestPreviewSubjectNode.value = "";
  requestPreviewBodyNode.value = "";
  approveRequestButton.disabled = true;
}

function renderRequestPreview(preview) {
  currentRequestPreviewContext = {
    caseId: preview.caseId,
    erasureGround: preview.erasureGround ?? "",
    identifierIds: [...(preview.identifierIds ?? [])],
  };
  requestPreviewTitleNode.textContent = `Request preview · ${preview.legalBasis}`;
  requestPreviewRecipientNode.textContent = preview.recipientEmail
    ? `To: ${preview.recipientName} <${preview.recipientEmail}>`
    : `To: ${preview.recipientName} · no privacy email registered`;
  requestPreviewSubjectNode.value = preview.subject;
  requestPreviewBodyNode.value = preview.body;
  approveRequestButton.disabled = !preview.recipientEmail;
  requestPreviewNode.hidden = false;
}

function renderIdentityIdentifiers(identifiers) {
  clearNode(identifierListNode);
  if (!identifiers.length) {
    const empty = document.createElement("p");
    empty.className = "muted empty-state";
    empty.textContent = "No identifiers stored yet.";
    identifierListNode.appendChild(empty);
    return;
  }
  for (const identifier of identifiers) {
    const row = document.createElement("div");
    row.className = "timeline-event";
    const title = document.createElement("strong");
    title.textContent = identifier.label
      ? `${identifier.kind} · ${identifier.label}`
      : identifier.kind;
    const value = document.createElement("small");
    value.textContent = identifier.value;
    row.append(title, value);
    identifierListNode.appendChild(row);
  }
}

function renderRequestIdentifierOptions(identifiers) {
  clearNode(requestIdentifierOptionsNode);
  if (!identifiers.length) {
    const empty = document.createElement("p");
    empty.className = "muted empty-state";
    empty.textContent = "No identifiers available. Add them in the Identity Vault if needed.";
    requestIdentifierOptionsNode.appendChild(empty);
    return;
  }
  for (const identifier of identifiers.filter((item) => item.active)) {
    const label = document.createElement("label");
    label.className = "identifier-check";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.dataset.identifierId = String(identifier.id);
    checkbox.addEventListener("change", clearRequestPreview);
    const text = document.createElement("span");
    text.textContent = identifier.label
      ? `${identifier.kind} · ${identifier.label}: ${identifier.value}`
      : `${identifier.kind}: ${identifier.value}`;
    label.append(checkbox, text);
    requestIdentifierOptionsNode.appendChild(label);
  }
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
  if (!backend || !selectedInvestigationId || researchBusy) return;
  const approved = window.confirm(
    "Fetch the public URLs deterministically extracted from this artifact? Network access will be restricted by the research policy.",
  );
  if (!approved) return;
  backend.researchArtifactUrls(selectedInvestigationId, artifactId, approved, (response) => {
    if (response?.ok) setStatus("Public research started in the background.");
    else if (response?.error?.message) setStatus(response.error.message, true);
  });
}

function requestModelAnalysis() {
  if (!backend || !selectedInvestigationId || activeModelInvestigationId !== null) return;
  const approved = window.confirm(
    "Send the bounded Evidence snapshot for this investigation to the configured inference endpoint and generate inert proposals for review?",
  );
  if (!approved) return;
  backend.analyzeInvestigationWithModel(selectedInvestigationId, approved, (response) => {
    if (response?.ok) setStatus("Model analysis started in the background.");
    else if (response?.error?.message) setStatus(response.error.message, true);
  });
}

function removeProposalView(investigationId, token) {
  const proposals = proposalViews.get(investigationId) ?? [];
  proposalViews.set(investigationId, proposals.filter((proposal) => proposal.token !== token));
  if (selectedInvestigationId === investigationId) renderModelProposals(investigationId);
}

function acceptModelClaim(investigationId, token) {
  if (!backend) return;
  const approved = window.confirm(
    "Accept this model proposal as a MODEL_INFERENCE hypothesis backed by its cited Evidence?",
  );
  if (!approved) return;
  backend.acceptModelClaim(token, approved, (response) => {
    if (response?.ok) {
      removeProposalView(investigationId, token);
      setStatus("Reviewed model claim accepted as a hypothesis.");
      loadInvestigation(investigationId);
    } else if (response?.error?.message) {
      setStatus(response.error.message, true);
    }
  });
}

function executeModelResearch(investigationId, token, evidenceId) {
  if (!backend || researchBusy) return;
  const approved = window.confirm(
    `Research the public URL stored in Evidence #${evidenceId}? The model cannot choose or modify the destination; Python will resolve it from persisted Evidence and enforce network policy.`,
  );
  if (!approved) return;
  backend.executeModelResearchProposal(token, approved, (response) => {
    if (response?.ok) {
      removeProposalView(investigationId, token);
      setStatus(`Reviewed research for Evidence #${evidenceId} started in the background.`);
    } else if (response?.error?.message) {
      setStatus(response.error.message, true);
    }
  });
}

function discardModelProposal(investigationId, token) {
  if (!backend) return;
  backend.discardModelProposal(token, (response) => {
    if (response?.ok) {
      removeProposalView(investigationId, token);
      setStatus("Model proposal discarded.");
    } else if (response?.error?.message) {
      setStatus(response.error.message, true);
    }
  });
}

function renderModelProposals(investigationId) {
  clearNode(modelProposalListNode);
  const proposals = proposalViews.get(investigationId) ?? [];
  if (!proposals.length) {
    const empty = document.createElement("p");
    empty.className = "muted empty-state";
    empty.textContent = "No model proposals awaiting review.";
    modelProposalListNode.appendChild(empty);
    return;
  }
  for (const proposal of proposals) {
    const row = document.createElement("div");
    row.className = "record";
    const info = document.createElement("div");
    const title = document.createElement("strong");
    const detail = document.createElement("small");
    if (proposal.kind === "CLAIM") {
      title.textContent = `Claim proposal · ${Math.round(proposal.confidence * 100)}% confidence`;
      detail.textContent = `${proposal.statement} · Evidence ${proposal.evidenceIds.join(", ")}`;
    } else {
      title.textContent = `Research proposal · Evidence #${proposal.evidenceId}`;
      detail.textContent = proposal.rationale;
    }
    info.append(title, detail);
    const actions = document.createElement("div");
    actions.className = "record-actions";
    if (proposal.kind === "CLAIM") {
      actions.appendChild(makeButton("Accept claim", () => acceptModelClaim(investigationId, proposal.token)));
    } else {
      const researchButton = makeButton(
        "Research evidence",
        () => executeModelResearch(investigationId, proposal.token, proposal.evidenceId),
      );
      researchButton.disabled = researchBusy;
      actions.appendChild(researchButton);
    }
    actions.appendChild(makeButton("Discard", () => discardModelProposal(investigationId, proposal.token)));
    row.append(info, actions);
    modelProposalListNode.appendChild(row);
  }
}

function renderInvestigationDetail(detail) {
  selectedInvestigationDetail = detail;
  investigationDetailEmptyNode.hidden = true;
  investigationDetailNode.hidden = false;
  investigationDetailTitleNode.textContent = detail.investigation.title ?? `Investigation #${detail.investigation.id}`;
  modelAnalysisButton.disabled = activeModelInvestigationId !== null;
  renderModelProposals(detail.investigation.id);
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
    researchButton.disabled = researchBusy;
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

function renderErasureGrounds(grounds) {
  const selected = caseErasureGroundNode.value;
  clearNode(caseErasureGroundNode);
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select an Article 17 ground";
  caseErasureGroundNode.appendChild(placeholder);
  for (const ground of grounds) {
    const option = document.createElement("option");
    option.value = ground.id;
    option.textContent = `${ground.article} · ${ground.title}`;
    caseErasureGroundNode.appendChild(option);
  }
  if (grounds.some((ground) => ground.id === selected)) caseErasureGroundNode.value = selected;
  renderErasureGroundSummary();
}

function renderErasureGroundSummary() {
  const ground = currentState?.erasureGrounds?.find((item) => item.id === caseErasureGroundNode.value);
  erasureGroundSummaryNode.textContent = ground
    ? `${ground.summary} It becomes part of an immutable payload only after explicit approval.`
    : "Used only for Article 17 requests. The selected ground becomes part of an approved payload only after explicit approval.";
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

function previewCaseRequest(caseItem) {
  if (!backend || caseItem.right === "UNSPECIFIED") return;
  const erasureGround = caseItem.right === "ERASURE" ? caseErasureGroundNode.value : "";
  if (caseItem.right === "ERASURE" && !erasureGround) {
    setStatus("Select the Article 17 ground before previewing an erasure request.", true);
    caseErasureGroundNode.focus();
    return;
  }
  const identifierIds = selectedIdentifierIds();
  backend.previewCaseRequest(caseItem.id, erasureGround, identifierIds, (response) => {
    if (response?.error) {
      setStatus(response.error.message, true);
      clearRequestPreview();
      return;
    }
    renderRequestPreview(response);
    setStatus("Deterministic request preview generated locally. Nothing has been sent.");
  });
}

function approveCurrentRequest() {
  if (!backend || !currentRequestPreviewContext) return;
  const approved = window.confirm(
    "Persist an encrypted, immutable copy of exactly this recipient, subject and body as the user-approved outbound payload? This does not send, queue or hand off the message.",
  );
  if (!approved) return;
  const context = currentRequestPreviewContext;
  backend.approveCaseRequest(
    context.caseId,
    context.erasureGround,
    context.identifierIds,
    approved,
    (response) => {
      if (response?.ok) {
        setStatus(`Approved payload #${response.result.id} persisted locally. Nothing has been sent.`);
      } else if (response?.error?.message) {
        setStatus(response.error.message, true);
      }
    },
  );
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
    const approvals = (currentState?.approvedRequests ?? []).filter((item) => item.caseId === caseItem.id);
    if (approvals.length) {
      const approval = approvals[0];
      const approvedDetail = document.createElement("small");
      approvedDetail.textContent = `Latest approved payload #${approval.id} · ${approval.approvedAt} · not sent`;
      info.appendChild(approvedDetail);
    }
    if (caseItem.effectiveDueOn) {
      const due = document.createElement("small");
      due.textContent = `Tracked deadline: ${caseItem.effectiveDueOn}${caseItem.extensionNotifiedOn ? " · extension recorded" : ""}`;
      info.appendChild(due);
    }
    if (caseItem.deadlineJurisdiction) {
      const jurisdiction = document.createElement("small");
      const reviewState = caseItem.publicHolidayReviewRequired
        ? "local/public-holiday review required"
        : "holiday calendar complete";
      jurisdiction.textContent = `Deadline jurisdiction: ${caseItem.deadlineJurisdiction} · ${reviewState}`;
      info.appendChild(jurisdiction);
      if (caseItem.holidayCalendarSource) {
        const source = document.createElement("small");
        source.textContent = `Calendar source: ${caseItem.holidayCalendarSource}`;
        info.appendChild(source);
      }
    } else if (caseItem.receivedOn) {
      const legacy = document.createElement("small");
      legacy.textContent = "Legacy deadline · no jurisdiction/calendar snapshot";
      info.appendChild(legacy);
    }
    const actions = document.createElement("div");
    actions.className = "record-actions";
    if (caseItem.right !== "UNSPECIFIED") {
      actions.appendChild(makeButton("Preview request", () => previewCaseRequest(caseItem)));
    }
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
  milestoneNode.textContent = state.milestone ?? "M18";
  investigationCountNode.textContent = String(state.investigations?.length ?? 0);
  targetCountNode.textContent = String(state.targets?.length ?? 0);
  caseCountNode.textContent = String(state.cases?.length ?? 0);
  displayNameNode.value = state.identity?.displayName ?? "";
  clearRequestPreview();
  renderIdentityIdentifiers(state.identity?.identifiers ?? []);
  renderRequestIdentifierOptions(state.identity?.identifiers ?? []);
  renderInvestigations(state.investigations ?? []);
  renderRights(state.rights ?? []);
  renderErasureGrounds(state.erasureGrounds ?? []);
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
  const jurisdiction = caseJurisdictionNode.value.trim().toUpperCase();
  if (!jurisdiction) {
    setStatus("Enter the controller action jurisdiction before recording submission.", true);
    caseJurisdictionNode.focus();
    return;
  }
  backend.submitCase(caseId, receivedOn, jurisdiction, (response) => {
    handleMutation(response, "Submission recorded with an immutable jurisdiction/deadline snapshot.");
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
      researchBusy = true;
      setStatus(`Researching public URLs from artifact #${artifactId}…`);
      if (selectedInvestigationId) loadInvestigation(selectedInvestigationId);
    });
    backend.researchCompleted.connect((investigationId, _artifactId, result) => {
      researchBusy = false;
      const count = result?.createdCount ?? 0;
      setStatus(count ? `${count} research evidence item(s) recorded.` : "Research completed with no new evidence.");
      if (selectedInvestigationId === investigationId) loadInvestigation(investigationId);
    });
    backend.researchFailed.connect((investigationId, _artifactId, _code, message) => {
      researchBusy = false;
      setStatus(message, true);
      if (selectedInvestigationId === investigationId) loadInvestigation(investigationId);
    });
    backend.modelResearchStarted.connect((investigationId, evidenceId) => {
      researchBusy = true;
      setStatus(`Researching model-proposed Evidence #${evidenceId}…`);
      if (selectedInvestigationId === investigationId) renderModelProposals(investigationId);
    });
    backend.modelResearchCompleted.connect((investigationId, evidenceId, result) => {
      researchBusy = false;
      const count = result?.createdCount ?? 0;
      setStatus(count ? `${count} reviewed research evidence item(s) recorded from Evidence #${evidenceId}.` : `Reviewed research for Evidence #${evidenceId} completed with no new evidence.`);
      if (selectedInvestigationId === investigationId) loadInvestigation(investigationId);
    });
    backend.modelResearchFailed.connect((investigationId, _evidenceId, _code, message) => {
      researchBusy = false;
      setStatus(message, true);
      if (selectedInvestigationId === investigationId) loadInvestigation(investigationId);
    });
    backend.modelAnalysisStarted.connect((investigationId) => {
      activeModelInvestigationId = investigationId;
      modelAnalysisButton.disabled = true;
      proposalViews.delete(investigationId);
      if (selectedInvestigationId === investigationId) renderModelProposals(investigationId);
      setStatus(`Generating model proposals for investigation #${investigationId}…`);
    });
    backend.modelAnalysisCompleted.connect((investigationId, result) => {
      activeModelInvestigationId = null;
      modelAnalysisButton.disabled = false;
      proposalViews.set(investigationId, result?.proposals ?? []);
      if (selectedInvestigationId === investigationId) renderModelProposals(investigationId);
      const count = result?.proposals?.length ?? 0;
      setStatus(count ? `${count} model proposal(s) awaiting review.` : "Model analysis returned no proposals.");
    });
    backend.modelAnalysisFailed.connect((investigationId, _code, message) => {
      activeModelInvestigationId = null;
      modelAnalysisButton.disabled = false;
      setStatus(message, true);
      if (selectedInvestigationId === investigationId) renderModelProposals(investigationId);
    });
  });
}

caseRightNode.addEventListener("change", renderRightSummary);
caseErasureGroundNode.addEventListener("change", () => {
  renderErasureGroundSummary();
  clearRequestPreview();
});
caseJurisdictionNode.addEventListener("input", () => {
  caseJurisdictionNode.value = caseJurisdictionNode.value.toUpperCase();
});
approveRequestButton.addEventListener("click", approveCurrentRequest);
modelAnalysisButton.addEventListener("click", requestModelAnalysis);

nameForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!backend) return;
  backend.setDisplayName(displayNameNode.value, (response) => handleMutation(response, "Profile saved locally."));
});

identifierForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!backend) return;
  backend.addIdentifier(
    identifierKindNode.value,
    identifierValueNode.value,
    identifierLabelNode.value,
    (response) => {
      handleMutation(response, "Identifier encrypted and stored locally.");
      if (response?.ok) identifierForm.reset();
    },
  );
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