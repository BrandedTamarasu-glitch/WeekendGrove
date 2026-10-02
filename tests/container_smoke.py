"""Optional local Docker validation; uses only temporary synthetic databases.

Run: python tests/container_smoke.py --image weekend-grove:deployment-review
Requires Docker/Compose. Does not use an existing .env, database, or LAN binding.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(*args, env=None, check=True):
    return subprocess.run(args, cwd=ROOT, env=env, check=check, capture_output=True, text=True)


def request(port, path='/api/state', data=None, binary=False):
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}',
        data=None if data is None else json.dumps(data).encode(),
        headers={} if data is None else {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=4) as response:
        return response.read() if binary else json.load(response)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, help='An already built local app image; never pulled.')
    args = parser.parse_args()
    run('docker', 'image', 'inspect', args.image)
    with tempfile.TemporaryDirectory(prefix='grove-container-fixture-') as temporary:
        root = Path(temporary)
        empty_env = root/'empty.env'; empty_env.write_text('')
        instances = []

        def helper(directory, script, extra=()):
            return run('docker', 'run', '--rm', '--network', 'none', '--user', '0:0',
                '--mount', f'type=bind,source={directory},target=/fixture', *extra,
                '--entrypoint', 'python', args.image, '-c', script)

        def ownership(directory, uid=10001, gid=10001):
            helper(directory, f"import os; os.chown('/fixture',{uid},{gid}); os.chmod('/fixture',0o700); "
                f"[(os.chown('/fixture/'+n,{uid},{gid}),os.chmod('/fixture/'+n,0o600)) for n in os.listdir('/fixture')]")

        def instance(name, prepare=True):
            directory = root/name; directory.mkdir(mode=0o700)
            port = free_port()
            env = dict(os.environ, GROVE_IMAGE=args.image, GROVE_BIND_IP='127.0.0.1',
                GROVE_PORT=str(port), GROVE_ALLOWED_HOSTS='localhost,127.0.0.1',
                GROVE_APPDATA_PATH=str(directory))
            project = 'grove-smoke-'+uuid.uuid4().hex[:12]
            command = ['docker','compose','--env-file',str(empty_env),'-p',project,
                '-f','compose.yaml','-f','compose.unraid.yaml']
            result = dict(directory=directory, port=port, env=env, command=command)
            instances.append(result)
            if prepare: ownership(directory)
            return result

        def compose(instance, *args, check=True):
            return run(*instance['command'], *args, env=instance['env'], check=check)

        def start(instance, recreate=False):
            extra = ['--force-recreate'] if recreate else []
            compose(instance,'up','-d','--no-build','--pull','never',*extra)
            for _ in range(100):
                try: request(instance['port']); return
                except OSError: time.sleep(.1)
            raise RuntimeError('Fixture container did not become available.')

        try:
            a = instance('source')
            config=json.loads(compose(a,'config','--format','json').stdout)['services']['weekend-grove']
            assert config['ports'][0]['host_ip']=='127.0.0.1'
            assert len(config['volumes'])==1 and config['volumes'][0]['type']=='bind'
            assert config['volumes'][0]['bind']['create_host_path'] is False
            assert config['read_only'] and config['restart']=='unless-stopped'
            missing = dict(a['env'],GROVE_APPDATA_PATH='')
            assert run(*a['command'],'config','--quiet',env=missing,check=False).returncode != 0
            absent = root/'must-not-be-created'
            missing_path = dict(a['env'],GROVE_APPDATA_PATH=str(absent))
            rejected = run(*a['command'],'up','-d','--no-build','--pull','never',env=missing_path,check=False)
            assert rejected.returncode != 0 and not absent.exists()
            bad = instance('unprepared',prepare=False)
            failed=run('docker','run','--rm','--network','none','--user','10001:10001',
                '--mount',f"type=bind,source={bad['directory']},target=/data",'--entrypoint','python',
                args.image,'-c',"open('/data/permission-probe','w').close()",check=False)
            assert failed.returncode != 0 and 'PermissionError' in failed.stderr
            print('PASS: localhost defaults, bind override, required path, and non-root permission guard.',flush=True)
            start(a)
            probe=compose(a,'exec','-T','weekend-grove','python','-c',
                "import os; assert os.geteuid()==10001 and os.getegid()==10001; "
                "open('/tmp/probe','w').close(); "
                "assert not os.access('/app',os.W_OK); print('UID/GID 10001, writable /tmp, read-only app')")
            print(probe.stdout.strip(),flush=True)
            p=a['port']
            request(p,'/api/currency',dict(currency='CAD'))
            for title,category,cost in [('Generic container project','Projects',12.34),('Generic container activity','Activities',0)]:
                request(p,'/api/ideas',dict(title=title,category=category,duration=30,cost=cost,location='At home',energy='low'))
            limits=dict(minutes=180,budget=20,energy='low',count=2,include_lazy=True,
                day_caps={d:{c:1 for c in ('Projects','Restaurants','Places','Activities')} for d in ('Saturday','Sunday')})
            plan=request(p,'/api/generate',limits)
            request(p,'/api/plans',dict(name='Generic container weekend',ids=[i['id'] for i in plan['items']],expected_items=plan['items'],schedule=plan['schedule'],limits=plan['limits'],defaults=plan['defaults'],currency=plan['currency'],currency_assumed=plan['currency_assumed']))
            request(p,'/api/archive',dict(id=1,archived=True))
            expected=request(p)
            start(a,recreate=True); assert request(p)==expected
            compose(a,'restart');
            for _ in range(100):
                try:
                    assert request(p)==expected;break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Restart did not recover.')
            print('PASS: recreate and restart preserve ideas/archive flags, currency, and day/Lazy Day snapshots.',flush=True)
            for _ in range(45):
                cid=compose(a,'ps','-q','weekend-grove').stdout.strip()
                health=run('docker','inspect','--format','{{.State.Health.Status}}',cid).stdout.strip()
                if health=='healthy':break
                time.sleep(1)
            assert health=='healthy'; print('PASS: Docker health check becomes healthy.',flush=True)
            backup=root/'synthetic.sqlite3'; backup.write_bytes(request(p,'/api/backup',binary=True))
            with closing(sqlite3.connect(backup)) as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            export=request(p,'/api/export')
            b=instance('json-restore');start(b)
            payload=json.dumps(export)
            preview=request(b['port'],'/api/restore/preview',dict(backup_text=payload))
            assert preview['currency_mismatch']
            body=dict(backup_text=payload,digest=preview['digest'],apply_defaults=True,acknowledge_relabel=True)
            request(b['port'],'/api/restore',body);assert request(b['port'])==expected
            repeat=request(b['port'],'/api/restore',body);assert repeat['ideas_to_add']==repeat['plans_to_add']==0
            print('PASS: consistent SQLite backup and additive/idempotent JSON restore retain full synthetic state.',flush=True)
            c=instance('sqlite-migration',prepare=False)
            shutil.copy2(backup,c['directory']/'weekend.sqlite3');ownership(c['directory']);start(c)
            assert request(c['port'])==expected
            request(c['port'],'/api/currency',dict(currency='EUR'));assert request(c['port'])!=expected
            compose(c,'stop')
            helper(c['directory'],"import shutil,os; shutil.copyfile('/backup/synthetic.sqlite3','/fixture/weekend.sqlite3'); os.chown('/fixture/weekend.sqlite3',10001,10001); os.chmod('/fixture/weekend.sqlite3',0o600)",
                ('--mount',f'type=bind,source={root},target=/backup,readonly'))
            start(c);assert request(c['port'])==expected
            print('PASS: fresh SQLite migration and stopped-container rollback recover exact backup state.',flush=True)
        finally:
            for instance in reversed(instances):
                compose(instance,'down','--remove-orphans',check=False)
                ownership(instance['directory'],os.getuid(),os.getgid())
            print('Temporary containers/networks removed; only synthetic fixtures were used.',flush=True)


if __name__=='__main__':
    main()
