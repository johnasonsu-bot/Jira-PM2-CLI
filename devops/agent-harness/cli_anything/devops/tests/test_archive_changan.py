import importlib.util
from pathlib import Path
import zipfile
import json
import hashlib

import pytest


def archive_module():
    path = Path(__file__).resolve().parents[5] / 'scripts' / 'archive_changan.py'
    spec = importlib.util.spec_from_file_location('archive_changan', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unsafe_zip_is_rejected_before_destination_creation(tmp_path):
    module = archive_module()
    archive = tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('../escape.txt','bad')
    output = tmp_path/'archive'
    with pytest.raises(ValueError, match='路径'):
        module.archive_sources(archive, output)
    assert not output.exists() and not (tmp_path/'escape.txt').exists()


def test_archive_preserves_every_byte_and_never_overwrites(tmp_path):
    module = archive_module()
    archive = tmp_path/'good.zip'
    content = '财务\n完整原文'.encode()
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('parsed/doc1.md',content)
        z.writestr('data/requirements.json','[]')
        z.writestr('api.py','# preserved but never executed')
    output = tmp_path/'archive'
    result = module.archive_sources(archive,output)
    assert (output/'source/parsed/doc1.md').read_bytes() == content
    assert (output/archive.name).read_bytes() == archive.read_bytes()
    assert result['files']['parsed/doc1.md']['sha256'] == hashlib.sha256(content).hexdigest()
    assert len(result['files']) == 3
    with pytest.raises(FileExistsError): module.archive_sources(archive,output)


def test_duplicate_zip_entries_are_rejected(tmp_path):
    module = archive_module()
    archive = tmp_path/'duplicate.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('data.json','one')
        with pytest.warns(UserWarning): z.writestr('data.json','two')
    with pytest.raises(ValueError, match='重复'): module.archive_sources(archive,tmp_path/'archive')


def test_bundle_keeps_current_and_initial_data_separate(tmp_path):
    module = archive_module()
    original = [{'req_code':'P1-A-1','req_desc':'初始'}]
    archive = tmp_path/'source.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('data/requirements.json',json.dumps(original))
        z.writestr('parsed/doc1.md','来源')
    manifest = module.archive_sources(archive,tmp_path/'copy')
    tables = {'projects':[], 'requirements':[{'req_code':'P1-A-1','req_desc':'当前','workload_md':'0.00'}],
              'requirement_scenarios':[], 'field_rules':[], 'import_batches':[]}
    bundle = module.build_bundle(tmp_path/'copy', manifest, tables, {'new_column':'kept'})
    assert bundle['original_requirements'] == original
    assert bundle['requirements'] == tables['requirements']
    assert bundle['documents']['doc1'] == '来源'
    assert bundle['schema'] == {'new_column':'kept'}
