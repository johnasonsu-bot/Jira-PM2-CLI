"""Current workload rankings derived from the same report as the web UI."""
from .analytics import ratio

SORT_FIELDS = ('open_points', 'open', 'in_progress')


def rank_report(report, sort_by='open_points'):
    if sort_by not in SORT_FIELDS:
        raise ValueError('排序字段必须是 open_points、open 或 in_progress')
    rows = report['workload']
    assigned = [dict(row) for row in rows if row['assignee'] and row['open'] > 0]
    # Numeric ties share a competition rank; names only stabilize display order.
    fields = (sort_by,) + tuple(field for field in ('open_points', 'open') if field != sort_by)
    score = lambda row: tuple(row[field] for field in fields)
    assigned.sort(key=lambda row: (*(-n for n in score(row)), row['assignee']))
    previous, rank = None, 0
    for position, row in enumerate(assigned, 1):
        current = score(row)
        if current != previous:
            rank = position
        row['rank'] = rank
        previous = current
    unassigned = next((dict(row) for row in rows if not row['assignee']), None)
    if unassigned is None:
        unassigned = {'assignee': '', 'open': 0, 'open_points': 0}
    metrics = report['metrics']
    open_count = metrics['open']
    coverage = {key: metrics[key] for key in (
        'positive_points_pct', 'zero_points_open', 'undated_open', 'assignee_coverage_pct')}
    coverage.update({
        'open_positive_points_pct': ratio(open_count - metrics['zero_points_open'], open_count),
        'open_assignee_coverage_pct': ratio(open_count - metrics['unassigned_open'], open_count),
        'open_due_date_coverage_pct': ratio(open_count - metrics['undated_open'], open_count),
        'all_items_denominator': metrics['total'], 'open_items_denominator': open_count,
        'percentage_basis': 'positive_points_pct、assignee_coverage_pct 分母为所选全部工作项；open_*_pct 分母仅为未完成工作项。',
    })
    return {
        'project': report['project'], 'scope': report['scope'], 'sprint': report['sprint'],
        'as_of': report['as_of'], 'date_basis': report['date_basis'],
        'sort_by': sort_by, 'sort_fields': list(fields), 'ranking': assigned,
        'unassigned': unassigned,
        'excluded_completed_only': sum(bool(row['assignee']) and row['open'] == 0 for row in rows),
        'coverage': coverage,
        'methodology': [
            '仅对所选项目和范围内有未完成工作项的负责人排名，包含 backlog、todo、in_progress、review。',
            '按 sort_fields 依次降序；数值完全相同共享竞赛名次，姓名只决定并列展示顺序。',
            '未分配工作单独列示，不作为一名开发人员；无任务的人员无法从工作项中识别。',
            '故事点（SP）不是工时；0 SP 不代表没有工作；不同项目的故事点不直接相加。',
            '这是当前负载排名，不是绩效、产能利用率或交付效率排名。',
            '逾期数量只覆盖填写了截止日期的未完成工作项；缺少日期不代表没有风险。',
            '解释当前负载的数据质量时使用 coverage.open_*_pct，避免已完成项掩盖未完成项的缺失。',
        ],
    }
