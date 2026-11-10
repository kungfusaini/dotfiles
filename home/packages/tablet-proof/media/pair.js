document.getElementById("pair").addEventListener("click", async () => {
  try {
    const result = await chrome.runtime.sendMessage({op: "pair-window"});
    document.getElementById("status").textContent = result?.ok
      ? "Registration opened. Once it finishes, close this pairing page."
      : "Pairing unavailable. Open tablet mode in this window and try again.";
  } catch (_) {
    document.getElementById("status").textContent = "The native companion is unavailable.";
  }
});
