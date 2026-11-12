const RESULT_COPY = "先新建一个项目，这里会列出资料和成果里的文件。";

const ROBOT_SVG = `<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 6v3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="16" cy="5" r="1.3" fill="currentColor"/><rect x="7" y="9" width="18" height="15" rx="5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="13" cy="15.5" r="1.4" fill="currentColor"/><circle cx="19" cy="15.5" r="1.4" fill="currentColor"/><path d="M12.5 20h7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`;

const titleEl = document.getElementById("title");
const projectLabel = document.getElementById("project-label");
const projectsEl = document.getElementById("projects");
const newChatBtn = document.getElementById("new-chat");
const historyEl = document.getElementById("history");
const searchEl = document.getElementById("search");
const welcomeTitle = document.querySelector("#welcome h2");
const welcomeText = document.querySelector("#welcome p");
const projectDialog = document.getElementById("project-dialog");
const sapDialog = document.getElementById("sap-dialog");
const projectForm = document.getElementById("project-form");
const projectNameEl = document.getElementById("project-name");
const projectError = document.getElementById("project-error");
const welcomeEl = document.getElementById("welcome");
const messagesEl = document.getElementById("messages");
const transcriptEl = document.getElementById("transcript");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const formEl = document.getElementById("composer");
const modelEl = document.getElementById("model");
const bannerEl = document.getElementById("banner");
const toastEl = document.getElementById("toast");
const resultsEl = document.getElementById("results");
const toggleBtn = document.getElementById("toggle-panel");
const resultBody = document.getElementById("result-body");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");

let projects = [];
let activeProjectId = null;
let conversations = [];
let activeId = null;
let streaming = false;
let abortController = null;

document.getElementById("new-project").addEventListener("click", openProjectDialog);
document.getElementById("project-cancel").addEventListener("click", closeProjectDialog);
projectDialog.addEventListener("click", (event) => {
  if (event.target === projectDialog) closeProjectDialog();
});
projectForm.addEventListener("submit", createProject);
document.getElementById("sap-cancel").addEventListener("click", closeSapDialog);
sapDialog.addEventListener("click", (event) => {
  if (event.target === sapDialog) closeSapDialog();
});
document.getElementById("sap-form").addEventListener("submit", confirmSap);
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  closeFileMenu();
  if (!projectDialog.hidden) closeProjectDialog();
  if (!sapDialog.hidden) closeSapDialog();
});
document.addEventListener("click", (event) => {
  if (fileMenu && !fileMenu.hidden && !fileMenu.contains(event.target)) closeFileMenu();
});
newChatBtn.addEventListener("click", newConversation);
searchEl.addEventListener("input", renderHistory);
formEl.addEventListener("submit", onSubmit);
inputEl.addEventListener("input", () => {
  fitInput();
  syncSend();
});
inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    formEl.requestSubmit();
  }
});
toggleBtn.addEventListener("click", () => setPanel(resultsEl.hidden));
for (const button of document.querySelectorAll(".tabs button")) {
  button.addEventListener("click", () => showTab(button.dataset.tab));
}

let booting = false;
let projectsLoaded = false;
let currentTab = "files";
let filesRequest = 0;
let preferredLeft = 0;
let preferredRight = 0;

init();
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && !projectsLoaded) init();
});

function remember(key, value) {
  try { localStorage.setItem(key, value); } catch (error) { /* 窗口刚打开时可能还写不进 */ }
  try { sessionStorage.setItem(key, value); } catch (error) { /* 同上 */ }
}

function recall(key) {
  try {
    return localStorage.getItem(key) || sessionStorage.getItem(key) || "";
  } catch (error) {
    return "";
  }
}

function forget(key) {
  try { localStorage.removeItem(key); } catch (error) { /* 没有这份记录也没关系 */ }
  try { sessionStorage.removeItem(key); } catch (error) { /* 同上 */ }
}

function fetchJson(url, options) {
  const controller = new AbortController();
  let abortTimer = 0;
  let watchdog = 0;
  const request = fetch(url, { ...(options || {}), signal: controller.signal, cache: "no-store" }).then((response) => {
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  });
  request.catch(() => {});
  const timeout = new Promise((_, reject) => {
    watchdog = setTimeout(() => reject(new Error("timeout")), 4500);
  });
  abortTimer = setTimeout(() => controller.abort(), 4000);
  return Promise.race([request, timeout]).finally(() => {
    clearTimeout(abortTimer);
    clearTimeout(watchdog);
  });
}

function chosenProject() {
  if (!projects.length) return "";
  const savedProject = recall("agent-project-id");
  return projects.some((item) => item.id === savedProject) ? savedProject : projects[0].id;
}

