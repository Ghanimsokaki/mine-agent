const ALLOWED = new Set(["read_page", "click", "type", "insert_code", "select", "download_file"]);
const BLOCKED = /password|passcode|one[- ]?time|\botp\b|credit.?card|\bcvv\b|security.?code/i;

function elementLooksSensitive(element) {
  if (!element) return false;
  const fingerprint = [element.type, element.name, element.id, element.placeholder, element.autocomplete]
    .filter(Boolean).join(" ");
  return element.type === "password" || BLOCKED.test(fingerprint);
}

function safeAction(action) {
  const text = JSON.stringify(action || {});
  return action && ALLOWED.has(action.action) && !BLOCKED.test(text) &&
    (action.action === "download_file" || (typeof action.selector === "string" && action.selector.length <= 500));
}

function setInputValue(element, value) {
  const prototype = Object.getPrototypeOf(element);
  const descriptor = Object.getOwnPropertyDescriptor(prototype, "value") ||
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
  if (descriptor?.set) descriptor.set.call(element, value);
  else element.value = value;
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

function execute(action) {
  if (!safeAction(action)) throw new Error("This task was blocked by the bridge safety rules.");
  if (action.action === "read_page") {
    return { title: document.title, url: location.href, visible_text: (document.body?.innerText || "").slice(0, 12000) };
  }
  if (action.action === "download_file") {
    const blob = new Blob([String(action.text || "")], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = String(action.filename || "forgepilot-output.txt").replace(/[^a-zA-Z0-9._-]/g, "_");
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return { downloaded: link.download };
  }
  const element = document.querySelector(action.selector);
  if (!element) throw new Error(`No element matches selector: ${action.selector}`);
  if (elementLooksSensitive(element)) throw new Error("The bridge will not interact with sensitive input fields.");
  if (action.action === "click") {
    element.click();
    return { clicked: action.selector };
  }
  if (action.action === "select") {
    setInputValue(element, String(action.value || ""));
    return { selected: action.selector };
  }
  if (action.action === "type" || action.action === "insert_code") {
    if (!(element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element.isContentEditable)) {
      throw new Error("The selected element is not an editable field.");
    }
    const text = String(action.text || "");
    if (element.isContentEditable) {
      element.focus();
      element.textContent = text;
      element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
    } else {
      setInputValue(element, text);
      element.focus();
    }
    return { updated: action.selector, characters: text.length };
  }
  throw new Error("Unsupported action.");
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "forgepilot-task") return;
  const actions = Array.isArray(message.task?.payload?.actions) ? message.task.payload.actions : [];
  const source = message.task?.payload?.source || "ForgePilot";
  (async () => {
    const results = [];
    for (const action of actions) {
      const description = String(action.description || action.action || "browser action");
      const warning = action.action === "read_page"
        ? " This shares visible page text with your private ForgePilot workspace."
        : "";
      const approved = window.confirm(`${source} requests: ${description}\n\nApprove this one action?${warning}`);
      if (!approved) {
        sendResponse({ status: "declined", result: { message: "User declined a browser action.", results } });
        return;
      }
      try {
        results.push({ action: action.action, ok: true, output: execute(action) });
      } catch (error) {
        sendResponse({ status: "failed", result: { message: error.message || "Action failed.", results } });
        return;
      }
    }
    sendResponse({ status: "completed", result: { message: "Approved action(s) completed.", url: location.href, results } });
  })();
  return true;
});
