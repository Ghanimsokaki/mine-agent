const POLL_ALARM = "forgepilot-poll";

async function bridge() {
  const { pairing } = await chrome.storage.local.get("pairing");
  return pairing || null;
}

async function rpc(functionName, body) {
  const pair = await bridge();
  if (!pair?.project_url || !pair?.anon_key || !pair?.agent_id || !pair?.bridge_secret) {
    throw new Error("Pair this browser first.");
  }
  const response = await fetch(`${pair.project_url.replace(/\/$/, "")}/rest/v1/rpc/${functionName}`, {
    method: "POST",
    headers: {
      apikey: pair.anon_key,
      Authorization: `Bearer ${pair.anon_key}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ p_agent_id: pair.agent_id, p_secret: pair.bridge_secret, ...body })
  });
  if (!response.ok) throw new Error(`Bridge request failed (${response.status}).`);
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

async function saveStatus(status) {
  await chrome.storage.local.set({ lastStatus: { ...status, at: new Date().toISOString() } });
}

async function complete(taskId, status, result) {
  return rpc("complete_browser_task", {
    p_task_id: taskId,
    p_status: status,
    p_result: result || {}
  });
}

async function runTaskInActiveTab(task) {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab?.id || !tab.url || /^(chrome|edge|about|moz-extension):/i.test(tab.url)) {
    throw new Error("Open the authorized website in an ordinary browser tab, then try again.");
  }
  const outcome = await chrome.tabs.sendMessage(tab.id, { type: "forgepilot-task", task });
  if (!outcome?.status) throw new Error("The page bridge did not return a result.");
  return outcome;
}

async function pollOnce() {
  try {
    const pair = await bridge();
    if (!pair) return { status: "unpaired" };
    const task = await rpc("claim_browser_task", {});
    if (!task) {
      await saveStatus({ status: "waiting", message: "No queued task" });
      return { status: "waiting" };
    }
    await saveStatus({ status: "approval_needed", message: "Request sent to the active page", taskId: task.id });
    let outcome;
    try {
      outcome = await runTaskInActiveTab(task);
    } catch (error) {
      outcome = { status: "failed", result: { error: error.message || "Could not reach the active page." } };
    }
    await complete(task.id, outcome.status, outcome.result || {});
    await saveStatus({ status: outcome.status, message: outcome.result?.message || "Task finished", taskId: task.id });
    return outcome;
  } catch (error) {
    await saveStatus({ status: "error", message: error.message || "Bridge error" });
    return { status: "error", message: error.message };
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.5 });
});
chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.5 });
});
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === POLL_ALARM) pollOnce();
});
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "forgepilot-poll") {
    pollOnce().then(sendResponse);
    return true;
  }
  if (message?.type === "forgepilot-status") {
    chrome.storage.local.get(["pairing", "lastStatus"]).then(sendResponse);
    return true;
  }
});
