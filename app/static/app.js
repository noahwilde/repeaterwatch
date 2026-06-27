const dashboardUrl = "/api/dashboard";
const activityRangeStorageKey = "repeaterwatch.activityHours";
const apiUsageRangeStorageKey = "repeaterwatch.apiUsageHours";
const activityChatRangeStorageKey = "repeaterwatch.activityChatHours";
const textSizeStorageKey = "repeaterwatch.textSize";
const themeStorageKey = "repeaterwatch.theme";
const lightThemeColor = "#24413a";
const darkThemeColor = "#111113";
const activityHourOptions = new Set([1, 6, 12, 24, 72, 168]);
const apiUsageHourOptions = new Set([24, 72, 168, 720]);
const activityChatHourOptions = new Set([1, 6, 12, 24, 72, 168, 720]);
const textSizeMin = 85;
const textSizeMax = 125;
const textSizeStep = 5;
const saveConfirmationMs = 1800;
const saveStatusClasses = ["state-completed", "state-error"];
const callsignPattern = /\b(?:[AKNW][A-Z]?[0-9][A-Z]{1,3}|[A-Z]{1,2}[0-9][A-Z]{1,3})\b/g;

const els = {
  pullRefresh: document.querySelector("#pullRefresh"),
  installPanel: document.querySelector("#installPanel"),
  activityChatPanel: document.querySelector("#activityChatPanel"),
  activityRange: document.querySelector("#activityRange"),
  homeGlance: document.querySelector("#homeGlance"),
  repeaterForm: document.querySelector("#repeaterForm"),
  repeaterStatus: document.querySelector("#repeaterStatus"),
  trafficAlertForm: document.querySelector("#trafficAlertForm"),
  trafficAlertStatus: document.querySelector("#trafficAlertStatus"),
  displaySettingsForm: document.querySelector("#displaySettingsForm"),
  displaySettingsStatus: document.querySelector("#displaySettingsStatus"),
  textSizeValue: document.querySelector("#textSizeValue"),
  darkMode: document.querySelector("#darkMode"),
  resetTextSizeBtn: document.querySelector("#resetTextSizeBtn"),
  ruleForm: document.querySelector("#ruleForm"),
  ruleStatus: document.querySelector("#ruleStatus"),
  summaryForm: document.querySelector("#summaryForm"),
  summaryRepeater: document.querySelector("#summaryRepeater"),
  summarySearchForm: document.querySelector("#summarySearchForm"),
  summarySearch: document.querySelector("#summarySearch"),
  clearSummarySearchBtn: document.querySelector("#clearSummarySearchBtn"),
  summarySearchStatus: document.querySelector("#summarySearchStatus"),
  summaryStats: document.querySelector("#summaryStats"),
  summaryStatus: document.querySelector("#summaryStatus"),
  adHocSummary: document.querySelector("#adHocSummary"),
  activityChatRange: document.querySelector("#activityChatRange"),
  activityChatRepeater: document.querySelector("#activityChatRepeater"),
  activityChatMessages: document.querySelector("#activityChatMessages"),
  activityChatForm: document.querySelector("#activityChatForm"),
  activityChatInput: document.querySelector("#activityChatInput"),
  activityChatStatus: document.querySelector("#activityChatStatus"),
  clearActivityChatBtn: document.querySelector("#clearActivityChatBtn"),
  settingsForm: document.querySelector("#settingsForm"),
  apiUsageRange: document.querySelector("#apiUsageRange"),
  refreshApiUsageBtn: document.querySelector("#refreshApiUsageBtn"),
  apiUsageStatus: document.querySelector("#apiUsageStatus"),
  apiUsageStats: document.querySelector("#apiUsageStats"),
  apiUsageChart: document.querySelector("#apiUsageChart"),
  apiUsageBreakdown: document.querySelector("#apiUsageBreakdown"),
  apiUsageSettingsForm: document.querySelector("#apiUsageSettingsForm"),
  apiUsageSettingsStatus: document.querySelector("#apiUsageSettingsStatus"),
  apiUsageEvents: document.querySelector("#apiUsageEvents"),
  liveTestForm: document.querySelector("#liveTestForm"),
  clearRecordingsBtn: document.querySelector("#clearRecordingsBtn"),
  clearStaticRecordingsBtn: document.querySelector("#clearStaticRecordingsBtn"),
  transcriptSearchForm: document.querySelector("#transcriptSearchForm"),
  transcriptSearch: document.querySelector("#transcriptSearch"),
  clearTranscriptSearchBtn: document.querySelector("#clearTranscriptSearchBtn"),
  transcriptSearchStatus: document.querySelector("#transcriptSearchStatus"),
  clearSummariesBtn: document.querySelector("#clearSummariesBtn"),
  clearEventsBtn: document.querySelector("#clearEventsBtn"),
  enablePushBtn: document.querySelector("#enablePushBtn"),
  testPushBtn: document.querySelector("#testPushBtn"),
  refreshLogsBtn: document.querySelector("#refreshLogsBtn"),
  startLiveBtn: document.querySelector("#startLiveBtn"),
  stopLiveBtn: document.querySelector("#stopLiveBtn"),
  logs: document.querySelector("#logs"),
  logLimit: document.querySelector("#logLimit"),
  logStatus: document.querySelector("#logStatus"),
  recordingStatus: document.querySelector("#recordingStatus"),
  pushStatus: document.querySelector("#pushStatus"),
  settingsStatus: document.querySelector("#settingsStatus"),
  liveStatus: document.querySelector("#liveStatus"),
  liveLevelBar: document.querySelector("#liveLevelBar"),
  liveLevelText: document.querySelector("#liveLevelText"),
  liveActiveText: document.querySelector("#liveActiveText"),
  receiverStatus: document.querySelector("#receiverStatus"),
  activityChart: document.querySelector("#activityChart"),
  activityWindow: document.querySelector("#activityWindow"),
  sdrWindow: document.querySelector("#sdrWindow"),
  sdrWindowStatus: document.querySelector("#sdrWindowStatus"),
  repeaters: document.querySelector("#repeaters"),
  recordings: document.querySelector("#recordings"),
  summaries: document.querySelector("#summaries"),
  rules: document.querySelector("#rules"),
  events: document.querySelector("#events"),
  metricReceivers: document.querySelector("#metricReceivers"),
  metricRecordings: document.querySelector("#metricRecordings"),
  metricRules: document.querySelector("#metricRules"),
  metricDisk: document.querySelector("#metricDisk"),
  callsignModal: document.querySelector("#callsignModal"),
  callsignTitle: document.querySelector("#callsignTitle"),
  callsignDetails: document.querySelector("#callsignDetails"),
};

let currentConfig = null;
let liveSocket = null;
let liveAudioContext = null;
let liveNextStart = 0;
let liveDecayTimer = null;
let liveFormInitialized = false;
let listenSocket = null;
let listenAudioContext = null;
let listenNextStart = 0;
let listeningRepeaterId = null;
let listenSampleRate = 24000;
let listenStatusMessage = "";
let activeView = "";
let activityHours = loadActivityHours();
let apiUsageHours = loadApiUsageHours();
let activityChatHours = loadActivityChatHours();
let pullStartY = 0;
let pullDistance = 0;
let pullTracking = false;
let pullRefreshing = false;
let expandedHomeCard = null;
let activeCallsignLookup = null;
let textSizePercent = loadTextSize();
let displayTheme = loadDisplayTheme();
let selectedHomeReceiverId = null;
let receiverRestartMessage = "";
let transcriptSearchTerm = "";
let transcriptRenderSignature = "";
let transcriptNeedsRender = false;
let transcriptHighlightSignature = "";
let currentRecordings = [];
let currentTranscripts = [];
let currentKeywordRules = [];
let currentSummaries = [];
let currentRepeaters = [];
let summarySearchTerm = "";
let adHocSummary = null;
let activityChatMessages = [];
let activityChatInFlight = false;
let dashboardRefreshInFlight = false;
let dashboardRefreshPending = false;
let apiUsageRefreshInFlight = false;
let editingRepeaterId = null;
let editingRuleId = null;

const views = new Set(["monitor", "transcripts", "summaries", "more"]);
const legacyViews = new Map([
  ["review", "transcripts"],
  ["transcript", "transcripts"],
  ["radio", "more"],
  ["repeaters", "more"],
  ["live", "more"],
  ["recordings", "transcripts"],
  ["summary", "summaries"],
  ["chat", "monitor"],
  ["activity-chat", "monitor"],
  ["notifications", "more"],
  ["logs", "more"],
  ["settings", "more"],
]);

function viewTabButtons() {
  return document.querySelectorAll("[data-view-tab]");
}

function viewFromHash() {
  const view = window.location.hash.replace("#", "").trim();
  if (legacyViews.has(view)) return legacyViews.get(view);
  return views.has(view) ? view : "monitor";
}

function hashTargetsActivityChat() {
  const view = window.location.hash.replace("#", "").trim();
  return view === "chat" || view === "activity-chat";
}

function scrollActivityChatIntoView() {
  if (!els.activityChatPanel) return;
  window.requestAnimationFrame(() => {
    els.activityChatPanel.scrollIntoView({ block: "start", behavior: "smooth" });
  });
}

function updateViewHash(view) {
  const nextHash = `#${view === "more" ? "settings" : view}`;
  if (window.location.hash !== nextHash) {
    history.pushState(null, "", nextHash);
  }
}

function loadActivityHours() {
  const value = Number(window.localStorage.getItem(activityRangeStorageKey) || 24);
  return activityHourOptions.has(value) ? value : 24;
}

function loadApiUsageHours() {
  const value = Number(window.localStorage.getItem(apiUsageRangeStorageKey) || 24);
  return apiUsageHourOptions.has(value) ? value : 24;
}

function loadActivityChatHours() {
  const value = Number(window.localStorage.getItem(activityChatRangeStorageKey) || 24);
  return activityChatHourOptions.has(value) ? value : 24;
}

function normalizeTextSize(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 100;
  const stepped = Math.round(numeric / textSizeStep) * textSizeStep;
  return Math.min(textSizeMax, Math.max(textSizeMin, stepped));
}

function loadTextSize() {
  return normalizeTextSize(window.localStorage.getItem(textSizeStorageKey) || 100);
}

function normalizeDisplayTheme(value) {
  return value === "dark" ? "dark" : "light";
}

function loadDisplayTheme() {
  return normalizeDisplayTheme(window.localStorage.getItem(themeStorageKey) || document.documentElement.dataset.theme || "light");
}

