#!/usr/bin/env python3
"""Android inputs and translation for one disc region of Super Paper Mario.

  usa     R8PE01 revision 0. Inputs: main.dol, relF.bin (the USA disc).
  europa  R8PP01 (any revision). Inputs: main.dol, relF.bin (the USA disc, needed to build the PAL runtime)
          and main-eu.dol, relF-eu.bin (the European disc).

Subcommands:
  prepare    checks the inputs, writes game/ (USA) and game_pal/ (Europe) the way tools/build-spm.ps1 does,
             and for europa builds wiicompiled/pal/runtime with make_pal_runtime.py (the same as -Pal on the PC).
             Writes the variables the APK needs (region id, revision, main.dol hash, runtime CMake path) to
             $GITHUB_ENV when that is set.
  translate  runs the WiiCompiled translator for the region (the translator must be built already).
"""
import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WC = ROOT / 'wiicompiled'
ORIGINAL_USA = '0d7487bc387ee1e905be335acc1e25300eb28bb8949667f753f038dbd9cf53b3'
PATCHED_USA = 'cd3b5662f61369d5ff946098033be69de8084a20b0dfd3c3d4f4819eed6d21ac'
PATCHED_EU = 'b3c3f0d7609f33a6cac5e039895e288ad51ef8fa47d69144299d14c9edfb447a'
TRANSLATOR = WC / 'translator/src/Translator.Cli/bin/Release/net8.0/Translator.Cli.dll'


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def run(argv, log, cwd):
    subprocess.run([str(x) for x in argv], cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)


def stage(name, fn):
    """Runs fn(log); on failure prints the log's tail and exits."""
    logdir = ROOT / 'build-logs/android-region'
    logdir.mkdir(parents=True, exist_ok=True)
    logfile = logdir / (name + '.log')
    try:
        with logfile.open('w') as log:
            fn(log)
        print(f'PASS {name} (log: {logfile})', flush=True)
    except (subprocess.CalledProcessError, SystemExit) as e:
        print(f'FAIL {name}: log {logfile}', file=sys.stderr)
        print('\n'.join(logfile.read_text(errors='replace').splitlines()[-25:]), file=sys.stderr)
        raise SystemExit(1) from e


# Load addresses of the pre-linked REL in each disc (projects/spm/recomp.yml and projects/spm/pal/recomp.yml, inputs.rel).
# Without them prelink_spm_rel.py assumes the USA layout, which fails on the European relF.bin.
USA_REL_ADDRESSES = []
EUROPA_REL_ADDRESSES = ['0x80C40000', '0x80F5EB20']


def prelink(rel, out_rel, out_layout, log, addresses=()):
    run([sys.executable, WC / 'projects/spm/tools/prelink_spm_rel.py', rel, out_rel, out_layout, *addresses], log, ROOT)


def write_usa(args):
    game = ROOT / 'game'
    game.mkdir(exist_ok=True)
    stock = args.usa_dol.read_bytes()
    if sha256_file(args.usa_dol) != ORIGINAL_USA:
        raise SystemExit('USA main.dol does not match R8PE01 revision 0 (SHA-256 ' + ORIGINAL_USA + ')')
    (game / 'main.dol.orig').write_bytes(stock)
    # The HQ-audio patched DOL is not used on Android (stock audio); recorded for reference only.
    patched = bytearray(stock)
    for offset, before, after in ((0x21e518, 0x40820038, 0x48000038), (0x21e85c, 0x41820014, 0x48000014)):
        if struct.unpack_from('>I', patched, offset)[0] != before:
            raise SystemExit('unexpected USA patch input instruction')
        struct.pack_into('>I', patched, offset, after)
    if hashlib.sha256(bytes(patched)).hexdigest() != PATCHED_USA:
        raise SystemExit('patched USA DOL hash mismatch')

    def prelink_usa(log):
        prelink(args.usa_rel, game / 'spm_linked.rel', game / 'spm_rel_layout.json', log, USA_REL_ADDRESSES)
    stage('prelink-usa', prelink_usa)

    source = (WC / 'projects/spm/recomp.yml').read_text()
    source = source.replace('workspace_root: ../..', 'workspace_root: ../wiicompiled')
    source = source.replace('../game/main.dol', '../game/main.dol.orig').replace(PATCHED_USA, ORIGINAL_USA)
    source = '\n'.join(line.split('  # HQ audio')[0] for line in source.splitlines()) + '\n'
    (game / 'android-stock.yml').write_text(source)


