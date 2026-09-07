// Run with node --test; exercise the actual browser refresh function in isolation.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
test('project switch queues fresh request and discards the old project response', async () => {
  const source = fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
  const refresh = source.slice(source.indexOf('async function refresh()'),source.indexOf('function opts('));
  const requests = [];
  const context = vm.createContext({
    fetch: url => new Promise(resolve => requests.push({url,resolve})),
    $: () => ({}), render: () => {}, toast: () => {},
  });
  vm.runInContext("let project='APP',state=null,loading=false,refreshPending=false;" + refresh, context);
  const first = vm.runInContext('refresh()',context);
  await vm.runInContext("project='OPS';refresh()",context);
  requests[0].resolve({ok:true,json:async()=>({project:'APP'})});
  await new Promise(setImmediate);
  assert.equal(vm.runInContext('project',context),'OPS');
  assert.equal(requests.length,2);
  assert.equal(requests[1].url,'/api/state?project=OPS');
  requests[1].resolve({ok:true,json:async()=>({project:'OPS'})});
  await first;
  assert.equal(vm.runInContext('state.project',context),'OPS');
});