function applyDisplayTheme(value) {
  displayTheme = normalizeDisplayTheme(value);
  if (displayTheme === "dark") {
    document.documentElement.dataset.theme = "dark";
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  const themeColor = document.querySelector("meta[name='theme-color']");
  if (themeColor) {
    themeColor.setAttribute("content", displayTheme === "dark" ? darkThemeColor : lightThemeColor);
  }
  if (els.darkMode) {
    els.darkMode.checked = displayTheme === "dark";
  }
}

function applyTextSize(value) {
  textSizePercent = normalizeTextSize(value);
  document.documentElement.style.setProperty("--text-scale", `${textSizePercent}%`);
  if (els.displaySettingsForm) {
    els.displaySettingsForm.elements.text_size.value = String(textSizePercent);
  }
  if (els.textSizeValue) {
    els.textSizeValue.textContent = `${textSizePercent}%`;
  }
}

function setView(view, updateHash = true) {
  const nextView = views.has(view) ? view : "monitor";
  if (activeView === nextView) {
    if (updateHash) updateViewHash(nextView);
    return;
  }

  if (activeView === "more" && nextView !== "more") {
    stopLiveTest();
  }
  if (activeView === "transcripts" && nextView !== "transcripts") {
    pauseRecordingPlayback();
  }

  activeView = nextView;
  for (const section of document.querySelectorAll("[data-view]")) {
    section.hidden = section.dataset.view !== nextView;
  }
  for (const button of viewTabButtons()) {
    const isActive = button.dataset.viewTab === nextView;
    button.classList.toggle("active", isActive);
    if (isActive) {
      button.setAttribute("aria-current", "page");
    } else {
      button.removeAttribute("aria-current");
    }
  }
  if (updateHash) updateViewHash(nextView);
  if (nextView === "more") {
    refreshLogs();
    refreshApiUsage();
  }
  if (nextView === "transcripts") {
    flushTranscriptRender();
  }
  if (nextView === "monitor") {
    renderActivityChatMessages();
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    let message = text || response.statusText;
    try {
      const payload = JSON.parse(text);
      message = payload.detail || payload.message || message;
    } catch {
      // Non-JSON error responses are still useful as-is.
    }
    throw new Error(message);
  }
  return response.json();
}

function setSaveStatus(statusElement, message, stateClass = "") {
  if (!statusElement) return;
  statusElement.textContent = message;
  for (const className of saveStatusClasses) {
    statusElement.classList.remove(className);
  }
  if (stateClass) {
    statusElement.classList.add(stateClass);
  }
}

function defaultSubmitLabel(submitButton) {
  if (!submitButton) return "";
  if (!submitButton.dataset.defaultText) {
    submitButton.dataset.defaultText = submitButton.textContent;
  }
  return submitButton.dataset.defaultText;
}

async function withSaveFeedback(form, statusElement, messages, action) {
  const submitButton = form.querySelector("button[type='submit']");
  const defaultLabel = defaultSubmitLabel(submitButton);
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = messages.savingButton || "Saving...";
  }
  setSaveStatus(statusElement, messages.saving || "Saving...");

  try {
    const value = await action();
    setSaveStatus(statusElement, messages.saved || "Saved.", "state-completed");
    if (submitButton) {
      submitButton.textContent = messages.savedButton || "Saved";
      window.setTimeout(() => {
        if (!submitButton.isConnected) return;
        submitButton.disabled = false;
        submitButton.textContent = defaultLabel;
      }, saveConfirmationMs);
    }
    return { ok: true, value };
  } catch (error) {
    setSaveStatus(statusElement, error.message || messages.error || "Save failed.", "state-error");
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = defaultLabel;
    }
    return { ok: false, error };
  }
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatAxisTime(value) {
  if (!value) return "";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatActivityDateTime(value) {
  if (!value) return "";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function formatDuration(seconds) {
  const value = Math.max(0, Number(seconds || 0));
  if (value < 60) return `${Math.round(value)}s`;
  if (value < 3600) return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
  const hours = Math.floor(value / 3600);
  const minutes = Math.round((value % 3600) / 60);
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

function formatCount(value) {
  return Number(value || 0).toLocaleString();
}

function activityHoursFromWindow(activity) {
  if (!activity || !activity.start_time || !activity.end_time) return activityHours;
  const start = new Date(activity.start_time);
  const end = new Date(activity.end_time);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return activityHours;
  return Math.max(1, Math.round((end.getTime() - start.getTime()) / 3600000));
}

function formatActivityWindowLabel(activity) {
  const hours = activityHoursFromWindow(activity);
  if (hours < 24) return `Last ${hours}h`;
  if (hours % 24 === 0) {
    const days = hours / 24;
    return `Last ${days}d`;
  }
  return `Last ${hours}h`;
}

function item(html) {
  const div = document.createElement("div");
  div.className = "item";
  div.innerHTML = html;
  return div;
}

function setEmpty(container, text) {
  container.innerHTML = "";
  const div = item(`<p class="muted">${text}</p>`);
  container.appendChild(div);
}

async function refreshDashboard() {
  if (dashboardRefreshInFlight) {
    dashboardRefreshPending = true;
    return;
  }
  dashboardRefreshInFlight = true;
  try {
    const params = new URLSearchParams({ activity_hours: String(activityHours) });
    const data = await fetchJson(`${dashboardUrl}?${params.toString()}`);
    renderDashboard(data);
  } catch (error) {
    els.receiverStatus.innerHTML = "";
    els.receiverStatus.appendChild(item(`<p class="state-error">${escapeHtml(error.message)}</p>`));
  } finally {
    dashboardRefreshInFlight = false;
    if (dashboardRefreshPending) {
      dashboardRefreshPending = false;
      refreshDashboard();
    }
  }
}

function renderDashboard(data) {
  currentConfig = data.config;
  els.metricReceivers.textContent = data.receiver_status.length || data.repeaters.filter((r) => r.enabled).length;
  els.metricRecordings.textContent = data.recordings.length;
  els.metricRules.textContent = data.keyword_rules.length;
  els.metricDisk.textContent = formatBytes(data.disk_usage.used);
  renderHomeGlance(data);
  renderReceivers(data);
  renderActivity(data.activity);
  renderRepeaters(data.repeaters);
  renderSdrWindow(data.sdr_window);
  renderRecordings(data.recordings, data.transcripts, data.keyword_rules);
  renderSummaries(data.summaries, data.repeaters);
  renderActivityChatScopeOptions(data.repeaters);
  renderRules(data.keyword_rules);
  renderEvents(data.notification_events);
  renderSettings(data.config);
}

function renderHomeGlance(data) {
  if (!els.homeGlance) return;
  const repeaters = Array.isArray(data.repeaters) ? data.repeaters : [];
  const enabledRepeaters = repeaters.filter((repeater) => repeater.enabled);
  const statuses = Array.isArray(data.receiver_status) ? data.receiver_status : [];
  const statusByRepeater = new Map(statuses.map((status) => [String(status.repeater_id), status]));
  const running = statuses.filter((status) => status.state === "running");
  const primaryStatus = statuses[0] || null;
  const receiverCount = repeaters.length || statuses.length;
  const receiverSummary = receiverCount
    ? `${running.length}/${receiverCount} running`
    : "No receivers";
  const runningNames = running.map((status) => status.repeater_name).filter(Boolean).slice(0, 2);
  const receiverSummaryDetail = listeningRepeaterId && listenSocket
    ? `Listening to ${receiverNameById(repeaters, statuses, listeningRepeaterId)}`
    : running.length
      ? `${runningNames.length ? runningNames.join(", ") : "Receiver"} active`
      : enabledRepeaters.length
        ? `${enabledRepeaters.length} enabled`
        : "Configure a repeater";
  const receiverStatusState = running.length ? "running" : enabledRepeaters.length ? "pending" : "disabled";
  const receiverKey = "receiver";

  const recordings = Array.isArray(data.recordings) ? data.recordings : [];
  const transcripts = Array.isArray(data.transcripts) ? data.transcripts : [];
  const latestRecording = recordings[0] || null;
  const transcriptByRecording = new Map(transcripts.map((transcript) => [transcript.recording_id, transcript]));
  const latestTranscript = latestRecording ? transcriptByRecording.get(latestRecording.id) : null;
  const lastHeardTitle = latestRecording ? formatTime(latestRecording.start_time) : "No transmissions";
  const lastHeardDetail = latestRecording
    ? `${latestRecording.repeater_name} ${latestRecording.duration_seconds ? `for ${formatDuration(latestRecording.duration_seconds)}` : ""}`.trim()
    : "Nothing recorded yet";
  const lastHeardText = latestTranscript ? latestTranscript.text : latestRecording ? "Transcript pending." : "";

  const summaries = Array.isArray(data.summaries) ? data.summaries : [];
  const latestSummary = summaries[0] || null;
  const summaryTitle = latestSummary ? formatSummaryWindow(latestSummary.window_name) : "No summary";
  const summaryDetail = latestSummary ? formatTime(latestSummary.created_at) : "Generate one from the Summary tab";
  const summaryText = latestSummary ? latestSummary.text : "";
  const latestRecordingKey = latestRecording ? `recording:${latestRecording.id}` : null;
  const latestSummaryKey = latestSummary ? `summary:${latestSummary.id}` : null;
  const receiverExpanded = expandedHomeCard === receiverKey;
  const recordingExpanded = expandedHomeCard === latestRecordingKey;
  const summaryExpanded = expandedHomeCard === latestSummaryKey;
  const lastHeardPreviewText = recordingExpanded
    ? (lastHeardText || "No transcript yet.")
    : compactText(lastHeardText, "No transcript yet.", 120);

  els.homeGlance.innerHTML = `
    <article class="glance-card glance-card-action ${receiverExpanded ? "expanded" : ""}" data-home-target="receiver" data-home-key="${receiverKey}" role="button" tabindex="0" aria-expanded="${receiverExpanded}">
      <div class="glance-card-head">
        <span class="metric-label">Receiver</span>
        <span class="pill state-${escapeHtml(receiverStatusState)}">${escapeHtml(receiverStatusState)}</span>
      </div>
      <strong>${escapeHtml(receiverSummary)}</strong>
      <p class="muted">${callsignTextHtml(receiverSummaryDetail)}</p>
      ${receiverExpanded ? receiverPickerHtml(repeaters, statusByRepeater, running, primaryStatus) : ""}
    </article>
    <article class="glance-card ${latestRecording ? "glance-card-action" : ""} ${recordingExpanded ? "expanded" : ""}" ${latestRecording ? `data-home-target="recording" data-home-key="${latestRecordingKey}" data-recording-id="${latestRecording.id}" role="button" tabindex="0" aria-expanded="${recordingExpanded}"` : ""}>
      <div class="glance-card-head">
        <span class="metric-label">Last Heard</span>
        <span class="pill">${recordings.length}</span>
      </div>
      <strong>${escapeHtml(lastHeardTitle)}</strong>
      <p>${callsignTextHtml(lastHeardDetail)}</p>
      <p class="muted">${transcriptTextHtml(lastHeardPreviewText, data.keyword_rules, latestRecording)}</p>
      ${recordingExpanded ? `<button class="secondary glance-card-link" data-home-link="recording" type="button">View in Transcript</button>` : ""}
    </article>
    <article class="glance-card glance-card-wide ${latestSummary ? "glance-card-action" : ""} ${summaryExpanded ? "expanded" : ""}" ${latestSummary ? `data-home-target="summary" data-home-key="${latestSummaryKey}" data-summary-id="${latestSummary.id}" role="button" tabindex="0" aria-expanded="${summaryExpanded}"` : ""}>
      <div class="glance-card-head">
        <span class="metric-label">Latest Summary</span>
        <span class="pill">${escapeHtml(latestSummary ? formatStatus(latestSummary.status) : "none")}</span>
      </div>
      <strong>${escapeHtml(summaryTitle)}</strong>
      <p class="muted">${escapeHtml(summaryDetail)}</p>
      <p>${callsignTextHtml(summaryExpanded ? (summaryText || "No summary available.") : compactText(summaryText, "No summary available.", 170))}</p>
      ${summaryExpanded ? `<button class="secondary glance-card-link" data-home-link="summary" type="button">View in Summary</button>` : ""}
    </article>
  `;
  setupHomeGlanceActions();
}

function receiverNameById(repeaters, statuses, repeaterId) {
  const id = String(repeaterId);
  const repeater = repeaters.find((row) => String(row.id) === id);
  if (repeater) return repeater.name;
  const status = statuses.find((row) => String(row.repeater_id) === id);
  return status && status.repeater_name ? status.repeater_name : "Receiver";
}

function receiverPickerHtml(repeaters, statusByRepeater, running, primaryStatus) {
  const receiverRows = repeaters.length
    ? repeaters
    : Array.from(statusByRepeater.values()).map((status) => ({
        id: status.repeater_id,
        name: status.repeater_name || `Repeater ${status.repeater_id}`,
        frequency_mhz: status.frequency_mhz,
        enabled: status.state !== "disabled",
      }));
  if (!receiverRows.length) {
    return `<p class="muted">No repeaters configured.</p>`;
  }

  const rowIds = new Set(receiverRows.map((row) => String(row.id)));
  const fallbackId = listeningRepeaterId && rowIds.has(String(listeningRepeaterId))
    ? listeningRepeaterId
    : running[0] && rowIds.has(String(running[0].repeater_id))
      ? running[0].repeater_id
      : primaryStatus && rowIds.has(String(primaryStatus.repeater_id))
        ? primaryStatus.repeater_id
        : receiverRows.find((row) => row.enabled)?.id ?? receiverRows[0].id;
  if (selectedHomeReceiverId == null || !rowIds.has(String(selectedHomeReceiverId))) {
    selectedHomeReceiverId = fallbackId;
  }

  const selectedId = String(selectedHomeReceiverId);
  const selectedRepeater = receiverRows.find((row) => String(row.id) === selectedId) || receiverRows[0];
  const selectedStatus = statusByRepeater.get(selectedId) || null;
  const selectedState = selectedStatus ? selectedStatus.state : selectedRepeater.enabled ? "pending" : "disabled";
  const selectedFrequency = selectedStatus && selectedStatus.frequency_mhz
    ? selectedStatus.frequency_mhz
    : selectedRepeater.frequency_mhz;
  const selectedName = selectedStatus && selectedStatus.repeater_name
    ? selectedStatus.repeater_name
    : selectedRepeater.name;
  const selectedMessage = selectedStatus && selectedStatus.message
    ? selectedStatus.message
    : selectedRepeater.enabled
      ? "Receiver configured."
      : "Repeater is disabled.";
  const canListen = Boolean(selectedRepeater.enabled && selectedState === "running");
  const canRestart = Boolean(selectedRepeater.enabled && !["running", "starting"].includes(selectedState));
  const isListening = canListen && String(listeningRepeaterId) === selectedId && listenSocket;
  const options = receiverRows
    .map((row) => {
      const status = statusByRepeater.get(String(row.id));
      const state = status ? status.state : row.enabled ? "pending" : "disabled";
      const label = `${row.name} (${state})`;
      return `<option value="${escapeHtml(row.id)}" ${String(row.id) === selectedId ? "selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");

  return `
    <div class="home-receiver-expanded">
      <label class="home-receiver-select">
        <span>Repeater</span>
        <select data-home-receiver-select aria-label="Home receiver repeater">${options}</select>
      </label>
      <div class="meta">
        <span class="pill state-${escapeHtml(selectedState)}">${escapeHtml(selectedState)}</span>
        ${selectedFrequency ? `<span class="pill">${Number(selectedFrequency).toFixed(6)} MHz</span>` : ""}
      </div>
      <p class="muted">${callsignTextHtml(selectedMessage)}</p>
      <div class="receiver-action-row">
        <button class="secondary glance-card-link" data-listen-repeater="${escapeHtml(selectedId)}" type="button" ${canListen ? "" : "disabled"}>${isListening ? "Stop listening" : "Listen"}</button>
        ${canRestart ? `<button class="secondary glance-card-link" data-restart-receivers type="button">Restart receiver</button>` : ""}
      </div>
      <p class="muted" data-home-listen-status>${callsignTextHtml(receiverRestartMessage || (isListening ? (listenStatusMessage || "Listening. Recording continues.") : canListen ? `Listen to ${selectedName}. Recording continues.` : selectedRepeater.enabled ? "Restart the receiver before listening." : "Enable this repeater to listen."))}</p>
    </div>
  `;
}

function setupHomeGlanceActions() {
  if (!els.homeGlance) return;
  for (const card of els.homeGlance.querySelectorAll("[data-home-target]")) {
    card.addEventListener("click", (event) => {
      if (event.target.closest("button, select, input, textarea, label, [data-callsign]")) return;
      toggleHomeCard(card);
    });
    card.addEventListener("keydown", (event) => {
      if (event.target.closest("button, select, input, textarea, label, [data-callsign]")) return;
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      toggleHomeCard(card);
    });
  }
  for (const button of els.homeGlance.querySelectorAll("[data-home-link]")) {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openHomeTarget(button.closest("[data-home-target]"));
    });
  }
  for (const select of els.homeGlance.querySelectorAll("[data-home-receiver-select]")) {
    select.addEventListener("click", (event) => event.stopPropagation());
    select.addEventListener("change", (event) => {
      event.stopPropagation();
      selectedHomeReceiverId = select.value;
      refreshDashboard();
    });
  }
  for (const button of els.homeGlance.querySelectorAll("[data-listen-repeater]")) {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const repeaterId = Number(button.dataset.listenRepeater);
      if (String(listeningRepeaterId) === String(repeaterId) && listenSocket) {
        stopHomeListen();
      } else {
        startHomeListen(repeaterId).catch((error) => {
          updateHomeListenStatus(error.message || "Listen failed.");
          stopHomeListen();
        });
      }
    });
  }
  for (const button of els.homeGlance.querySelectorAll("[data-restart-receivers]")) {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      button.disabled = true;
      receiverRestartMessage = "Restarting receiver...";
      updateHomeListenStatus(receiverRestartMessage);
      try {
        await fetchJson("/api/receivers/restart", { method: "POST" });
        receiverRestartMessage = "Receiver restart requested.";
        await refreshDashboard();
      } catch (error) {
        receiverRestartMessage = error.message || "Receiver restart failed.";
        updateHomeListenStatus(receiverRestartMessage);
      } finally {
        window.setTimeout(() => {
          receiverRestartMessage = "";
          refreshDashboard();
        }, saveConfirmationMs);
      }
    });
  }
}

function toggleHomeCard(card) {
  const key = card.dataset.homeKey;
  expandedHomeCard = expandedHomeCard === key ? null : key;
  refreshDashboard();
}

function openHomeTarget(card) {
  const target = card.dataset.homeTarget;
  setView(target === "summary" ? "summaries" : "transcripts");
  window.requestAnimationFrame(() => {
    const selector = target === "summary"
      ? `[data-summary-id="${card.dataset.summaryId || ""}"]`
      : `[data-recording-id="${card.dataset.recordingId || ""}"]`;
    const fallback = target === "summary" ? els.summaries : els.recordings;
    const element = document.querySelector(selector) || fallback;
    if (!element) return;
    element.scrollIntoView({ block: "start", behavior: "smooth" });
    if (element instanceof HTMLElement && element.tabIndex >= 0) {
      element.focus({ preventScroll: true });
    }
  });
}

function compactText(value, fallback = "", maxLength = 120) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return fallback;
  if (text.length <= maxLength) return text;
  return `${text.slice(0, Math.max(0, maxLength - 3)).trim()}...`;
}

function renderReceivers(data) {
  els.receiverStatus.innerHTML = "";
  if (!data.repeaters.length) {
    setEmpty(els.receiverStatus, "No repeaters configured.");
    return;
  }
  const byRepeater = new Map(data.receiver_status.map((row) => [row.repeater_id, row]));
  for (const repeater of data.repeaters) {
    const status = byRepeater.get(repeater.id) || { state: repeater.enabled ? "pending" : "disabled", message: "" };
    const level = status.level_proxy == null ? "n/a" : Number(status.level_proxy).toFixed(3);
    els.receiverStatus.appendChild(
      item(`
        <div class="item-head">
          <div>
            <h3>${callsignTextHtml(repeater.name)}</h3>
            <p class="muted">${Number(repeater.frequency_mhz).toFixed(6)} MHz</p>
          </div>
          <span class="pill state-${escapeHtml(status.state)}">${escapeHtml(status.state)}</span>
        </div>
        <div class="meta">
          <span class="pill">level ${level}</span>
          <span class="pill">squelch ${repeater.squelch_level}</span>
          <span class="pill">restarts ${status.restart_count || 0}</span>
        </div>
        <p class="muted">${callsignTextHtml(status.message || "")}</p>
      `)
    );
  }
}

function renderActivity(activity) {
  if (!els.activityChart) return;
  els.activityChart.innerHTML = "";
  if (!activity || !Array.isArray(activity.buckets) || !activity.buckets.length) {
    if (els.activityWindow) els.activityWindow.textContent = formatActivityWindowLabel(activity);
    setEmpty(els.activityChart, "No activity data available.");
    return;
  }

  const repeaters = Array.isArray(activity.repeaters) ? activity.repeaters : [];
  const windowLabel = formatActivityWindowLabel(activity);
  const totalCount = repeaters.reduce((sum, repeater) => sum + Number(repeater.total_count || 0), 0);
  const totalSeconds = repeaters.reduce((sum, repeater) => sum + Number(repeater.total_duration_seconds || 0), 0);
  if (els.activityWindow) {
    els.activityWindow.textContent = totalCount
      ? `${windowLabel} - ${totalCount} ${totalCount === 1 ? "transmission" : "transmissions"} - ${formatDuration(totalSeconds)}`
      : windowLabel;
  }

  if (!repeaters.length) {
    setEmpty(els.activityChart, "No repeaters configured.");
    return;
  }

  if (!totalCount) {
    setEmpty(els.activityChart, `No activity in ${windowLabel.toLowerCase()}.`);
    return;
  }

  const maxBucketValue = Math.max(
    1,
    ...repeaters.flatMap((repeater) =>
      repeater.buckets.map((bucket) => Number(bucket.duration_seconds || 0) || Number(bucket.count || 0))
    )
  );
  const rows = [...repeaters].sort((left, right) =>
    Number(right.total_count || 0) - Number(left.total_count || 0) || String(left.name).localeCompare(String(right.name))
  );
  const chart = document.createElement("div");
  chart.className = "activity-rows";
  chart.style.setProperty("--bucket-count", String(activity.buckets.length));

  for (const repeater of rows) {
    const row = document.createElement("div");
    row.className = "activity-row";
    const cells = repeater.buckets.map((bucket, index) => activityCell(bucket, activity.buckets[index], maxBucketValue)).join("");
    row.innerHTML = `
      <div class="activity-label">
        <h3>${callsignTextHtml(repeater.name)}</h3>
        <p class="muted">${repeater.frequency_mhz ? `${Number(repeater.frequency_mhz).toFixed(6)} MHz` : ""}</p>
        <div class="meta">
          <span class="pill">${Number(repeater.total_count || 0)} heard</span>
          <span class="pill">${formatDuration(Number(repeater.total_duration_seconds || 0))}</span>
        </div>
      </div>
      <div class="activity-track">
        <div class="activity-bars">${cells}</div>
        ${activityAxis(activity)}
      </div>
    `;
    chart.appendChild(row);
  }
  els.activityChart.appendChild(chart);
}

function activityCell(bucket, windowBucket, maxBucketValue) {
  const count = Number(bucket.count || 0);
  const duration = Number(bucket.duration_seconds || 0);
  const value = duration || count;
  const level = count ? Math.min(0.95, 0.22 + (value / maxBucketValue) * 0.73) : 0;
  const title = `${formatActivityDateTime(windowBucket.start_time)} to ${formatActivityDateTime(windowBucket.end_time)}: ${count} ${count === 1 ? "transmission" : "transmissions"}, ${formatDuration(duration)}`;
  return `<span class="activity-cell${count ? " active" : ""}" style="--activity-level: ${level.toFixed(2)}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}"></span>`;
}

function activityAxis(activity) {
  const start = new Date(activity.start_time);
  const end = new Date(activity.end_time);
  const middle = new Date(start.getTime() + (end.getTime() - start.getTime()) / 2);
  return `
    <div class="activity-axis">
      ${activityAxisTick("24h ago", start)}
      ${activityAxisTick("12h ago", middle)}
      ${activityAxisTick("now", end)}
    </div>
  `;
}

function activityAxisTick(label, value) {
  return `<span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(formatAxisTime(value))}</small></span>`;
}

function repeaterEditFormHtml(repeater) {
  return `
    <form class="form-grid repeater-edit-form">
      <label>
        <span>Name</span>
        <input name="name" required value="${escapeHtml(repeater.name)}" />
      </label>
      <label>
        <span>Frequency MHz</span>
        <input name="frequency_mhz" required type="number" step="0.000001" min="24" max="1766" value="${Number(repeater.frequency_mhz).toFixed(6)}" />
      </label>
      <label>
        <span>Transmit MHz</span>
        <input name="transmit_frequency_mhz" type="number" step="0.000001" min="24" max="1766" value="${repeater.transmit_frequency_mhz ? Number(repeater.transmit_frequency_mhz).toFixed(6) : ""}" />
      </label>
      <label>
        <span>Tone</span>
        <input name="tone" value="${escapeHtml(repeater.tone || "")}" />
      </label>
      <label>
        <span>Squelch</span>
        <input name="squelch_level" type="number" min="0" max="200" value="${repeater.squelch_level}" />
      </label>
      <label>
        <span>Sample rate</span>
        <input name="sample_rate" type="number" min="8000" value="${repeater.sample_rate}" />
      </label>
      <label>
        <span>Gain</span>
        <input name="gain" value="${escapeHtml(repeater.gain)}" />
      </label>
      <label>
        <span>PPM</span>
        <input name="ppm" type="number" min="-200" max="200" value="${repeater.ppm}" />
      </label>
      <label>
        <span>Location</span>
        <input name="location" value="${escapeHtml(repeater.location || "")}" />
      </label>
      <label>
        <span>Coverage</span>
        <input name="coverage_area" value="${escapeHtml(repeater.coverage_area || "")}" />
      </label>
      <label>
        <span>Type</span>
        <input name="repeater_type" value="${escapeHtml(repeater.repeater_type || "")}" />
      </label>
      <label>
        <span>Notes</span>
        <input name="notes" value="${escapeHtml(repeater.notes || "")}" />
      </label>
      <label class="check">
        <input name="enabled" type="checkbox" ${repeater.enabled ? "checked" : ""} />
        <span>Enabled</span>
      </label>
      <div class="button-row">
        <button type="submit">Save</button>
        <button class="secondary" data-cancel-edit="${repeater.id}" type="button">Cancel</button>
      </div>
      <p class="muted form-status" data-save-status aria-live="polite"></p>
    </form>
  `;
}

function removeRepeaterEditForm() {
  const form = els.repeaters ? els.repeaters.querySelector(".repeater-edit-form") : null;
  if (form) form.remove();
  editingRepeaterId = null;
}

function openRepeaterEdit(row, repeater) {
  removeRepeaterEditForm();
  editingRepeaterId = String(repeater.id);
  row.insertAdjacentHTML("beforeend", repeaterEditFormHtml(repeater));

  const editForm = row.querySelector(".repeater-edit-form");
  const editStatus = editForm.querySelector("[data-save-status]");
  editForm.querySelector("[data-cancel-edit]").addEventListener("click", () => {
    setSaveStatus(editStatus, "");
    removeRepeaterEditForm();
  });
  editForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const result = await withSaveFeedback(editForm, editStatus, {
      saving: "Saving repeater...",
      saved: "Repeater saved.",
    }, () =>
      fetchJson(`/api/repeaters/${repeater.id}`, {
        method: "PUT",
        body: JSON.stringify(repeaterPayloadFromForm(editForm)),
      })
    );
    if (!result.ok) return;
    window.setTimeout(() => {
      removeRepeaterEditForm();
      refreshDashboard();
    }, saveConfirmationMs);
  });
  editForm.elements.name.focus();
}

function renderRepeaters(repeaters) {
  if (editingRepeaterId !== null) return;
  els.repeaters.innerHTML = "";
  if (!repeaters.length) {
    setEmpty(els.repeaters, "No repeaters configured.");
    return;
  }
  for (const repeater of repeaters) {
    const row = item(`
      <div class="item-head">
        <div>
          <h3>${callsignTextHtml(repeater.name)}</h3>
          <p class="muted">${Number(repeater.frequency_mhz).toFixed(6)} MHz</p>
        </div>
        <div class="item-actions">
          <button data-edit-repeater="${repeater.id}" type="button">Edit</button>
          <button class="danger" data-delete-repeater="${repeater.id}" type="button">Delete</button>
        </div>
      </div>
      <div class="meta">
        <span class="pill">${repeater.enabled ? "enabled" : "disabled"}</span>
        <span class="pill">mode ${escapeHtml(repeater.mode)}</span>
        <span class="pill">gain ${escapeHtml(repeater.gain)}</span>
        <span class="pill">squelch ${repeater.squelch_level}</span>
        ${repeater.tone ? `<span class="pill">tone ${escapeHtml(repeater.tone)}</span>` : ""}
        ${repeater.location ? `<span class="pill">${escapeHtml(repeater.location)}</span>` : ""}
        <span class="pill">ppm ${repeater.ppm}</span>
      </div>
    `);
    row.querySelector("[data-edit-repeater]").addEventListener("click", () => {
      openRepeaterEdit(row, repeater);
    });
    row.querySelector("[data-delete-repeater]").addEventListener("click", async () => {
      removeRepeaterEditForm();
      await fetchJson(`/api/repeaters/${repeater.id}`, { method: "DELETE" });
      refreshDashboard();
    });
    els.repeaters.appendChild(row);
  }
}

function renderSdrWindow(windowData) {
  if (!els.sdrWindow) return;
  els.sdrWindow.innerHTML = "";
  if (!windowData || !Number(windowData.center_frequency_mhz)) {
    if (els.sdrWindowStatus) els.sdrWindowStatus.textContent = "No repeaters";
    setEmpty(els.sdrWindow, "Enable at least one repeater to calculate the SDR window.");
    return;
  }

  if (els.sdrWindowStatus) {
    els.sdrWindowStatus.textContent = windowData.can_monitor ? "in range" : "attention";
    els.sdrWindowStatus.className = `pill ${windowData.can_monitor ? "state-running" : "state-error"}`;
  }

  const lower = Number(windowData.lower_usable_mhz);
  const upper = Number(windowData.upper_usable_mhz);
  const span = Math.max(0.000001, upper - lower);
  const markers = (windowData.repeaters || [])
    .map((repeater) => {
      const position = ((Number(repeater.frequency_mhz) - lower) / span) * 100;
      const clamped = Math.max(0, Math.min(100, position));
      const title = `${repeater.name} ${Number(repeater.frequency_mhz).toFixed(6)} MHz - ${repeater.message}`;
      return `
        <span class="sdr-marker ${escapeHtml(repeater.status)}" style="left: ${clamped.toFixed(2)}%" title="${escapeHtml(title)}">
          <span>${callsignTextHtml(repeater.name)}</span>
        </span>
      `;
    })
    .join("");
  const warnings = (windowData.warnings || []).map((warning) => `<li>${escapeHtml(warning)}</li>`).join("");

  els.sdrWindow.innerHTML = `
    <div class="sdr-metrics">
      <div><span class="metric-label">Center</span><strong>${Number(windowData.center_frequency_mhz).toFixed(6)} MHz</strong></div>
      <div><span class="metric-label">Sample rate</span><strong>${Number(windowData.sample_rate_hz).toLocaleString()} Hz</strong></div>
      <div><span class="metric-label">Usable range</span><strong>${lower.toFixed(6)}-${upper.toFixed(6)} MHz</strong></div>
      <div><span class="metric-label">Guard band</span><strong>${Number(windowData.guard_band_khz).toFixed(0)} kHz</strong></div>
    </div>
    <div class="sdr-band" aria-label="Current SDR usable passband">
      <span class="sdr-edge left">${lower.toFixed(3)}</span>
      <span class="sdr-center" style="left: 50%">center</span>
      ${markers}
      <span class="sdr-edge right">${upper.toFixed(3)}</span>
    </div>
    ${
      Number(windowData.recommended_center_frequency_mhz)
        ? `<p class="muted">Recommended center: ${Number(windowData.recommended_center_frequency_mhz).toFixed(6)} MHz. Required sample rate: ${Number(windowData.required_sample_rate_hz || 0).toLocaleString()} Hz.</p>`
        : ""
    }
    ${warnings ? `<ul class="sdr-warnings">${warnings}</ul>` : ""}
  `;
}

function renderRecordings(recordings, transcripts, keywordRules = []) {
  currentRecordings = Array.isArray(recordings) ? recordings : [];
  currentTranscripts = Array.isArray(transcripts) ? transcripts : [];
  currentKeywordRules = Array.isArray(keywordRules) ? keywordRules : [];
  if (activeView !== "transcripts") {
    transcriptNeedsRender = true;
    return;
  }
  renderRecordingsNow();
}

function flushTranscriptRender() {
  if (activeView !== "transcripts") return;
  if (!transcriptNeedsRender && transcriptRenderSignature) {
    applyTranscriptSearchFilter();
    return;
  }
  renderRecordingsNow();
}

function renderRecordingsNow() {
  const recordings = currentRecordings;
  const transcripts = currentTranscripts;
  const keywordRules = currentKeywordRules;
  const nextSignature = transcriptRenderFingerprint(recordings, transcripts, keywordRules);
  const shouldRebuild = nextSignature !== transcriptRenderSignature;
  if (isRecordingPlaybackActive()) {
    if (shouldRebuild) {
      updateRenderedTranscriptHighlights(recordings, transcripts, keywordRules);
      transcriptRenderSignature = nextSignature;
      transcriptHighlightSignature = transcriptHighlightFingerprint();
      transcriptNeedsRender = true;
    }
    applyTranscriptSearchFilter();
    return;
  }
  if (!shouldRebuild) {
    transcriptNeedsRender = false;
    applyTranscriptSearchFilter();
    return;
  }
  transcriptRenderSignature = nextSignature;
  transcriptNeedsRender = false;
  els.recordings.innerHTML = "";
  if (!recordings.length) {
    setEmpty(els.recordings, "No transmissions recorded yet.");
    updateTranscriptSearchStatus(0, 0);
    transcriptHighlightSignature = transcriptHighlightFingerprint();
    return;
  }
  const transcriptByRecording = new Map(transcripts.map((t) => [t.recording_id, t]));
  const fragment = document.createDocumentFragment();
  for (const recording of recordings) {
    const transcript = transcriptByRecording.get(recording.id);
    const audioAvailable = recording.status !== "audio_deleted";
    const row = item(`
        <div class="item-head">
          <div>
            <h3>${callsignTextHtml(recording.repeater_name)}</h3>
            <p class="muted">${formatTime(recording.start_time)} ${recording.duration_seconds ? `for ${Number(recording.duration_seconds).toFixed(1)}s` : ""}</p>
          </div>
          <div class="item-actions">
            <span class="pill">${escapeHtml(recording.status)}</span>
            <button class="danger" data-delete-recording="${recording.id}" type="button">Delete</button>
          </div>
        </div>
        ${audioAvailable ? `<audio controls preload="none" src="/api/recordings/${recording.id}/audio"></audio>` : ""}
        <p class="transcript">${transcriptTextHtml(transcript ? transcript.text : "Transcript pending.", keywordRules, recording, transcriptSearchTokens())}</p>
    `);
    row.dataset.recordingId = String(recording.id);
    row.dataset.searchText = transcriptSearchText(recording, transcript);
    row.tabIndex = -1;
    row.querySelector("[data-delete-recording]").addEventListener("click", async () => {
      stopRecordingPlayback();
      await fetchJson(`/api/recordings/${recording.id}`, { method: "DELETE" });
      refreshDashboard();
    });
    fragment.appendChild(row);
  }
  els.recordings.appendChild(fragment);
  transcriptHighlightSignature = transcriptHighlightFingerprint();
  applyTranscriptSearchFilter();
}

function updateRenderedTranscriptHighlights(recordings, transcripts, keywordRules = []) {
  const recordingById = new Map(recordings.map((recording) => [String(recording.id), recording]));
  const transcriptByRecording = new Map(transcripts.map((transcript) => [String(transcript.recording_id), transcript]));
  for (const row of els.recordings.querySelectorAll("[data-recording-id]")) {
    const recording = recordingById.get(String(row.dataset.recordingId));
    const transcript = transcriptByRecording.get(String(row.dataset.recordingId));
    const transcriptElement = row.querySelector(".transcript");
    if (!recording || !transcriptElement) continue;
    row.dataset.searchText = transcriptSearchText(recording, transcript);
    transcriptElement.innerHTML = transcriptTextHtml(transcript ? transcript.text : "Transcript pending.", keywordRules, recording, transcriptSearchTokens());
  }
}

function transcriptRenderFingerprint(recordings, transcripts, keywordRules = []) {
  return JSON.stringify({
    recordings: recordings.map((recording) => [
      recording.id,
      recording.repeater_id,
      recording.repeater_name,
      recording.frequency_mhz,
      recording.start_time,
      recording.duration_seconds,
      recording.status,
    ]),
    transcripts: transcripts.map((transcript) => [
      transcript.id,
      transcript.recording_id,
      transcript.updated_at,
      transcript.text,
    ]),
    keyword_rules: keywordRules.map((rule) => [
      rule.id,
      rule.keyword,
      rule.is_regex,
      rule.case_sensitive,
      rule.repeater_id,
      rule.notify_transcript,
      rule.enabled,
    ]),
  });
}

function transcriptSearchText(recording, transcript) {
  return [
    recording.id,
    recording.repeater_name,
    recording.frequency_mhz,
    recording.status,
    recording.start_time,
    transcript && transcript.text,
    transcript && transcript.original_text,
    transcript && transcript.corrected_text,
    transcript && transcript.backend,
  ]
    .filter((value) => value != null && value !== "")
    .join(" ")
    .toLocaleLowerCase();
}

function transcriptSearchTokens() {
  return transcriptSearchTerm
    .trim()
    .toLocaleLowerCase()
    .split(/\s+/)
    .filter(Boolean);
}

function transcriptHighlightFingerprint() {
  return `${transcriptRenderSignature}|${transcriptSearchTerm}`;
}

function applyTranscriptSearchFilter() {
  if (!els.recordings || activeView !== "transcripts") return;
  const tokens = transcriptSearchTokens();
  const nextHighlightSignature = transcriptHighlightFingerprint();
  if (nextHighlightSignature !== transcriptHighlightSignature) {
    updateRenderedTranscriptHighlights(currentRecordings, currentTranscripts, currentKeywordRules);
    transcriptHighlightSignature = nextHighlightSignature;
  }
  let visible = 0;
  let total = 0;
  for (const row of els.recordings.querySelectorAll("[data-recording-id]")) {
    total += 1;
    const searchText = row.dataset.searchText || "";
    const matched = !tokens.length || tokens.every((token) => searchText.includes(token));
    row.hidden = !matched;
    if (matched) visible += 1;
  }
  updateTranscriptSearchStatus(total, visible);
}

function updateTranscriptSearchStatus(total, visible) {
  if (!els.transcriptSearchStatus) return;
  if (!transcriptSearchTerm.trim()) {
    els.transcriptSearchStatus.textContent = "";
    return;
  }
  els.transcriptSearchStatus.textContent = visible
    ? `Showing ${visible} of ${total} transcript${total === 1 ? "" : "s"}.`
    : "No matching transcripts.";
}

function isRecordingPlaybackActive() {
  return Array.from(els.recordings.querySelectorAll("audio")).some((audio) => !audio.paused && !audio.ended);
}

function stopRecordingPlayback() {
  for (const audio of els.recordings.querySelectorAll("audio")) {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
  }
}

function pauseRecordingPlayback() {
  for (const audio of els.recordings.querySelectorAll("audio")) {
    if (!audio.paused && !audio.ended) {
      audio.pause();
    }
  }
}

function renderSummaries(summaries, repeaters = []) {
  currentSummaries = Array.isArray(summaries) ? summaries : [];
  currentRepeaters = Array.isArray(repeaters) ? repeaters : [];
  renderSummaryScopeOptions(repeaters);
  const repeaterNames = new Map(currentRepeaters.map((repeater) => [String(repeater.id), repeater.name]));
  maybeClearAdHocSummary(currentSummaries);
  renderAdHocSummary(repeaterNames);
  const visibleSummaries = filteredSummaries(currentSummaries);
  renderSummaryStats(visibleSummaries);
  els.summaries.innerHTML = "";
  if (!visibleSummaries.length) {
    setEmpty(els.summaries, "No saved summaries match this view.");
    updateSummarySearchStatus(0, currentSummaries.length);
    return;
  }
  const searchTokens = summarySearchTokens();
  for (const summary of visibleSummaries) {
    const sourceCount = summarySourceCount(summary);
    const row = item(`
        <div class="summary-card-head">
          <div>
            <h3>${escapeHtml(formatSummaryRange(summary))}</h3>
            <p class="muted">${callsignTextHtml(summaryScope(summary, repeaterNames))} - ${escapeHtml(formatSummaryWindow(summary.window_name))}</p>
          </div>
          <span class="pill state-${escapeHtml(summary.status)}">${escapeHtml(formatStatus(summary.status))}</span>
        </div>
        <p class="summary-text">${summaryTextHtml(summary.text, searchTokens)}</p>
        <div class="summary-card-foot">
          <div class="meta">
            <span class="pill">${escapeHtml(formatTime(summary.created_at))}</span>
            <span class="pill">${escapeHtml(formatSummaryRange(summary))}</span>
            <span class="pill">${sourceCount} ${sourceCount === 1 ? "recording" : "recordings"}</span>
            <span class="pill">${escapeHtml(summary.model || "local")}</span>
          </div>
          <button class="danger" data-delete-summary="${summary.id}" type="button">Delete</button>
        </div>
      `);
    row.classList.add("summary-card");
    row.dataset.summaryId = String(summary.id);
    row.dataset.searchText = summarySearchText(summary, repeaterNames);
    row.tabIndex = -1;
    row.querySelector("[data-delete-summary]").addEventListener("click", async () => {
      await fetchJson(`/api/summaries/${summary.id}`, { method: "DELETE" });
      refreshDashboard();
    });
    els.summaries.appendChild(row);
  }
  updateSummarySearchStatus(visibleSummaries.length, currentSummaries.length);
}

function renderSummaryScopeOptions(repeaters) {
  if (!els.summaryRepeater) return;
  const nextValues = ["", ...repeaters.map((repeater) => String(repeater.id))];
  const currentValues = [...els.summaryRepeater.options].map((option) => option.value);
  const labelsMatch = repeaters.every((repeater) => {
    const option = [...els.summaryRepeater.options].find((candidate) => candidate.value === String(repeater.id));
    return option && option.textContent === repeater.name;
  });
  if (nextValues.length === currentValues.length && nextValues.every((value, index) => value === currentValues[index]) && labelsMatch) {
    return;
  }
  const currentValue = els.summaryRepeater.value;
  els.summaryRepeater.innerHTML = `<option value="">All repeaters</option>`;
  for (const repeater of repeaters) {
    const option = document.createElement("option");
    option.value = String(repeater.id);
    option.textContent = repeater.name;
    els.summaryRepeater.appendChild(option);
  }
  if ([...els.summaryRepeater.options].some((option) => option.value === currentValue)) {
    els.summaryRepeater.value = currentValue;
  }
}

function renderActivityChatScopeOptions(repeaters) {
  if (!els.activityChatRepeater) return;
  const nextValues = ["", ...repeaters.map((repeater) => String(repeater.id))];
  const currentValues = [...els.activityChatRepeater.options].map((option) => option.value);
  const labelsMatch = repeaters.every((repeater) => {
    const option = [...els.activityChatRepeater.options].find((candidate) => candidate.value === String(repeater.id));
    return option && option.textContent === repeater.name;
  });
  if (nextValues.length === currentValues.length && nextValues.every((value, index) => value === currentValues[index]) && labelsMatch) {
    return;
  }
  const currentValue = els.activityChatRepeater.value;
  els.activityChatRepeater.innerHTML = `<option value="">All repeaters</option>`;
  for (const repeater of repeaters) {
    const option = document.createElement("option");
    option.value = String(repeater.id);
    option.textContent = repeater.name;
    els.activityChatRepeater.appendChild(option);
  }
  if ([...els.activityChatRepeater.options].some((option) => option.value === currentValue)) {
    els.activityChatRepeater.value = currentValue;
  }
}

function renderActivityChatMessages() {
  if (!els.activityChatMessages) return;
  els.activityChatMessages.innerHTML = "";
  if (!activityChatMessages.length) {
    setEmpty(els.activityChatMessages, "No chat messages yet.");
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const message of activityChatMessages) {
    const row = document.createElement("article");
    row.className = `chat-message ${message.role === "user" ? "user" : "assistant"}`;
    const meta = message.role === "assistant" && message.meta
      ? `<div class="meta">
          <span class="pill">${escapeHtml(message.meta.model || "model")}</span>
          <span class="pill">${formatCount(message.meta.transcripts || 0)} transcript${message.meta.transcripts === 1 ? "" : "s"}</span>
          <span class="pill">${formatCount(message.meta.summaries || 0)} summar${message.meta.summaries === 1 ? "y" : "ies"}</span>
        </div>`
      : "";
    row.innerHTML = `
      <p class="chat-message-role">${message.role === "user" ? "You" : "Assistant"}</p>
      <p class="chat-message-text">${callsignTextHtml(message.content)}</p>
      ${meta}
    `;
    fragment.appendChild(row);
  }
  els.activityChatMessages.appendChild(fragment);
  els.activityChatMessages.scrollTop = els.activityChatMessages.scrollHeight;
}

function activityChatHistoryPayload() {
  return activityChatMessages
    .filter((message) => message.role === "user" || message.role === "assistant")
    .map((message) => ({ role: message.role, content: message.content }));
}

function canonicalSummaryWindow(windowName) {
  const aliases = {
    last_15_minutes: "quarter_hour",
    last_hour: "hour",
    today: "day",
  };
  const value = String(windowName || "quarter_hour");
  return aliases[value] || value;
}

function selectedSummaryWindow() {
  const selected = els.summaryForm && els.summaryForm.elements.window_name
    ? els.summaryForm.elements.window_name.value
    : "quarter_hour";
  return canonicalSummaryWindow(selected);
}

function selectedSummaryRepeaterId() {
  return els.summaryRepeater && els.summaryRepeater.value ? String(els.summaryRepeater.value) : "";
}

function filteredSummaries(summaries) {
  const selectedWindow = selectedSummaryWindow();
  const repeaterId = selectedSummaryRepeaterId();
  const tokens = summarySearchTokens();
  const repeaterNames = new Map(currentRepeaters.map((repeater) => [String(repeater.id), repeater.name]));
  return summaries
    .filter((summary) => String(summary.window_name || "") === selectedWindow)
    .filter((summary) => repeaterId ? String(summary.repeater_id) === repeaterId : summary.repeater_id == null)
    .filter((summary) => {
      if (!tokens.length) return true;
      const haystack = summarySearchText(summary, repeaterNames).toLocaleLowerCase();
      return tokens.every((token) => haystack.includes(token.toLocaleLowerCase()));
    })
    .sort((a, b) => new Date(b.start_time || b.created_at || 0) - new Date(a.start_time || a.created_at || 0));
}

function summarySearchTokens() {
  return summarySearchTerm
    .trim()
    .split(/\s+/)
    .filter(Boolean);
}

function summarySearchText(summary, repeaterNames = new Map()) {
  return [
    formatSummaryWindow(summary.window_name),
    formatSummaryRange(summary),
    summaryScope(summary, repeaterNames),
    summary.text,
    summary.model,
    summary.status,
  ].filter(Boolean).join(" ");
}

function updateSummarySearchStatus(visible, total) {
  if (!els.summarySearchStatus) return;
  const tokens = summarySearchTokens();
  if (!tokens.length) {
    els.summarySearchStatus.textContent = "";
    return;
  }
  els.summarySearchStatus.textContent = visible
    ? `Showing ${visible} matching summar${visible === 1 ? "y" : "ies"}.`
    : `No matching summaries in this ${formatSummaryWindow(selectedSummaryWindow()).toLocaleLowerCase()} timeline.`;
}

function maybeClearAdHocSummary(summaries) {
  if (!adHocSummary || !adHocSummary.created_at) return;
  const adHocCreatedAt = new Date(adHocSummary.created_at).getTime();
  if (!Number.isFinite(adHocCreatedAt)) return;
  const newerSavedSummary = summaries.some((summary) => {
    const createdAt = new Date(summary.created_at || 0).getTime();
    return Number.isFinite(createdAt) && createdAt > adHocCreatedAt;
  });
  if (newerSavedSummary) {
    adHocSummary = null;
  }
}

function renderAdHocSummary(repeaterNames) {
  if (!els.adHocSummary) return;
  if (!adHocSummary || canonicalSummaryWindow(adHocSummary.window_name) !== selectedSummaryWindow()) {
    els.adHocSummary.hidden = true;
    els.adHocSummary.innerHTML = "";
    return;
  }
  const repeaterId = selectedSummaryRepeaterId();
  if (repeaterId ? String(adHocSummary.repeater_id) !== repeaterId : adHocSummary.repeater_id != null) {
    els.adHocSummary.hidden = true;
    els.adHocSummary.innerHTML = "";
    return;
  }
  const sourceCount = summarySourceCount(adHocSummary);
  els.adHocSummary.hidden = false;
  els.adHocSummary.innerHTML = `
    <div class="summary-card-head">
      <div>
        <h3>Ad Hoc Summary</h3>
        <p class="muted">${callsignTextHtml(summaryScope(adHocSummary, repeaterNames))} - ${escapeHtml(formatSummaryRange(adHocSummary))}</p>
      </div>
      <span class="pill state-${escapeHtml(adHocSummary.status)}">${escapeHtml(formatStatus(adHocSummary.status))}</span>
    </div>
    <p class="summary-text">${summaryTextHtml(adHocSummary.text, summarySearchTokens())}</p>
    <div class="summary-card-foot">
      <div class="meta">
        <span class="pill">${escapeHtml(formatTime(adHocSummary.created_at))}</span>
        <span class="pill">${sourceCount} ${sourceCount === 1 ? "recording" : "recordings"}</span>
        <span class="pill">${escapeHtml(adHocSummary.model || "local")}</span>
      </div>
    </div>
  `;
}

function renderSummaryStats(summaries) {
  if (!els.summaryStats) return;
  const completed = summaries.filter((summary) => summary.status === "completed").length;
  const latest = summaries[0] ? formatSummaryRange(summaries[0]) : "None";
  els.summaryStats.innerHTML = `
    <div>
      <span class="metric-label">Showing</span>
      <strong>${summaries.length}</strong>
    </div>
    <div>
      <span class="metric-label">Completed</span>
      <strong>${completed}</strong>
    </div>
    <div>
      <span class="metric-label">Latest Period</span>
      <strong>${escapeHtml(latest)}</strong>
    </div>
  `;
}

function formatSummaryWindow(windowName) {
  const labels = {
    quarter_hour: "15 Minutes",
    hour: "Hour",
    day: "Day",
    last_15_minutes: "Last 15 Minutes",
    last_hour: "Last Hour",
    today: "Today",
  };
  return labels[windowName] || String(windowName || "Summary").replaceAll("_", " ");
}

function formatStatus(status) {
  return String(status || "unknown").replaceAll("_", " ");
}

function summaryScope(summary, repeaterNames) {
  if (summary.repeater_id == null) return "All repeaters";
  return repeaterNames.get(String(summary.repeater_id)) || `Repeater ${summary.repeater_id}`;
}

function formatSummaryRange(summary) {
  if (!summary.start_time || !summary.end_time) return formatSummaryWindow(summary.window_name);
  if (canonicalSummaryWindow(summary.window_name) === "day") {
    const start = new Date(summary.start_time);
    const end = new Date(summary.end_time);
    if (!Number.isNaN(start.getTime()) && !Number.isNaN(end.getTime())) {
      const sameLocalDate = start.toDateString() === new Date(end.getTime() - 1).toDateString();
      if (sameLocalDate) {
        return start.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
      }
    }
  }
  return `${formatAxisTime(summary.start_time)}-${formatAxisTime(summary.end_time)}`;
}

function summarySourceCount(summary) {
  if (!summary.source_transcript_ids) return 0;
  if (Array.isArray(summary.source_transcript_ids)) return summary.source_transcript_ids.length;
  try {
    const parsed = JSON.parse(summary.source_transcript_ids);
    return Array.isArray(parsed) ? parsed.length : 0;
  } catch {
    return 0;
  }
}

function ruleEditFormHtml(rule) {
  return `
    <form class="form-grid rule-edit-form">
      <label>
        <span>Keyword or regex</span>
        <input name="keyword" required value="${escapeHtml(rule.keyword)}" />
      </label>
      <label>
        <span>Cooldown minutes</span>
        <input name="cooldown_minutes" type="number" min="0" value="${rule.cooldown_minutes}" />
      </label>
      <label class="check">
        <input name="is_regex" type="checkbox" ${rule.is_regex ? "checked" : ""} />
        <span>Regex</span>
      </label>
      <label class="check">
        <input name="case_sensitive" type="checkbox" ${rule.case_sensitive ? "checked" : ""} />
        <span>Case sensitive</span>
      </label>
      <label class="check">
        <input name="notify_transcript" type="checkbox" ${rule.notify_transcript ? "checked" : ""} />
        <span>Transcript alerts</span>
      </label>
      <label class="check">
        <input name="notify_summary" type="checkbox" ${rule.notify_summary ? "checked" : ""} />
        <span>Summary alerts</span>
      </label>
      <label class="check">
        <input name="enabled" type="checkbox" ${rule.enabled ? "checked" : ""} />
        <span>Enabled</span>
      </label>
      <div class="button-row">
        <button type="submit">Save</button>
        <button class="secondary" data-cancel-rule-edit="${rule.id}" type="button">Cancel</button>
      </div>
      <p class="muted form-status" data-save-status aria-live="polite"></p>
    </form>
  `;
}

function removeRuleEditForm() {
  const form = els.rules ? els.rules.querySelector(".rule-edit-form") : null;
  if (form) form.remove();
  editingRuleId = null;
}

function openRuleEdit(row, rule) {
  removeRuleEditForm();
  editingRuleId = String(rule.id);
  row.insertAdjacentHTML("beforeend", ruleEditFormHtml(rule));

  const editForm = row.querySelector(".rule-edit-form");
  const editStatus = editForm.querySelector("[data-save-status]");
  editForm.querySelector("[data-cancel-rule-edit]").addEventListener("click", () => {
    setSaveStatus(editStatus, "");
    removeRuleEditForm();
    els.pushStatus.textContent = "";
  });
  editForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = keywordRulePayloadFromForm(editForm);
    if (!payload.notify_transcript && !payload.notify_summary) {
      setSaveStatus(editStatus, "Choose transcript alerts, summary alerts, or both.", "state-error");
      return;
    }
    const result = await withSaveFeedback(editForm, editStatus, {
      saving: "Saving rule...",
      saved: "Rule saved.",
    }, () =>
      fetchJson(`/api/notifications/rules/${rule.id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      })
    );
    if (!result.ok) return;
    els.pushStatus.textContent = "";
    window.setTimeout(() => {
      removeRuleEditForm();
      refreshDashboard();
    }, saveConfirmationMs);
  });
  editForm.elements.keyword.focus();
}

