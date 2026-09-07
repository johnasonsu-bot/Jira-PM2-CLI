const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const pm2Service = require('./pm2-service');

const PAGE = fs.readFileSync(path.join(__dirname, 'index.html'));

function sendJson(response, status, data) {
  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
  response.end(JSON.stringify(data));
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    let body = '';
    request.on('data', (chunk) => {
      body += chunk;
      if (body.length > 8192) reject(new Error('Request body too large'));
    });
    request.on('end', () => resolve(body));
    request.on('error', reject);
  });
}

function createDashboardServer(service = pm2Service) {
  return http.createServer(async (request, response) => {
    try {
      if (request.method === 'GET' && request.url === '/') {
        response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
        return response.end(PAGE);
      }
      if (request.method === 'GET' && request.url === '/api/processes') {
        return sendJson(response, 200, { processes: await service.listProcesses() });
      }
      if (request.method === 'POST' && request.url === '/api/command') {
        const body = JSON.parse(await readBody(request) || '{}');
        return sendJson(response, 200, await service.executeCommand(body.command));
      }
      return sendJson(response, 404, { error: 'Not found' });
    } catch (error) {
      return sendJson(response, 400, { error: error.message });
    }
  });
}

if (require.main === module) {
  const port = Number(process.env.PORT || 8765);
  createDashboardServer().listen(port, '127.0.0.1', () => {
    console.log(`PM2 Operations Console listening on http://127.0.0.1:${port}`);
  });
}

module.exports = { createDashboardServer };
