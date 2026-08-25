const statusNode = document.getElementById("status");
const milestoneNode = document.getElementById("milestone");
const identifierCountNode = document.getElementById("identifier-count");
const displayNameNode = document.getElementById("display-name");
const nameForm = document.getElementById("name-form");

let backend = null;

function setStatus(message, isError = false) {
  statusNode.textContent = message;
  statusNode.classList.toggle("error", isError);
}

function renderState(state) {
  milestoneNode.textContent = state.milestone ?? "M1 — Foundation";
  identifierCountNode.textContent = String(state.identity?.identifierCount ?? 0);
  displayNameNode.value = state.identity?.displayName ?? "";
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
  if (!backend) {
    setStatus("Native backend is unavailable.", true);
    return;
  }

  backend.setDisplayName(displayNameNode.value, (response) => {
    if (response?.ok) {
      setStatus("Profile saved locally.");
    } else if (response?.error?.message) {
      setStatus(response.error.message, true);
    }
  });
});

connectBackend();