function renderRules(rules) {
  if (editingRuleId !== null) return;
  els.rules.innerHTML = "";
  if (!rules.length) {
    setEmpty(els.rules, "No keyword rules configured.");
    return;
  }
  for (const rule of rules) {
    const row = item(`
      <div class="item-head">
        <div>
          <h3>${callsignTextHtml(rule.keyword)}</h3>
          <p class="muted">cooldown ${rule.cooldown_minutes} minute(s)</p>
        </div>
        <div class="item-actions">
          <button data-edit-rule="${rule.id}" type="button">Edit</button>
          <button class="danger" data-delete-rule="${rule.id}" type="button">Delete</button>
        </div>
      </div>
      <div class="meta">
        <span class="pill">${rule.enabled ? "enabled" : "disabled"}</span>
        <span class="pill">${rule.is_regex ? "regex" : "phrase"}</span>
        <span class="pill">${rule.case_sensitive ? "case sensitive" : "case insensitive"}</span>
        <span class="pill">${rule.notify_transcript ? "transcripts" : "no transcripts"}</span>
        <span class="pill">${rule.notify_summary ? "summaries" : "no summaries"}</span>
      </div>
    `);
    row.querySelector("[data-edit-rule]").addEventListener("click", () => {
      openRuleEdit(row, rule);
    });
    row.querySelector("[data-delete-rule]").addEventListener("click", async () => {
      removeRuleEditForm();
      await fetchJson(`/api/notifications/rules/${rule.id}`, { method: "DELETE" });
      refreshDashboard();
    });
    els.rules.appendChild(row);
  }
}

