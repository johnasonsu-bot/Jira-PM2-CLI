"""Read-only management metrics; no synthetic history or inferred capacity."""
from datetime import date, datetime, timedelta

STATUS_ORDER = ('backlog', 'todo', 'in_progress', 'review', 'done')

def ratio(numerator, denominator):
    return round(numerator / denominator * 100, 1) if denominator else None

def age_days(timestamp, today):
    try:
        return max(0, (today - datetime.fromisoformat(timestamp).astimezone().date()).days)
    except (ValueError, TypeError):
        return None

def release_readiness(releases, all_items):
    indexed = {item['key']: item for item in all_items}
    result = []
    for release in releases:
        keys = release['issue_keys']
        done = sum(k in indexed and indexed[k]['status'] == 'done' for k in keys)
        result.append({**release, 'linked_count': len(keys), 'done_count': done,
                       'pending_count': len(keys) - done, 'completion_pct': ratio(done, len(keys)),
                       'ready': release['status'] != 'released' and bool(keys) and done == len(keys)})
    return result

def build_report(items, sprint, scope, project, releases, today=None):
    today = today or date.today()
    open_items = [i for i in items if i['status'] != 'done']
    done = [i for i in items if i['status'] == 'done']
    due = today.isoformat()
    soon = (today + timedelta(days=3)).isoformat()
    def flags(item):
        if item['status'] == 'done': return []
        reasons = []
        if item['due_date'] and item['due_date'] < due: reasons.append('overdue')
        if item['priority'] in ('critical', 'high'): reasons.append('high')
        if item['due_date'] and due <= item['due_date'] <= soon: reasons.append('due_soon')
        if not item['assignee']: reasons.append('unassigned')
        if item['points'] == 0: reasons.append('zero_points')
        if not item['due_date']: reasons.append('undated')
        if (age_days(item['updated_at'], today) or 0) >= 7: reasons.append('stale')
        return reasons
    risks = [{**{k:i[k] for k in ('key','title','status','priority','assignee','points','due_date')},
              'reasons': flags(i), 'age_days': age_days(i['created_at'], today),
              'unchanged_days': age_days(i['updated_at'], today)} for i in open_items if flags(i)]
    risks.sort(key=lambda i: (not ('overdue' in i['reasons']), not ('high' in i['reasons']),
                             not ('due_soon' in i['reasons']), i['key']))
    count = lambda flag: sum(flag in i['reasons'] for i in risks)
    points = sum(i['points'] for i in items)
    done_points = sum(i['points'] for i in done)
    ages = [age_days(i['created_at'], today) for i in open_items]
    ages = [n for n in ages if n is not None]
    m = {'total':len(items), 'done':len(done), 'open':len(open_items),
         'done_pct':ratio(len(done),len(items)), 'points':points, 'done_points':done_points,
         'remaining_points':points-done_points, 'points_done_pct':ratio(done_points,points),
         'in_progress':sum(i['status']=='in_progress' for i in items),
         'review':sum(i['status']=='review' for i in items), 'high_open':count('high'),
         'critical_open':sum(i['priority']=='critical' for i in open_items),
         'open_bugs':sum(i['type']=='bug' for i in open_items),
         'overdue':count('overdue'), 'due_soon':count('due_soon'), 'undated_open':count('undated'),
         'unassigned_open':count('unassigned'), 'zero_points_open':count('zero_points'),
         'stale_open':count('stale'), 'average_open_age_days':round(sum(ages)/len(ages),1) if ages else None,
         'due_date_coverage_pct':ratio(sum(bool(i['due_date']) for i in items),len(items)),
         'assignee_coverage_pct':ratio(sum(bool(i['assignee']) for i in items),len(items)),
         'positive_points_pct':ratio(sum(i['points']>0 for i in items),len(items)),
         'description_coverage_pct':ratio(sum(bool(i['description']) for i in items),len(items))}
    workload = []
    for assignee in sorted({i['assignee'] for i in items}):
        group = [i for i in items if i['assignee']==assignee]
        pending = [i for i in group if i['status']!='done']
        workload.append({'assignee':assignee, 'total':len(group), 'open':len(pending),
            'points':sum(i['points'] for i in group), 'open_points':sum(i['points'] for i in pending),
            'done_points':sum(i['points'] for i in group if i['status']=='done'),
            'in_progress':sum(i['status']=='in_progress' for i in group),
            'review':sum(i['status']=='review' for i in group),
            'high_open':sum(i['priority'] in ('high','critical') for i in pending),
            'overdue':sum(bool(i['due_date']) and i['due_date']<due for i in pending)})
    workload.sort(key=lambda row: (-row['open_points'], -row['open'], row['assignee']))
    timeline = None
    if sprint and sprint['start_date'] and sprint['end_date']:
        start, end = date.fromisoformat(sprint['start_date']), date.fromisoformat(sprint['end_date'])
        duration = (end-start).days
        elapsed = max(0,min(100,(today-start).days/max(1,duration)*100))
        timeline = {'start':start.isoformat(),'end':end.isoformat(), 'days_to_end':(end-today).days,
                    'elapsed_pct':round(elapsed,1)}
    return {'project':project, 'scope':scope, 'sprint':sprint, 'as_of':due, 'date_basis':'服务器本地日历日期',
        'metrics':m, 'timeline':timeline,
        'by_status':[{'status':s,'count':sum(i['status']==s for i in items),
                      'points':sum(i['points'] for i in items if i['status']==s)} for s in STATUS_ORDER],
        'workload':workload, 'risks':risks, 'releases':releases, 'release_scope':'project',
        'unavailable':{'burndown':'缺少迭代承诺基线与每日历史快照',
            'velocity':'尚未采集已完成迭代的冻结交付数据',
            'cycle_time':'缺少可靠的开始、完成及重开时间口径',
            'blocked':'没有阻塞标记与依赖关系字段',
            'capacity':'没有人员可用工时与计划产能，故事点不等于工时',
            'dora':'未接入 CI/CD 部署、变更失败与故障恢复数据'}}
