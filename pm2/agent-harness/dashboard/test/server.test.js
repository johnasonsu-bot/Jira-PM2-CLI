const test = require('node:test');
const assert = require('node:assert/strict');

const { createDashboardServer } = require('../server');

function request(server, path, options = {}) {
  const address = server.address();
  return fetch(`http://127.0.0.1:${address.port}${path}`, options);
}

test('dashboard serves the PM2 control page', async (t) => {
  const server = createDashboardServer({ listProcesses: async () => [], executeCommand: async () => ({}) });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => server.close());

  const response = await request(server, '/');
  const html = await response.text();
  assert.equal(response.status, 200);
  assert.match(html, /PM2 Operations Console/);
  assert.match(html, /Codex/);
});

test('process API returns sanitized service data', async (t) => {
  const expected = [{ id: 1, name: 'api', status: 'online' }];
  const server = createDashboardServer({ listProcesses: async () => expected, executeCommand: async () => ({}) });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => server.close());

  const response = await request(server, '/api/processes');
  assert.deepEqual(await response.json(), { processes: expected });
});