function renderEvents(events) {
  els.events.innerHTML = "";
  if (!events.length) {
    setEmpty(els.events, "No notification history.");
    return;
  }
  for (const event of events) {
    const row = item(`
        <div class="item-head">
          <div>
            <h3>${callsignTextHtml(event.title)}</h3>
            <div class="meta">
              <span class="pill">${escapeHtml(formatEventType(event.source_type))}</span>
              <span class="pill">sent ${event.sent_count}</span>
            </div>
          </div>
          <button class="danger" data-delete-event="${event.id}" type="button">Delete</button>
        </div>
        <p>${callsignTextHtml(event.body)}</p>
        <p class="muted">${formatTime(event.created_at)}</p>
      `);
    row.querySelector("[data-delete-event]").addEventListener("click", async () => {
      await fetchJson(`/api/notifications/events/${event.id}`, { method: "DELETE" });
      refreshDashboard();
    });
    els.events.appendChild(row);
  }
}

function formatEventType(sourceType) {
  const labels = {
    receiver_status: "receiver down",
    receiver_recovered: "receiver restored",
    traffic: "traffic",
    transcript: "transcript",
    summary: "summary",
    test: "test",
  };
  return labels[sourceType] || String(sourceType || "event").replaceAll("_", " ");
}

async function refreshLogs() {
  if (!els.logs || !els.logLimit) return;
  const limit = Number(els.logLimit.value || 200);
  if (els.logStatus) {
    els.logStatus.textContent = "Loading logs...";
  }
  try {
    const data = await fetchJson(`/api/logs?limit=${encodeURIComponent(limit)}`);
    const lines = Array.isArray(data.lines) ? data.lines : [];
    els.logs.textContent = lines.length ? lines.join("\n") : "No log lines returned.";
    if (els.logStatus) {
      els.logStatus.textContent = data.available
        ? `Showing ${lines.length} recent RepeaterWatch service log line(s).`
        : data.error || "Logs are unavailable.";
    }
  } catch (error) {
    els.logs.textContent = "";
    if (els.logStatus) {
      els.logStatus.textContent = error.message;
    }
  }
}

