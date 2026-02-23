import { WebSocketManager } from "./shared/websocket";
import type {
  ServerMessage,
  ScreenshotRequest,
  ActionCommand,
  ScreenshotResponse,
  ActionResult,
  ContentActionMessage,
  ContentActionResponse,
} from "./shared/types";

// ── Session state ──
let wsManager: WebSocketManager | null = null;
let activeTabId: number | null = null;
let sessionCode: string | null = null;

// ── Handle messages from popup ──
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === "connect_session") {
    startSession(msg.code, msg.tabId);
    sendResponse({ ok: true });
  } else if (msg.action === "get_status") {
    sendResponse({
      connected: wsManager?.isConnected ?? false,
      code: sessionCode,
    });
  }
  return false;
});

function startSession(code: string, tabId: number): void {
  // Clean up any existing session
  if (wsManager) {
    wsManager.close();
  }

  sessionCode = code;
  activeTabId = tabId;

  wsManager = new WebSocketManager(code, handleServerMessage, () => {
    console.log("WebSocket disconnected");
  });
  wsManager.connect();
  console.log(`Session started: code=${code}, tab=${tabId}`);
}

// ── Route server messages ──
function handleServerMessage(msg: ServerMessage): void {
  switch (msg.type) {
    case "screenshot_request":
      handleScreenshotRequest(msg);
      break;
    case "action_command":
      handleActionCommand(msg);
      break;
    case "status":
      console.log("Status:", msg.status, msg.detail ?? "");
      break;
    case "session_ended":
      console.log("Session ended by server");
      cleanup();
      break;
    case "pong":
      break;
  }
}

// ── Ensure the session tab is the active tab in its window (without stealing window focus) ──
async function ensureTabActive(): Promise<void> {
  if (!activeTabId) return;
  try {
    const tab = await chrome.tabs.get(activeTabId);
    if (!tab.active) {
      await chrome.tabs.update(activeTabId, { active: true });
    }
  } catch {
    // Tab may have been closed
  }
}

// ── Screenshot handling ──
async function handleScreenshotRequest(req: ScreenshotRequest): Promise<void> {
  if (!activeTabId || !wsManager) return;

  try {
    // Make sure the session tab is the active tab in its window (for captureVisibleTab)
    await ensureTabActive();

    const tab = await chrome.tabs.get(activeTabId);
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId!, {
      format: "jpeg",
      quality: 80,
    });

    // dataUrl is "data:image/jpeg;base64,<data>"
    const base64Data = dataUrl.split(",")[1];

    // Use content script to get accurate viewport dimensions and devicePixelRatio
    let width = 1920;
    let height = 1080;
    let devicePixelRatio = 1;

    try {
      const [result] = await chrome.scripting.executeScript({
        target: { tabId: activeTabId },
        func: () => ({
          width: window.innerWidth,
          height: window.innerHeight,
          devicePixelRatio: window.devicePixelRatio,
        }),
      });
      if (result?.result) {
        width = result.result.width;
        height = result.result.height;
        devicePixelRatio = result.result.devicePixelRatio;
      }
    } catch {
      // Fall back to defaults
    }

    const response: ScreenshotResponse = {
      type: "screenshot_response",
      requestId: req.requestId,
      data: base64Data,
      width,
      height,
      devicePixelRatio,
    };
    wsManager.send(response);
  } catch (err) {
    console.error("Screenshot failed:", err);
  }
}

// ── Action handling ──
async function handleActionCommand(cmd: ActionCommand): Promise<void> {
  if (!activeTabId || !wsManager) return;

  try {
    // Handle navigate action directly in background (no content script needed)
    if (cmd.action === "navigate" && cmd.url) {
      await chrome.tabs.update(activeTabId, { url: cmd.url });
      // Wait for the page to start loading
      await waitForTabLoad(activeTabId);
      const result: ActionResult = {
        type: "action_result",
        requestId: cmd.requestId,
        success: true,
      };
      wsManager.send(result);
      return;
    }

    // Ensure content script is injected for other actions
    await ensureContentScript(activeTabId);

    // Forward action to content script
    const contentMsg: ContentActionMessage = {
      source: "pbu-background",
      action: cmd.action as "click" | "type" | "key" | "scroll",
      x: cmd.x,
      y: cmd.y,
      text: cmd.text,
      keys: cmd.keys,
      deltaX: cmd.deltaX,
      deltaY: cmd.deltaY,
    };

    const response = await sendToContentScript(activeTabId, contentMsg);

    const result: ActionResult = {
      type: "action_result",
      requestId: cmd.requestId,
      success: response.success,
      error: response.error,
    };
    wsManager.send(result);
  } catch (err) {
    const result: ActionResult = {
      type: "action_result",
      requestId: cmd.requestId,
      success: false,
      error: err instanceof Error ? err.message : "Unknown error",
    };
    wsManager.send(result);
  }
}

function waitForTabLoad(tabId: number): Promise<void> {
  return new Promise((resolve) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    }, 10000);

    const listener = (
      updatedTabId: number,
      changeInfo: { status?: string }
    ) => {
      if (updatedTabId === tabId && changeInfo.status === "complete") {
        clearTimeout(timeout);
        chrome.tabs.onUpdated.removeListener(listener);
        // Extra delay for page to settle
        setTimeout(resolve, 500);
      }
    };
    chrome.tabs.onUpdated.addListener(listener);
  });
}

function sendToContentScript(
  tabId: number,
  msg: ContentActionMessage
): Promise<ContentActionResponse> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error("Content script did not respond within 3s"));
    }, 3000);

    chrome.tabs.sendMessage(tabId, msg, (response: ContentActionResponse) => {
      clearTimeout(timeout);
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
      } else {
        resolve(response ?? { success: false, error: "No response" });
      }
    });
  });
}

async function ensureContentScript(tabId: number): Promise<void> {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"],
    });
  } catch {
    // Content script may already be injected or page doesn't allow it
  }
}

function cleanup(): void {
  if (wsManager) {
    wsManager.close();
    wsManager = null;
  }
  sessionCode = null;
  activeTabId = null;
}

// ── Service worker lifecycle ──
chrome.runtime.onInstalled.addListener(() => {
  console.log("PhoneBrowserUse extension installed");
});
