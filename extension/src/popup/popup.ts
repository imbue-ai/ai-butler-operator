import { createSession } from "../shared/api";

const btnStart = document.getElementById("btn-start") as HTMLButtonElement;
const statusEl = document.getElementById("status")!;

btnStart.addEventListener("click", async () => {
  btnStart.disabled = true;
  statusEl.textContent = "Creating session...";
  statusEl.className = "status";

  try {
    // Get the current tab's URL
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const currentUrl = tab?.url || undefined;

    const session = await createSession(currentUrl);

    // Open the viewer in a new tab
    const viewerUrl = chrome.runtime.getURL(
      `viewer.html?code=${session.code}&phone=${encodeURIComponent(session.phone_number)}`
    );
    await chrome.tabs.create({ url: viewerUrl });

    // Close the popup
    window.close();
  } catch (err) {
    console.error("Failed to create session", err);
    statusEl.textContent = "Could not connect to server. Is it running?";
    statusEl.className = "status error";
    btnStart.disabled = false;
  }
});