async function refreshApiUsage() {
  if (!els.apiUsageChart || apiUsageRefreshInFlight) return;
  apiUsageRefreshInFlight = true;
  if (els.apiUsageStatus) {
    els.apiUsageStatus.textContent = "Loading API usage...";
  }
  try {
    const data = await fetchJson(`/api/api-usage?hours=${encodeURIComponent(apiUsageHours)}`);
    renderApiUsage(data);
  } catch (error) {
    if (els.apiUsageStatus) {
      els.apiUsageStatus.textContent = error.message;
    }
    if (els.apiUsageStats) els.apiUsageStats.innerHTML = "";
    if (els.apiUsageChart) els.apiUsageChart.innerHTML = "";
    if (els.apiUsageBreakdown) els.apiUsageBreakdown.innerHTML = "";
    if (els.apiUsageEvents) els.apiUsageEvents.innerHTML = "";
  } finally {
    apiUsageRefreshInFlight = false;
  }
}

function renderApiUsage(data) {
  const totals = data && data.totals ? data.totals : {};
  const callTypes = Array.isArray(data && data.call_types) ? data.call_types : [];
  const events = Array.isArray(data && data.recent_events) ? data.recent_events : [];
  renderApiUsageStats(totals);
  renderApiUsageChart(data, callTypes);
  renderApiUsageBreakdown(data);
  renderApiUsageEvents(events);
  if (els.apiUsageStatus) {
    const range = formatApiUsageWindowLabel(data);
    els.apiUsageStatus.textContent = totals.events
      ? `${range} - ${formatCount(totals.remote_calls)} remote call${totals.remote_calls === 1 ? "" : "s"}, ${formatCount(totals.skipped)} skipped.`
      : `${range} - no API usage events recorded yet.`;
  }
}

function renderApiUsageStats(totals) {
  if (!els.apiUsageStats) return;
  els.apiUsageStats.innerHTML = `
    <div>
      <span class="metric-label">Remote calls</span>
      <strong>${formatCount(totals.remote_calls)}</strong>
    </div>
    <div>
      <span class="metric-label">Skipped</span>
      <strong>${formatCount(totals.skipped)}</strong>
    </div>
    <div>
      <span class="metric-label">Errors</span>
      <strong>${formatCount(totals.errors)}</strong>
    </div>
    <div>
      <span class="metric-label">Audio sent</span>
      <strong>${formatDuration(totals.audio_duration_seconds)}</strong>
    </div>
    <div>
      <span class="metric-label">Tokens</span>
      <strong>${totals.token_events ? formatCount(totals.total_tokens) : "n/a"}</strong>
    </div>
  `;
}

function renderApiUsageChart(data, callTypes) {
  if (!els.apiUsageChart) return;
  els.apiUsageChart.innerHTML = "";
  const buckets = Array.isArray(data && data.buckets) ? data.buckets : [];
  if (!buckets.length) {
    setEmpty(els.apiUsageChart, "No usage bucket data available.");
    return;
  }
  const visible = callTypes.filter((row) => Number(row.events || 0) > 0);
  if (!visible.length) {
    setEmpty(els.apiUsageChart, "Usage tracking starts with this version; earlier API calls are not shown.");
    return;
  }
  const maxValue = Math.max(
    1,
    ...visible.flatMap((row) => row.buckets.map((bucket) => Number(bucket.remote_calls || 0) + Number(bucket.skipped || 0)))
  );
  const chart = document.createElement("div");
  chart.className = "api-usage-rows";
  chart.style.setProperty("--bucket-count", String(buckets.length));
  for (const rowData of visible) {
    const row = document.createElement("div");
    row.className = "api-usage-row";
    const cells = rowData.buckets.map((bucket, index) => apiUsageCell(bucket, buckets[index], maxValue)).join("");
    row.innerHTML = `
      <div class="api-usage-label">
        <h3>${escapeHtml(formatApiCallType(rowData.call_type))}</h3>
        <div class="meta">
          <span class="pill">${formatCount(rowData.remote_calls)} calls</span>
          <span class="pill">${formatCount(rowData.skipped)} skipped</span>
          ${rowData.errors ? `<span class="pill state-error">${formatCount(rowData.errors)} errors</span>` : ""}
        </div>
        <p class="muted">${apiUsageRowDetail(rowData)}</p>
      </div>
      <div class="api-usage-track">
        <div class="api-usage-bars">${cells}</div>
        ${apiUsageAxis(data)}
      </div>
    `;
    chart.appendChild(row);
  }
  els.apiUsageChart.appendChild(chart);
}

function apiUsageCell(bucket, windowBucket, maxValue) {
  const calls = Number(bucket.remote_calls || 0);
  const skipped = Number(bucket.skipped || 0);
  const errors = Number(bucket.errors || 0);
  const value = calls + skipped;
  const level = value ? Math.min(0.95, 0.22 + (value / maxValue) * 0.73) : 0;
  const classes = ["api-usage-cell"];
  if (calls) classes.push("active");
  if (skipped && !calls) classes.push("skipped");
  if (errors) classes.push("error");
  const title = `${formatActivityDateTime(windowBucket.start_time)}: ${formatCount(calls)} remote call${calls === 1 ? "" : "s"}, ${formatCount(skipped)} skipped${errors ? `, ${formatCount(errors)} error${errors === 1 ? "" : "s"}` : ""}`;
  return `<span class="${classes.join(" ")}" style="--usage-level: ${level.toFixed(2)}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}"></span>`;
}

function apiUsageAxis(data) {
  const start = new Date(data.start_time);
  const end = new Date(data.end_time);
  const middle = new Date(start.getTime() + (end.getTime() - start.getTime()) / 2);
  return `
    <div class="api-usage-axis">
      ${apiUsageAxisTick("start", start)}
      ${apiUsageAxisTick("middle", middle)}
      ${apiUsageAxisTick("now", end)}
    </div>
  `;
}

function apiUsageAxisTick(label, value) {
  return `<span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(formatAxisTime(value))}</small></span>`;
}

function renderApiUsageBreakdown(data) {
  if (!els.apiUsageBreakdown) return;
  const models = Array.isArray(data && data.models) ? data.models : [];
  const reasons = Array.isArray(data && data.reasons) ? data.reasons : [];
  els.apiUsageBreakdown.innerHTML = `
    <div>
      <h3>Models</h3>
      ${models.length ? models.map((row) => `
        <p><strong>${escapeHtml(row.model || "unknown")}</strong> <span class="muted">${escapeHtml(formatApiCallType(row.call_type))}</span></p>
        <div class="meta">
          <span class="pill">${formatCount(row.remote_calls)} calls</span>
          ${row.total_tokens ? `<span class="pill">${formatCount(row.total_tokens)} tokens</span>` : ""}
          ${row.audio_duration_seconds ? `<span class="pill">${formatDuration(row.audio_duration_seconds)} audio</span>` : ""}
        </div>
      `).join("") : `<p class="muted">No remote model calls in this range.</p>`}
    </div>
    <div>
      <h3>Why</h3>
      ${reasons.length ? reasons.map((row) => `
        <p><strong>${escapeHtml(formatApiReason(row.reason))}</strong> <span class="muted">${escapeHtml(formatStatus(row.status))}</span></p>
        <div class="meta">
          <span class="pill">${formatCount(row.events)} event${row.events === 1 ? "" : "s"}</span>
          <span class="pill">${escapeHtml(formatApiCallType(row.call_type))}</span>
        </div>
      `).join("") : `<p class="muted">No reasons recorded in this range.</p>`}
    </div>
  `;
}

