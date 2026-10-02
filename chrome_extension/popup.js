const bundle = document.getElementById("bundle");
const status = document.getElementById("status");

function setStatus(text, error = false) {
  status.textContent = text;
  status.className = error ? "error" : "";
}

async function refresh() {
  const data = await chrome.storage.local.get(["pairing", "lastStatus"]);
  if (data.pairing) bundle.value = JSON.stringify(data.pairing, null, 2);
  if (data.lastStatus) setStatus(`${data.lastStatus.status}: ${data.lastStatus.message || ""}`);
}

document.getElementById("save").addEventListener("click", async () => {
  try {
    const value = JSON.parse(bundle.value);
    if (value.version !== 1 || !value.project_url || !value.anon_key || !value.agent_id || !value.bridge_secret) {
      throw new Error("This does not look like a ForgePilot pairing bundle.");
    }
    await chrome.storage.local.set({ pairing: value });
    setStatus("Browser paired. Keep this extension enabled only when needed.");
  } catch (error) {
    setStatus(error.message || "Invalid JSON bundle.", true);
  }
});

document.getElementById("clear").addEventListener("click", async () => {
  await chrome.storage.local.remove(["pairing", "lastStatus"]);
  bundle.value = "";
  setStatus("Browser unpaired.");
});

document.getElementById("poll").addEventListener("click", async () => {
  setStatus("Checking for a queued task…");
  const result = await chrome.runtime.sendMessage({ type: "forgepilot-poll" });
  setStatus(`${result?.status || "error"}: ${result?.message || "Task check finished."}`, result?.status === "error");
});

refresh();
