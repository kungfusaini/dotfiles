"""Local synthetic download regression, shared by headless and private headed tests."""
import json
import os
from pathlib import Path

PAYLOAD = b"dummy,only\n1,2\n"
CONTROLS = b'''<a id="download-http" href="/download.csv">Download HTTP</a>
<button id="download-blob" onclick="downloadBlob()">Download blob</button>
<button id="download-sandbox" onclick="downloadSandbox()">Download sandbox</button>
<script>
function downloadBlob() {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['dummy,only\\n1,2\\n'], {type:'text/csv'}));
  a.download = 'dummy.csv'; a.click();
}
function downloadSandbox() {
  const f = document.createElement('iframe');
  f.setAttribute('sandbox', 'allow-scripts allow-downloads');
  f.srcdoc = '<script>' + downloadBlob.toString() + ';downloadBlob();</scr' + 'ipt>';
  document.body.append(f);
}
</script>'''


def serve(handler):
    if handler.path != '/download.csv':
        return False
    handler.send_response(200)
    handler.send_header('Content-Type', 'text/csv')
    handler.send_header('Content-Disposition', 'attachment; filename="dummy.csv"')
    handler.send_header('Content-Length', str(len(PAYLOAD)))
    handler.end_headers()
    handler.wfile.write(PAYLOAD)
    return True


def prepare_native_home(root):
    """Model the user's normal XDG Downloads directory on the private desktop.

    An empty test HOME otherwise resolves Downloads to HOME itself on this host;
    Chromium rightly treats that destination as unsafe and asks for a file chooser.
    This is fixture setup, not a production download-policy override.
    """
    home = Path(os.environ['HOME'])
    assert home.resolve().is_relative_to(Path(root).parent.resolve())
    (home/'Downloads').mkdir(exist_ok=True)
    config = Path(os.environ['XDG_CONFIG_HOME'])
    config.mkdir(parents=True, exist_ok=True)
    (config/'user-dirs.dirs').write_text('XDG_DOWNLOAD_DIR="$HOME/Downloads"\n')


def settle_first_install(call):
    """Fresh unpacked Bitwarden opens onboarding asynchronously in test profiles.

    Model the time a human spends on initial setup, then return to our fixture.
    This reads only synthetic-context tab URLs, not extension/vault storage.
    """
    call('run-code', '''async page => {
const deadline = Date.now() + 15000;
while (!page.context().pages().some(p => p.url().startsWith('https://bitwarden.com/browser-start'))) {
  if (Date.now() > deadline) throw Error('Fresh extension onboarding did not appear');
  await page.waitForTimeout(50);
}
await page.bringToFront(); return {fixtureReady:true};}''')


def check(call, destination):
    """Use the actual configured policy, not a CDP download-permission override."""
    destination = Path(destination)
    destination.mkdir(exist_ok=True)
    for kind in ('http', 'blob', 'sandbox'):
        output = destination / (kind + '.csv')
        call('run-code', '''async page => {
const pending = page.waitForEvent('download', {timeout:10000});
await page.locator(%s).click();
const download = await pending;
await download.saveAs(%s);
if (await download.failure()) throw Error('Synthetic download failed');
return {saved:true};}''' % (json.dumps('#download-' + kind), json.dumps(str(output))))
        assert output.read_bytes() == PAYLOAD, 'Download payload mismatch: ' + kind
