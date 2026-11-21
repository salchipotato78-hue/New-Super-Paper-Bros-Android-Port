#!/usr/bin/env python3
"""Saca del zip de datos del juego los archivos que necesita el APK.

Lo usa el workflow android-spm.yml: el secreto SPM_DATA_URL apunta a un .zip que contiene estos archivos,
buscados por su nombre (la carpeta en la que estén no importa):
  main.dol      sys/main.dol del disco USA (R8PE01 rev. 0)                 -- siempre
  relF.bin      files/rel/relF.bin del disco USA                            -- siempre
  main-eu.dol   sys/main.dol del disco europeo (R8PP01, original sin HQ)   -- solo región europa
  relF-eu.bin   files/rel/relF.bin del disco europeo                        -- solo región europa

Un zip de la carpeta DATA del disco USA ya sirve para la región usa. Para europa, añade al zip el main.dol y el
relF.bin europeos renombrados a main-eu.dol y relF-eu.bin (así no chocan con los de USA).

Nunca extrae el zip entero: lee solo los miembros que necesita, así que no hay rutas que sanear.
"""
import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

ORIGINAL_USA = '0d7487bc387ee1e905be335acc1e25300eb28bb8949667f753f038dbd9cf53b3'
PATCHED_USA = 'cd3b5662f61369d5ff946098033be69de8084a20b0dfd3c3d4f4819eed6d21ac'
PATCHED_EU = 'b3c3f0d7609f33a6cac5e039895e288ad51ef8fa47d69144299d14c9edfb447a'

USA_FILES = ['main.dol', 'relF.bin']
EUROPA_FILES = ['main-eu.dol', 'relF-eu.bin']


def fail(message):
    print(f'::error::{message}' if '--github' in sys.argv else f'ERROR: {message}', file=sys.stderr)
    raise SystemExit(1)


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('zip', type=Path, help='el zip descargado del secreto SPM_DATA_URL')
    parser.add_argument('outdir', type=Path, help='carpeta donde dejar los archivos con sus nombres canónicos')
    parser.add_argument('--region', choices=['usa', 'europa'], required=True)
    parser.add_argument('--github', action='store_true', help='formato de errores de GitHub Actions')
    args = parser.parse_args()

    if not args.zip.is_file() or args.zip.stat().st_size == 0:
        fail('la descarga está vacía.')
    if not zipfile.is_zipfile(args.zip):
        fail('el archivo de SPM_DATA_URL no es un .zip. Usa un enlace de descarga directa '
             '(en Dropbox, que termine en dl=1; no vale el enlace de vista previa).')

    wanted = USA_FILES + (EUROPA_FILES if args.region == 'europa' else [])
    args.outdir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(args.zip) as zf:
        members = {name: [] for name in wanted}
        for info in zf.infolist():
            if not info.is_dir():
                base = Path(info.filename).name
                if base in members:
                    members[base].append(info)

        for name in wanted:
            infos = members[name]
            if not infos:
                hint = ' (región europa: añade el archivo europeo renombrado, ver android/README.md)' \
                    if name in EUROPA_FILES else ''
                fail(f'el zip no contiene {name}{hint}.')
            if len({(i.file_size, i.CRC) for i in infos}) > 1:
                fail(f'el zip tiene varias copias distintas de {name}. Deja solo una.')
            target = args.outdir / name
            with zf.open(infos[0]) as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            if target.stat().st_size == 0:
                fail(f'{name} está vacío en el zip.')
            print(f'{name}: {target.stat().st_size} bytes')

    # The same checks the build does, but here, before the rest of the job runs.
    usa = sha256_file(args.outdir / 'main.dol')
    if usa == PATCHED_USA:
        fail('main.dol (USA) es el que lleva el mod de música HQ. Usa el sys/main.dol original.')
    if usa != ORIGINAL_USA:
        fail(f'main.dol (USA) no es el original de R8PE01 rev. 0 (SHA-256 {usa}, esperado {ORIGINAL_USA}).')
    print(f'main.dol USA verificado: SHA-256 {usa}')

    if args.region == 'europa':
        eu = sha256_file(args.outdir / 'main-eu.dol')
        if eu == PATCHED_EU:
            fail('main-eu.dol es el europeo CON el mod de música HQ. Usa el sys/main.dol original.')
        print(f'main-eu.dol verificado: SHA-256 {eu}')


if __name__ == '__main__':
    main()
