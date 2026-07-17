#!/usr/bin/env bash
# Assemble src/<name>.s into src/<name>_imemory.hex (one 32-bit word per line,
# the format init_memory() in test_cpu.py expects). Run this whenever you add or
# edit a .s file, then `make run HEX=<name>`.
#
#   make asm ASM=hello                # the usual way (from tb/cpu)
#   ./software/build_asm.sh hello     # equivalent, run directly from the repo root
#
# Override the toolchain prefix if yours differs, e.g.:
#   PREFIX=riscv64-linux-gnu- ./software/build_asm.sh hello
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -ne 1 ]; then
    echo "usage: $0 <name>   (assembles src/<name>.s, using runtime/link.ld)" >&2
    exit 1
fi
NAME="$1"

# This script lives in software/; program sources and the generated
# hex/intermediates live together in software/src/, the linker script in
# software/runtime/.
PROG=src

PREFIX="${PREFIX:-riscv64-unknown-elf-}"

# zicsr: CSR instructions (csrrw...) are a separate extension in modern binutils.
"${PREFIX}as"      -march=rv32i_zicsr -mabi=ilp32 "$PROG/$NAME.s" -o "$PROG/$NAME.o"
"${PREFIX}ld"      -m elf32lriscv -T runtime/link.ld "$PROG/$NAME.o" -o "$PROG/$NAME.elf"
"${PREFIX}objcopy" -O binary "$PROG/$NAME.elf" "$PROG/$NAME.bin"

# 1/4 "%08x" => read 4 bytes, print as a 32-bit little-endian word, matching
# what init_memory() reads back with int(word,16).to_bytes(4,'little').
hexdump -v -e '1/4 "%08x\n"' "$PROG/$NAME.bin" > "$PROG/${NAME}_imemory.hex"

rm -f "$PROG/$NAME.o" "$PROG/$NAME.elf" "$PROG/$NAME.bin"
echo "Wrote software/src/${NAME}_imemory.hex ($(wc -l < "$PROG/${NAME}_imemory.hex") words):"
cat "$PROG/${NAME}_imemory.hex"
