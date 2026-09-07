#!/usr/bin/env python3
"""Archive the supplied source ZIP and a READ ONLY, consistent MySQL snapshot.

No source Python/shell/SQL scripts are run. Output is local business data and
must stay outside the public repository. The MySQL client is already present
in the user-selected original application directory.
"""
import argparse
import hashlib
import json
import re
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

TABLES = ('projects','requirements','requirement_scenarios','field_rules','import_batches')


def archive_sources(archive, output):
    archive, output = Path(archive), Path(output)
    with zipfile.ZipFile(archive) as source:
        names = set()
        members = source.infolist()
        if sum(i.file_size for i in members)>100*1024*1024:
            raise ValueError('代码包解压大小超过 100 MiB')
        # Validate the entire inventory before creating even the output directory.
        for member in members:
            path = PurePosixPath(member.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in member.filename or not path.parts:
                raise ValueError('代码包包含不安全路径')
            if str(path) in names: raise ValueError('代码包包含重复路径')
            names.add(str(path))
            mode = member.external_attr >> 16
            if stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR):
                raise ValueError('代码包不允许符号链接或特殊文件路径')
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        target = output/'source'
        target.mkdir()
        shutil.copyfile(archive, output/archive.name)
        manifest = {'archive_name':archive.name,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':{}}
        for member in members:
            path = target/member.filename
            if member.is_dir():
                path.mkdir(parents=True,exist_ok=True)
                continue
            path.parent.mkdir(parents=True,exist_ok=True)
            content = source.read(member)
            with path.open('xb') as stream:
                stream.write(content)
            manifest['files'][member.filename] = {'size':len(content),'sha256':hashlib.sha256(content).hexdigest()}
        with (output/'manifest.json').open('x',encoding='utf-8') as stream:
            json.dump(manifest,stream,ensure_ascii=False,indent=2)
        return manifest


def snapshot_mysql(source_root):
    root = Path(source_root)
    client = root/'_mysql/mysql-server/bin/mysql'
    socket = root/'_mysql/mysql.sock'
    if not client.is_file() or not socket.exists(): raise ValueError('未找到原系统已运行的本地数据库')
    command = [str(client),'--no-defaults','--default-character-set=utf8mb4',
               '--socket='+str(socket),'--user=root','--batch','--raw','--skip-column-names','reqdb']

    def query(sql):
        result = subprocess.run(command+['--execute',sql], capture_output=True, text=True, timeout=60)
        if result.returncode: raise RuntimeError('原数据库只读导出失败；未执行任何写操作')
        return result.stdout

    schema = {}
    selects = []
    for table in TABLES:
        columns = [line.split('\t') for line in query('SHOW COLUMNS FROM `'+table+'`').splitlines()]
        if not columns or any(not re.fullmatch(r'[a-zA-Z0-9_]+',column[0]) for column in columns):
            raise ValueError('来源表结构无法安全读取')
        schema[table] = columns
        pairs = []
        for column in columns:
            name, dtype = column[:2]
            value = f'CAST(`{name}` AS CHAR)' if dtype.startswith('decimal') else f'`{name}`'
            pairs.append(f"'{name}',{value}")
        selects.append(f"SELECT JSON_OBJECT('table','{table}','row',JSON_OBJECT({','.join(pairs)})) FROM `{table}`;")
    sql = 'SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ; START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY; '
    output = query(sql+' '.join(selects)+' COMMIT;')
    tables = {table:[] for table in TABLES}
    for line in output.splitlines():
        item = json.loads(line)
        tables[item['table']].append(item['row'])
    return tables, schema


def build_bundle(output, manifest, tables, schema):
    root = Path(output)/'source'
    with (root/'data/requirements.json').open(encoding='utf-8') as stream:
        original = json.load(stream)
    documents = {path.stem:path.read_text(encoding='utf-8') for path in sorted((root/'parsed').glob('*.md'))}
    return {'source_id':'changan-finance-20260907', 'archive':manifest,
            'projects':tables['projects'],'requirements':tables['requirements'],
            'scenarios':tables['requirement_scenarios'],'field_rules':tables['field_rules'],
            'import_batches':tables['import_batches'],'original_requirements':original,
            'documents':documents,'schema':schema}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.output.resolve().is_relative_to(repo):
        parser.error('业务档案必须保存到代码仓库之外')
    tables, schema = snapshot_mysql(args.source_root)
    manifest = archive_sources(args.archive,args.output)
    bundle = build_bundle(args.output,manifest,tables,schema)
    path = args.output/'bundle.json'
    with path.open('x',encoding='utf-8') as stream:
        json.dump(bundle,stream,ensure_ascii=False,allow_nan=False,indent=2)
    print(json.dumps({'bundle':str(path),'counts':{k:len(v) for k,v in tables.items()},
                      'archive_sha256':manifest['archive_sha256']},ensure_ascii=False))


if __name__ == '__main__':
    main()
