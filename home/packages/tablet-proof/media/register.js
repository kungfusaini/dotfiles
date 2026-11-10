// This script can see only our dedicated local registration origin.
chrome.runtime.sendMessage({op: "register"}).then(result => {
  if (!result?.ok) document.body.textContent = "Tablet media pairing failed. Close this registration tab and try the companion button in the tablet window.";
}).catch(() => {
  document.body.textContent = "Tablet media companion unavailable. You can close this registration tab.";
});
