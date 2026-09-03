import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const moduleUrl = pathToFileURL(join(process.cwd(), 'agent/extensions/markdown-local-paths.ts')).href;
const { linkifyLocalPathsInMarkdown, localPathToFileUrl } = await import(moduleUrl);

const cwd = mkdtempSync(join(tmpdir(), 'pi-md-links-'));
mkdirSync(join(cwd, 'templates/invoice'), { recursive: true });
writeFileSync(join(cwd, 'templates/invoice/invoice-template.pdf'), 'pdf');
writeFileSync(join(cwd, 'templates/invoice/logo.png'), 'png');

const pdfUrl = pathToFileURL(join(cwd, 'templates/invoice/invoice-template.pdf')).href;
const logoUrl = pathToFileURL(join(cwd, 'templates/invoice/logo.png')).href;

assert.equal(localPathToFileUrl('templates/invoice/invoice-template.pdf', cwd), pdfUrl);
assert.equal(localPathToFileUrl('templates/invoice/missing.pdf', cwd), undefined);

assert.equal(
  linkifyLocalPathsInMarkdown('Updated templates/invoice/invoice-template.pdf', cwd),
  `Updated [templates/invoice/invoice-template.pdf](${pdfUrl})`,
);

assert.equal(
  linkifyLocalPathsInMarkdown('- templates/invoice/logo.png', cwd),
  `- [templates/invoice/logo.png](${logoUrl})`,
);

assert.equal(
  linkifyLocalPathsInMarkdown('Open templates/invoice/invoice-template.pdf.', cwd),
  `Open [templates/invoice/invoice-template.pdf](${pdfUrl}).`,
);

assert.equal(
  linkifyLocalPathsInMarkdown('Missing templates/invoice/missing.pdf', cwd),
  'Missing templates/invoice/missing.pdf',
);

assert.equal(
  linkifyLocalPathsInMarkdown('Already [invoice](templates/invoice/invoice-template.pdf)', cwd),
  'Already [invoice](templates/invoice/invoice-template.pdf)',
);

assert.equal(
  linkifyLocalPathsInMarkdown('Code `templates/invoice/invoice-template.pdf` stays plain', cwd),
  'Code `templates/invoice/invoice-template.pdf` stays plain',
);

assert.equal(
  linkifyLocalPathsInMarkdown('```\ntemplates/invoice/invoice-template.pdf\n```', cwd),
  '```\ntemplates/invoice/invoice-template.pdf\n```',
);

console.log('markdown-rendering local path linkification tests passed');