function applyBootProjects() {
  const boot = window.__BOOT_PROJECTS__;
  if (!Array.isArray(boot) || !boot.length) return false;
  projects = boot.slice();
  projectsLoaded = true;
  renderProjects();
  return true;
}

async function init() {
  if (booting) return;
  booting = true;
  try {
    const savedPanel = recall("agent-results-open");
    if (savedPanel === "") setPanel(window.innerWidth >= 1180);
    else setPanel(savedPanel === "1");
    applyBootProjects();
    showTab();
    const first = chosenProject();
    if (first) selectProject(first);
    loadMeta();
    await loadProjects();
    const next = chosenProject();
    if (!next) {
      applyProjectChrome();
      showWelcome();
      return;
    }
    if (next !== activeProjectId) await selectProject(next);
  } catch (error) {
    if (statusText.textContent === "正在连接") statusText.textContent = "页面没有完成加载";
  } finally {
    booting = false;
  }
}

async function loadMeta() {
  let data;
  try {
    data = await fetchJson("/api/meta");
  } catch (error) {
    if (statusText.textContent === "正在连接") statusText.textContent = "模型状态没有读出来";
    return;
  }
  modelEl.replaceChildren();
  for (const name of data.models) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = modelLabel(name);
    option.selected = name === data.model;
    modelEl.append(option);
  }
  statusDot.classList.toggle("is-ready", Boolean(data.ready));
  statusText.textContent = data.ready ? "DeepSeek 已连接" : "等待 API Key";
  bannerEl.hidden = Boolean(data.ready);
  if (!data.ready) {
    bannerEl.textContent = "还没有 API Key。请在项目根目录的 .env 里填写 DEEPSEEK_API_KEY，保存后刷新此页。";
  }
}

async function loadProjects() {
  let lastError = null;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      const data = await fetchJson("/api/projects");
      projects = data.projects || [];
      projectsLoaded = true;
      renderProjects();
      return;
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
  }
  if (!projects.length) {
    projectsLoaded = false;
    statusText.textContent = "项目没有读出来";
    renderProjects();
  }
}

function renderProjects() {
  projectsEl.replaceChildren();
  if (!projects.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "还没有项目";
    projectsEl.append(empty);
    return;
  }
  for (const item of projects) projectsEl.append(projectRow(item));
}

function projectRow(item) {
  const row = document.createElement("div");
  row.className = "project-row";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "project" + (item.id === activeProjectId ? " is-active" : "");
  button.addEventListener("click", () => selectProject(item.id));
  const name = document.createElement("span");
  name.className = "project-name";
  name.textContent = item.name;
  button.append(name);
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "conv-delete";
  remove.setAttribute("aria-label", "删除项目");
  remove.textContent = "×";
  remove.addEventListener("click", (event) => {
    event.stopPropagation();
    deleteProject(item.id, item.name);
  });
  row.append(button, remove);
  return row;
}

async function selectProject(id) {
  if (!projects.some((item) => item.id === id)) return;
  if (id === activeProjectId && !streaming) return;
  if (streaming) stop();
  activeProjectId = id;
  remember("agent-project-id", id);
  activeId = null;
  messagesEl.replaceChildren();
  inputEl.value = "";
  searchEl.value = "";
  fitInput();
  hideToast();
  applyProjectChrome();
  await loadConversations();
}

function openProjectDialog() {
  projectError.hidden = true;
  projectError.textContent = "";
  projectNameEl.value = "";
  projectDialog.hidden = false;
  projectNameEl.focus();
}

function closeProjectDialog() {
  projectDialog.hidden = true;
}

function showSapDialog() {
  sapDialog.hidden = false;
}

function closeSapDialog() {
  sapDialog.hidden = true;
}

function confirmSap(event) {
  event.preventDefault();
  closeSapDialog();
  sendMessage("确认调用 SAP2000", { confirmSap: true });
}

async function createProject(event) {
  event.preventDefault();
  projectError.hidden = true;
  const response = await fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: projectNameEl.value }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    projectError.hidden = false;
    projectError.textContent = data.message || "没有建成。";
    return;
  }
  closeProjectDialog();
  projects = [data, ...projects.filter((item) => item.id !== data.id)];
  projects.sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
  await selectProject(data.id);
}

async function deleteProject(id, name) {
  if (!window.confirm("删除项目「" + name + "」？其中的对话会一起删掉，资料和成果目录会保留。")) return;
  if (streaming && activeProjectId === id) stop();
  const response = await fetch("/api/projects/" + encodeURIComponent(id), { method: "DELETE" });
  if (!response.ok) {
    showToast("没有删掉。");
    return;
  }
  projects = projects.filter((item) => item.id !== id);
  if (activeProjectId === id) {
    activeProjectId = null;
    activeId = null;
    forget("agent-project-id");
    conversations = [];
    messagesEl.replaceChildren();
    inputEl.value = "";
    fitInput();
    if (projects[0]) {
      await selectProject(projects[0].id);
      return;
    }
    applyProjectChrome();
    renderHistory();
    showWelcome();
  } else {
    renderProjects();
  }
}

