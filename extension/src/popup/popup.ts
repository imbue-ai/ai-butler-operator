import { createSession } from "../shared/api";

const btnStart = document.getElementById("btn-start") as HTMLButtonElement;
const statusEl = document.getElementById("status")!;
const screenStart = document.getElementById("screen-start")!;
const screenSession = document.getElementById("screen-session")!;
const codeEl = document.getElementById("session-code")!;
const phoneEl = document.getElementById("session-phone")!;
const sessionStatusEl = document.getElementById("session-status")!;

function formatPhone(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("1")) {
    return `+1 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  }
  return raw;
}

btnStart.addEventListener("click", async () => {
  btnStart.disabled = true;
  statusEl.textContent = "Creating session...";
  statusEl.className = "status";

  try {
    // Get the current tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) {
      throw new Error("No active tab found");
    }

    const session = await createSession();

    // Tell background to connect WebSocket for this session + tab
    chrome.runtime.sendMessage({
      action: "connect_session",
      code: session.code,
      tabId: tab.id,
    });

    // Show session info
    screenStart.classList.add("hidden");
    screenSession.classList.remove("hidden");
    codeEl.textContent = session.code;
    phoneEl.textContent = formatPhone(session.phone_number);
    statusEl.classList.add("hidden");
  } catch (err) {
    console.error("Failed to create session", err);
    statusEl.textContent = "Could not connect to server. Is it running?";
    statusEl.className = "status error";
    btnStart.disabled = false;
  }
});