def write_europa(args):
    game_pal = ROOT / 'game_pal'
    game_pal.mkdir(exist_ok=True)
    eu = args.eu_dol.read_bytes()
    eu_sha = hashlib.sha256(eu).hexdigest()
    if eu_sha == PATCHED_EU:
        raise SystemExit('This is the European main.dol WITH the HQ music mod. Upload the original sys/main.dol.')
    (game_pal / 'main.dol.orig').write_bytes(eu)

    def prelink_eu(log):
        prelink(args.eu_rel, game_pal / 'spm_linked.rel', game_pal / 'spm_rel_layout.json', log, EUROPA_REL_ADDRESSES)
    stage('prelink-europa', prelink_eu)

    # The European project with stock audio: the original DOL, its own hash, and the workspace next to game_pal/.
    source = (WC / 'projects/spm/pal/recomp.yml').read_text()
    source = source.replace('workspace_root: ../../../pal', 'workspace_root: ../wiicompiled/pal')
    source = source.replace('../../game_pal/main.dol', '../../game_pal/main.dol.orig')
    source = source.replace(PATCHED_EU, eu_sha)
    source = '\n'.join(line.split('  # HQ audio')[0] for line in source.splitlines()) + '\n'
    (game_pal / 'android-stock.yml').write_text(source)

    def runtime(log):
        run([sys.executable, WC / 'projects/spm/pal/tools/make_pal_runtime.py', ROOT], log, ROOT)
        link = WC / 'pal/aurora-main'
        if not link.exists():
            link.symlink_to(Path('..') / 'aurora-main')
    stage('pal-runtime', runtime)
    return eu_sha


def prepare(args):
    write_usa(args)
    env = {'SPM_GAME_ID': 'R8PE01', 'SPM_GAME_REVISION': '0', 'SPM_DOL_SHA': ORIGINAL_USA,
           'SPM_RUNTIME_CMAKE': str(WC / 'runtime/CMakeLists.txt'), 'SPM_REGION': 'usa'}
    if args.region == 'europa':
        if not (args.eu_dol and args.eu_rel):
            raise SystemExit('europa needs --eu-dol and --eu-rel')
        eu_sha = write_europa(args)
        env.update({'SPM_GAME_ID': 'R8PP01', 'SPM_GAME_REVISION': '-1', 'SPM_DOL_SHA': eu_sha,
                    'SPM_RUNTIME_CMAKE': str(WC / 'pal/runtime/CMakeLists.txt'), 'SPM_REGION': 'europa'})
    github_env = os.environ.get('GITHUB_ENV')
    if github_env:
        with open(github_env, 'a') as f:
            for k, v in env.items():
                f.write(f'{k}={v}\n')
    print(json.dumps(env, indent=2))


def translate(args):
    if args.region == 'europa':
        workspace, project, region = WC / 'pal', ROOT / 'game_pal/android-stock.yml', 'P'
        resumable = WC / 'projects/spm/pal/resumable_functions.inc'  # PAL addresses; was None (no list at all)
    else:
        workspace, project, region = WC, ROOT / 'game/android-stock.yml', 'E'
        resumable = WC / 'projects/spm/resumable_functions.inc'
    if not TRANSLATOR.exists():
        raise SystemExit('the translator is not built: run tools/android/pipeline.py translator first')
    dotnet = str(args.dotnet)
    cli = [dotnet, TRANSLATOR]
    jobs = str(args.jobs)

    def tr(log):
        run([*cli, 'translate-recursive', '0x80006124', '--project', project, '--outdir', 'generated/functions',
             '--output-metadata', 'generated/base_translation_output.json',
             '--production-source-bundle', 'generated/base_translation_sources.bin',
             '--no-function-files', '--prune-stale', '--threads', jobs], log, workspace)
        run([*cli, 'emit-base-manifest', '--project', project, '--out', 'build/base',
             '--functions-dir', 'generated/functions', '--translation-output-metadata',
             'generated/base_translation_output.json', '--region', region], log, workspace)
        run([*cli, 'generate-data-init', '--project', project], log, workspace)
        shards = ['emit-build-shards', '--project', project,
                  '--base-metadata', 'generated/base_translation_output.json',
                  '--base-functions-dir', 'generated/functions',
                  '--native-source-dir', 'runtime/src', '--out', 'generated/build_shards']
        if resumable:
            shards += ['--resumable-functions', os.path.relpath(resumable, workspace)]
        run([*cli, *shards], log, workspace)
    stage(f'translate-{args.region}', tr)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    pp = sub.add_parser('prepare')
    pp.add_argument('--region', choices=['usa', 'europa'], required=True)
    pp.add_argument('--usa-dol', type=Path, required=True)
    pp.add_argument('--usa-rel', type=Path, required=True)
    pp.add_argument('--eu-dol', type=Path)
    pp.add_argument('--eu-rel', type=Path)
    pp.set_defaults(fn=prepare)
    pt = sub.add_parser('translate')
    pt.add_argument('--region', choices=['usa', 'europa'], required=True)
    pt.add_argument('--dotnet', type=Path, default='dotnet')
    pt.add_argument('--jobs', type=int, default=4)
    pt.set_defaults(fn=translate)
    args = p.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
