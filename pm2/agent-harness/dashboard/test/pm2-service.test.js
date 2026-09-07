const test = require('node:test');
const assert = require('node:assert/strict');

const {
  sanitizeProcess,
  parseDashboardCommand,
} = require('../pm2-service');

test('sanitizeProcess exposes metrics without leaking environment variables', () => {
  const process = sanitizeProcess({
    pm_id: 3,
    name: 'api',
    pid: 321,
    monit: { cpu: 4.2, memory: 10485760 },
    pm2_env: {
      status: 'online',
      restart_time: 2,
      pm_uptime: 1700000000000,
      SECRET_TOKEN: 'must-not-leak',
    },
  });

  assert.deepEqual(process, {
    id: 3,
    name: 'api',
    pid: 321,
    status: 'online',
    cpu: 4.2,
    memory: 10485760,
    restarts: 2,
    uptime: 1700000000000,
  });
  assert.equal(JSON.stringify(process).includes('SECRET_TOKEN'), false);
});

test('parseDashboardCommand accepts read and lifecycle commands', () => {
  assert.deepEqual(parseDashboardCommand('process list'), { action: 'list' });
  assert.deepEqual(parseDashboardCommand('logs view api --lines 20'), {
    action: 'logs', name: 'api', lines: 20,
  });
  assert.deepEqual(parseDashboardCommand('lifecycle restart api'), {
    action: 'restart', name: 'api',
  });
});

test('parseDashboardCommand rejects shell syntax and unsupported commands', () => {
  assert.throws(() => parseDashboardCommand('process list; cat ~/.ssh/id_rsa'), /Unsupported/);
  assert.throws(() => parseDashboardCommand('rm -rf /'), /Unsupported/);
});
