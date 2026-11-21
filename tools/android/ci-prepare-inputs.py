#!/usr/bin/env python3
"""Prepare the translator inputs for the Android APK from two files, without the whole disc.

CI downloads two files from the `game-data` release of your fork (you upload them once, see
android/README.md):
  main.dol   sys/main.dol of your disc (stock, SHA-256 0d7487bc...)
  relF.bin   files/rel/relF.bin of your disc

It writes what tools/android/pipeline.py expects after `prepare-inputs`: the stock DOL, the HQ-audio
patched DOL (kept for reference), the pre-linked REL, and game/android-stock.yml (stock audio), so
that `pipeline.py translator` and `pipeline.py translate` can run. Nothing from the game is committed.
"""
import argparse
import hashlib
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WC = ROOT / 'wiicompiled'
ORIGINAL = '0d7487bc387ee1e905be335acc1e25300eb28bb8949667f753f038dbd9cf53b3'
PATCHED = 'cd3b5662f61369d5ff946098033be69de8084a20b0dfd3c3d4f4819eed6d21ac'


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dol', type=Path, required=True, help='stock sys/main.dol of the disc')
    parser.add_argument('--rel', type=Path, required=True, help='files/rel/relF.bin of the disc')
    args = parser.parse_args()

    stock = args.dol.read_bytes()
    if sha256(stock) != ORIGINAL:
        raise SystemExit('main.dol does not match R8PE01 revision 0 (expected SHA-256 ' + ORIGINAL + ')')

    game = ROOT / 'game'
    game.mkdir(exist_ok=True)

    # Same two code patches as pipeline.py prepare-inputs (HQ audio); recorded, not used for Android.
    patched = bytearray(stock)
    for offset, before, after in ((0x21e518, 0x40820038, 0x48000038), (0x21e85c, 0x41820014, 0x48000014)):
        if struct.unpack_from('>I', patched, offset)[0] != before:
            raise SystemExit('unexpected patch input instruction')
        struct.pack_into('>I', patched, offset, after)
    if sha256(bytes(patched)) != PATCHED:
        raise SystemExit('patched DOL hash mismatch')
    (game / 'main.dol.orig').write_bytes(stock)
    (game / 'main.dol').write_bytes(bytes(patched))

    subprocess.run([sys.executable, str(WC / 'projects/spm/tools/prelink_spm_rel.py'), str(args.rel),
                    str(game / 'spm_linked.rel'), str(game / 'spm_rel_layout.json')], check=True)

    # The project file the translator reads: stock audio, the original DOL, the pre-linked REL.
    source = (WC / 'projects/spm/recomp.yml').read_text()
    source = source.replace('workspace_root: ../..', 'workspace_root: ../wiicompiled')
    source = source.replace('../game/main.dol', '../game/main.dol.orig').replace(PATCHED, ORIGINAL)
    source = '\n'.join(line.split('  # HQ audio')[0] for line in source.splitlines()) + '\n'
    (game / 'android-stock.yml').write_text(source)
    print('inputs ready in', game)


if __name__ == '__main__':
    main()
