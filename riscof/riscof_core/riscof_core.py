import os
import logging

import riscof.utils as utils
import riscof.constants as constants
from riscof.pluginTemplate import pluginTemplate

logger = logging.getLogger()


class core(pluginTemplate):
    # RISCOF diffs a file named  DUT-<__model__>.signature  (see
    # riscof/framework/test.py: dut.name[:-1] + ".signature", where
    # name == "DUT-<__model__>"). Our refactored cocotb testbench
    # (tb/cpu/test_program.py: riscof_signature_test) hard-codes the name
    # "DUT-core.signature", so __model__ must stay "core" for RISCOF to find
    # the signature the TB dumps. This also matches the class/plugin name.
    __model__ = "core"
    __version__ = "0.0.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        config = kwargs.get('config')  # the [core] section of config.ini
        if config is None:
            print("Please enter input file paths in configuration.")
            raise SystemExit(1)

        # We use cocotb, so there is no single DUT binary to invoke: the "run"
        # step is a `make` inside tb/cpu/ (see runTests). Kept for symmetry with
        # the spike template, but unused.
        self.dut_exe = None

        # Serial on purpose. Every test cd's into the SAME tb/cpu/ dir and
        # writes dut.log / dump.vcd there, so -j>1 would race on those files
        # (and on Verilator's shared sim_build/). The per-test signature is
        # safe because it lands in each test's own work_dir, but the debug
        # artifacts are not. Keep this at 1.
        self.num_jobs = 1

        # Directory this plugin lives in (core/), from config.ini.
        self.pluginpath = os.path.abspath(config['pluginpath'])

        # riscv-config checked ISA / platform yamls for HolyCore.
        self.isa_spec = os.path.abspath(config['ispec'])
        self.platform_spec = os.path.abspath(config['pspec'])

        # Compile-only mode (target_run=0) still emits the ELF/hex but skips
        # the cocotb run.
        if 'target_run' in config and config['target_run'] == '0':
            self.target_run = False
        else:
            self.target_run = True

    def initialise(self, suite, work_dir, archtest_env):
        self.work_dir = work_dir
        self.suite_dir = suite

        # One shell recipe that takes a single arch-test .S all the way to the
        # flat little-endian hex image init_memory() loads (same pipeline as
        # tb/cpu/runtime/build_asm.sh: gcc -> objcopy -O binary -> hexdump).
        #
        #   {0} : -march string (per-test, from testentry['isa'])
        #   {1} : input assembly (.S)
        #   {2} : output ELF
        #   {3} : compile macros (-DFOO ...)
        #   {4} : intermediate raw binary
        #   {5} : final hex dump (one 32-bit word per line)
        #
        # riscv32-unknown-elf-* toolchain: this machine has the full C compiler
        # only under the riscv32 prefix (~/riscv32/bin); the system riscv64
        # prefix is binutils-only (no gcc). We need gcc, not bare as/ld, because
        # gcc runs the C preprocessor over model_test.h (#include/#define) that
        # the arch tests depend on. -mabi=ilp32 + a per-test rv32* -march keeps
        # it a 32-bit build (so nm below prints 8-hex-digit addresses).
        self.compile_cmd = 'riscv32-unknown-elf-gcc -march={0} -mabi=ilp32 \
         -static -mcmodel=medany -fvisibility=hidden -nostdlib -nostartfiles -g \
         -T ' + self.pluginpath + '/env/link.ld \
         -I ' + self.pluginpath + '/env/ \
         -I ' + archtest_env + ' {1} -o {2} {3} \
         ; \
         riscv32-unknown-elf-objcopy -O binary {2} {4} \
         ; \
         hexdump -v -e \'1/4 "%08x\\n"\' {4} > {5}'

        # Absolute path to the cocotb testbench (repo's tb/cpu/). This plugin
        # lives at <repo>/riscof/riscof_core/, so tb/cpu is two levels up.
        self.tb_dir = os.path.normpath(os.path.join(self.pluginpath, "../../tb/cpu"))

    def build(self, isa_yaml, platform_yaml):
        # Nothing to build. cocotb/Verilator elaborates the RTL into
        # tb/cpu/sim_build/ on the first `make` and caches it for the rest, so
        # there is no separate model to compile the way spike/sail need one.
        pass

    def runTests(self, testList):
        # Fresh makefile of per-test targets each run.
        if os.path.exists(self.work_dir + "/Makefile." + self.name[:-1]):
            os.remove(self.work_dir + "/Makefile." + self.name[:-1])
        make = utils.makeUtil(makefilePath=os.path.join(self.work_dir, "Makefile." + self.name[:-1]))
        make.makeCommand = 'make -k -j' + str(self.num_jobs)

        for testname in testList:
            testentry = testList[testname]
            test = testentry['test_path']          # the arch-test .S
            test_dir = testentry['work_dir']        # per-test artifact/work dir

            elf = 'my.elf'
            binf = 'my.bin'
            hexf = 'my.hex'

            # -DFOO -DBAR ... macros this specific test needs.
            compile_macros = ' -D' + " -D".join(testentry['macros'])

            # Compile with the SAME -march the reference (sail) uses for this
            # test (testentry['isa']); otherwise the two models would assemble
            # different binaries and the signature diff would be meaningless.
            comp_cmd = self.compile_cmd.format(
                testentry['isa'].lower(),  # {0} -march
                test,                      # {1} input .S
                elf,                       # {2} ELF
                compile_macros,            # {3} macros
                binf,                      # {4} bin
                hexf,                      # {5} hex
            )

            # riscof_signature_test needs the addresses of these symbols as env
            # vars (hex, no 0x). Pull them from the ELF's symbol table. cut -c
            # 1-8 grabs the 8-hex-digit address column nm prints for a 32-bit
            # object; grep -w avoids matching e.g. begin_signature inside a
            # longer name.
            symbols = ['begin_signature', 'end_signature', 'write_tohost', 'tohost', 'fromhost']
            symbol_cmds = ['riscv32-unknown-elf-nm ' + elf + ' > dut.symbols']
            for symbol in symbols:
                # $$ escapes $ for make; the export persists because the whole
                # target is one backslash-continued shell line (see join below).
                symbol_cmds.append(
                    'export {0}=$$(grep -w {0} dut.symbols | cut -c 1-8)'.format(symbol)
                )

            if self.target_run:
                # Run the cocotb TB. cd into tb/cpu/, hand it the hex image plus
                # (via the exported symbols above, inherited through the env)
                # begin_signature/end_signature/write_tohost. TESTCASE pins it to
                # riscof_signature_test so we don't also re-run the whole
                # cpu_insrt_test regression on every arch test.
                sim = 'cd {0} && '.format(self.tb_dir)
                sim += 'IHEX_PATH="{0}" TESTCASE=riscof_signature_test make > tb_messages.log 2>&1'.format(
                    os.path.join(test_dir, hexf)
                )
                # The TB writes DUT-core.signature straight into test_dir
                # (dirname of IHEX_PATH), so no signature copy is needed. Copy
                # the debug artifacts (which land in the shared tb/cpu/) back
                # into this test's work_dir so a failure can be diffed/inspected.
                sim += ' ; cp ./dut.log {0}'.format(test_dir)
                sim += ' ; cp ./dump.vcd {0}'.format(test_dir)
                sim += ' ; cp ./tb_messages.log {0}'.format(test_dir)
            else:
                sim = 'echo "NO RUN"'

            # Assemble one target as a single logical shell line (';\<newline>'
            # continuation) so the `export`s stay in scope for `make`.
            execute = ['cd {0}'.format(test_dir), comp_cmd] + symbol_cmds + [sim]
            make.add_target('@' + ';\\\n'.join(execute))

        make.execute_all(self.work_dir)

        if not self.target_run:
            raise SystemExit(0)