function renderApiUsageEvents(events) {
  if (!els.apiUsageEvents) return;
  els.apiUsageEvents.innerHTML = "";
  if (!events.length) {
    setEmpty(els.apiUsageEvents, "No API usage events recorded yet.");
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const event of events.slice(0, 25)) {
    const detail = [
      event.operation ? formatApiReason(event.operation) : "",
      event.model || "",
      event.repeater_name || "",
      event.window_name ? formatSummaryWindow(event.window_name) : "",
    ].filter(Boolean).join(" - ");
    const metrics = [
      event.input_count != null ? `${formatCount(event.input_count)} input${Number(event.input_count) === 1 ? "" : "s"}` : "",
      event.audio_duration_seconds ? `${formatDuration(event.audio_duration_seconds)} audio` : "",
      event.total_tokens ? `${formatCount(event.total_tokens)} tokens` : "",
      event.elapsed_ms != null ? `${formatCount(event.elapsed_ms)}ms` : "",
    ].filter(Boolean).map((value) => `<span class="pill">${escapeHtml(value)}</span>`).join("");
    const error = event.error ? `<p class="state-error">${escapeHtml(compactText(event.error, "", 160))}</p>` : "";
    fragment.appendChild(item(`
      <div class="item-head">
        <div>
          <h3>${escapeHtml(formatApiCallType(event.call_type))}</h3>
          <p class="muted">${escapeHtml(formatTime(event.created_at))}${detail ? ` - ${escapeHtml(detail)}` : ""}</p>
        </div>
        <span class="pill state-${escapeHtml(event.status)}">${escapeHtml(formatStatus(event.status))}</span>
      </div>
      <div class="meta">
        <span class="pill">${escapeHtml(formatApiReason(event.reason || "unspecified"))}</span>
        ${metrics}
      </div>
      ${error}
    `));
  }
  els.apiUsageEvents.appendChild(fragment);
}

function apiUsageRowDetail(row) {
  const parts = [];
  if (row.total_tokens) parts.push(`${formatCount(row.total_tokens)} tokens`);
  if (row.audio_duration_seconds) parts.push(`${formatDuration(row.audio_duration_seconds)} audio sent`);
  if (!parts.length) parts.push("No billable size detail returned for these events.");
  return parts.join(" - ");
}

function formatApiCallType(value) {
  const labels = {
    transcription: "Transcriptions",
    summary: "Summaries",
    activity_chat: "Activity chat",
  };
  return labels[value] || String(value || "API").replaceAll("_", " ");
}

function formatApiReason(value) {
  const labels = {
    remote_transcription: "Remote transcription",
    short_recording: "Short recording guardrail",
    remote_summary: "Remote summary",
    remote_activity_chat: "Remote activity chat",
    ollama_activity_chat: "Ollama activity chat",
    missing_api_key: "Missing API key",
    disabled: "Disabled",
    automated_only: "Automated-only guardrail",
    not_enough_traffic: "Not enough traffic",
    recording: "Recording",
    scheduled: "Scheduled",
    ad_hoc: "Ad hoc",
    manual: "Manual",
  };
  return labels[value] || String(value || "unspecified").replaceAll("_", " ");
}

function formatApiUsageWindowLabel(data) {
  if (!data || !data.start_time || !data.end_time) return `Last ${apiUsageHours}h`;
  const start = new Date(data.start_time);
  const end = new Date(data.end_time);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return `Last ${apiUsageHours}h`;
  const hours = Math.max(1, Math.round((end.getTime() - start.getTime()) / 3600000));
  if (hours < 24) return `Last ${hours}h`;
  if (hours % 24 === 0) return `Last ${hours / 24}d`;
  return `Last ${hours}h`;
}

function renderSettings(config) {
  if (!config) return;
  if (!document.activeElement.closest("#settingsForm")) {
    els.settingsForm.elements.threshold.value = config.vox.threshold;
    els.settingsForm.elements.pre_roll_seconds.value = config.vox.pre_roll_seconds;
    els.settingsForm.elements.post_silence_seconds.value = config.vox.post_silence_seconds;
    els.settingsForm.elements.min_duration_seconds.value = config.vox.min_duration_seconds;
    els.settingsForm.elements.max_duration_seconds.value = config.vox.max_duration_seconds;
    els.settingsForm.elements.raw_audio_days.value = config.retention.raw_audio_days;
    els.settingsForm.elements.transcripts_days.value = config.retention.transcripts_days;
    els.settingsForm.elements.summaries_days.value = config.retention.summaries_days;
    els.settingsForm.elements.transcript_display_limit.value = config.retention.transcript_display_limit;
    els.settingsForm.elements.summary_display_limit.value = config.retention.summary_display_limit;
  }
  renderApiUsageSettings(config);
  if (!liveFormInitialized) {
    const firstRepeater = config.repeaters && config.repeaters[0];
    if (firstRepeater) {
      els.liveTestForm.elements.frequency_mhz.value = firstRepeater.frequency_mhz;
      els.liveTestForm.elements.squelch_level.value = "0";
      els.liveTestForm.elements.gain.value = firstRepeater.gain;
      els.liveTestForm.elements.ppm.value = firstRepeater.ppm;
      els.liveTestForm.elements.sample_rate.value = firstRepeater.sample_rate;
      liveFormInitialized = true;
    }
  }
}

function renderApiUsageSettings(config) {
  if (!els.apiUsageSettingsForm || document.activeElement.closest("#apiUsageSettingsForm")) return;
  const form = els.apiUsageSettingsForm;
  const scheduledWindows = new Set((config.summary && config.summary.scheduled_windows) || []);
  form.elements.remote_min_duration_seconds.value = config.transcription.remote_min_duration_seconds;
  form.elements.summary_min_transcripts.value = config.summary.min_transcripts;
  form.elements.summary_schedule_delay_seconds.value = config.summary.schedule_delay_seconds;
  form.elements.summary_window_quarter_hour.checked = scheduledWindows.has("quarter_hour");
  form.elements.summary_window_hour.checked = scheduledWindows.has("hour");
  form.elements.summary_window_day.checked = scheduledWindows.has("day");
  form.elements.per_repeater_scheduled.checked = Boolean(config.summary.per_repeater_scheduled);
  form.elements.skip_automated_only.checked = Boolean(config.summary.skip_automated_only);
  form.elements.activity_chat_backend.value = config.activity_chat.backend || "noop";
  form.elements.activity_chat_model.value = config.activity_chat.model || "gpt-5.4-nano";
  form.elements.activity_chat_default_hours.value = config.activity_chat.default_hours || 24;
}

function formData(form) {
  const data = new FormData(form);
  return Object.fromEntries(data.entries());
}

function repeaterPayloadFromForm(form) {
  const data = formData(form);
  return {
    name: data.name,
    frequency_mhz: Number(data.frequency_mhz),
    transmit_frequency_mhz: data.transmit_frequency_mhz ? Number(data.transmit_frequency_mhz) : null,
    tone: data.tone || null,
    mode: "NFM",
    squelch_level: Number(data.squelch_level || 50),
    sample_rate: Number(data.sample_rate || 24000),
    gain: data.gain || "auto",
    ppm: Number(data.ppm || 0),
    location: data.location || null,
    coverage_area: data.coverage_area || null,
    repeater_type: data.repeater_type || null,
    notes: data.notes || null,
    enabled: form.elements.enabled.checked,
  };
}

function resetRepeaterForm() {
  els.repeaterForm.reset();
  els.repeaterForm.elements.squelch_level.value = "50";
  els.repeaterForm.elements.sample_rate.value = "24000";
  els.repeaterForm.elements.gain.value = "auto";
  els.repeaterForm.elements.ppm.value = "0";
  els.repeaterForm.elements.enabled.checked = true;
}

function keywordRulePayloadFromForm(form) {
  const data = formData(form);
  return {
    keyword: data.keyword,
    cooldown_minutes: Number(data.cooldown_minutes || 10),
    is_regex: form.elements.is_regex.checked,
    case_sensitive: form.elements.case_sensitive.checked,
    notify_transcript: form.elements.notify_transcript.checked,
    notify_summary: form.elements.notify_summary.checked,
    enabled: form.elements.enabled ? form.elements.enabled.checked : true,
  };
}

async function loadTrafficAlertSettings() {
  if (!els.trafficAlertForm) return;
  try {
    const settings = await fetchJson("/api/notifications/traffic-alerts");
    els.trafficAlertForm.elements.enabled.checked = Boolean(settings.enabled);
    els.trafficAlertForm.elements.suppress_phrases.value = settings.suppress_phrases || "";
    setSaveStatus(els.trafficAlertStatus, "");
  } catch (error) {
    setSaveStatus(els.trafficAlertStatus, error.message, "state-error");
  }
}

function setupActivityRange() {
  if (!els.activityRange) return;
  els.activityRange.value = String(activityHours);
  els.activityRange.addEventListener("change", () => {
    const nextHours = Number(els.activityRange.value);
    activityHours = activityHourOptions.has(nextHours) ? nextHours : 24;
    els.activityRange.value = String(activityHours);
    window.localStorage.setItem(activityRangeStorageKey, String(activityHours));
    refreshDashboard();
  });
}

function setupApiUsageControls() {
  if (!els.apiUsageRange) return;
  els.apiUsageRange.value = String(apiUsageHours);
  els.apiUsageRange.addEventListener("change", () => {
    const nextHours = Number(els.apiUsageRange.value);
    apiUsageHours = apiUsageHourOptions.has(nextHours) ? nextHours : 24;
    els.apiUsageRange.value = String(apiUsageHours);
    window.localStorage.setItem(apiUsageRangeStorageKey, String(apiUsageHours));
    refreshApiUsage();
  });
  if (els.refreshApiUsageBtn) {
    els.refreshApiUsageBtn.addEventListener("click", refreshApiUsage);
  }
}

function setupTranscriptSearch() {
  if (!els.transcriptSearch) return;
  transcriptSearchTerm = els.transcriptSearch.value || "";
  if (els.transcriptSearchForm) {
    els.transcriptSearchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      applyTranscriptSearchFilter();
    });
  }
  els.transcriptSearch.addEventListener("input", () => {
    transcriptSearchTerm = els.transcriptSearch.value;
    applyTranscriptSearchFilter();
  });
  if (els.clearTranscriptSearchBtn) {
    els.clearTranscriptSearchBtn.addEventListener("click", () => {
      els.transcriptSearch.value = "";
      transcriptSearchTerm = "";
      applyTranscriptSearchFilter();
      els.transcriptSearch.focus();
    });
  }
}

function setupSummaryControls() {
  if (els.summaryForm) {
    els.summaryForm.addEventListener("change", () => {
      renderSummaries(currentSummaries, currentRepeaters);
    });
  }
  if (els.summarySearch) {
    summarySearchTerm = els.summarySearch.value || "";
    if (els.summarySearchForm) {
      els.summarySearchForm.addEventListener("submit", (event) => {
        event.preventDefault();
        renderSummaries(currentSummaries, currentRepeaters);
      });
    }
    els.summarySearch.addEventListener("input", () => {
      summarySearchTerm = els.summarySearch.value;
      renderSummaries(currentSummaries, currentRepeaters);
    });
  }
  if (els.clearSummarySearchBtn) {
    els.clearSummarySearchBtn.addEventListener("click", () => {
      if (els.summarySearch) {
        els.summarySearch.value = "";
        summarySearchTerm = "";
        renderSummaries(currentSummaries, currentRepeaters);
        els.summarySearch.focus();
      }
    });
  }
}

function setupActivityChatControls() {
  if (els.activityChatRange) {
    els.activityChatRange.value = String(activityChatHours);
    els.activityChatRange.addEventListener("change", () => {
      const nextHours = Number(els.activityChatRange.value);
      activityChatHours = activityChatHourOptions.has(nextHours) ? nextHours : 24;
      els.activityChatRange.value = String(activityChatHours);
      window.localStorage.setItem(activityChatRangeStorageKey, String(activityChatHours));
    });
  }
  if (els.clearActivityChatBtn) {
    els.clearActivityChatBtn.addEventListener("click", () => {
      activityChatMessages = [];
      if (els.activityChatStatus) els.activityChatStatus.textContent = "";
      renderActivityChatMessages();
      if (els.activityChatInput) els.activityChatInput.focus();
    });
  }
  if (!els.activityChatForm || !els.activityChatInput) return;
  renderActivityChatMessages();
  els.activityChatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (activityChatInFlight) return;
    const message = els.activityChatInput.value.trim();
    if (!message) return;
    const history = activityChatHistoryPayload();
    const repeaterValue = els.activityChatRepeater ? els.activityChatRepeater.value : "";
    const payload = {
      message,
      history,
      hours: activityChatHours,
      repeater_id: repeaterValue ? Number(repeaterValue) : null,
    };
    activityChatMessages.push({ role: "user", content: message });
    els.activityChatInput.value = "";
    renderActivityChatMessages();

    const submitButton = els.activityChatForm.querySelector("button[type='submit']");
    activityChatInFlight = true;
    if (submitButton) submitButton.disabled = true;
    els.activityChatInput.disabled = true;
    if (els.activityChatStatus) {
      els.activityChatStatus.textContent = "Asking activity chat...";
    }
    try {
      const response = await fetchJson("/api/activity-chat", { method: "POST", body: JSON.stringify(payload) });
      const sourceCounts = response.source_counts || {};
      activityChatMessages.push({
        role: "assistant",
        content: response.answer || "",
        meta: {
          model: response.model || response.backend || "model",
          transcripts: Number(sourceCounts.transcripts || 0),
          summaries: Number(sourceCounts.summaries || 0),
        },
      });
      if (els.activityChatStatus) {
        els.activityChatStatus.textContent = `${formatCount(sourceCounts.transcripts || 0)} transcript${sourceCounts.transcripts === 1 ? "" : "s"}, ${formatCount(sourceCounts.summaries || 0)} summar${sourceCounts.summaries === 1 ? "y" : "ies"} in context.`;
      }
    } catch (error) {
      activityChatMessages.push({ role: "assistant", content: error.message || "Activity chat failed." });
      if (els.activityChatStatus) {
        els.activityChatStatus.textContent = error.message || "Activity chat failed.";
      }
    } finally {
      activityChatInFlight = false;
      if (submitButton) submitButton.disabled = false;
      els.activityChatInput.disabled = false;
      renderActivityChatMessages();
      els.activityChatInput.focus();
    }
  });
}

function setupDisplaySettings() {
  if (!els.displaySettingsForm) return;
  applyTextSize(textSizePercent);
  applyDisplayTheme(displayTheme);
  els.displaySettingsForm.addEventListener("input", (event) => {
    if (event.target.name === "text_size") {
      applyTextSize(event.target.value);
    } else if (event.target.name === "dark_mode") {
      applyDisplayTheme(event.target.checked ? "dark" : "light");
    } else {
      return;
    }
    setSaveStatus(els.displaySettingsStatus, "");
  });
  els.displaySettingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await withSaveFeedback(els.displaySettingsForm, els.displaySettingsStatus, {
      saving: "Saving display...",
      saved: "Display saved.",
    }, () => {
      window.localStorage.setItem(textSizeStorageKey, String(textSizePercent));
      window.localStorage.setItem(themeStorageKey, displayTheme);
      return { text_size: textSizePercent, theme: displayTheme };
    });
  });
  if (els.resetTextSizeBtn) {
    els.resetTextSizeBtn.addEventListener("click", () => {
      applyTextSize(100);
      window.localStorage.setItem(textSizeStorageKey, "100");
      setSaveStatus(els.displaySettingsStatus, "Text size reset.", "state-completed");
    });
  }
}

