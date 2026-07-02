#!/usr/bin/env bash
# Assemble <name>.s into <name>_imemory.hex (one 32-bit word per line, the
# format init_memory() in test_cpu.py expects). Run this whenever you add or
# edit a .s file, then `make run HEX=<name>_imemory.hex` to see its output.
#
#   ./build_asm.sh hello
#
# Override the toolchain prefix if yours differs, e.g.:
#   PREFIX=riscv64-linux-gnu- ./build_asm.sh hello
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -ne 1 ]; then
    echo "usage: $0 <name>   (assembles <name>.s, using the shared link.ld)" >&2
    exit 1
fi
NAME="$1"

PREFIX="${PREFIX:-riscv64-unknown-elf-}"

# zicsr: CSR instructions (csrrw...) are a separate extension in modern binutils.
"${PREFIX}as"      -march=rv32i_zicsr -mabi=ilp32 "$NAME.s" -o "$NAME.o"
"${PREFIX}ld"      -m elf32lriscv -T link.ld "$NAME.o" -o "$NAME.elf"
"${PREFIX}objcopy" -O binary "$NAME.elf" "$NAME.bin"

# 1/4 "%08x" => read 4 bytes, print as a 32-bit little-endian word, matching
# what init_memory() reads back with int(word,16).to_bytes(4,'little').
hexdump -v -e '1/4 "%08x\n"' "$NAME.bin" > "${NAME}_imemory.hex"

rm -f "$NAME.o" "$NAME.elf" "$NAME.bin"
echo "Wrote ${NAME}_imemory.hex ($(wc -l < "${NAME}_imemory.hex") words):"
cat "${NAME}_imemory.hex"
