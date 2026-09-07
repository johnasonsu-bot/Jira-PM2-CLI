'use strict';
// Presentation only: metric values come from the same backend used by the CLI.
const ForgeAnalytics = (() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const statuses={backlog:'待办池',todo:'待开始',in_progress:'进行中',review:'待验收',done:'已完成'};
  const lifecycle={planned:'计划中',active:'进行中',completed:'已完成',staging:'验证中',released:'已发布'};
  const reasons={overdue:'已逾期',high:'高优先级',due_soon:'3 天内到期',unassigned:'未分配',zero_points:'0 SP 待确认',undated:'未设截止日期',stale:'≥7 天未更新字段'};
  const percent=value=>value==null?'—':`${value}%`;
  const selectReport=(data,scope)=>Object.hasOwn(data.analytics||{},scope)?data.analytics[scope]:data.analytics?.active??null;
  const selectRisks=(report,filter)=>report.risks.filter(i=>filter==='all'||i.reasons.includes(filter));
  const metric=(label,value,note)=>`<div class="metric"><div class="metric-top"><span>${esc(label)}</span></div><strong>${esc(value??'—')}</strong><small>${esc(note)}</small></div>`;
  const openIssue=(key,label)=>`<button class="analytics-link" data-action="open-issue" data-issue="${esc(key)}">${esc(label||key)}</button>`;

  function pulse(report) {
    if(!report)return '';
    const m=report.metrics;
    return `<div class="pulse-heading"><span>项目管理摘要 <small>整个项目 · 不随下方筛选改变</small></span><button class="secondary" data-action="show-analytics">查看管理分析 ↗</button></div><div class="management-pulse">${[['待验收',m.review],['高优先级未完',m.high_open],['已逾期',m.overdue],['未分配',m.unassigned_open],['0 SP 待确认',m.zero_points_open],['≥7 天未更新',m.stale_open]].map(([label,value])=>`<div><small>${label}</small><strong>${value}</strong></div>`).join('')}</div>`;
  }

  function render(data,scope='active',filter='all') {
    const report=selectReport(data,scope);
    if(!report)return '<div class="empty-state">管理指标暂不可用，请刷新后重试。</div>';
    if(!Object.hasOwn(data.analytics,scope))scope='active';
    const m=report.metrics,sprint=report.sprint,timeline=report.timeline;
    const choices=[['active','当前活动迭代'],['project','整个项目'],...data.sprints.map(s=>[`sprint:${s.id}`,`${s.name} · ${lifecycle[s.status]}`])];
    const riskItems=selectRisks(report,filter);
    const label=scope==='project'?'整个项目':sprint?.name||'暂无活动迭代';
    const noScope=scope==='active'&&!sprint;
    const metricCards=[
      ['工作项完成率',percent(m.done_pct),`${m.done} / ${m.total} 项已完成`],
      ['故事点完成率',percent(m.points_done_pct),`${m.done_points} / ${m.points} SP 已完成`],
      ['剩余故事点',`${m.remaining_points} SP`,`${m.open} 项尚未完成 · SP ≠ 工时`],
      ['进行中 WIP',m.in_progress,'仅统计进行中，不含待验收'],
      ['待验收',m.review,'等待检查与验收的工作项'],
      ['高优先级未完成',m.high_open,`包含 ${m.critical_open} 项最高优先级`],
      ['未解决缺陷',m.open_bugs,'类型为缺陷且尚未完成'],
      ['已逾期',m.overdue,`仅统计已设截止日期；${m.undated_open} 项未设`],
      ['3 天内到期',m.due_soon,'截止日期在今天至今天 +3 天，且未完成'],
      ['未分配负责人',m.unassigned_open,'仅统计未完成工作项'],
      ['0 SP 待确认',m.zero_points_open,'可能未估算，也可能确为零点'],
      ['≥7 天未更新字段',m.stale_open,'未完成工作项；评论不算字段更新']
    ];
    const readiness=report.releases;
    const readyCount=readiness.filter(r=>r.ready).length;
    const gateCount=readiness.filter(r=>r.status!=='released'&&!r.ready).length;
    const coverage=[['负责人覆盖率',m.assignee_coverage_pct],['截止日期覆盖率',m.due_date_coverage_pct],['正故事点覆盖率',m.positive_points_pct],['描述覆盖率',m.description_coverage_pct]];
    const maxWork=Math.max(1,...report.workload.map(w=>w.points));
    return `<div class="analysis-toolbar"><label>统计范围<select id="analysis-scope" aria-label="管理分析统计范围">${choices.map(([key,name])=>`<option value="${esc(key)}" ${key===scope?'selected':''}>${esc(name)}</option>`).join('')}</select></label><div class="analysis-date">截至 ${esc(report.as_of)} · ${esc(report.date_basis)}${data.project==='DEMO'?'<span class="pill">含演示数据</span>':''}</div><button class="secondary" data-action="refresh-analysis">↻ 刷新指标</button></div>
      <section class="analysis-summary"><div><small>当前统计口径</small><h2>${esc(label)}</h2><p>${esc(sprint?.goal||'项目工作项、风险与交付情况')}</p><span>${m.total} 项 · ${m.points} SP ${sprint?'· '+esc(lifecycle[sprint.status]):''}</span></div><div class="analysis-schedule">${timeline?`<span>${esc(timeline.start)} → ${esc(timeline.end)}</span><strong>${timeline.days_to_end<0?'超出计划结束日 '+Math.abs(timeline.days_to_end)+' 天':timeline.days_to_end===0?'计划今天结束':'距计划结束 '+timeline.days_to_end+' 天'}</strong><div class="progress" role="progressbar" aria-label="计划日期窗口已过比例" aria-valuenow="${timeline.elapsed_pct}" aria-valuemin="0" aria-valuemax="100"><i style="width:${timeline.elapsed_pct}%"></i></div><small>计划日期窗口已过 ${timeline.elapsed_pct}% · 非燃尽预测</small>`:`<strong>${scope==='project'?'项目范围':'未设置完整日期窗口'}</strong><small>${scope==='project'?'切换迭代可查看计划日期窗口':'日期不足，不计算剩余天数'}</small>`}</div></section>
      ${noScope?'<div class="analysis-notice">当前项目没有活动迭代。以下迭代指标为空，可切换“整个项目”或指定计划迭代；不会自动启动任何迭代。</div>':m.total===0?'<div class="analysis-notice">当前范围尚无工作项，完成率与覆盖率显示“—”，不代表已全部完成。</div>':''}
      <div class="analytics-metrics">${metricCards.map(args=>metric(...args)).join('')}</div>
      <div class="analysis-columns"><section class="analysis-panel"><div class="analysis-section-head"><h3>工作流分布</h3><small>条长为工作项占比 · 共 ${m.total} 项</small></div>${report.by_status.map(row=>`<div class="analysis-bar-row"><div><span>${esc(statuses[row.status])}</span><span>${row.count} 项 · ${row.points} SP</span></div><div class="analysis-track" role="img" aria-label="${esc(statuses[row.status])} ${row.count} 项 ${row.points} 故事点"><i class="status-${row.status}" style="width:${m.total?row.count/m.total*100:0}%"></i></div></div>`).join('')}</section>
      <section class="analysis-panel"><div class="analysis-section-head"><h3>数据完整性</h3><small>分母为当前范围全部工作项</small></div>${coverage.map(([name,value])=>`<div class="analysis-bar-row"><div><span>${name}</span><span>${percent(value)}</span></div><div class="analysis-track" role="img" aria-label="${name} ${value==null?'无数据':percent(value)}"><i style="width:${value??0}%"></i></div></div>`).join('')}<p class="analysis-footnote">未完成工作平均存续 ${m.average_open_age_days??'—'} 天（从创建日起算，非周期时间）。</p></section></div>
      <section class="analysis-panel"><div class="analysis-section-head"><h3>负责人工作量</h3><small>按未完成 SP 排序 · 未配置产能，不判定“超负荷”</small></div><div class="analysis-table-wrap"><table class="analytics-table"><thead><tr><th>负责人 / 总 SP</th><th>工作项</th><th>未完成 SP</th><th>已完成 SP</th><th>进行中</th><th>待验收</th><th>高优未完</th><th>逾期</th></tr></thead><tbody>${report.workload.map(w=>`<tr><td><span>${esc(w.assignee||'未分配')} · ${w.points} SP</span><div class="analysis-track mini"><i style="width:${w.points/maxWork*100}%"></i></div></td><td>${w.total}</td><td>${w.open_points}</td><td>${w.done_points}</td><td>${w.in_progress}</td><td>${w.review}</td><td>${w.high_open}</td><td>${w.overdue}</td></tr>`).join('')||'<tr><td colspan="8">当前范围暂无工作量。</td></tr>'}</tbody></table></div></section>
      <section class="analysis-panel"><div class="analysis-section-head"><div><h3>关注项与待完善字段</h3><small>点击工作项查看详情 · 按逾期、高优先级、近期到期排序</small></div><label>筛选<select id="analysis-risk" aria-label="筛选管理关注项">${[['all','全部关注项'],...Object.entries(reasons)].map(([key,name])=>`<option value="${key}" ${filter===key?'selected':''}>${name}</option>`).join('')}</select></label></div><div class="analysis-table-wrap"><table class="analytics-table"><thead><tr><th>工作项 / 标题</th><th>状态</th><th>负责人</th><th>关注原因</th><th>截止日期</th></tr></thead><tbody>${riskItems.map(i=>`<tr><td>${openIssue(i.key)}<div>${esc(i.title)}</div></td><td>${esc(statuses[i.status])}</td><td>${esc(i.assignee||'未分配')}</td><td><div class="analysis-flags">${i.reasons.map(r=>`<span class="pill ${r==='overdue'?'alert':''}">${esc(reasons[r])}</span>`).join('')}</div></td><td>${esc(i.due_date||'未设置')}</td></tr>`).join('')||'<tr><td colspan="5">没有匹配的关注项；未记录的阻塞信息不在此统计。</td></tr>'}</tbody></table></div><small>${riskItems.length} 项匹配 · 同一工作项可有多个原因</small></section>
      <section class="analysis-panel"><div class="analysis-section-head"><div><h3>版本发布门禁 <span class="pill">整个项目</span></h3><small>始终使用项目全量关联工作项；不代表 CI/CD 部署结果</small></div><span>${readyCount} 个可标记发布 · ${gateCount} 个未通过门禁</span></div><div class="analysis-table-wrap"><table class="analytics-table"><thead><tr><th>版本</th><th>状态</th><th>完成 / 关联</th><th>门禁结果</th></tr></thead><tbody>${readiness.map(r=>`<tr><td>${esc(r.name)}</td><td>${esc(lifecycle[r.status])}</td><td>${r.done_count} / ${r.linked_count} 项</td><td>${r.status==='released'?'已标记发布':r.ready?'关联工作全部完成':!r.linked_count?'缺少关联工作项':`${r.pending_count} 项仍未完成`}</td></tr>`).join('')||'<tr><td colspan="4">当前项目暂无版本。</td></tr>'}</tbody></table></div></section>
      <details class="analysis-panel"><summary>指标口径与暂不可计算项</summary><div class="analysis-definitions"><p>完成率仅使用当前状态，不代表历史承诺完成率。无分母时显示“—”；已完成工作项不纳入逾期、近期到期及待完善字段统计。</p><p>“3 天内到期”含今天与第 3 天；“≥7 天未更新”按服务器本地日历日计算字段更新时间，评论不改变该时间。版本区固定为项目口径，不随迭代选择收缩。</p>${Object.entries(report.unavailable).map(([key,why])=>`<div><b>${esc({burndown:'燃尽 / 承诺达成率',velocity:'迭代速率',cycle_time:'周期时间 / 吞吐趋势',blocked:'阻塞率 / 依赖风险',capacity:'产能利用率',dora:'DORA 指标'}[key]||key)}</b><span>暂不可计算：${esc(why)}</span></div>`).join('')}</div></details>`;
  }
  return {render,pulse,selectReport,selectRisks,percent,metric};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=ForgeAnalytics;
