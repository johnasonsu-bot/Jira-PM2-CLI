'use strict';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const statusNames = {backlog:'待办池',todo:'待开始',in_progress:'进行中',review:'待验收',done:'已完成'};
const typeNames = {story:'用户故事',task:'任务',bug:'缺陷',epic:'史诗'};
const typeIcons = {story:'◆',task:'✓',bug:'•',epic:'ϟ'};
const priorityNames = {critical:'最高',high:'高',medium:'中',low:'低'};
const lifecycleNames = {planned:'计划中',active:'进行中',completed:'已完成',staging:'验证中',released:'已发布'};
const viewNames = {board:'工作看板',analytics:'管理分析',backlog:'工作项',sprints:'迭代计划',releases:'版本发布',activity:'活动记录',guide:'Codex & CLI'};
const subtitles = {board:'每一步进展，都清晰可见。',analytics:'从交付进度，到风险与资源，一页掌握。',backlog:'把想法拆成可以交付的工作。',sprints:'以目标为起点，以交付为终点。',releases:'聚合变更、验证完成度、追踪版本。',activity:'每一次协作，都有迹可循。',guide:'一句话，让你的研发工作流动起来。'};
let state = null, view = 'board', project = new URLSearchParams(location.search).get('project') || '', selectedIssue = null, editKind = '', editItem = null, loading = false;
let requirementPage=1,boardVisible={};
const initialQuery=new URLSearchParams(location.search);
if(Object.hasOwn(viewNames,initialQuery.get('view')))view=initialQuery.get('view');
let analysisScope=initialQuery.get('scope')||'active',analysisRisk='all';
let toastTimer, refreshPending=false;
function toast(message, error=false) { const node=$('#toast');node.textContent=message;node.className='visible'+(error?' error':'');clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.className='',4000); }
async function api(action,data={}) {
  const response=await fetch('/api/call',{method:'POST',headers:{'Content-Type':'application/json','X-Forge-Client':'1','X-Forge-Actor':'Web'},body:JSON.stringify({action,data})});
  const payload=await response.json();if(!response.ok)throw new Error(payload.error||'请求失败');return payload.data;
}
async function refresh() {
  if(loading){refreshPending=true;return;}
  loading=true;
  const requestedProject=project;
  try {
    const response=await fetch('/api/state'+(requestedProject?'?project='+encodeURIComponent(requestedProject):''));
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    if(project!==requestedProject)return;
    const changed=JSON.stringify(state)!==JSON.stringify(data);
    state=data;project=data.project;
    $('#connection').textContent='本地已连接';$('#last-update').textContent='最近同步 '+new Date().toLocaleTimeString('zh-CN');
    if(changed)render();
  } catch(error) { if(project===requestedProject){$('#connection').textContent='连接已断开';toast(error.message,true);} }
  finally {loading=false;if(refreshPending||project!==requestedProject){refreshPending=false;await refresh();}}
}
function opts(values,current,empty) { return (empty===undefined?'':`<option value="">${empty}</option>`)+Object.entries(values).map(([key,name])=>`<option value="${esc(key)}" ${String(current)===String(key)?'selected':''}>${esc(name)}</option>`).join(''); }
function dateText(value) { return value ? new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—'; }
function syncLocation(){const q=new URLSearchParams();if(project)q.set('project',project);if(view!=='board')q.set('view',view);if(view==='analytics')q.set('scope',analysisScope);history.replaceState(null,'','?'+q.toString());}
function percent(items) { return items.length?Math.round(items.filter(i=>i.status==='done').length/items.length*100):0; }
function typeBadge(item) {return `<span class="type-icon ${esc(item.type)}">${typeIcons[item.type]||'✓'}</span>`;}
function filtered() {
  const filters={query:$('#search').value,issueType:$('#filter-type').value,priority:$('#filter-priority').value,sprint:$('#filter-sprint').value,system:$('#filter-req-system').value,chapter:$('#filter-req-chapter').value,reqType:$('#filter-req-type').value,missing:$('#filter-req-missing').value};
  return state.issues.filter(i=>ForgeRequirements.matches(i,filters));
}
function updateRequirementFilters() {
  const definitions=[['#filter-req-system','system_name','所有需求系统'],['#filter-req-chapter','chapter','所有需求章节'],['#filter-req-type','req_type','所有需求类型']];
  for(const [selector,field,label] of definitions){const node=$(selector),current=node.value,values=ForgeRequirements.filterValues(state.issues,field);node.innerHTML=`<option value="">${label}</option>`+values.map(value=>`<option value="${esc(value)}">${esc(value)}</option>`).join('');if(values.includes(current))node.value=current;}
  const missingNode=$('#filter-req-missing'),currentMissing=missingNode.value,missingValues=[...new Set(state.issues.flatMap(i=>Array.isArray(i.requirement?.missing)?i.requirement.missing:[]))].sort((a,b)=>a.localeCompare(b,'zh-CN'));
  missingNode.innerHTML='<option value="">所有字段完整度</option>'+missingValues.map(value=>`<option value="${esc(value)}">缺失：${esc(value)}</option>`).join('');if(missingValues.includes(currentMissing))missingNode.value=currentMissing;
  document.querySelectorAll('.requirement-filter').forEach(node=>node.hidden=!state.issues.some(i=>i.requirement));
}
function render() {
  $('#project-select').innerHTML=state.projects.length?state.projects.map(p=>`<option value="${esc(p.key)}" ${p.key===project?'selected':''}>${esc(p.name)}</option>`).join(''):'<option>创建你的项目</option>';
  $('#project-name').textContent=state.projects.find(p=>p.key===project)?.name||'Forge DevOps';
  $('#heading').textContent=viewNames[view];$('#view-crumb').textContent=viewNames[view];$('#subtitle').textContent=subtitles[view];
  document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  $('#nav-count').textContent=state.issues.length;
  $('#new-issue').hidden=!['board','backlog'].includes(view);
  const s=state.summary;
  $('#metrics').hidden=!['board','backlog'].includes(view);
  $('#management-pulse').hidden=!['board','backlog'].includes(view);
  $('#management-pulse').innerHTML=ForgeAnalytics.pulse(state.analytics?.project);
  $('#metrics').innerHTML=[['全部工作项',s.total,'scope','项目范围'],['进行中',s.in_progress,'↗','正在推进'],['待解决缺陷',s.open_bugs,'◈','质量关注'],['已完成',s.done,'✓',`${s.total?Math.round(s.done/s.total*100):0}% 完成率`]].map(([label,n,icon,note],i)=>`<div class="metric ${i===3?'highlight':''}"><div class="metric-top"><span>${label}</span><span>${icon==='scope'?'▧':icon}</span></div><strong>${n}</strong><small>${note}</small></div>`).join('');
  const active=state.sprints.find(s=>s.status==='active');
  $('#sprint-banner').hidden=view!=='board';
  if(active) {
    const items=state.issues.filter(i=>i.sprint_id===active.id),progress=percent(items);
    $('#sprint-banner').innerHTML=`<div><div class="sprint-title"><h3>◷ &nbsp; ${esc(active.name)}</h3><span class="pill">进行中</span></div><div class="sprint-description">${esc(active.goal||'专注当前迭代的交付目标')} · ${esc(active.start_date||'未设日期')} → ${esc(active.end_date||'未设日期')}</div></div><div class="sprint-right"><div class="sprint-progress"><div><span>${items.filter(i=>i.status==='done').length} / ${items.length} 项完成</span><span>${progress}%</span></div><div class="progress"><i style="width:${progress}%"></i></div></div><button class="secondary" data-action="show-sprints">管理迭代 ↗</button></div>`;
  } else $('#sprint-banner').innerHTML=`<div><div class="sprint-title"><h3>◷ &nbsp; 为下一个目标规划迭代</h3></div><span class="sprint-description">从待办池挑选工作项，安排一个专注的交付周期。</span></div><button class="secondary" data-action="new-sprint">＋ 创建迭代</button>`;
  $('#filters').hidden=!['board','backlog'].includes(view);
  const filter=$('#filter-sprint').value;
  $('#filter-sprint').innerHTML='<option value="">所有迭代</option><option value="none">未排期</option>'+state.sprints.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');
  if([...$('#filter-sprint').options].some(o=>o.value===filter))$('#filter-sprint').value=filter;
  updateRequirementFilters();
  renderContent();
}
function card(item) {
  return `<article class="card" draggable="true" data-key="${esc(item.key)}" tabindex="0" role="button" aria-label="打开 ${esc(item.key)} ${esc(item.title)}"><div class="card-top"><span>${typeBadge(item)}${esc(item.key)}</span><span class="priority ${esc(item.priority)}">${item.priority==='critical'?'⇈':'↑'} ${item.requirement?'工作项调度：':''}${priorityNames[item.priority]}</span></div><div class="card-title">${esc(item.title)}</div>${ForgeRequirements.cardMeta(item)}<div class="tags">${item.labels.map(l=>`<span class="tag">${esc(l)}</span>`).join('')}</div><div class="card-bottom"><span class="card-person"><span class="avatar">${esc(item.assignee?item.assignee.slice(0,1):'–')}</span>${esc(item.assignee||'未分配')}</span><span class="points">${item.points} SP</span></div></article>`;
}
function empty(title,body,action,label) {return `<div class="empty-state"><h3>${esc(title)}</h3><p>${esc(body)}</p>${action?`<button class="primary" data-action="${action}">${esc(label)}</button>`:''}</div>`;}
function renderContent() {
  if(!state.projects.length){$('#content').innerHTML=empty('从一个项目开始','创建项目后，即可管理工作项、迭代与版本。','new-project','＋ 创建项目');return;}
  const items=filtered();$('#filtered-count').textContent=`${items.length} 个工作项`;
  if(view==='board')$('#content').innerHTML=`<div class="board">${Object.entries(statusNames).map(([status,name])=>{const group=items.filter(i=>i.status===status),visible=boardVisible[status]||30,windowed=ForgeRequirements.boardSlice(group,visible);return `<section class="column" data-status="${status}" aria-label="${name}"><div class="column-head"><span class="column-dot"></span>${name}<span class="count">${group.length}</span><button data-action="new-issue" data-status="${status}" aria-label="在${name}创建工作项">＋</button></div>${windowed.items.map(card).join('')}${!group.length?'<div class="column-empty">将工作项拖到这里</div>':''}${windowed.hasMore?`<button class="board-show-more" data-action="show-more-requirements" data-status="${status}">再显示 ${Math.min(30,windowed.remaining)} 项 · 尚有 ${windowed.remaining} 项</button>`:''}</section>`;}).join('')}</div>`;
  if(view==='backlog'){
    const page=ForgeRequirements.paginate(items,requirementPage,50),hasRequirements=items.some(i=>i.requirement),requirementHead=hasRequirements?'<th>原需求编号</th><th>需求系统</th><th>需求评估</th>':'';
    requirementPage=page.page;
    $('#content').innerHTML=items.length?`<div class="list-table"><table><thead><tr><th>工作项</th><th>标题</th>${requirementHead}<th>工作项状态</th><th>工作项调度优先级</th><th>负责人</th><th>迭代</th><th>故事点</th></tr></thead><tbody>${page.items.map(i=>`<tr data-key="${esc(i.key)}" tabindex="0" role="button" aria-label="打开 ${esc(i.key)}"><td>${typeBadge(i)}${esc(i.key)}</td><td class="title-cell">${esc(i.title)}</td>${hasRequirements?(ForgeRequirements.listCells(i)||'<td>—</td><td>—</td><td>—</td>'):''}<td><span class="pill">${statusNames[i.status]}</span></td><td class="priority ${esc(i.priority)}">${priorityNames[i.priority]}</td><td>${esc(i.assignee||'未分配')}</td><td>${esc(state.sprints.find(s=>s.id===i.sprint_id)?.name||'未排期')}</td><td>${i.points}</td></tr>`).join('')}</tbody></table></div>${ForgeRequirements.pager(page)}`:empty('没有匹配的工作项','试试调整筛选条件，或创建一个新任务。','new-issue','创建工作项');
  }
  if(view==='sprints') renderSprints();
  if(view==='analytics') {
    if(!Object.hasOwn(state.analytics||{},analysisScope))analysisScope='active';
    $('#content').innerHTML=ForgeAnalytics.render(state,analysisScope,analysisRisk);
  }
  if(view==='releases') renderReleases();
  if(view==='activity') $('#content').innerHTML=state.activity.length?`<div class="list-table">${state.activity.map(activityRow).join('')}</div>`:empty('还没有活动','创建工作项后，变更会自动记录。');
  if(view==='guide') renderGuide();
}
function renderSprints() {
  $('#content').innerHTML=`<div class="section-toolbar"><p>完成迭代时，未完成工作项会自动回到待办池。</p><button class="primary" data-action="new-sprint">＋ 创建迭代</button></div><div class="stack">${state.sprints.map(s=>{const items=state.issues.filter(i=>i.sprint_id===s.id),p=percent(items);return `<div class="wide-card"><div class="topline"><h3>${esc(s.name)}</h3><span class="pill">${lifecycleNames[s.status]}</span></div><p>${esc(s.goal||'尚未填写迭代目标')}</p><div class="progress"><i style="width:${p}%"></i></div><div class="bottomline"><span>${esc(s.start_date||'未设开始日期')} → ${esc(s.end_date||'未设结束日期')} &nbsp; · &nbsp; ${items.length} 项 · ${items.reduce((n,i)=>n+i.points,0)} SP · ${p}% 已完成</span>${s.status==='planned'?`<button class="secondary" data-action="start-sprint" data-id="${s.id}">开始迭代 →</button>`:s.status==='active'?`<button class="secondary" data-action="complete-sprint" data-id="${s.id}">完成迭代</button>`:''}</div></div>`;}).join('')||empty('第一个迭代，从这里开始','给团队一个清晰的目标与时间窗口。')}</div>`;
}
function renderReleases() {
  $('#content').innerHTML=`<div class="section-toolbar"><p>发布记录 · 关联工作项全部完成后可标记发布，外部部署需另外接入。</p><button class="primary" data-action="new-release">＋ 创建版本</button></div><div class="stack">${state.releases.map(r=>{const linked=state.issues.filter(i=>r.issue_keys.includes(i.key)),p=percent(linked);return `<div class="wide-card"><div class="topline"><h3>◇ &nbsp; ${esc(r.name)}</h3><span class="pill">${lifecycleNames[r.status]}</span></div><p>${esc(r.notes||'尚未填写发布说明')}</p><div class="tags">${r.issue_keys.map(k=>`<button class="tag" data-action="open-issue" data-issue="${esc(k)}">${esc(k)}</button>`).join('')}</div><div class="progress"><i style="width:${p}%"></i></div><div class="bottomline"><span>${linked.length} 项关联工作 · ${p}% 已完成 ${r.released_at?' · 发布于 '+dateText(r.released_at):''}</span>${r.status!=='released'?`<button class="secondary" data-action="edit-release" data-id="${r.id}">编辑版本</button><button class="secondary" data-action="promote-release" data-id="${r.id}" data-status="${r.status==='planned'?'staging':'released'}">${r.status==='planned'?'进入验证':'标记已发布'} →</button>`:''}</div></div>`;}).join('')||empty('让每一次发布有据可查','关联本次交付的工作项，记录版本与发布说明。')}</div>`;
}
const actionNames={'project.create':'创建项目','issue.create':'创建工作项','issue.update':'更新工作项','issue.comment':'发表评论','sprint.create':'创建迭代','sprint.start':'开始迭代','sprint.complete':'完成迭代','release.create':'创建版本','release.update':'更新版本'};
function changesText(a) {
  const display=value=>statusNames[value]??lifecycleNames[value]??(Array.isArray(value)?value.join(', '):(value===null||value===''?'未设置':String(value)));
  if(a.action==='issue.update'||(a.action==='release.update'&&!('after' in a.changes)))return Object.entries(a.changes).map(([k,v])=>`${({status:'状态',assignee:'负责人',priority:'优先级',title:'标题',sprint_id:'迭代',points:'故事点',name:'名称',notes:'说明',issue_keys:'关联工作项'}[k]||k)}：${display(v.before)} → ${display(v.after)}`).join(' · ');
  return a.changes.title||a.changes.name||a.changes.body||(a.changes.after?lifecycleNames[a.changes.after]:'')||'';
}
function activityRow(a) {return `<div class="activity-row"><span class="activity-dot">↗</span><div><p><b>${esc(a.actor)}</b> ${actionNames[a.action]||esc(a.action)} <b>${esc(a.target)}</b></p><div class="changes">${esc(changesText(a))}</div></div><time>${dateText(a.created_at)}</time></div>`;}
function renderGuide() {
  const k=state.issues[0]?.key||project+'-1';
  const examples=[['创建工作','在 '+project+' 项目里创建一个高优先级缺陷：修复登录超时，指派给 Sushi。',`cli-anything-devops --json issue create --project ${project} --title "修复登录超时" --type bug --priority high --assignee Sushi`],['推进状态',`把 ${k} 改成进行中，并留言“已开始处理”。`,`cli-anything-devops --json issue move ${k} in_progress\ncli-anything-devops --json issue comment ${k} --body "已开始处理"`],['查询进度','帮我汇总 '+project+' 的完成率、未解决缺陷和工作项分布。',`cli-anything-devops --json report --project ${project}`],['查看变更',`查一下 ${k} 的操作记录和评论。`,`cli-anything-devops --json issue get ${k}`]];
  $('#content').innerHTML=`<div class="guide-hero"><div><div class="eyebrow">YOUR WORDS. REAL ACTIONS.</div><h2>用对话，驱动交付。</h2><p>在 Codex 当前对话中描述目标。Codex 调用 CLI-Anything，<br>执行结果写入同一个工作台，并在活动记录中留下来源。</p><div class="workflow">你 → Codex 对话 → CLI-Anything → Forge API → 看板同步</div></div><span class="assistant-mark" style="font-size:64px">✳</span></div><div class="guide-grid">${examples.map(([title,prompt,command])=>`<section class="guide-card"><small>CODEX WORKFLOW</small><h3>${title}</h3><p>${esc(prompt)}</p><pre>${esc(command)}</pre><button class="secondary" data-action="copy" data-text="${esc(prompt)}">复制对话指令</button></section>`).join('')}<section class="guide-card"><small>CLI-ANYTHING</small><h3>命令行入口</h3><pre>cli-anything-devops --help\ncli-anything-devops --json project list\ncli-anything-devops</pre><p>最后一条命令打开交互式 REPL。支持项目、工作项、迭代、版本、报告与审计查询。</p></section><section class="guide-card"><small>LOCAL FIRST</small><h3>对话发生在 Codex</h3><p>此页面是研发工作台，没有内嵌聊天模型。请把对话指令发送到 Codex；只读请求只查询，修改请求执行后会回读确认。</p><p>所有者标签是操作来源记录，不是多用户登录认证。</p></section></div>`;
}
function field(name,label,value='',type='text',full=false,required=false) {return `<label class="${full?'full':''}">${label}<input name="${name}" type="${type}" value="${esc(value)}" ${required?'required':''} ${name==='points'?'min="0" max="100"':''}></label>`;}
function selectField(name,label,values,value='',empty){return `<label>${label}<select name="${name}">${opts(values,value,empty)}</select></label>`;}
function openEditor(kind,item=null,initialStatus='backlog') {
  if(!project&&kind!=='project')return openEditor('project');
  editKind=kind;editItem=item;$('#form-error').textContent='';$('#form-title').textContent=(item?'编辑':'创建')+({issue:'工作项',project:'项目',sprint:'迭代',release:'版本'}[kind]);
  if(kind==='issue') {
    const i=item||{type:'task',status:initialStatus,priority:'medium',points:0},sprints=Object.fromEntries(state.sprints.filter(s=>s.status!=='completed'||s.id===i.sprint_id).map(s=>[s.id,s.name]));
    $('#form-fields').innerHTML=field('title','标题 *',i.title,'text',true,true)+`<label class="full">描述<textarea name="description">${esc(i.description||'')}</textarea></label>`+selectField('type','类型',typeNames,i.type)+selectField('status','状态',statusNames,i.status)+selectField('priority','优先级',priorityNames,i.priority)+field('assignee','负责人',i.assignee)+field('points','故事点',i.points,'number')+selectField('sprint_id','迭代',sprints,i.sprint_id,'未排期')+field('due_date','截止日期',i.due_date,'date')+field('labels','标签（逗号分隔）',(i.labels||[]).join(', '));
  }
  if(kind==='project')$('#form-fields').innerHTML=field('name','项目名称 *','','text',true,true)+field('key','项目标识（如 APP、OPS）*','','text',true,true)+`<label class="full">项目描述<textarea name="description"></textarea></label>`;
  if(kind==='sprint')$('#form-fields').innerHTML=field('name','迭代名称 *','','text',true,true)+`<label class="full">迭代目标<textarea name="goal"></textarea></label>`+field('start_date','开始日期','','date')+field('end_date','结束日期','','date');
  if(kind==='release')$('#form-fields').innerHTML=field('name','版本名称 *',item?.name||'','text',true,true)+`<label class="full">发布说明<textarea name="notes">${esc(item?.notes||'')}</textarea></label>`+field('issue_keys','关联工作项 *（至少一项，逗号分隔，如 '+project+'-1）',(item?.issue_keys||[]).join(', '),'text',true,true);
  $('#editor').showModal();
}
async function openIssue(key) {
  try {
    const i=await api('issue.get',{key});selectedIssue=i;
    const requirementDetail=i.requirement?ForgeRequirements.renderDetail({...i.requirement,key:i.key},i.key):'';
    $('#detail-content').innerHTML=`<div class="dialog-header"><div><small>${typeBadge(i)} ${esc(i.key)} · ${typeNames[i.type]}</small></div><button class="icon-button" data-close="detail" aria-label="关闭详情">×</button></div><div class="detail-body"><div class="detail-title">${esc(i.title)}</div><div class="detail-description">${esc(i.description||'尚未添加描述')}</div><div class="detail-facts"><div><small>工作项状态</small><span>${statusNames[i.status]}</span></div><div><small>负责人</small><span>${esc(i.assignee||'未分配')}</span></div><div><small>工作项调度优先级</small><span>${priorityNames[i.priority]}</span></div><div><small>故事点</small><span>${i.points} SP</span></div><div><small>迭代</small><span>${esc(state.sprints.find(s=>s.id===i.sprint_id)?.name||'未排期')}</span></div><div><small>截止日期</small><span>${esc(i.due_date||'未设置')}</span></div></div><div class="tags">${i.labels.map(l=>`<span class="tag">${esc(l)}</span>`).join('')}</div><div class="detail-actions"><select id="detail-status" aria-label="工作项状态">${opts(statusNames,i.status)}</select><button class="secondary" data-action="edit-issue">编辑工作项</button></div>${requirementDetail}<h3>评论 · ${i.comments.length}</h3>${i.comments.map(c=>`<div class="comment"><small>${esc(c.actor)} · ${dateText(c.created_at)}</small><p>${esc(c.body)}</p></div>`).join('')}<form class="comment-form" id="comment-form"><input name="body" placeholder="留下评论，与团队同步进展…" aria-label="评论内容" required><button class="primary">发送</button></form><h3>最近活动</h3>${i.activity.slice(0,8).map(activityRow).join('')}</div>`;
    if(!$('#detail').open)$('#detail').showModal();
    $('#detail-status').onchange=async e=>{try{await api('issue.update',{key:i.key,status:e.target.value,version:i.version});toast('状态已更新');await refresh();await openIssue(i.key);}catch(err){toast(err.message,true);await openIssue(i.key);}};
    $('#comment-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget;form.querySelector('button').disabled=true;try{await api('issue.comment',{key:i.key,body:new FormData(form).get('body')});await openIssue(i.key);toast('评论已发送');await refresh();}catch(err){toast(err.message,true);form.querySelector('button').disabled=false;}};
  } catch(error){toast(error.message,true);}
}
$('#edit-form').onsubmit=async e=>{
  e.preventDefault();$('#save').disabled=true;$('#form-error').textContent='';
  const data=Object.fromEntries(new FormData(e.currentTarget));
  try {
    if(editKind!=='project')data.project=project;
    if(editKind==='issue') {data.points=Number(data.points);data.sprint_id=data.sprint_id?Number(data.sprint_id):null;data.labels=data.labels.split(/[,，]/).map(s=>s.trim()).filter(Boolean);}
    if(editKind==='release')data.issue_keys=data.issue_keys.split(/[,，\s]+/).map(s=>s.trim()).filter(Boolean);
    if(editItem){delete data.project;if(editKind==='release'){data.id=editItem.id;}else{data.key=editItem.key;data.version=editItem.version;if(data.sprint_id===editItem.sprint_id)delete data.sprint_id;}}
    const result=await api(editKind+'.'+(editItem?'update':'create'),data);
    if(editKind==='project'){project=result.key;analysisScope='active';analysisRisk='all';syncLocation();}
    $('#editor').close();toast(editItem?'修改已保存':'已创建'+({issue:'工作项 '+result.key,project:'项目',sprint:'迭代',release:'版本'}[editKind]));
    await refresh();if(editKind==='issue'&&$('#detail').open)await openIssue(result.key);
  } catch(error){$('#form-error').textContent=error.message;}
  finally{$('#save').disabled=false;}
};
function changedFormValues(form){const values={};for(const control of form.querySelectorAll('[name]'))if(control.value!==control.dataset.original)values[control.name]=control.value;return values;}
async function saveRequirementForm(form,scenario=false){
  const button=form.querySelector('button[type="submit"]'),errorNode=form.querySelector('.requirement-form-error'),values=changedFormValues(form);
  if(!Object.keys(values).length){toast('没有需要保存的变更');return;}
  button.disabled=true;errorNode.textContent='';
  try{
    const payload=scenario?ForgeRequirements.scenarioUpdatePayload(form.dataset.key,form.dataset.scenarioCode,form.dataset.version,values):ForgeRequirements.updatePayload(form.dataset.key,form.dataset.version,values);
    await api(scenario?'requirement.scenario.update':'requirement.update',payload);
    toast(scenario?'场景已保存，待复核状态已同步':'需求分析已保存');
    await refresh();await openIssue(form.dataset.key);
  }catch(error){errorNode.textContent=`保存失败：${error.message}。若为版本冲突，请刷新详情后重新确认变更。`;button.disabled=false;}
}
document.addEventListener('submit',e=>{const requirementForm=e.target.closest('[data-requirement-form]'),scenarioForm=e.target.closest('[data-scenario-form]');if(!requirementForm&&!scenarioForm)return;e.preventDefault();void saveRequirementForm(requirementForm||scenarioForm,Boolean(scenarioForm));});
function downloadRequirementExport(payload,sourceId){
  const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download=`forge-requirements-${String(sourceId||'snapshot').replace(/[^a-zA-Z0-9._-]/g,'_')}.json`;document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);
}
async function handleAction(button) {
  const action=button.dataset.action;
  if(action==='show-analytics'){view='analytics';analysisScope='project';analysisRisk='all';syncLocation();return render();}
  if(action==='refresh-analysis')return refresh();
  if(action==='new-project')return openEditor('project');
  if(action==='new-issue')return openEditor('issue',null,button.dataset.status||'backlog');
  if(action==='new-sprint')return openEditor('sprint');
  if(action==='new-release')return openEditor('release');
  if(action==='edit-release')return openEditor('release',state.releases.find(r=>r.id===Number(button.dataset.id)));
  if(action==='edit-issue')return openEditor('issue',selectedIssue);
  if(action==='open-issue')return openIssue(button.dataset.issue);
  if(action==='requirements-page'){requirementPage=Number(button.dataset.page)||1;renderContent();return;}
  if(action==='show-more-requirements'){const status=button.dataset.status;boardVisible[status]=(boardVisible[status]||30)+30;renderContent();return;}
  if(action==='export-requirement'){
    button.disabled=true;
    try{const result=await api('requirement.export',{source_id:button.dataset.sourceId});downloadRequirementExport(result,button.dataset.sourceId);toast('完整来源 JSON 已导出');}catch(error){toast(error.message,true);}finally{button.disabled=false;}
    return;
  }
  if(action==='show-sprints'){view='sprints';return render();}
  if(action==='copy'){try{await navigator.clipboard.writeText(button.dataset.text);toast('已复制，请粘贴到 Codex 对话');}catch{toast('复制不可用，请直接选择提示词文本',true);}return;}
  button.disabled=true;
  try {
    if(action==='start-sprint')await api('sprint.start',{id:Number(button.dataset.id)});
    if(action==='complete-sprint')await api('sprint.complete',{id:Number(button.dataset.id)});
    if(action==='promote-release')await api('release.update',{id:Number(button.dataset.id),status:button.dataset.status});
    toast('已更新');await refresh();
  }catch(error){toast(error.message,true);}finally{button.disabled=false;}
}
document.addEventListener('click',e=>{
  const close=e.target.closest('[data-close]');if(close)return $('#'+close.dataset.close).close();
  const nav=e.target.closest('[data-view]');if(nav){view=nav.dataset.view;syncLocation();if(state)render();return;}
  const action=e.target.closest('[data-action]');if(action)return void handleAction(action);
  const card=e.target.closest('.card[data-key],tr[data-key]');if(card)openIssue(card.dataset.key);
});
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.matches('[data-key]'))openIssue(e.target.dataset.key);});
$('#project-select').onchange=async e=>{project=e.target.value;analysisScope='active';analysisRisk='all';requirementPage=1;boardVisible={};$('#search').value='';$('#filter-sprint').value='';['#filter-req-system','#filter-req-chapter','#filter-req-type','#filter-req-missing'].forEach(selector=>$(selector).value='');syncLocation();await refresh();};
document.addEventListener('change',e=>{if(e.target.id==='analysis-scope'){analysisScope=e.target.value;analysisRisk='all';syncLocation();renderContent();}if(e.target.id==='analysis-risk'){analysisRisk=e.target.value;renderContent();}});
$('#new-project').onclick=()=>openEditor('project');$('#new-issue').onclick=()=>openEditor('issue');$('#refresh').onclick=refresh;
['#search','#filter-type','#filter-priority','#filter-sprint','#filter-req-system','#filter-req-chapter','#filter-req-type','#filter-req-missing'].forEach(s=>$(s).addEventListener(s==='#search'?'input':'change',()=>{requirementPage=1;boardVisible={};if(state)renderContent();}));
let draggedKey=null;
document.addEventListener('dragstart',e=>{const card=e.target.closest('.card');if(card){draggedKey=card.dataset.key;e.dataTransfer.setData('text/plain',draggedKey);e.dataTransfer.effectAllowed='move';}});
document.addEventListener('dragover',e=>{const col=e.target.closest('.column');if(col&&draggedKey){e.preventDefault();col.classList.add('drop-over');}});
document.addEventListener('dragleave',e=>{const col=e.target.closest('.column');if(col&&!col.contains(e.relatedTarget))col.classList.remove('drop-over');});
document.addEventListener('dragend',()=>{draggedKey=null;document.querySelectorAll('.drop-over').forEach(c=>c.classList.remove('drop-over'));});
document.addEventListener('drop',async e=>{const col=e.target.closest('.column');if(!col||!draggedKey)return;e.preventDefault();const key=draggedKey;draggedKey=null;col.classList.remove('drop-over');const item=state.issues.find(i=>i.key===key);if(!item||item.status===col.dataset.status)return;try{await api('issue.update',{key,status:col.dataset.status,version:item.version});toast(`${key} → ${statusNames[col.dataset.status]}`);await refresh();}catch(err){toast(err.message,true);await refresh();}});
refresh();setInterval(()=>{if(!$('#editor').open&&!$('#detail').open&&!draggedKey)refresh();},5000);
