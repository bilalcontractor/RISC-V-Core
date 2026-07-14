#!/usr/bin/env bash
# Assemble programs/<name>.s into programs/<name>_imemory.hex (one 32-bit word
# per line, the format init_memory() in test_cpu.py expects). Run this whenever
# you add or edit a .s file, then `make run HEX=programs/<name>_imemory.hex`.
#
#   make asm ASM=hello              # the usual way (from tb/cpu)
#   ./runtime/build_asm.sh hello    # equivalent, run directly
#
# Override the toolchain prefix if yours differs, e.g.:
#   PREFIX=riscv64-linux-gnu- ./runtime/build_asm.sh hello
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -ne 1 ]; then
    echo "usage: $0 <name>   (assembles programs/<name>.s, using link.ld here)" >&2
    exit 1
fi
NAME="$1"

# This script lives in tb/cpu/runtime/ (link.ld is a sibling); program sources
# and the generated hex/intermediates live next to each other in tb/cpu/programs/.
PROG=../programs

PREFIX="${PREFIX:-riscv64-unknown-elf-}"

# zicsr: CSR instructions (csrrw...) are a separate extension in modern binutils.
"${PREFIX}as"      -march=rv32i_zicsr -mabi=ilp32 "$PROG/$NAME.s" -o "$PROG/$NAME.o"
"${PREFIX}ld"      -m elf32lriscv -T link.ld "$PROG/$NAME.o" -o "$PROG/$NAME.elf"
"${PREFIX}objcopy" -O binary "$PROG/$NAME.elf" "$PROG/$NAME.bin"

# 1/4 "%08x" => read 4 bytes, print as a 32-bit little-endian word, matching
# what init_memory() reads back with int(word,16).to_bytes(4,'little').
hexdump -v -e '1/4 "%08x\n"' "$PROG/$NAME.bin" > "$PROG/${NAME}_imemory.hex"

rm -f "$PROG/$NAME.o" "$PROG/$NAME.elf" "$PROG/$NAME.bin"
echo "Wrote programs/${NAME}_imemory.hex ($(wc -l < "$PROG/${NAME}_imemory.hex") words):"
cat "$PROG/${NAME}_imemory.hex"
