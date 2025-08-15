import argparse
import pathlib

MINIMUM_TARGET_SIZE = 30_000

PROGRAM_HEADER = """.section .data
has_read:
    .byte 0
region:
    .zero {0}
pointer:
    .long 0
abort_message:
    .string "abort: pointer out of range"
    abort_message_len = (. - abort_message)

.section .text
.global _start

dotproc:
    movq $1, %rdi
    lea [region], %rsi
    add [pointer], %esi
    movq $1, %rdx
    movq $1, %rax
    syscall
    ret
commaproc:
    movq $1, [has_read]
    movq $0, %rdi
    lea [region], %rsi
    add [pointer], %esi
    movq $1, %rdx
    movq $0, %rax
    syscall
    ret

cleanup:
    cmpb $1, [has_read]
    jne exit
clearbuf:
    movq $0, %rdi
    lea [region], %rsi
    movq ${1}, %rdx
    movq $0, %rax
    syscall

    cmp ${1}, %rax
    je clearbuf
exit:
    movq $0, %rdi
    movq $60, %rax
    syscall

abort:
    movq $1, %rdi
    lea [abort_message], %rsi
    movq $abort_message_len, %rdx
    movq $1, %rax
    syscall
    jmp exit

_start:
"""
SHIFT_RIGHT_INSTRUCTION = """addl $%d, [pointer]
cmpl $-1, [pointer]
je abort\n"""
SHIFT_LEFT_INSTRUCTION = """subl $%d, [pointer]
cmpl $-1, [pointer]
je abort\n"""
ADD_INSTRUCTION = """lea [region], %%eax
add [pointer], %%eax
addb $%d, (%%eax)\n"""
SUB_INSTRUCTION = """lea [region], %%eax
add [pointer], %%eax
subb $%d, (%%eax)\n"""
VALID_TOKENS = "<>[].,+-"


class BFCompiler:
    source: str
    cursor: int

    labels: dict[int, str]

    num_cells: int

    # optimization state
    consumed: int
    quantity: int

    @staticmethod
    def normalize(source_code):
        return "".join([c for c in source_code if c in VALID_TOKENS])

    def __init__(self, source: str, size = 30_000):
        self.label_counter = 0
        self.labels = {}

        self.source = BFCompiler.normalize(source)
        self.cursor = 0
        self.num_cells = size

    def __produce_header(self):
        buf_size = min(self.num_cells, 1024)
        return PROGRAM_HEADER.format(self.num_cells, buf_size)

    def __produce_shift_instruction(self) -> str | None:
        char = self.source[self.cursor]
        while char in ["<", ">"]:
            self.consumed += 1
            self.quantity += 1 if char == ">" else -1
            self.cursor += 1
            if self.cursor == len(self.source):
                break

            char = self.source[self.cursor]

        if self.consumed > 0:
            if self.quantity > 0:
                # emit instruction
                return SHIFT_RIGHT_INSTRUCTION % self.quantity
            if self.quantity < 0:
                return SHIFT_LEFT_INSTRUCTION % -self.quantity
            else:
                # all continguous moves cancel out
                return ""

        return None

    def __produce_mutate_instruction(self) -> str | None:
        char = self.source[self.cursor]
        while char in ["+", "-"]:
            self.consumed += 1
            self.quantity += 1 if char == "+" else -1
            self.cursor += 1
            if self.cursor == len(self.source):
                break

            char = self.source[self.cursor]

        if self.consumed > 0:
            instruction = "lea [region], %eax\nadd [pointer], %eax\n"
            if self.quantity > 0:
                return ADD_INSTRUCTION % self.quantity
            elif self.quantity < 0:
                return SUB_INSTRUCTION % -self.quantity
            else:
                # all contiguous add/subtracts cancel out
                return ""

        return None

    def __produce_loop_start(self):
        target = self.__lookahead()
        return """%s:
lea [region], %%eax
add [pointer], %%eax
cmpb $0, (%%eax)
je %s\n""" % (self.__get_label(self.cursor), target)

    def __produce_loop_end(self):
        target = self.__lookbehind()
        return """%s:
lea [region], %%eax
add [pointer], %%eax
cmpb $0, (%%eax)
jne %s\n""" % (self.__get_label(self.cursor), target)

    def __produce_instruction(self):
        if self.cursor == len(self.source):
            raise StopIteration()

        self.consumed = 0
        self.quantity = 0

        instruction = self.__produce_shift_instruction()
        if instruction is not None:
            return instruction

        instruction = self.__produce_mutate_instruction()
        if instruction is not None:
            return instruction

        char = self.source[self.cursor]
        instruction = ""
        if char == "[":
            instruction = self.__produce_loop_start()
        elif char == "]":
            instruction = self.__produce_loop_end()
        elif char == ".":
            instruction = "call dotproc\n"
        elif char == ",":
            instruction = "call commaproc\n"
        else:
            instruction = ""

        self.cursor += 1
        return instruction

    def __get_label(self, index):
        return f"tag_{index}"

    def __lookahead(self):
        local_cursor = self.cursor + 1
        nest_level = 0
        while nest_level >= 0 and local_cursor < len(self.source):
            if self.source[local_cursor] == "[":
                nest_level += 1
            elif self.source[local_cursor] == "]":
                nest_level -= 1

            local_cursor += 1

        if nest_level < 0:
            return self.__get_label(local_cursor - 1)
        else:
            raise ValueError("missing matching bracket")

    def __lookbehind(self):
        local_cursor = self.cursor - 1
        nest_level = 0
        while nest_level >= 0 and local_cursor > 0:
            if self.source[local_cursor] == "]":
                nest_level += 1
            elif self.source[local_cursor] == "[":
                nest_level -= 1

            local_cursor -= 1

        if nest_level < 0:
            return self.__get_label(local_cursor + 1)
        else:
            raise ValueError("missing matching bracket")

    def compile(self):
        output = self.__produce_header()
        while True:
            try:
                output += self.__produce_instruction()
            except StopIteration:
                break

        # add exit logic
        output += "call cleanup"
        return output


