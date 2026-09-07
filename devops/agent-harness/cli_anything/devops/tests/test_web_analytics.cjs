const {test}=require('node:test');
const assert=require('node:assert/strict');
const analytics=require('../web/analytics.js');

test('scope switches select exactly the requested report; missing sprint does not select another project',()=>{
  const data={analytics:{project:{metrics:{total:13}},active:{metrics:{total:9}},'sprint:3':{metrics:{total:0}}}};
  assert.equal(analytics.selectReport(data,'project').metrics.total,13);
  assert.equal(analytics.selectReport(data,'active').metrics.total,9);
  assert.equal(analytics.selectReport(data,'sprint:3').metrics.total,0);
  assert.equal(analytics.selectReport(data,'sprint:999').metrics.total,9);
  for(const scope of ['constructor','toString','__proto__']) {
    assert.equal(analytics.selectReport(data,scope).metrics.total,9);
  }
});

test('risk drilldown filters real reasons and preserves escaped issue identity',()=>{
  const report={risks:[{key:'APP-1',reasons:['high','undated']},{key:'APP-2',reasons:['overdue']}]};
  assert.deepEqual(analytics.selectRisks(report,'high').map(i=>i.key),['APP-1']);
  assert.deepEqual(analytics.selectRisks(report,'overdue').map(i=>i.key),['APP-2']);
  assert.equal(analytics.selectRisks(report,'all').length,2);
  assert.equal(analytics.percent(null),'—');
  assert.equal(analytics.percent(0),'0%');
});

test('metric rendering preserves zero and escapes untrusted content',()=>{
  const html=analytics.metric('零数据',0,'<img src=x onerror=alert(1)>');
  assert.match(html,/>0</);
  assert.ok(!html.includes('<img'));
  assert.match(html,/&lt;img/);
});