function currentProject() {
  return projects.find((item) => item.id === activeProjectId) || null;
}

function applyProjectChrome() {
  const project = currentProject();
  projectLabel.textContent = project ? project.name : "未选择项目";
  newChatBtn.disabled = !project;
  searchEl.disabled = !project;
  inputEl.disabled = !project;
  modelEl.disabled = !project;
  inputEl.placeholder = project ? "输入消息，Enter 发送" : "请先新建项目";
  if (!activeId) {
    titleEl.textContent = project ? "新对话" : "设计助手";
    document.title = project ? project.name + " · 设计助手" : "设计助手";
  }
  syncSend();
  renderProjects();
  renderResult(currentTab);
}

function showWelcome() {
  const project = currentProject();
  if (!project) {
    welcomeTitle.textContent = "先新建一个项目";
    welcomeText.textContent = "每个项目的对话单独保存，不会和别的项目混在一起。";
    welcomeEl.hidden = false;
    return;
  }
  if (messagesEl.childElementCount) {
    welcomeEl.hidden = true;
    return;
  }
  welcomeTitle.textContent = "需要我做什么？";
  welcomeText.textContent = "只讨论「" + project.name + "」。可以说「从资料提取设计参数」，或「设计支架」先布置线模。";
  welcomeEl.hidden = false;
}

async function loadConversations() {
  if (!activeProjectId) {
    conversations = [];
    renderHistory();
    showWelcome();
    return;
  }
  const response = await fetch("/api/conversations?project_id=" + encodeURIComponent(activeProjectId));
  const data = await response.json();
  conversations = data.conversations || [];
  renderHistory();
  if (conversations.length) await openConversation(conversations[0].id);
  else newConversation();
}

function renderHistory() {
  const query = searchEl.value.trim().toLowerCase();
  const matched = conversations.filter((item) => item.title.toLowerCase().includes(query));
  historyEl.replaceChildren();
  if (!matched.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = !activeProjectId
      ? "请先选择项目"
      : conversations.length
        ? "没有匹配的对话"
        : "还没有对话";
    historyEl.append(empty);
    return;
  }
  const groups = new Map();
  for (const item of matched) {
    const label = bucket(item.updated_at);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(item);
  }
  for (const label of ["今天", "昨天", "更早"]) {
    const items = groups.get(label);
    if (!items) continue;
    const heading = document.createElement("div");
    heading.className = "group-label";
    heading.textContent = label;
    historyEl.append(heading);
    for (const item of items) historyEl.append(conversationRow(item));
  }
}

function conversationRow(item) {
  const row = document.createElement("div");
  row.className = "conv-row";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "conv" + (item.id === activeId ? " is-active" : "");
  button.addEventListener("click", () => openConversation(item.id));
  const name = document.createElement("span");
  name.className = "conv-title";
  name.textContent = item.title;
  const time = document.createElement("span");
  time.className = "conv-time";
  time.textContent = formatTime(item.updated_at);
  button.append(name, time);
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "conv-delete";
  remove.setAttribute("aria-label", "删除对话");
  remove.textContent = "×";
  remove.addEventListener("click", (event) => {
    event.stopPropagation();
    deleteConversation(item.id, item.title);
  });
  row.append(button, remove);
  return row;
}

async function openConversation(id) {
  if (streaming && activeId === id) return;
  if (streaming) stop();
  const response = await fetch("/api/conversations/" + encodeURIComponent(id));
  if (!response.ok) {
    showToast("这则对话打不开。");
    return;
  }
  const data = await response.json();
  if (data.project_id && data.project_id !== activeProjectId) {
    showToast("这则对话不属于当前项目。");
    return;
  }
  activeId = data.id;
  titleEl.textContent = data.title;
  document.title = pageTitle(data.title);
  messagesEl.replaceChildren();
  for (const message of data.messages || []) {
    appendMessage(message.role, message.content, { markdown: message.role === "assistant" });
  }
  showWelcome();
  hideToast();
  renderHistory();
  scrollDown();
}

function newConversation() {
  if (!activeProjectId) return;
  if (streaming) stop();
  activeId = null;
  titleEl.textContent = "新对话";
  document.title = pageTitle("新对话");
  messagesEl.replaceChildren();
  inputEl.value = "";
  fitInput();
  syncSend();
  hideToast();
  showWelcome();
  renderHistory();
  inputEl.focus();
}

