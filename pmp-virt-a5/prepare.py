#!/usr/bin/env python3
import pathlib
import sys
import importlib.util
HERE = pathlib.Path(__file__).resolve().parent
WORK = pathlib.Path.home() / 'work'

def change(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Expected one source block: ' + old[:80])
    return text.replace(old, new, 1)

def linux():
    path = WORK / 'linux-pmp-virt-user-src/arch/riscv/kernel/pv_access.c'
    text = path.read_text()
    text = change(text, 'static bool armed;',
                  'static bool armed;\nstatic bool pv_boot_tests_done;')
    text = change(text, '    vunmap(ro_alias);',
                  '    vunmap(ro_alias);\n    WRITE_ONCE(pv_boot_tests_done, true);')
    text += '\n' + (HERE / 'driver.inc').read_text()
    path.write_text(text)

def firmware():
    spec = importlib.util.spec_from_file_location('layout', HERE / 'layout-template.py')
    layout = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(layout)
    layout.WORK = WORK
    layout.firmware()

if __name__ == '__main__':
    {'linux':linux, 'firmware':firmware}[sys.argv[1]]()
