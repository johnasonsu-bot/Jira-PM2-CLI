const { execFile } = require('node:child_process');
const { promisify } = require('node:util');

const execFileAsync = promisify(execFile);
const PM2_BIN = process.env.PM2_BIN || '/Users/sushi/.npm-global/bin/pm2';

function sanitizeProcess(item) {
  const env = item.pm2_env || {};
  const metrics = item.monit || {};
  return {
    id: item.pm_id,
    name: item.name,
    pid: item.pid,
    status: env.status || 'unknown',
    cpu: metrics.cpu || 0,
    memory: metrics.memory || 0,
    restarts: env.restart_time || 0,
    uptime: env.pm_uptime || null,
  };
}

function parseDashboardCommand(input) {
  const command = String(input || '').trim();
  if (command === 'process list' || command === 'process metrics') return { action: 'list' };

  let match = command.match(/^logs view ([A-Za-z0-9_.:-]+)(?: --lines (\d{1,3}))?$/);
  if (match) return { action: 'logs', name: match[1], lines: Math.min(Number(match[2] || 50), 200) };

  match = command.match(/^lifecycle (restart|stop) ([A-Za-z0-9_.:-]+)$/);
  if (match) return { action: match[1], name: match[2] };

  throw new Error('Unsupported command. Use process list, logs view, lifecycle restart, or lifecycle stop.');
}

async function runPm2(args) {
  const { stdout, stderr } = await execFileAsync(PM2_BIN, args, {
    timeout: 10000,
    maxBuffer: 1024 * 1024,
  });
  return { stdout, stderr };
}

async function listProcesses() {
  const { stdout } = await runPm2(['jlist']);
  return JSON.parse(stdout).map(sanitizeProcess);
}

async function executeCommand(command) {
  const parsed = parseDashboardCommand(command);
  if (parsed.action === 'list') return { processes: await listProcesses() };
  if (parsed.action === 'logs') {
    const result = await runPm2(['logs', parsed.name, '--lines', String(parsed.lines), '--nostream']);
    return { output: `${result.stdout}${result.stderr}`.trim() };
  }
  const result = await runPm2([parsed.action, parsed.name]);
  return { output: `${result.stdout}${result.stderr}`.trim(), processes: await listProcesses() };
}

module.exports = { sanitizeProcess, parseDashboardCommand, listProcesses, executeCommand };