function setupZoomGuard() {
  for (const eventName of ["gesturestart", "gesturechange", "gestureend"]) {
    document.addEventListener(eventName, (event) => event.preventDefault(), { passive: false });
  }
}

els.repeaterForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const result = await withSaveFeedback(els.repeaterForm, els.repeaterStatus, {
    saving: "Saving repeater...",
    saved: "Repeater saved.",
  }, () =>
    fetchJson("/api/repeaters", { method: "POST", body: JSON.stringify(repeaterPayloadFromForm(els.repeaterForm)) })
  );
  if (!result.ok) return;
  resetRepeaterForm();
  refreshDashboard();
});

els.ruleForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = keywordRulePayloadFromForm(els.ruleForm);
  if (!payload.notify_transcript && !payload.notify_summary) {
    setSaveStatus(els.ruleStatus, "Choose transcript alerts, summary alerts, or both.", "state-error");
    return;
  }
  const result = await withSaveFeedback(els.ruleForm, els.ruleStatus, {
    saving: "Saving rule...",
    saved: "Rule saved.",
  }, () =>
    fetchJson("/api/notifications/rules", { method: "POST", body: JSON.stringify(payload) })
  );
  if (!result.ok) return;
  els.ruleForm.reset();
  els.ruleForm.elements.cooldown_minutes.value = "10";
  els.ruleForm.elements.notify_transcript.checked = true;
  els.ruleForm.elements.notify_summary.checked = false;
  els.pushStatus.textContent = "";
  refreshDashboard();
});

els.trafficAlertForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const result = await withSaveFeedback(els.trafficAlertForm, els.trafficAlertStatus, {
    saving: "Saving alerts...",
    saved: "Alerts saved.",
  }, () =>
    fetchJson("/api/notifications/traffic-alerts", {
      method: "PUT",
      body: JSON.stringify({
        enabled: els.trafficAlertForm.elements.enabled.checked,
        suppress_phrases: els.trafficAlertForm.elements.suppress_phrases.value,
      }),
    })
  );
  if (!result.ok) return;
  els.trafficAlertForm.elements.enabled.checked = Boolean(result.value.enabled);
  els.trafficAlertForm.elements.suppress_phrases.value = result.value.suppress_phrases || "";
});

els.summaryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = formData(els.summaryForm);
  const submitButton = els.summaryForm.querySelector("button[type='submit']");
  const payload = {
    window_name: data.window_name || "quarter_hour",
    repeater_id: data.repeater_id ? Number(data.repeater_id) : null,
  };
  submitButton.disabled = true;
  if (els.summaryStatus) {
    els.summaryStatus.textContent = "Generating summary...";
  }
  try {
    const summary = await fetchJson("/api/summaries", { method: "POST", body: JSON.stringify(payload) });
    adHocSummary = summary;
    if (els.summaryStatus) {
      if (summary.status === "not_enough_traffic") {
        els.summaryStatus.textContent = "Not enough traffic for that window.";
      } else if (summary.status === "automated_only") {
        els.summaryStatus.textContent = "Only automated repeater messages in that window.";
      } else {
        els.summaryStatus.textContent = "Ad hoc summary generated.";
      }
    }
    renderSummaries(currentSummaries, currentRepeaters);
  } catch (error) {
    if (els.summaryStatus) {
      els.summaryStatus.textContent = error.message;
    }
  } finally {
    submitButton.disabled = false;
  }
});

els.settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentConfig) return;
  const data = formData(els.settingsForm);
  const result = await withSaveFeedback(els.settingsForm, els.settingsStatus, {
    saving: "Saving settings...",
    saved: "Settings saved.",
  }, () =>
    fetchJson("/api/audio-settings", {
      method: "PUT",
      body: JSON.stringify({
        vox: {
          threshold: Number(data.threshold),
          pre_roll_seconds: Number(data.pre_roll_seconds),
          post_silence_seconds: Number(data.post_silence_seconds),
          min_duration_seconds: Number(data.min_duration_seconds),
          max_duration_seconds: Number(data.max_duration_seconds),
        },
        retention: {
          raw_audio_days: Number(data.raw_audio_days),
          transcripts_days: Number(data.transcripts_days),
          summaries_days: Number(data.summaries_days),
          transcript_display_limit: Number(data.transcript_display_limit),
          summary_display_limit: Number(data.summary_display_limit),
        },
      }),
    })
  );
  if (!result.ok) return;
  currentConfig = result.value;
  refreshDashboard();
});

if (els.apiUsageSettingsForm) {
  els.apiUsageSettingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!currentConfig) return;
    const data = formData(els.apiUsageSettingsForm);
    const scheduledWindows = [];
    if (els.apiUsageSettingsForm.elements.summary_window_quarter_hour.checked) scheduledWindows.push("quarter_hour");
    if (els.apiUsageSettingsForm.elements.summary_window_hour.checked) scheduledWindows.push("hour");
    if (els.apiUsageSettingsForm.elements.summary_window_day.checked) scheduledWindows.push("day");
    const result = await withSaveFeedback(els.apiUsageSettingsForm, els.apiUsageSettingsStatus, {
      saving: "Saving API settings...",
      saved: "API settings saved.",
    }, () =>
      fetchJson("/api/audio-settings", {
        method: "PUT",
        body: JSON.stringify({
          transcription: {
            remote_min_duration_seconds: Number(data.remote_min_duration_seconds),
          },
          summary: {
            min_transcripts: Number(data.summary_min_transcripts),
            scheduled_windows: scheduledWindows,
            per_repeater_scheduled: els.apiUsageSettingsForm.elements.per_repeater_scheduled.checked,
            skip_automated_only: els.apiUsageSettingsForm.elements.skip_automated_only.checked,
            schedule_delay_seconds: Number(data.summary_schedule_delay_seconds),
          },
          activity_chat: {
            backend: data.activity_chat_backend || "noop",
            model: data.activity_chat_model || "gpt-5.4-nano",
            default_hours: Number(data.activity_chat_default_hours || 24),
          },
        }),
      })
    );
    if (!result.ok) return;
    currentConfig = result.value;
    renderApiUsageSettings(currentConfig);
    refreshApiUsage();
  });
}

els.liveTestForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  liveFormInitialized = true;
  startLiveTest();
});

els.liveTestForm.addEventListener("input", () => {
  liveFormInitialized = true;
});

els.stopLiveBtn.addEventListener("click", stopLiveTest);

if (els.refreshLogsBtn) {
  els.refreshLogsBtn.addEventListener("click", refreshLogs);
}
if (els.logLimit) {
  els.logLimit.addEventListener("change", refreshLogs);
}
els.clearRecordingsBtn.addEventListener("click", async () => {
  if (!window.confirm("Delete all recordings and audio files?")) return;
  stopRecordingPlayback();
  try {
    const result = await fetchJson("/api/recordings", { method: "DELETE" });
    setSaveStatus(els.recordingStatus, `Deleted ${result.deleted} recording(s).`, "state-completed");
    refreshDashboard();
  } catch (error) {
    setSaveStatus(els.recordingStatus, error.message, "state-error");
  }
});
els.clearStaticRecordingsBtn.addEventListener("click", async () => {
  if (!window.confirm("Delete recordings whose transcript is [static only]?")) return;
  stopRecordingPlayback();
  try {
    const result = await fetchJson("/api/recordings/static-only", { method: "DELETE" });
    setSaveStatus(els.recordingStatus, `Deleted ${result.deleted} static-only recording(s).`, "state-completed");
    refreshDashboard();
  } catch (error) {
    setSaveStatus(els.recordingStatus, error.message, "state-error");
  }
});
els.clearSummariesBtn.addEventListener("click", async () => {
  if (!window.confirm("Delete all summaries?")) return;
  await fetchJson("/api/summaries", { method: "DELETE" });
  adHocSummary = null;
  refreshDashboard();
});
els.clearEventsBtn.addEventListener("click", async () => {
  if (!window.confirm("Clear notification history?")) return;
  await fetchJson("/api/notifications/events", { method: "DELETE" });
  refreshDashboard();
});
els.enablePushBtn.addEventListener("click", enablePush);
els.testPushBtn.addEventListener("click", async () => {
  const result = await fetchJson("/api/notifications/test", {
    method: "POST",
    body: JSON.stringify({ title: "RepeaterWatch test", body: "Notification path is configured." }),
  });
  if (result.sent === 0 && "Notification" in window && Notification.permission === "granted") {
    new Notification("RepeaterWatch test", { body: "Local browser fallback notification." });
  }
  els.pushStatus.textContent = `Test event sent to ${result.sent} push subscription(s).`;
});

function getPushSetupStatus() {
  const isIos = /iphone|ipad|ipod/.test(navigator.userAgent.toLowerCase()) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
  const needsHttps = !window.isSecureContext;

  if (needsHttps || (isIos && !isStandalone)) {
    const steps = [];
    if (needsHttps) {
      steps.push("open RepeaterWatch with an HTTPS URL");
    }
    if (isIos && !isStandalone) {
      steps.push("use Share > Add to Home Screen, then launch it from the Home Screen icon");
    }
    return {
      canRegisterServiceWorker: false,
      canEnablePush: false,
      message: `On iPhone and iPad, Web Push requires ${steps.join(" and ")}.`,
    };
  }

  if (!("serviceWorker" in navigator)) {
    return {
      canRegisterServiceWorker: false,
      canEnablePush: false,
      message: "Service workers are unavailable in this browser, so Web Push cannot be enabled.",
    };
  }

  if (!("PushManager" in window) || !("Notification" in window)) {
    return {
      canRegisterServiceWorker: true,
      canEnablePush: false,
      message: "Web Push APIs are unavailable in this browser.",
    };
  }

  return { canRegisterServiceWorker: true, canEnablePush: true, message: "" };
}

async function setupPwa() {
  const status = getPushSetupStatus();
  if (status.canRegisterServiceWorker) {
    try {
      await navigator.serviceWorker.register("/sw.js");
    } catch {
      status.canEnablePush = false;
      status.message = "Service worker registration failed. Refresh after opening RepeaterWatch over HTTPS, then try again.";
    }
  }

  if (status.message) {
    els.installPanel.classList.add("active");
    els.installPanel.textContent = status.message;
  }
  els.enablePushBtn.disabled = !status.canEnablePush;
}

async function enablePush() {
  const status = getPushSetupStatus();
  if (!status.canEnablePush) {
    els.pushStatus.textContent = status.message;
    return;
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    els.pushStatus.textContent = "Notification permission was not granted.";
    return;
  }
  const { public_key: publicKey } = await fetchJson("/api/notifications/vapid-public-key");
  if (!publicKey) {
    els.pushStatus.textContent = "VAPID keys are not configured on the server.";
    return;
  }
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey),
  });
  const payload = subscription.toJSON();
  payload.user_agent = navigator.userAgent;
  await fetchJson("/api/notifications/subscriptions", { method: "POST", body: JSON.stringify(payload) });
  els.pushStatus.textContent = "Notifications enabled for this device.";
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i += 1) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function transcriptTextHtml(value, keywordRules = [], recording = null, searchTokens = []) {
  const text = String(value ?? "");
  if (!text) return "";
  const keywordRanges = keywordMatchRanges(text, keywordRules, recording);
  const searchRanges = searchMatchRanges(text, searchTokens);
  if (!keywordRanges.length && !searchRanges.length) return callsignTextHtml(text);

  const boundaries = new Set([0, text.length]);
  for (const range of [...keywordRanges, ...searchRanges]) {
    boundaries.add(range.start);
    boundaries.add(range.end);
  }
  const points = [...boundaries].sort((left, right) => left - right);
  let html = "";
  for (let i = 0; i < points.length - 1; i += 1) {
    const start = points[i];
    const end = points[i + 1];
    if (end <= start) continue;
    let segment = callsignTextHtml(text.slice(start, end));
    if (rangeCovers(keywordRanges, start, end)) {
      segment = `<strong class="keyword-match">${segment}</strong>`;
    }
    if (rangeCovers(searchRanges, start, end)) {
      segment = `<mark class="search-match">${segment}</mark>`;
    }
    html += segment;
  }
  return html;
}

function summaryTextHtml(value, searchTokens = []) {
  const text = String(value ?? "");
  if (!text) return "";
  const searchRanges = searchMatchRanges(text, searchTokens);
  if (!searchRanges.length) return callsignTextHtml(text);

  const boundaries = new Set([0, text.length]);
  for (const range of searchRanges) {
    boundaries.add(range.start);
    boundaries.add(range.end);
  }
  const points = [...boundaries].sort((left, right) => left - right);
  let html = "";
  for (let i = 0; i < points.length - 1; i += 1) {
    const start = points[i];
    const end = points[i + 1];
    if (end <= start) continue;
    let segment = callsignTextHtml(text.slice(start, end));
    if (rangeCovers(searchRanges, start, end)) {
      segment = `<mark class="search-match">${segment}</mark>`;
    }
    html += segment;
  }
  return html;
}

function keywordMatchRanges(text, keywordRules = [], recording = null) {
  const ranges = [];
  for (const rule of transcriptKeywordRules(keywordRules, recording)) {
    const ruleRanges = rule.is_regex
      ? regexKeywordRanges(text, rule)
      : phraseKeywordRanges(text, rule);
    ranges.push(...ruleRanges);
  }
  return mergeRanges(ranges);
}

function searchMatchRanges(text, tokens = []) {
  const ranges = [];
  for (const token of tokens) {
    ranges.push(...phraseKeywordRanges(text, { keyword: token, case_sensitive: false }));
  }
  return expandRangesToCallsigns(text, mergeRanges(ranges));
}

function rangeCovers(ranges, start, end) {
  return ranges.some((range) => start >= range.start && end <= range.end);
}

function expandRangesToCallsigns(text, ranges) {
  if (!ranges.length) return ranges;
  const callsignRanges = [];
  callsignPattern.lastIndex = 0;
  for (const match of text.matchAll(callsignPattern)) {
    const start = match.index || 0;
    callsignRanges.push({ start, end: start + match[0].length });
  }
  if (!callsignRanges.length) return ranges;
  return mergeRanges(ranges.map((range) => {
    const overlap = callsignRanges.find((callsignRange) => rangesOverlap(range, callsignRange));
    return overlap ? { start: Math.min(range.start, overlap.start), end: Math.max(range.end, overlap.end) } : range;
  }));
}

function rangesOverlap(left, right) {
  return left.start < right.end && right.start < left.end;
}

function transcriptKeywordRules(keywordRules = [], recording = null) {
  const repeaterId = recording && recording.repeater_id != null ? String(recording.repeater_id) : null;
  return keywordRules.filter((rule) => {
    if (!rule || !rule.enabled || !rule.notify_transcript || !rule.keyword) return false;
    if (rule.repeater_id == null || repeaterId == null) return true;
    return String(rule.repeater_id) === repeaterId;
  });
}

