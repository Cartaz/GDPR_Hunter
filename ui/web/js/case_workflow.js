export function createCaseWorkflow({ setStatus, clearNode, makeButton, localDateString }) {
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
  const responsePanelTitleNode = document.getElementById("response-panel-title");
  const responsePanelEmptyNode = document.getElementById("response-panel-empty");
  const responsePanelNode = document.getElementById("response-panel");
  const responseForm = document.getElementById("response-form");
  const responseChannelNode = document.getElementById("response-channel");
  const responseReceivedOnNode = document.getElementById("response-received-on");
  const responseSenderNode = document.getElementById("response-sender");
  const responseSubjectNode = document.getElementById("response-subject");
  const responseBodyNode = document.getElementById("response-body");
  const responseListNode = document.getElementById("response-list");
  const responseDetailTitleNode = document.getElementById("response-detail-title");
  const responseDetailEmptyNode = document.getElementById("response-detail-empty");
  const responseDetailNode = document.getElementById("response-detail");
  const responseDetailMetaNode = document.getElementById("response-detail-meta");
  const responseDetailSenderNode = document.getElementById("response-detail-sender");
  const responseDetailSubjectNode = document.getElementById("response-detail-subject");
  const responseDetailBodyNode = document.getElementById("response-detail-body");

  let backend = null;
  let state = null;
  let requestPreviewContext = null;
  let selectedResponseCaseId = null;

  function handleMutation(response, successMessage) {
    if (response?.ok) setStatus(successMessage);
    else if (response?.error?.message) setStatus(response.error.message, true);
  }

  function targetName(targetId) {
    const target = state?.targets?.find((item) => item.id === targetId);
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
    requestPreviewContext = null;
    requestPreviewNode.hidden = true;
    requestPreviewTitleNode.textContent = "Request preview";
    requestPreviewRecipientNode.textContent = "";
    requestPreviewSubjectNode.value = "";
    requestPreviewBodyNode.value = "";
    approveRequestButton.disabled = true;
  }

  function renderRequestPreview(preview) {
    requestPreviewContext = {
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
    const right = state?.rights?.find((item) => item.id === caseRightNode.value);
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
    const ground = state?.erasureGrounds?.find((item) => item.id === caseErasureGroundNode.value);
    erasureGroundSummaryNode.textContent = ground
      ? `${ground.summary} It becomes part of an immutable payload only after explicit approval.`
      : "Used only for Article 17 requests. The selected ground becomes part of an approved payload only after explicit approval.";
  }

  function createCase(targetId) {
    if (!backend || !caseRightNode.value) return;
    backend.createCase(targetId, caseRightNode.value, (response) => {
      handleMutation(response, "Draft GDPR case created locally.");
    });
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

  function makeSubmissionAction(caseId, approvals) {
    const wrapper = document.createElement("div");
    wrapper.className = "date-action submission-action";
    const selector = document.createElement("select");
    selector.setAttribute("aria-label", `Approved payload for Case #${caseId}`);
    for (const approval of approvals) {
      const option = document.createElement("option");
      option.value = String(approval.id);
      option.textContent = `Payload #${approval.id} · ${approval.approvedAt}`;
      selector.appendChild(option);
    }
    const input = document.createElement("input");
    input.type = "date";
    input.value = localDateString();
    input.setAttribute("aria-label", `Controller receipt date for Case #${caseId}`);
    const button = makeButton("Confirm sent payload", () => {
      submitCase(caseId, Number(selector.value), input.value);
    });
    wrapper.append(selector, input, button);
    return wrapper;
  }

  function clearResponseDetail() {
    responseDetailTitleNode.textContent = "No response selected";
    responseDetailEmptyNode.hidden = false;
    responseDetailNode.hidden = true;
    responseDetailMetaNode.textContent = "";
    responseDetailSenderNode.value = "";
    responseDetailSubjectNode.value = "";
    responseDetailBodyNode.value = "";
  }

  function resetResponseDraft() {
    responseForm.reset();
    responseChannelNode.value = "EMAIL";
    responseReceivedOnNode.value = localDateString();
    clearResponseDetail();
  }

  function renderCaseResponseDetail(response) {
    responseDetailTitleNode.textContent = `Response #${response.id}`;
    responseDetailEmptyNode.hidden = true;
    responseDetailNode.hidden = false;
    responseDetailMetaNode.textContent = `${response.channel} · received ${response.receivedOn} · recorded ${response.recordedAt}`;
    responseDetailSenderNode.value = response.sender ?? "";
    responseDetailSubjectNode.value = response.subject ?? "";
    responseDetailBodyNode.value = response.body;
  }

  function openCaseResponse(responseId, caseId) {
    if (!backend) return;
    backend.getCaseResponse(responseId, (response) => {
      if (selectedResponseCaseId !== caseId) return;
      if (response?.error) {
        setStatus(response.error.message, true);
        return;
      }
      if (response.caseId !== caseId) {
        setStatus("The selected response no longer belongs to the active Case view.", true);
        return;
      }
      renderCaseResponseDetail(response);
    });
  }

  function renderCaseResponseSummaries(caseId, summaries) {
    clearNode(responseListNode);
    if (!summaries.length) {
      const empty = document.createElement("p");
      empty.className = "muted empty-state";
      empty.textContent = "No controller responses recorded for this Case.";
      responseListNode.appendChild(empty);
      return;
    }
    for (const summary of summaries) {
      const row = document.createElement("div");
      row.className = "record";
      const info = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = `Response #${summary.id} · ${summary.channel}`;
      const detail = document.createElement("small");
      detail.textContent = `Received ${summary.receivedOn} · recorded ${summary.recordedAt}`;
      info.append(title, detail);
      row.append(info, makeButton("Open", () => openCaseResponse(summary.id, caseId)));
      responseListNode.appendChild(row);
    }
  }

  function closeResponsePanel() {
    selectedResponseCaseId = null;
    responsePanelTitleNode.textContent = "Select a submitted case";
    responsePanelEmptyNode.hidden = false;
    responsePanelNode.hidden = true;
    clearNode(responseListNode);
    resetResponseDraft();
  }

  function loadCaseResponses(caseId) {
    if (!backend) return;
    const caseItem = state?.cases?.find((item) => item.id === caseId);
    if (!caseItem || !caseItem.receivedOn) {
      closeResponsePanel();
      return;
    }
    const caseChanged = selectedResponseCaseId !== caseId;
    selectedResponseCaseId = caseId;
    if (caseChanged) resetResponseDraft();
    responsePanelTitleNode.textContent = `Case #${caseId} · ${targetName(caseItem.targetId)}`;
    responsePanelEmptyNode.hidden = true;
    responsePanelNode.hidden = false;
    responseForm.hidden = caseItem.status !== "AWAITING_RESPONSE";
    if (caseItem.status !== "AWAITING_RESPONSE") resetResponseDraft();
    else if (!responseReceivedOnNode.value) responseReceivedOnNode.value = localDateString();
    const requestedCaseId = caseId;
    backend.listCaseResponses(caseId, (response) => {
      if (selectedResponseCaseId !== requestedCaseId) return;
      if (response?.error) {
        setStatus(response.error.message, true);
        return;
      }
      renderCaseResponseSummaries(requestedCaseId, response);
    });
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
    if (!backend || !requestPreviewContext) return;
    const approved = window.confirm(
      "Persist an encrypted, immutable copy of exactly this recipient, subject and body as the user-approved outbound payload? This does not send, queue or hand off the message.",
    );
    if (!approved) return;
    const context = requestPreviewContext;
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

  function handoffApprovedRequest(approvedRequestId) {
    if (!backend) return;
    const approved = window.confirm(
      `Open approved payload #${approvedRequestId} in the system mail client? Python will load exactly the immutable recipient, subject and body already approved. Opening the mail client is not proof that the message was sent.`,
    );
    if (!approved) return;
    backend.handoffApprovedRequest(approvedRequestId, approved, (response) => {
      if (response?.ok && response.result?.accepted) {
        setStatus(`Approved payload #${approvedRequestId} opened in the system mail client. Confirm submission only after you actually send it.`);
      } else if (response?.ok) {
        setStatus("The operating system did not accept the mail-client handoff. Nothing was sent.", true);
      } else if (response?.error?.message) {
        setStatus(response.error.message, true);
      }
    });
  }

  function submitCase(caseId, approvedRequestId, receivedOn) {
    if (!backend || !receivedOn || !approvedRequestId) return;
    const jurisdiction = caseJurisdictionNode.value.trim().toUpperCase();
    if (!jurisdiction) {
      setStatus("Enter the controller action jurisdiction before confirming submission.", true);
      caseJurisdictionNode.focus();
      return;
    }
    const confirmed = window.confirm(
      `Confirm that approved payload #${approvedRequestId} was actually transmitted and that ${receivedOn} is the controller receipt date to use for the GDPR deadline snapshot?`,
    );
    if (!confirmed) return;
    backend.submitCase(
      caseId,
      approvedRequestId,
      receivedOn,
      jurisdiction,
      confirmed,
      (response) => {
        handleMutation(
          response,
          `Payload #${approvedRequestId} bound to the submission with an immutable jurisdiction/deadline snapshot.`,
        );
        if (response?.ok) loadTimeline(caseId);
      },
    );
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
      const approvals = (state?.approvedRequests ?? []).filter((item) => item.caseId === caseItem.id);
      const approval = approvals[0] ?? null;
      if (approval) {
        const approvedDetail = document.createElement("small");
        approvedDetail.textContent = `Latest approved payload #${approval.id} · ${approval.approvedAt} · not automatically sent`;
        info.appendChild(approvedDetail);
        const deliveryEvent = (state?.deliveryEvents ?? []).find(
          (item) => item.approvedRequestId === approval.id,
        );
        if (deliveryEvent) {
          const deliveryDetail = document.createElement("small");
          deliveryDetail.textContent = `Latest mail handoff event: ${deliveryEvent.type} · ${deliveryEvent.createdAt}`;
          info.appendChild(deliveryDetail);
        }
      }
      const submissionBinding = (state?.submissionBindings ?? []).find(
        (item) => item.caseId === caseItem.id,
      );
      if (submissionBinding) {
        const submittedDetail = document.createElement("small");
        submittedDetail.textContent = `Confirmed submitted payload #${submissionBinding.approvedRequestId} · bound ${submissionBinding.confirmedAt}`;
        info.appendChild(submittedDetail);
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
        legacy.textContent = submissionBinding
          ? "Legacy deadline · no jurisdiction/calendar snapshot"
          : "Legacy submission · exact approved payload was not historically recorded";
        info.appendChild(legacy);
      }
      const actions = document.createElement("div");
      actions.className = "record-actions";
      if (caseItem.right !== "UNSPECIFIED") {
        actions.appendChild(makeButton("Preview request", () => previewCaseRequest(caseItem)));
      }
      if (caseItem.status === "DRAFT" && approval) {
        actions.appendChild(makeButton("Open approved payload", () => handoffApprovedRequest(approval.id)));
      }
      if (caseItem.receivedOn) {
        actions.appendChild(makeButton("Responses", () => loadCaseResponses(caseItem.id)));
      }
      actions.appendChild(makeButton("Timeline", () => loadTimeline(caseItem.id)));
      if (caseItem.status === "DRAFT" && caseItem.right !== "UNSPECIFIED") {
        if (approvals.length) actions.appendChild(makeSubmissionAction(caseItem.id, approvals));
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

  function render(nextState) {
    state = nextState;
    clearRequestPreview();
    renderRequestIdentifierOptions(state.identity?.identifiers ?? []);
    renderRights(state.rights ?? []);
    renderErasureGrounds(state.erasureGrounds ?? []);
    renderTargets(state.targets ?? []);
    renderCases(state.cases ?? []);
    if (selectedResponseCaseId) loadCaseResponses(selectedResponseCaseId);
  }

  function setBackend(nextBackend) {
    backend = nextBackend;
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

  targetForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!backend) return;
    backend.createTarget(targetNameNode.value, targetDomainNode.value, privacyEmailNode.value, (response) => {
      handleMutation(response, "Target added locally.");
      if (response?.ok) targetForm.reset();
    });
  });

  responseForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!backend || !selectedResponseCaseId) return;
    const caseId = selectedResponseCaseId;
    const confirmed = window.confirm(
      "Record this controller response exactly as entered? Sensitive response content will be encrypted locally. This does not classify compliance, alter the deadline, or complete the Case.",
    );
    if (!confirmed) return;
    backend.recordCaseResponse(
      caseId,
      responseChannelNode.value,
      responseReceivedOnNode.value,
      responseSenderNode.value,
      responseSubjectNode.value,
      responseBodyNode.value,
      confirmed,
      (response) => {
        if (selectedResponseCaseId !== caseId) return;
        handleMutation(response, "Controller response encrypted and recorded locally.");
        if (response?.ok) {
          resetResponseDraft();
          loadCaseResponses(caseId);
        }
      },
    );
  });

  resetResponseDraft();

  return Object.freeze({ render, setBackend });
}