# these steps are handled by external tools (as and ld)
import shutil
import subprocess
import sys

def assemble_and_link(compiled_code: str, output_path: str = "a.out"):
    assembler = shutil.which("as")
    if assembler is None:
        sys.stderr.write("fatal: could not find assembler 'as'\n")
        sys.exit(1)

    linker = shutil.which("ld")
    if linker is None:
        sys.stderr.write("fatal: could not find linker 'ld'\n'")
        sys.exit(1)

    proc = subprocess.Popen([assembler, "-o", "/tmp/bf.o", "--"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate(compiled_code.encode())
    if proc.returncode != 0:
        sys.stderr.write("fatal: assembler failed\n")
        sys.stderr.write(stderr.decode("utf-8"))
        sys.exit(1)

    proc = subprocess.Popen([linker, "/tmp/bf.o", "-o", output_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        sys.stderr.write("fatal: linker failed\n")
        sys.stderr.write(stderr.decode("utf-8"))
        sys.exit(1)


def read_options():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=argparse.FileType("r"), help="Source code file.")
    parser.add_argument("-o", "--output", type=pathlib.Path, help="Output executable.")
    parser.add_argument("--target-size", type=int, default=MINIMUM_TARGET_SIZE,
                        help="Number of cells in the BF memory tape.")
    parser.add_argument("-S", "--assemble-only", action="store_true")

    return parser.parse_args()


def main():
    options = read_options()

    if options.target_size < MINIMUM_TARGET_SIZE:
        print("A target machine size of less than 30,000 is not supported by the BF language.")
        sys.exit(1)
    
    source_code = options.source.read()
    compiler = BFCompiler(source_code, options.target_size)
    assembly = compiler.compile()

    if options.assemble_only:
        if options.output is None:
            sys.stdout.write(assembly)
        else:
            try:
                with open(options.output, "w") as fp:
                    fp.write(assembly)
            except IOError:
                sys.stderr.write("fatal: could not write assembly output\n")
                sys.exit(1)
    else:
        if options.output is None:
            sys.stderr.write("fatal: must provide output file (unless -S is used)\n")
            sys.exit(1)

        assemble_and_link(assembly, options.output)


if __name__ == '__main__':
    main()

