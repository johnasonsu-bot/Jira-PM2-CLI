"""Seed clearly labeled sample work via the installed CLI, never direct SQL."""
import json
import shutil
import subprocess
from datetime import date, timedelta

def run(*args):
    cli = shutil.which('cli-anything-devops')
    if not cli:
        raise SystemExit('Install cli-anything-devops first')
    result = subprocess.run([cli, '--json', '--actor', 'Demo seed', *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)

def main():
    if any(p['key'] == 'DEMO' for p in run('project', 'list')):
        print('DEMO project already exists; left unchanged.')
        return
    run('project','create','--key','DEMO','--name','Forge 研发 · 演示','--description','明确标注的演示数据，用于体验工作流；人员、计划与进度均为示例。')
    sprint = run('sprint','create','--project','DEMO','--name','Sprint 01 · 对话式研发','--goal','打通需求、迭代与 Codex 操作闭环（演示）','--start-date',date.today().isoformat(),'--end-date',(date.today()+timedelta(days=14)).isoformat())
    rows = [
        ('梳理产品权限与角色模型','story','backlog','medium','Sushi',5,'产品规划'),
        ('为关键接口补充性能基线','task','backlog','low','Lin（示例）',3,'性能'),
        ('规划 CI 流水线接入方案','epic','backlog','high','Sushi',8,'DevOps'),
        ('设计版本发布检查清单','task','todo','medium','Lin（示例）',3,'发布'),
        ('修复移动端筛选栏布局','bug','todo','high','Sushi',2,'体验优化'),
        ('搭建统一工作项数据模型','story','in_progress','high','Sushi',5,'后端'),
        ('实现可拖拽的项目看板','task','in_progress','medium','Lin（示例）',5,'前端'),
        ('接入 CLI-Anything 命令分组','story','in_progress','high','Sushi',5,'自动化'),
        ('迭代完成后归档与回收待办','task','review','medium','Lin（示例）',3,'工作流'),
        ('验证变更审计与评论追踪','task','review','medium','Sushi',2,'质量'),
        ('确定研发空间视觉规范','story','done','medium','Lin（示例）',3,'设计'),
        ('创建本地数据库与运行环境','task','done','low','Sushi',2,'基础设施'),
    ]
    done=[]
    for title,kind,status,priority,assignee,points,label in rows:
        args=['issue','create','--project','DEMO','--title',title,'--description','此工作项为演示数据，可自由编辑以体验 Forge DevOps。','--type',kind,'--status',status,'--priority',priority,'--assignee',assignee,'--points',str(points),'--label',label]
        if status!='backlog':
            args += ['--sprint',str(sprint['id'])]
        item=run(*args)
        if status=='done':
            done.append(item['key'])
    run('sprint','start',str(sprint['id']))
    release=run('release','create','--project','DEMO','--name','v0.1.0 · 示例版本','--notes','演示发布记录，不代表外部部署。','--issue',done[0],'--issue',done[1])
    run('release','promote',str(release['id']),'staging')
    print('Created DEMO with 12 sample issues, one active sprint and a staged release record.')

if __name__=='__main__':
    main()