function pageTitle(conversationTitle) {
  const project = currentProject();
  if (!project) return "设计助手";
  if (!conversationTitle || conversationTitle === "新对话") return project.name + " · 设计助手";
  return conversationTitle + " · " + project.name;
}

function onSubmit(event) {
  event.preventDefault();
  if (streaming) {
    stop();
    return;
  }
  sendMessage();
}

async function sendMessage(textOverride, options) {
  const text = String(textOverride || inputEl.value).trim();
  if (!activeProjectId) {
    showToast("请先新建并选中一个项目。");
    return;
  }
  if (!text || streaming) return;
  const projectAtSend = activeProjectId;
  const previous = inputEl.value;
  if (!textOverride) inputEl.value = "";
  fitInput();
  syncSend();
  hideToast();
  welcomeEl.hidden = true;
  const userNode = appendMessage("user", text);
  const pending = appendMessage("assistant", "正在回复");
  pending.classList.add("is-pending");
  const body = pending.querySelector(".msg-text");
  setStreaming(true);
  abortController = new AbortController();
  let started = false;
  let accumulated = "";
  scrollDown();
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: activeProjectId,
        conversation_id: activeId,
        text,
        model: modelEl.value,
        confirm_sap: Boolean(options && options.confirmSap),
      }),
      signal: abortController.signal,
    });
    if (!response.ok) {
      if (activeProjectId !== projectAtSend) return;
      userNode.remove();
      pending.remove();
      inputEl.value = previous;
      fitInput();
      const data = await response.json().catch(() => ({}));
      showToast(data.message || "发送失败。");
      showWelcome();
      return;
    }
    started = true;
    await readStream(response, {
      onMeta(conversation) {
        if (activeProjectId !== projectAtSend) return;
        if (conversation.project_id && conversation.project_id !== projectAtSend) return;
        activeId = conversation.id;
        upsert(conversation);
        titleEl.textContent = conversation.title;
        document.title = pageTitle(conversation.title);
        renderHistory();
      },
      onDelta(piece) {
        pending.classList.remove("is-pending");
        pending.classList.add("is-streaming");
        accumulated += piece;
        body.textContent = accumulated;
        scrollDown();
      },
      onError(message) {
        pending.classList.remove("is-pending", "is-streaming");
        pending.classList.add("is-error");
        body.textContent = accumulated ? accumulated + "\n\n" + message : message;
      },
      onDone(event) {
        pending.classList.remove("is-pending", "is-streaming");
        if (accumulated) body.innerHTML = renderMarkdown(accumulated);
        else body.textContent = "模型没有返回文字。";
        if (event && event.refresh_layout && activeProjectId === projectAtSend) showTab("layout");
        else if (event && event.refresh_files && activeProjectId === projectAtSend) renderResult();
        if (event && event.confirm_sap && activeProjectId === projectAtSend) showSapDialog();
        bannerEl.hidden = true;
        statusDot.classList.add("is-ready");
        statusText.textContent = "DeepSeek 已连接";
      },
    });
  } catch (error) {
    if (error.name === "AbortError" && !started) {
      userNode.remove();
      pending.remove();
      inputEl.value = previous;
      fitInput();
      showWelcome();
    } else if (error.name === "AbortError") {
      pending.classList.remove("is-pending", "is-streaming");
      if (!accumulated) pending.remove();
      else body.textContent = accumulated;
    } else if (!started) {
      userNode.remove();
      pending.remove();
      inputEl.value = previous;
      fitInput();
      showToast("没有连上助手服务。");
      showWelcome();
    } else {
      pending.classList.remove("is-pending", "is-streaming");
      pending.classList.add("is-error");
      body.textContent = accumulated || "回复中断了。";
    }
  } finally {
    setStreaming(false);
    abortController = null;
    scrollDown();
    inputEl.focus();
  }
}

async function readStream(response, handlers) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const line = frame.split("\n").find((item) => item.startsWith("data:"));
      if (!line) continue;
      const data = JSON.parse(line.slice(5).trim());
      if (data.type === "meta" && data.conversation) handlers.onMeta(data.conversation);
      else if (data.type === "delta") handlers.onDelta(data.text || "");
      else if (data.type === "error") handlers.onError(data.message || "没有收到模型回复。");
      else if (data.type === "done") handlers.onDone(data);
    }
  }
}

function stop() {
  if (abortController) abortController.abort();
}

