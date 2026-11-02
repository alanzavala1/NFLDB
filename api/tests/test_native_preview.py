"""Execute the real rollout shell script against a stateful Cloud Run stand-in."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


pytestmark = pytest.mark.skipif(os.name == 'nt' or not shutil.which('jq'), reason='Linux CI shell gate')
SERVICE = 'nfldb-native-preview'
OLD = SERVICE+'-previous'
NEW = SERVICE+'-n-123-1'
IMAGE = 'us-central1-docker.pkg.dev/test-project/nfldb/nfldb-native@sha256:'+'a'*64
SCRIPT = Path(__file__).resolve().parents[2]/'.github/scripts/native-preview.sh'

# No network or real cloud credentials: all commands mutate this fixture only.
TOOL = r'''
import json, os, pathlib, sys
path = pathlib.Path(os.environ['MOCK_STATE'])
state = json.loads(path.read_text())
args = sys.argv[1:]
tool = pathlib.Path(sys.argv[0]).name
state['events'].append([tool, *args])
def save(): path.write_text(json.dumps(state))
def value(flag): return next(a.split('=',1)[1] for a in args if a.startswith(flag+'='))
def status():
    return dict(url='https://preview.test', traffic=[dict(revisionName=state['live'],percent=100)]+
                [dict(revisionName=r, tag=t, url='https://'+t+'.preview.test') for t,r in state['tags'].items()])
if tool == 'python':
    state['selection_reads'] += 1
    save()
    sys.exit(1 if state['selection_reads'] == int(os.environ.get('STALE_AT','0')) else 0)
elif tool == 'curl':
    url = args[-1]
    target = state['tags'].get(url.split('//')[1].split('.')[0],state['live'])
    fail = (target == os.environ.get('FAIL_CANDIDATE') or
            (url.startswith('https://preview.test/') and target == os.environ.get('FAIL_BASE')))
    save()
    if fail: sys.exit(22)
    print('<div id="root"></div>' if url.endswith('/') else
          json.dumps(dict(status='ok') if url.endswith('health') else [1999,2026]))
    sys.exit(0)
elif 'list' in args:
    result = [dict(metadata=dict(name='nfldb-native-preview'),status=status())] if state['exists'] else []
elif 'deploy' in args:
    revision = 'nfldb-native-preview-'+args[args.index('--revision-suffix')+1]
    state['tags']['candidate'] = revision
    if not state['exists']: state['live'] = revision
    state['exists'] = True
    result = {}
elif 'update-traffic' in args:
    if any(a.startswith('--to-revisions=') for a in args): state['live'] = value('--to-revisions').split('=')[0]
    if any(a.startswith('--set-tags=') for a in args):
        tag,revision = value('--set-tags').split('=')
        state['tags'][tag] = revision
    result = {}
elif 'revisions' in args:
    result = dict(metadata=dict(name=args[args.index('describe')+1], labels={'serving.knative.dev/service':'nfldb-native-preview'}),
                  status=dict(conditions=[dict(type='Ready',status='True')], imageDigest=os.environ['IMAGE']))
elif 'describe' in args: result = dict(status=status())
else: raise AssertionError(args)
save()
print(json.dumps(result))
'''


@pytest.fixture
def preview(tmp_path):
    tools = tmp_path/'bin'
    tools.mkdir()
    for relative in ('bin/gcloud','bin/curl','api/.venv/bin/python'):
        path = tmp_path/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('#!'+sys.executable+'\n'+TOOL)
        path.chmod(0o755)
    state = tmp_path/'state.json'
    state.write_text(json.dumps(dict(exists=True,live=OLD,tags={},events=[],selection_reads=0)))
    env = dict(os.environ, PATH=str(tools)+os.pathsep+os.environ['PATH'], MOCK_STATE=str(state),
               PROJECT_ID='test-project', REGION='us-central1', EVIDENCE=str(tmp_path/'evidence'),
               OPERATION='deploy', DOWNLOAD=str(tmp_path/'download'), GITHUB_RUN_ID='123',
               GITHUB_RUN_ATTEMPT='1', IMAGE=IMAGE)
    def run(**overrides):
        result = subprocess.run(['bash',str(SCRIPT)],cwd=tmp_path,env=dict(env,**overrides),capture_output=True,text=True)
        return result,json.loads(state.read_text())
    return run,tmp_path,state


def test_candidate_is_checked_before_promotion_and_success_records_previous(preview):
    run,root,_ = preview
    result,state = run()
    assert result.returncode == 0, result.stderr
    assert state['live'] == NEW and state['selection_reads'] == 2
    receipt = json.loads((root/'evidence/result.json').read_text())
    assert receipt['previous_revision'] == OLD and receipt['image'] == IMAGE
    events = state['events']
    candidate_probe = next(i for i,e in enumerate(events) if e[0]=='curl' and 'candidate.preview.test' in e[-1])
    promotion = next(i for i,e in enumerate(events) if '--to-revisions='+NEW+'=100' in e)
    assert candidate_probe < promotion


@pytest.mark.parametrize('fault', ['candidate', 'stale', 'after-promotion'])
def test_failures_preserve_or_restore_the_exact_previous_revision(preview, fault):
    run,root,_ = preview
    options = {'candidate':dict(FAIL_CANDIDATE=NEW), 'stale':dict(STALE_AT='2'),
               'after-promotion':dict(FAIL_BASE=NEW)}[fault]
    result,state = run(**options)
    assert result.returncode != 0 and state['live'] == OLD
    assert not (root/'evidence/result.json').exists()
    if fault != 'after-promotion':
        assert not any('--to-revisions='+NEW+'=100' in e for e in state['events'])


def test_manual_rollback_checks_tagged_revision_and_restores_whole_revision(preview):
    run,root,state_path = preview
    state = json.loads(state_path.read_text())
    state['live'] = NEW
    state_path.write_text(json.dumps(state))
    result,state = run(OPERATION='rollback',ROLLBACK_REVISION=OLD)
    assert result.returncode == 0, result.stderr
    assert state['live'] == OLD and state['selection_reads'] == 0
    assert json.loads((root/'evidence/result.json').read_text())['previous_revision'] == NEW


def test_rollback_cannot_target_the_production_service(preview):
    run,_,_ = preview
    result,state = run(OPERATION='rollback',ROLLBACK_REVISION='nfldb-00072-vs6')
    assert result.returncode != 0 and state['live'] == OLD
    assert not any('update-traffic' in e for e in state['events'])


def test_first_preview_creation_has_no_previous_revision(preview):
    run,root,state_path = preview
    state = json.loads(state_path.read_text())
    state.update(exists=False,live='')
    state_path.write_text(json.dumps(state))
    result,state = run()
    assert result.returncode == 0, result.stderr
    assert state['live'] == NEW
    assert json.loads((root/'evidence/result.json').read_text())['previous_revision'] == ''
