#!/usr/bin/env bash
# Compile src/<name>.c into src/<name>_imemory.hex, the format init_memory()
# expects (one 32-bit little-endian word per line). Mirrors build_asm.sh but for
# C: runtime/crt0.s + runtime/syscalls.c + src/<name>.c, linked with
# runtime/link_c.ld against newlib.
#
#   make c C=hello_c                  # the usual way (from tb/cpu)
#   ./software/build_c.sh hello_c     # build only, from the repo root
#
# Requires the rv32i newlib toolchain (Route B) at PREFIX. Override if yours
# lives elsewhere:  PREFIX=/path/to/riscv32-unknown-elf- ./software/build_c.sh hello_c
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -ne 1 ]; then
    echo "usage: $0 <name>   (compiles src/<name>.c with runtime/crt0.s + runtime/syscalls.c)" >&2
    exit 1
fi
NAME="$1"

# This script lives in software/; the bare-metal runtime (crt0.s, syscalls.c,
# link_c.ld) sits in software/runtime/, while program sources and the generated
# hex/elf live together in software/src/.
PROG=src

PREFIX="${PREFIX:-/home/bilal/riscv32i/bin/riscv32-unknown-elf-}"

# rv32i_zicsr: base ISA our core implements, plus CSR ops (crt0 opens the MMIO
# window). ilp32 soft-float ABI matches the Route B library build. -nostartfiles
# because crt0.s provides _start; nosys.specs stubs the syscalls syscalls.c
# doesn't override; -Os keeps the image inside the 16 KiB map.
CFLAGS="-march=rv32i_zicsr -mabi=ilp32 -Os -ffreestanding -Wall -ffunction-sections -fdata-sections"
# nano.specs pulls in newlib-nano (libc_nano): its printf is ~30 KiB smaller than
# full newlib's, which is what lets the image fit under the 0x2000 UART window.
# Full newlib overflows the 0x0000-0x2000 code region (see link_c.ld's ASSERT).
LDFLAGS="-nostartfiles -T runtime/link_c.ld --specs=nano.specs --specs=nosys.specs -Wl,--gc-sections"

# nosys.specs stubs (_close, _fstat, _isatty, _lseek, _read...) each emit an "is
# not implemented and will always fail" warning + an "in function"/"does not take
# linker garbage collection" note, plus a RWX LOAD segment warning - all expected
# for this bare-metal image. ld splits these across stdout AND stderr, so capture
# both, drop just that noise, and re-emit the rest. gcc produces no other stdout
# (the ELF goes to -o), and we branch on gcc's exit status (never grep's) so real
# errors - e.g. link_c.ld's overflow ASSERT - still fail the build and show.
gcc_out="$(mktemp)"
if ! "${PREFIX}gcc" $CFLAGS $LDFLAGS \
        runtime/crt0.s runtime/syscalls.c "$PROG/$NAME.c" -o "$PROG/$NAME.elf" >"$gcc_out" 2>&1; then
    cat "$gcc_out" >&2          # real failure: show everything
    rm -f "$gcc_out"
    exit 1
fi
grep -vE 'is not implemented|does not take linker garbage|: in function|LOAD segment with RWX' \
    "$gcc_out" >&2 || true
rm -f "$gcc_out"

"${PREFIX}objcopy" -O binary "$PROG/$NAME.elf" "$PROG/$NAME.bin"

# 1/4 "%08x" => read 4 bytes, print as a 32-bit little-endian word, matching
# init_memory()'s int(word,16).to_bytes(4,'little').
hexdump -v -e '1/4 "%08x\n"' "$PROG/$NAME.bin" > "$PROG/${NAME}_imemory.hex"

rm -f "$PROG/$NAME.bin"
echo "Wrote software/src/${NAME}_imemory.hex ($(wc -l < "$PROG/${NAME}_imemory.hex") words). ELF sections:"
"${PREFIX}size" "$PROG/$NAME.elf"