function appendMessage(role, text, { markdown = false } = {}) {
  const node = document.createElement("article");
  node.className = "msg " + (role === "assistant" ? "assistant" : "user");
  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.innerHTML = ROBOT_SVG;
    node.append(avatar);
  }
  const body = document.createElement("div");
  body.className = "msg-text";
  if (role === "assistant" && markdown) body.innerHTML = renderMarkdown(text);
  else body.textContent = text;
  node.append(body);
  messagesEl.append(node);
  return node;
}

async function deleteConversation(id, title) {
  if (!window.confirm("删除「" + title + "」？")) return;
  if (streaming && activeId === id) stop();
  const response = await fetch("/api/conversations/" + encodeURIComponent(id), { method: "DELETE" });
  if (!response.ok) {
    showToast("没有删掉。");
    return;
  }
  conversations = conversations.filter((item) => item.id !== id);
  if (activeId === id) newConversation();
  else renderHistory();
}

function upsert(summary) {
  const index = conversations.findIndex((item) => item.id === summary.id);
  if (index >= 0) conversations[index] = { ...conversations[index], ...summary };
  else conversations.unshift(summary);
  conversations.sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
}

function setStreaming(value) {
  streaming = value;
  syncSend();
}

function syncSend() {
  if (streaming) {
    sendBtn.disabled = false;
    sendBtn.textContent = "停止";
    sendBtn.classList.add("is-stop");
    return;
  }
  sendBtn.classList.remove("is-stop");
  sendBtn.textContent = "发送";
  sendBtn.disabled = !activeProjectId || inputEl.value.trim() === "";
}

function fitInput() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
}

function setPanel(open) {
  resultsEl.hidden = !open;
  toggleBtn.setAttribute("aria-expanded", open ? "true" : "false");
  toggleBtn.textContent = open ? "收起结果" : "结果";
  remember("agent-results-open", open ? "1" : "0");
  if (open) keepColumnsInView();
}

const LEFT_MIN = 180;
const LEFT_MAX = 480;
const RIGHT_MIN = 280;
const RIGHT_MAX = 840;
const CENTER_MIN = 320;
const SPLITTER_WIDTH = 8;

function initSplitters() {
  preferredLeft = Number(recall("agent-sidebar-width")) || 0;
  preferredRight = Number(recall("agent-results-width")) || 0;
  keepColumnsInView();
  bindSplitter(document.getElementById("split-left"), "left");
  bindSplitter(document.getElementById("split-right"), "right");
  window.addEventListener("resize", () => {
    if (document.body.classList.contains("is-resizing")) return;
    keepColumnsInView();
  });
}

function bindSplitter(handle, side) {
  const key = side === "left" ? "agent-sidebar-width" : "agent-results-width";
  syncSplitterAria(handle, side, side === "left" ? currentLeft() : currentRight());
  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || (side === "right" && resultsEl.hidden)) return;
    event.preventDefault();
    const startX = event.clientX;
    const start = side === "left" ? currentLeft() : currentRight();
    handle.classList.add("is-dragging");
    document.body.classList.add("is-resizing");
    handle.setPointerCapture(event.pointerId);
    const onMove = (ev) => {
      const dx = ev.clientX - startX;
      const desired = side === "left" ? start + dx : start - dx;
      syncSplitterAria(handle, side, applyColumn(side, desired));
    };
    const onEnd = () => {
      handle.classList.remove("is-dragging");
      document.body.classList.remove("is-resizing");
      handle.removeEventListener("pointermove", onMove);
      handle.removeEventListener("pointerup", onEnd);
      handle.removeEventListener("pointercancel", onEnd);
      const width = side === "left" ? currentLeft() : currentRight();
      if (side === "left") preferredLeft = width;
      else preferredRight = width;
      remember(key, String(width));
      syncSplitterAria(handle, side, width);
    };
    handle.addEventListener("pointermove", onMove);
    handle.addEventListener("pointerup", onEnd);
    handle.addEventListener("pointercancel", onEnd);
  });
  handle.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    if (side === "right" && resultsEl.hidden) return;
    event.preventDefault();
    const step = event.shiftKey ? 32 : 8;
    const dir = event.key === "ArrowRight" ? 1 : -1;
    const current = side === "left" ? currentLeft() : currentRight();
    const desired = side === "left" ? current + dir * step : current - dir * step;
    const width = applyColumn(side, desired);
    if (side === "left") preferredLeft = width;
    else preferredRight = width;
    remember(key, String(width));
    syncSplitterAria(handle, side, width);
  });
}

function keepColumnsInView() {
  if (preferredLeft) applyColumn("left", preferredLeft);
  if (!resultsEl.hidden && preferredRight) applyColumn("right", preferredRight);
}

function applyColumn(side, desired) {
  const width = clampWidth(side, desired);
  document.querySelector(".app").style.setProperty(side === "left" ? "--col-left" : "--col-right", width + "px");
  return width;
}