function phraseKeywordRanges(text, rule) {
  const keyword = String(rule.keyword || "");
  if (!keyword) return [];
  const haystack = rule.case_sensitive ? text : text.toLocaleLowerCase();
  const needle = rule.case_sensitive ? keyword : keyword.toLocaleLowerCase();
  const ranges = [];
  let index = haystack.indexOf(needle);
  while (index !== -1) {
    ranges.push({ start: index, end: index + keyword.length });
    index = haystack.indexOf(needle, index + Math.max(1, needle.length));
  }
  return ranges;
}

function regexKeywordRanges(text, rule) {
  const ranges = [];
  try {
    const flags = rule.case_sensitive ? "g" : "gi";
    const regex = new RegExp(String(rule.keyword || ""), flags);
    for (const match of text.matchAll(regex)) {
      const value = match[0] || "";
      if (!value) continue;
      const start = match.index || 0;
      ranges.push({ start, end: start + value.length });
    }
  } catch {
    return [];
  }
  return ranges;
}

function mergeRanges(ranges) {
  const sorted = ranges
    .filter((range) => Number.isInteger(range.start) && Number.isInteger(range.end) && range.end > range.start)
    .sort((left, right) => left.start - right.start || right.end - left.end);
  const merged = [];
  for (const range of sorted) {
    const previous = merged[merged.length - 1];
    if (previous && range.start <= previous.end) {
      previous.end = Math.max(previous.end, range.end);
    } else {
      merged.push({ ...range });
    }
  }
  return merged;
}

function callsignTextHtml(value) {
  const text = String(value ?? "");
  if (!text) return "";
  let html = "";
  let lastIndex = 0;
  callsignPattern.lastIndex = 0;
  for (const match of text.matchAll(callsignPattern)) {
    const index = match.index || 0;
    const callsign = match[0].toUpperCase();
    html += escapeHtml(text.slice(lastIndex, index));
    html += `<button class="callsign-link" data-callsign="${escapeHtml(callsign)}" type="button" title="Look up ${escapeHtml(callsign)}">${escapeHtml(match[0])}</button>`;
    lastIndex = index + match[0].length;
  }
  html += escapeHtml(text.slice(lastIndex));
  return html;
}

function setupCallsignLookup() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-callsign]");
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    openCallsignLookup(button.dataset.callsign);
  });

  for (const closeButton of document.querySelectorAll("[data-close-callsign]")) {
    closeButton.addEventListener("click", closeCallsignLookup);
  }

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && els.callsignModal && !els.callsignModal.hidden) {
      closeCallsignLookup();
    }
  });
}

async function openCallsignLookup(callsign) {
  const normalized = String(callsign || "").toUpperCase();
  if (!normalized || !els.callsignModal || !els.callsignTitle || !els.callsignDetails) return;
  activeCallsignLookup = normalized;
  els.callsignTitle.textContent = normalized;
  els.callsignDetails.innerHTML = `<p class="muted">Looking up ${escapeHtml(normalized)}...</p>`;
  els.callsignModal.hidden = false;
  document.body.classList.add("modal-open");

  try {
    const details = await fetchJson(`/api/callsigns/${encodeURIComponent(normalized)}`);
    if (activeCallsignLookup !== normalized) return;
    renderCallsignLookup(details);
  } catch (error) {
    if (activeCallsignLookup !== normalized) return;
    renderCallsignLookup({
      callsign: normalized,
      found: false,
      message: error.message || "Lookup failed.",
      links: fallbackCallsignLinks(normalized),
    });
  }
}

function closeCallsignLookup() {
  if (!els.callsignModal) return;
  activeCallsignLookup = null;
  els.callsignModal.hidden = true;
  document.body.classList.remove("modal-open");
}

function renderCallsignLookup(details) {
  const rows = [
    ["Name", details.name],
    ["Type", titleCase(details.type)],
    ["Class", titleCase(details.license_class)],
    ["Location", details.location],
    ["Grid", details.grid],
    ["Granted", details.grant_date],
    ["Expires", details.expires],
    ["Trustee", details.trustee_name ? `${details.trustee_name}${details.trustee_callsign ? ` (${details.trustee_callsign})` : ""}` : ""],
    ["Previous", details.previous_callsign],
  ]
    .filter(([, value]) => String(value || "").trim())
    .map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`)
    .join("");
  const requested = details.requested_callsign && details.requested_callsign !== details.callsign
    ? `<p class="muted">Requested ${escapeHtml(details.requested_callsign)}; current record is ${escapeHtml(details.callsign)}.</p>`
    : "";
  const message = details.found
    ? requested
    : `<p class="muted">${escapeHtml(details.message || "No public license detail was returned for this callsign.")}</p>`;
  const fields = rows ? `<dl class="callsign-fields">${rows}</dl>` : "";
  const links = lookupLinksHtml(details.links || fallbackCallsignLinks(details.callsign));

  els.callsignTitle.textContent = details.callsign || activeCallsignLookup || "Callsign";
  els.callsignDetails.innerHTML = `
    <div class="callsign-status">
      <span class="pill ${details.found ? "state-completed" : "state-stopped"}">${details.found ? "found" : "not found"}</span>
      <span class="pill">${escapeHtml(details.source || "lookup")}</span>
    </div>
    ${message}
    ${fields}
    <div class="callsign-links">${links}</div>
  `;
}

function lookupLinksHtml(links) {
  return links
    .filter((link) => link && link.url)
    .map((link) => `<a href="${escapeHtml(safeHttpUrl(link.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(link.label || "Open")}</a>`)
    .join("");
}

function fallbackCallsignLinks(callsign) {
  return [
    { label: "QRZ", url: `https://www.qrz.com/db/${encodeURIComponent(callsign)}` },
    { label: "FCC Search", url: "https://wireless2.fcc.gov/UlsApp/UlsSearch/searchLicense.jsp" },
  ];
}

function safeHttpUrl(value) {
  try {
    const url = new URL(value, window.location.origin);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : "#";
  } catch {
    return "#";
  }
}

function titleCase(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
}

async function startHomeListen(repeaterId) {
  stopHomeListen(false);
  listeningRepeaterId = repeaterId;
  listenStatusMessage = "Connecting...";
  refreshDashboard();

  listenAudioContext = new AudioContext();
  await listenAudioContext.resume();
  listenNextStart = listenAudioContext.currentTime + 0.08;

  const params = new URLSearchParams({ repeater_id: String(repeaterId) });
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${location.host}/api/live-listen/ws?${params.toString()}`);
  listenSocket = socket;
  socket.binaryType = "arraybuffer";

  socket.addEventListener("message", (event) => {
    if (typeof event.data === "string") {
      const message = JSON.parse(event.data);
      if (message.sample_rate) {
        listenSampleRate = Number(message.sample_rate) || listenSampleRate;
      }
      updateHomeListenStatus(message.message || "Listening. Recording continues.");
      if (message.type === "error") {
        stopHomeListen(false);
        refreshDashboard();
      }
      return;
    }
    const samples = pcm16ToFloat(event.data);
    playHomeListenSamples(samples, listenSampleRate);
    updateHomeListenStatus("Listening. Recording continues.");
  });
  socket.addEventListener("close", () => {
    if (listenSocket !== socket) return;
    listenSocket = null;
    listeningRepeaterId = null;
    listenStatusMessage = "";
    if (listenAudioContext) {
      listenAudioContext.close();
      listenAudioContext = null;
    }
    refreshDashboard();
  });
  socket.addEventListener("error", () => {
    updateHomeListenStatus("Listen failed.");
  });
}

function stopHomeListen(update = true) {
  if (listenSocket) {
    listenSocket.close();
    listenSocket = null;
  }
  if (listenAudioContext) {
    listenAudioContext.close();
    listenAudioContext = null;
  }
  listeningRepeaterId = null;
  listenStatusMessage = "";
  if (update) refreshDashboard();
}

function updateHomeListenStatus(message) {
  listenStatusMessage = message;
  const status = document.querySelector("[data-home-listen-status]");
  if (status) status.textContent = message;
}

function playHomeListenSamples(samples, sampleRate) {
  if (!listenAudioContext || !samples.length) return;
  const buffer = listenAudioContext.createBuffer(1, samples.length, sampleRate);
  buffer.copyToChannel(samples, 0);
  const source = listenAudioContext.createBufferSource();
  source.buffer = buffer;
  source.connect(listenAudioContext.destination);
  listenNextStart = Math.max(listenNextStart, listenAudioContext.currentTime + 0.03);
  source.start(listenNextStart);
  listenNextStart += buffer.duration;
}

async function startLiveTest() {
  stopLiveTest();
  const data = formData(els.liveTestForm);
  const sampleRate = Number(data.sample_rate || 24000);
  liveAudioContext = new AudioContext({ sampleRate });
  await liveAudioContext.resume();
  liveNextStart = liveAudioContext.currentTime + 0.08;

  const params = new URLSearchParams({
    frequency_mhz: data.frequency_mhz,
    squelch_level: data.squelch_level || "0",
    gain: data.gain || "auto",
    ppm: data.ppm || "0",
    sample_rate: String(sampleRate),
  });
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  liveSocket = new WebSocket(`${scheme}://${location.host}/api/live-test/ws?${params.toString()}`);
  liveSocket.binaryType = "arraybuffer";
  els.startLiveBtn.disabled = true;
  els.stopLiveBtn.disabled = false;
  els.liveStatus.textContent = "Connecting to rtl_fm...";
  liveDecayTimer = setInterval(() => updateLiveMeter(0, false), 900);

  liveSocket.addEventListener("message", (event) => {
    if (typeof event.data === "string") {
      const message = JSON.parse(event.data);
      if (message.type === "level") {
        updateLiveMeter(Number(message.level || 0), false, message.message || "No audio");
      } else {
        els.liveStatus.textContent = message.message || message.type;
      }
      return;
    }
    const samples = pcm16ToFloat(event.data);
    const level = rms(samples);
    const threshold = currentConfig ? Number(currentConfig.vox.threshold) : 0.018;
    updateLiveMeter(level, level >= threshold, `Audio flowing; VOX threshold ${threshold.toFixed(3)}`);
    playSamples(samples, sampleRate);
  });
  liveSocket.addEventListener("close", () => {
    els.startLiveBtn.disabled = false;
    els.stopLiveBtn.disabled = true;
    if (liveDecayTimer) clearInterval(liveDecayTimer);
    liveDecayTimer = null;
    els.liveStatus.textContent = "Live test stopped.";
  });
  liveSocket.addEventListener("error", () => {
    els.liveStatus.textContent = "Live test failed. The SDR may already be in use by a receiver.";
  });
}

function stopLiveTest() {
  if (liveSocket) {
    liveSocket.close();
    liveSocket = null;
  }
  if (liveAudioContext) {
    liveAudioContext.close();
    liveAudioContext = null;
  }
  if (liveDecayTimer) {
    clearInterval(liveDecayTimer);
    liveDecayTimer = null;
  }
  els.startLiveBtn.disabled = false;
  els.stopLiveBtn.disabled = true;
  updateLiveMeter(0, false, "Stopped");
}

function pcm16ToFloat(arrayBuffer) {
  const view = new DataView(arrayBuffer);
  const samples = new Float32Array(Math.floor(view.byteLength / 2));
  for (let index = 0; index < samples.length; index += 1) {
    samples[index] = view.getInt16(index * 2, true) / 32768;
  }
  return samples;
}

function rms(samples) {
  if (!samples.length) return 0;
  let total = 0;
  for (const sample of samples) total += sample * sample;
  return Math.sqrt(total / samples.length);
}

function playSamples(samples, sampleRate) {
  if (!liveAudioContext || !samples.length) return;
  const buffer = liveAudioContext.createBuffer(1, samples.length, sampleRate);
  buffer.copyToChannel(samples, 0);
  const source = liveAudioContext.createBufferSource();
  source.buffer = buffer;
  source.connect(liveAudioContext.destination);
  liveNextStart = Math.max(liveNextStart, liveAudioContext.currentTime + 0.03);
  source.start(liveNextStart);
  liveNextStart += buffer.duration;
}

function updateLiveMeter(level, active, status) {
  const percent = Math.max(0, Math.min(100, level * 500));
  els.liveLevelBar.style.width = `${percent}%`;
  els.liveLevelText.textContent = `level ${level.toFixed(3)}`;
  els.liveActiveText.textContent = active ? "VOX active" : "idle";
  els.liveActiveText.classList.toggle("state-running", active);
  if (status) els.liveStatus.textContent = status;
}

function setupPullToRefresh() {
  if (!els.pullRefresh || !window.matchMedia("(pointer: coarse)").matches) return;

  window.addEventListener(
    "touchstart",
    (event) => {
      if (pullRefreshing || event.touches.length !== 1 || window.scrollY > 2) return;
      if (event.target.closest("input, select, button, textarea, audio, .navigation-shell")) return;
      pullTracking = true;
      pullStartY = event.touches[0].clientY;
      pullDistance = 0;
      setPullRefreshState(0);
    },
    { passive: true }
  );

  window.addEventListener(
    "touchmove",
    (event) => {
      if (!pullTracking || event.touches.length !== 1) return;
      const delta = event.touches[0].clientY - pullStartY;
      if (delta <= 0 || window.scrollY > 2) {
        resetPullRefresh();
        return;
      }
      pullDistance = Math.min(88, delta * 0.5);
      setPullRefreshState(pullDistance, pullDistance >= 64);
    },
    { passive: true }
  );

  window.addEventListener(
    "touchend",
    async () => {
      if (!pullTracking) return;
      const shouldRefresh = pullDistance >= 64;
      pullTracking = false;
      if (!shouldRefresh) {
        resetPullRefresh();
        return;
      }
      pullRefreshing = true;
      setPullRefreshState(72, true, true);
      try {
        await refreshDashboard();
      } finally {
        window.setTimeout(() => {
          pullRefreshing = false;
          resetPullRefresh();
        }, 280);
      }
    },
    { passive: true }
  );

  window.addEventListener(
    "touchcancel",
    () => {
      if (!pullRefreshing) resetPullRefresh();
    },
    { passive: true }
  );
}

function setPullRefreshState(distance, ready = false, refreshing = false) {
  if (!els.pullRefresh) return;
  els.pullRefresh.style.setProperty("--pull-distance", `${Math.max(0, distance)}px`);
  els.pullRefresh.classList.toggle("active", distance > 4 || refreshing);
  els.pullRefresh.classList.toggle("ready", ready);
  els.pullRefresh.classList.toggle("refreshing", refreshing);
}

function resetPullRefresh() {
  pullTracking = false;
  pullDistance = 0;
  setPullRefreshState(0);
}

for (const button of viewTabButtons()) {
  button.addEventListener("click", () => {
    setView(button.dataset.viewTab);
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

function applyHashView() {
  const shouldScrollToChat = hashTargetsActivityChat();
  setView(viewFromHash(), false);
  if (shouldScrollToChat) scrollActivityChatIntoView();
}

window.addEventListener("hashchange", applyHashView);
window.addEventListener("popstate", applyHashView);

applyDisplayTheme(displayTheme);
applyTextSize(textSizePercent);
applyHashView();
setupZoomGuard();
setupCallsignLookup();
setupPwa();
setupPullToRefresh();
setupActivityRange();
setupApiUsageControls();
setupTranscriptSearch();
setupSummaryControls();
setupActivityChatControls();
setupDisplaySettings();
loadTrafficAlertSettings();
refreshDashboard();
setInterval(refreshDashboard, 7000);
