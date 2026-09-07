"""CLI-Anything for Forge DevOps: one-shot JSON operations and REPL."""
import json
import os
import shlex
import click
from .backend import Backend
from .store import STATUSES, TYPES, PRIORITIES

def emit(ctx, action, data):
    try:
        result = ctx.obj['backend'].call(action, data)
    except ValueError as exc:
        click.echo(json.dumps({'error': str(exc)}, ensure_ascii=False), err=True)
        ctx.exit(1)
    if ctx.obj['json']:
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    elif isinstance(result, list):
        if not result:
            click.echo('暂无记录')
        for item in result:
            click.echo('  '.join(str(item.get(k, '')) for k in ('key', 'id', 'name', 'title', 'status', 'assignee') if k in item))
    else:
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    return result

@click.group(invoke_without_command=True)
@click.option('--url', default=lambda: os.environ.get('FORGE_DEVOPS_URL', 'http://127.0.0.1:8766'), show_default='http://127.0.0.1:8766')
@click.option('--json', 'json_mode', is_flag=True, help='Machine-readable JSON output')
@click.option('--actor', default='Codex/CLI', help='Audit attribution label, not an authenticated identity')
@click.version_option('0.1.0')
@click.pass_context
def cli(ctx, url, json_mode, actor):
    """Operate Forge DevOps via its real local HTTP API."""
    try:
        ctx.obj = {'backend': Backend(url, actor), 'json': json_mode}
    except ValueError as exc:
        raise click.ClickException(str(exc))
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)

@cli.command()
@click.pass_context
def health(ctx):
    """Check server availability."""
    try:
        click.echo(json.dumps(ctx.obj['backend'].request('/api/health'), ensure_ascii=False))
    except ValueError as exc:
        click.echo(json.dumps({'error': str(exc)}, ensure_ascii=False), err=True)
        ctx.exit(1)

@cli.group()
def project():
    """Projects and project keys."""

@project.command('list')
@click.pass_context
def project_list(ctx):
    emit(ctx, 'project.list', {})

@project.command('create')
@click.option('--key', required=True)
@click.option('--name', required=True)
@click.option('--description', default='')
@click.pass_context
def project_create(ctx, **data):
    emit(ctx, 'project.create', data)

@cli.group()
def issue():
    """Stories, tasks, bugs and epics."""

@issue.command('list')
@click.option('--project')
@click.option('--status', type=click.Choice(STATUSES))
@click.option('--type', type=click.Choice(TYPES))
@click.option('--priority', type=click.Choice(PRIORITIES))
@click.option('--assignee')
@click.option('--search', 'q')
@click.option('--sprint', 'sprint_id', type=int)
@click.pass_context
def issue_list(ctx, **data):
    emit(ctx, 'issue.list', {k:v for k,v in data.items() if v is not None})

def issue_options(command):
    options = [click.option('--title'), click.option('--description'), click.option('--type', type=click.Choice(TYPES)),
               click.option('--priority', type=click.Choice(PRIORITIES)), click.option('--status', type=click.Choice(STATUSES)),
               click.option('--assignee'), click.option('--points', type=int), click.option('--due-date'),
               click.option('--label', 'labels', multiple=True), click.option('--sprint', 'sprint_id', type=int)]
    for option in options:
        command = option(command)
    return command

def clean_fields(data):
    result = {k:v for k,v in data.items() if v is not None and k != 'labels'}
    if data.get('labels'):
        result['labels'] = list(data['labels'])
    return result

@issue.command('create')
@click.option('--project', required=True)
@issue_options
@click.pass_context
def issue_create(ctx, **data):
    emit(ctx, 'issue.create', clean_fields(data))

@issue.command('get')
@click.argument('key')
@click.pass_context
def issue_get(ctx, key):
    emit(ctx, 'issue.get', {'key': key})

@issue.command('update')
@click.argument('key')
@issue_options
@click.option('--version', type=int)
@click.option('--clear-sprint', is_flag=True)
@click.option('--clear-labels', is_flag=True)
@click.pass_context
def issue_update(ctx, clear_sprint, clear_labels, **data):
    fields = clean_fields(data)
    if clear_sprint:
        fields['sprint_id'] = None
    if clear_labels:
        fields['labels'] = []
    emit(ctx, 'issue.update', fields)

@issue.command('move')
@click.argument('key')
@click.argument('status', type=click.Choice(STATUSES))
@click.pass_context
def issue_move(ctx, key, status):
    emit(ctx, 'issue.update', {'key':key, 'status':status})