function clampWidth(side, desired) {
  const { min, max } = columnLimits(side);
  return Math.round(Math.min(Math.max(min, max), Math.max(min, desired)));
}

function columnLimits(side) {
  const app = document.querySelector(".app");
  const rightOpen = !resultsEl.hidden;
  const splitters = rightOpen ? SPLITTER_WIDTH * 2 : SPLITTER_WIDTH;
  const other = side === "left" ? (rightOpen ? currentRight() : 0) : currentLeft();
  const min = side === "left" ? LEFT_MIN : RIGHT_MIN;
  const cap = side === "left" ? LEFT_MAX : RIGHT_MAX;
  const room = app.clientWidth - splitters - CENTER_MIN - other;
  return { min, max: Math.min(cap, Math.max(min, room)) };
}

function currentLeft() {
  return Math.round(document.querySelector(".sidebar").getBoundingClientRect().width);
}

function currentRight() {
  if (resultsEl.hidden) return 0;
  return Math.round(resultsEl.getBoundingClientRect().width);
}

function syncSplitterAria(handle, side, width) {
  const { min, max } = columnLimits(side);
  handle.setAttribute("aria-valuemin", String(min));
  handle.setAttribute("aria-valuemax", String(max));
  handle.setAttribute("aria-valuenow", String(width));
}

initSplitters();

function showTab(tab) {
  currentTab = tab || "files";
  for (const button of document.querySelectorAll(".tabs button")) {
    button.classList.toggle("is-active", button.dataset.tab === currentTab);
  }
  renderResult();
}

function renderLayout(project, ticket) {
  resultBody.classList.add("is-layout");
  resultBody.textContent = "正在画主梁和立柱…";
  fetch("/api/projects/" + encodeURIComponent(project.id) + "/layout")
    .then((response) => {
      if (!response.ok) throw new Error("layout");
      return response.json();
    })
    .then((data) => {
      if (ticket !== filesRequest || currentProject()?.id !== project.id || currentTab !== "layout") return;
      paintLayout(data);
    })
    .catch(() => {
      if (ticket !== filesRequest) return;
      resultBody.textContent = "布置图没有画出来。";
    });
}

function paintLayout(data) {
  resultBody.replaceChildren();
  if (!data.ready) {
    const message = document.createElement("p");
    message.className = "layout-message";
    message.textContent = data.message || "暂时不能画主梁和立柱。";
    resultBody.append(message);
    return;
  }
  const scroll = document.createElement("div");
  scroll.className = "layout-scroll";
  scroll.innerHTML = data.svg || "";
  resultBody.append(scroll);
  for (const issue of data.issues || []) {
    const row = document.createElement("p");
    row.className = "layout-issues";
    row.textContent = issue;
    resultBody.append(row);
  }
  if (data.overhang_start_mm != null && data.overhang_end_mm != null) {
    const note = document.createElement("p");
    note.className = "layout-message";
    note.textContent = "起点悬挑 " + formatMm(data.overhang_start_mm) + " mm，终点悬挑 " + formatMm(data.overhang_end_mm) + " mm";
    resultBody.append(note);
  }
  if (data.columns && data.columns.length) {
    resultBody.append(layoutTable(data.columns));
  }
}

function layoutTable(columns) {
  const table = document.createElement("table");
  table.className = "layout-table";
  const head = document.createElement("tr");
  for (const label of ["序号", "类型", "y（mm）", "间距（mm）"]) {
    const cell = document.createElement("th");
    cell.textContent = label;
    head.append(cell);
  }
  table.append(head);
  columns.forEach((column, index) => {
    const row = document.createElement("tr");
    const gap = column.gap_mm == null ? "—" : formatMm(column.gap_mm);
    const cells = [
      String(column.index || index + 1),
      column.kind === "drive" ? "驱动立柱" : "非驱动立柱",
      formatMm(column.y_mm),
      gap,
    ];
    for (const value of cells) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    table.append(row);
  });
  return table;
}

function formatMm(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  if (Math.abs(number - Math.round(number)) < 0.05) return String(Math.round(number));
  return number.toFixed(1);
}

function renderResult() {
  const project = currentProject();
  const ticket = ++filesRequest;
  resultBody.classList.remove("is-path", "is-layout");
  if (!project) {
    resultBody.textContent = RESULT_COPY;
    return;
  }
  if (currentTab === "layout") {
    renderLayout(project, ticket);
    return;
  }
  resultBody.classList.add("is-path");
  resultBody.textContent = "正在读取文件…";
  fetch("/api/projects/" + encodeURIComponent(project.id) + "/files")
    .then((response) => {
      if (!response.ok) throw new Error("read");
      return response.json();
    })
    .then((data) => {
      if (ticket !== filesRequest || currentProject()?.id !== project.id) return;
      paintFiles(project.id, data);
    })
    .catch(() => {
      if (ticket !== filesRequest) return;
      resultBody.textContent = "文件没有读出来。";
    });
}

