// PI_GRILL_CORE=/path/to/pi-monorepo/dist/core node --test tests/pi-grill-me.test.mjs
// Optional PI_GRILL_AGENT_DIR verifies deployed files with the same checks.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import test from 'node:test';

if (!process.env.PI_GRILL_CORE) throw new Error('Set PI_GRILL_CORE to the installed Pi dist/core directory');
const core = resolve(process.env.PI_GRILL_CORE);
const { loadPromptTemplates, expandPromptTemplate } = await import(pathToFileURL(join(core, 'prompt-templates.js')));
const { loadSkillsFromDir } = await import(pathToFileURL(join(core, 'skills.js')));
const agentDir = process.env.PI_GRILL_AGENT_DIR ?? fileURLToPath(new URL('../home/config/pi/', import.meta.url));
const { templates, diagnostics } = loadPromptTemplates({ cwd: agentDir, agentDir, promptPaths: [], includeDefaults: true });
const skillResult = loadSkillsFromDir({ dir: join(agentDir, 'skills/grill-me'), source: 'user' });

test('grill-me is a valid explicitly invoked skill', () => {
  assert.deepEqual(skillResult.diagnostics, []);
  assert.equal(skillResult.skills.length, 1);
  assert.equal(skillResult.skills[0].name, 'grill-me');
  assert.equal(skillResult.skills[0].disableModelInvocation, true);
  const content = readFileSync(skillResult.skills[0].filePath, 'utf8');
  assert.match(content, /stateless conversation/);
  assert.match(content, /normal approval requirements/);
  assert.doesNotMatch(content, /Call the Skill tool/);
  assert.match(readFileSync(join(agentDir, 'skills/grill-me/LICENSE'), 'utf8'), /Copyright \(c\) 2026 Matt Pocock/);
});

test('/grill-me is discovered and expands with or without a topic', () => {
  assert.deepEqual(diagnostics, []);
  assert.equal(templates.filter(t => t.name === 'grill-me').length, 1);
  for (const [input, topic] of [
    ['/grill-me', ''],
    ['/grill-me a new product', 'a new product'],
    ['/grill-me "an idea with spaces"', 'an idea with spaces'],
    ['/grill-me literal $1 and $ARGUMENTS', 'literal $1 and $ARGUMENTS'],
  ]) {
    const expanded = expandPromptTemplate(input, templates);
    assert.match(expanded, /Read the grill-me skill at ~\/\.config\/pi\/agent\/skills\/grill-me\/SKILL\.md/);
    assert.match(expanded, /Stay stateless and do not implement changes/);
    assert.equal(expanded.trimEnd().split('\n').at(-1), topic || 'User\'s topic (if empty, ask what they want to explore):');
  }
});
