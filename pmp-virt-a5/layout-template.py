#!/usr/bin/env python3
import hashlib
import pathlib
import shutil
import sys
HERE = pathlib.Path(__file__).resolve().parent
WORK = pathlib.Path.home() / 'work'

def change(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f'Expected one matching block in {path}')
    path.write_text(text.replace(old, new, 1))

def linux():
    src = WORK / 'linux-pmp-virt-test-src'
    shutil.copyfile(HERE / 'pv_access.c', src / 'arch/riscv/kernel/pv_access.c')
    shutil.copyfile(HERE / 'pv_access.S', src / 'arch/riscv/kernel/pv_access_asm.S')
    path = src / 'arch/riscv/kernel/Makefile'
    path.write_text(path.read_text() + '\nobj-y += pv_access.o pv_access_asm.o\n')
    change(src / 'arch/riscv/kernel/traps.c', 'static void do_trap_error(',
        'extern bool pv_access_fixup(struct pt_regs *regs);\n\nstatic void do_trap_error(')
    change(src / 'arch/riscv/kernel/traps.c',
        '\tcurrent->thread.bad_cause = regs->cause;\n\n\tif (user_mode(regs)) {',
        '\tif (!user_mode(regs) && pv_access_fixup(regs))\n\t\treturn;\n'
        '\tcurrent->thread.bad_cause = regs->cause;\n\n\tif (user_mode(regs)) {')
    change(src / 'arch/riscv/mm/init.c', 'void mark_rodata_ro(void)',
        'extern void pv_access_before(void);\nextern void pv_access_after(void);\n\n'
        'void mark_rodata_ro(void)')
    change(src / 'arch/riscv/mm/init.c',
        '\t\tret = sbi_ecall(0x0a000056, 0, 0, 0, 0, 0, 0, 0);',
        '\t\tpv_access_before();\n'
        '\t\tret = sbi_ecall(0x0a000056, 0, 0, 0, 0, 0, 0, 0);')
    change(src / 'arch/riscv/mm/init.c',
        '\t\tpr_info("PMP.Virt seal acknowledged\\n");',
        '\t\tpr_info("PMP.Virt seal acknowledged\\n");\n\t\tpv_access_after();')

def firmware():
    out = WORK / 'linux-build-pmp-virt-user'
    src = WORK / 'opensbi-pmp-virt-user-src'
    symbols = {}
    for line in (out / 'System.map').read_text().splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    offset = 0x80200000 - symbols['_start']
    ts = symbols['_text'] + offset
    te = (symbols['_etext'] + offset + 4095) & ~4095
    rs = symbols['__start_rodata'] + offset
    re = symbols['_data'] + offset
    if not (0x80200000 <= ts < te <= rs < re < 0x90000000) or any(
            x % 4096 for x in [ts, te, rs, re]):
        raise RuntimeError('Unexpected physical layout')
    digest = hashlib.sha256((out / 'arch/riscv/boot/Image').read_bytes()).hexdigest()
    header = '/* Generated from final access-test Image. */\n'
    for name, value in [('TEXT_START',ts),('TEXT_LIMIT',te),('RO_START',rs),('RO_LIMIT',re)]:
        header += f'#define PV_{name} 0x{value:x}UL\n'
    header += f'#define PV_IMAGE_SHA "{digest}"\n'
    (src / 'include/sbi/pmp_virt_layout.h').write_text(header)
    (HERE / 'expected-image.sha256').write_text(digest + '\n')
    print(header)

if __name__ == '__main__':
    {'linux':linux, 'firmware':firmware}[sys.argv[1]]()