let fileMenu = null;
let fileMenuTarget = null;

function paintFiles(projectId, data) {
  closeFileMenu();
  resultBody.replaceChildren();
  const path = document.createElement("div");
  path.className = "result-path";
  path.textContent = data.path || "";
  resultBody.append(path);
  const picker = document.createElement("input");
  picker.type = "file";
  picker.multiple = true;
  picker.hidden = true;
  picker.addEventListener("change", () => {
    const chosen = [...picker.files];
    picker.value = "";
    addMaterials(projectId, chosen);
  });
  resultBody.append(picker);
  for (const folder of data.folders || []) {
    const section = document.createElement("section");
    section.className = "file-section";
    const heading = document.createElement("h3");
    heading.textContent = folder.name;
    section.append(heading);
    if (folder.name === "资料") {
      section.classList.add("is-drop");
      const hint = document.createElement("p");
      hint.className = "file-hint";
      hint.textContent = "把文件拖到这里。在文件上右键可以添加或删除。";
      section.append(hint);
    }
    section.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      openFileMenu(event, { projectId, path: "", name: "", picker });
    });
    if (!folder.files || !folder.files.length) {
      const empty = document.createElement("p");
      empty.className = "file-empty";
      empty.textContent = "还没有文件";
      section.append(empty);
    } else {
      section.append(fileList(projectId, folder.files, picker));
    }
    resultBody.append(section);
  }
}

function fileList(projectId, files, picker) {
  const list = document.createElement("ul");
  list.className = "file-list";
  for (const file of files) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "file-link";
    button.textContent = file.directory ? file.name + "/" : file.name;
    button.addEventListener("click", () => openWorkspaceFile(projectId, file.path));
    button.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      event.stopPropagation();
      openFileMenu(event, {
        projectId,
        path: file.directory ? "" : file.path,
        name: file.name,
        picker,
      });
    });
    item.append(button);
    list.append(item);
  }
  return list;
}

function ensureFileMenu() {
  if (fileMenu) return fileMenu;
  fileMenu = document.createElement("div");
  fileMenu.className = "file-menu";
  fileMenu.hidden = true;
  for (const [action, label] of [["add", "添加文件"], ["delete", "删除文件"]]) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.action = action;
    button.textContent = label;
    fileMenu.append(button);
  }
  fileMenu.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    const target = fileMenuTarget;
    closeFileMenu();
    if (!target) return;
    if (button.dataset.action === "add") target.picker.click();
    if (button.dataset.action === "delete") deleteWorkspaceFile(target.projectId, target.path, target.name);
  });
  document.body.append(fileMenu);
  return fileMenu;
}

function openFileMenu(event, target) {
  const menu = ensureFileMenu();
  fileMenuTarget = target;
  menu.querySelector("[data-action=delete]").disabled = !target.path;
  menu.hidden = false;
  const width = menu.offsetWidth;
  const height = menu.offsetHeight;
  const margin = 8;
  let x = event.clientX;
  let y = event.clientY;
  if (x + width > window.innerWidth - margin) x = window.innerWidth - width - margin;
  if (y + height > window.innerHeight - margin) y = window.innerHeight - height - margin;
  menu.style.left = Math.max(margin, x) + "px";
  menu.style.top = Math.max(margin, y) + "px";
}

function closeFileMenu() {
  if (!fileMenu) return;
  fileMenu.hidden = true;
  fileMenuTarget = null;
}

function deleteWorkspaceFile(projectId, path, name) {
  if (!path || currentProject()?.id !== projectId) return;
  if (!window.confirm("删除「" + name + "」？这个文件会从项目目录里去掉。")) return;
  showToast("正在删除…");
  fetch("/api/projects/" + encodeURIComponent(projectId) + "/files", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  }).then(async (response) => {
    const data = await response.json().catch(() => ({}));
    if (currentProject()?.id !== projectId) return;
    if (!response.ok) {
      showToast(data.message || "没有删掉。");
      return;
    }
    paintFiles(projectId, data);
    showToast("已删除。");
  }).catch(() => {
    if (currentProject()?.id === projectId) showToast("没有删掉。");
  });
}

function hasDroppedFiles(event) {
  return Boolean(event.dataTransfer && [...event.dataTransfer.types].includes("Files"));
}