@issue.command('comment')
@click.argument('key')
@click.option('--body', required=True)
@click.pass_context
def issue_comment(ctx, **data):
    emit(ctx, 'issue.comment', data)

@cli.group()
def sprint():
    """Plan, start and complete iterations."""

@sprint.command('list')
@click.option('--project')
@click.pass_context
def sprint_list(ctx, project):
    emit(ctx, 'sprint.list', {'project':project} if project else {})

@sprint.command('create')
@click.option('--project', required=True)
@click.option('--name', required=True)
@click.option('--goal', default='')
@click.option('--start-date', default='')
@click.option('--end-date', default='')
@click.pass_context
def sprint_create(ctx, **data):
    emit(ctx, 'sprint.create', data)

@sprint.command('start')
@click.argument('id', type=int)
@click.pass_context
def sprint_start(ctx, id):
    emit(ctx, 'sprint.start', {'id':id})

@sprint.command('complete')
@click.argument('id', type=int)
@click.pass_context
def sprint_complete(ctx, id):
    """Finish active iteration; unfinished work returns to backlog."""
    emit(ctx, 'sprint.complete', {'id':id})

@cli.group()
def release():
    """Track releases; released requires all linked issues done (no deployment)."""

@release.command('list')
@click.option('--project')
@click.pass_context
def release_list(ctx, project):
    emit(ctx, 'release.list', {'project':project} if project else {})

@release.command('create')
@click.option('--project', required=True)
@click.option('--name', required=True)
@click.option('--notes', default='')
@click.option('--issue', 'issue_keys', multiple=True)
@click.pass_context
def release_create(ctx, **data):
    data['issue_keys'] = list(data['issue_keys'])
    emit(ctx, 'release.create', data)

@release.command('promote')
@click.argument('id', type=int)
@click.argument('status', type=click.Choice(['planned', 'staging', 'released']))
@click.pass_context
def release_promote(ctx, **data):
    emit(ctx, 'release.update', data)

@release.command('update')
@click.argument('id', type=int)
@click.option('--name')
@click.option('--notes')
@click.option('--issue', 'issue_keys', multiple=True, help='Replace linked issues; repeat for each key.')
@click.pass_context
def release_update(ctx, **data):
    """Edit an unpublished version. Omitted fields remain unchanged."""
    if data['issue_keys']:
        data['issue_keys'] = list(data['issue_keys'])
    else:
        del data['issue_keys']
    emit(ctx, 'release.update', {k:v for k,v in data.items() if v is not None})

@cli.command()
@click.option('--project')
@click.pass_context
def report(ctx, project):
    """Project counts, completion, story points and open bugs."""
    emit(ctx, 'report.summary', {'project':project} if project else {})

@cli.command()
@click.option('--project', required=True)
@click.option('--scope', default='active', help='active, project, all, or sprint:ID')
@click.pass_context
def analytics(ctx, project, scope):
    """Read management metrics, workloads, risks and release readiness."""
    emit(ctx, 'report.analytics', {'project':project,'scope':scope})

@cli.command()
@click.option('--project')
@click.option('--target')
@click.option('--limit', type=int, default=30)
@click.pass_context
def activity(ctx, **data):
    """Read changes and their actor labels."""
    emit(ctx, 'activity.list', {k:v for k,v in data.items() if v is not None})

@cli.command()
@click.pass_context
def repl(ctx):
    """Interactive CLI-Anything session; quit to leave."""
    from .utils.repl_skin import ReplSkin
    skin = ReplSkin('devops', version='0.1.0')
    skin.skill_install_cmd = 'pip install -e devops/agent-harness'
    from pathlib import Path
    skin.global_skill_path = str(Path.home() / '.codex/skills/cli-anything-devops/SKILL.md')
    skin.print_banner()
    session = skin.create_prompt_session()
    while True:
        try:
            line = skin.get_input(session).strip()
            if line in ('quit', 'exit'):
                break
            if not line:
                continue
            args = ['--url', ctx.obj['backend'].url, '--actor', ctx.obj['backend'].actor]
            if ctx.obj['json']:
                args += ['--json']
            args += ['--help'] if line == 'help' else shlex.split(line)
            if 'repl' in args:
                skin.error('已经处于 REPL')
                continue
            cli.main(args=args, standalone_mode=False)
        except (EOFError, KeyboardInterrupt):
            break
        except (click.ClickException, ValueError) as exc:
            skin.error(str(exc))
    skin.print_goodbye()

def main():
    cli()

if __name__ == '__main__':
    main()