function droppedFiles(dataTransfer) {
  const items = [...(dataTransfer.items || [])];
  const files = [];
  let sawDirectory = false;
  if (items.length && items[0].webkitGetAsEntry) {
    for (const item of items) {
      const entry = item.webkitGetAsEntry && item.webkitGetAsEntry();
      if (entry && entry.isDirectory) {
        sawDirectory = true;
        continue;
      }
      const file = item.getAsFile && item.getAsFile();
      if (file) files.push(file);
    }
    return { files, sawDirectory };
  }
  return { files: [...dataTransfer.files], sawDirectory: false };
}

document.addEventListener("dragover", (event) => {
  if (!hasDroppedFiles(event)) return;
  event.preventDefault();
  const zone = event.target.closest ? event.target.closest(".is-drop") : null;
  for (const item of document.querySelectorAll(".is-drop")) {
    item.classList.toggle("is-over", item === zone);
  }
});

document.addEventListener("drop", (event) => {
  if (!hasDroppedFiles(event)) return;
  event.preventDefault();
  for (const item of document.querySelectorAll(".is-drop")) item.classList.remove("is-over");
  const project = currentProject();
  if (!project) return;
  const zone = event.target.closest ? event.target.closest(".is-drop") : null;
  if (!zone) {
    showToast("请把文件拖到「资料」上。");
    return;
  }
  const dropped = droppedFiles(event.dataTransfer);
  if (dropped.sawDirectory && !dropped.files.length) {
    showToast("请拖入文件，不要拖文件夹。");
    return;
  }
  if (dropped.sawDirectory) showToast("文件夹已跳过，只放入文件。");
  addMaterials(project.id, dropped.files);
});

function addMaterials(projectId, fileList) {
  const files = [...fileList].filter((file) => file && file.name);
  if (!files.length || currentProject()?.id !== projectId) return;
  const body = new FormData();
  for (const file of files) body.append("files", file, file.name);
  showToast("正在放入资料…");
  return fetch("/api/projects/" + encodeURIComponent(projectId) + "/materials", {
    method: "POST",
    body,
  }).then(async (response) => {
    const data = await response.json().catch(() => ({}));
    if (currentProject()?.id !== projectId) return;
    if (!response.ok) {
      showToast(data.message || "没有放进资料。");
      return;
    }
    paintFiles(projectId, data);
    showToast(data.message || "已放入资料。");
  }).catch(() => {
    if (currentProject()?.id === projectId) showToast("没有放进资料。");
  });
}

function openWorkspaceFile(projectId, path) {
  fetch("/api/projects/" + encodeURIComponent(projectId) + "/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  }).then(async (response) => {
    if (response.ok) return;
    const data = await response.json().catch(() => ({}));
    showToast(data.message || "没有打开。");
  }).catch(() => showToast("没有打开。"));
}

function showToast(message) {
  toastEl.hidden = false;
  toastEl.textContent = message;
}

function hideToast() {
  toastEl.hidden = true;
  toastEl.textContent = "";
}

function scrollDown() {
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

function modelLabel(name) {
  if (name === "deepseek-flash") return "DeepSeek Flash";
  if (name === "deepseek-v4-pro") return "DeepSeek V4 Pro";
  return name;
}

function bucket(iso) {
  const date = new Date(iso);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (date >= today) return "今天";
  if (date >= yesterday) return "昨天";
  return "更早";
}

function formatTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (value) => String(value).padStart(2, "0");
  const time = pad(date.getHours()) + ":" + pad(date.getMinutes());
  if (bucket(iso) === "今天") return time;
  return pad(date.getMonth() + 1) + "-" + pad(date.getDate()) + " " + time;
}

function renderMarkdown(source) {
  const parts = String(source).split("```");
  return parts.map((part, index) => {
    if (index % 2 === 1) {
      const newline = part.indexOf("\n");
      const body = newline === -1 ? part : part.slice(newline + 1);
      return "<pre><code>" + escapeHtml(body.replace(/\n$/, "")) + "</code></pre>";
    }
    return renderBlocks(part);
  }).join("");
}

function renderBlocks(source) {
  const lines = source.split("\n");
  let html = "";
  let list = [];
  const flush = () => {
    if (!list.length) return;
    html += "<ul>" + list.map((item) => "<li>" + inline(item) + "</li>").join("") + "</ul>";
    list = [];
  };
  for (const line of lines) {
    const item = /^[-*]\s+(.*)$/.exec(line);
    if (item) {
      list.push(item[1]);
      continue;
    }
    flush();
    if (!line.trim()) continue;
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) html += '<p class="md-h">' + inline(heading[2]) + "</p>";
    else html += "<p>" + inline(line) + "</p>";
  }
  flush();
  return html;
}

function inline(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}
