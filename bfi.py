import argparse
import pathlib
import sys


VALID_TOKENS = "<>[].,+-"
MINIMUM_TARGET_SIZE = 30_000


class InterpreterError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


_iobuf = []


def io_rebuffer(unused: str):
    global _iobuf
    _iobuf.extend(list(unused))


def io_getchar():
    global _iobuf
    if _iobuf:
        char = _iobuf[0]
        _iobuf.pop(0)
    else:
        raw = sys.stdin.read(1).encode()
        if len(raw) > 1:
            raise InterpreterError("interpreter does not accept multibyte characters")
        elif len(raw) == 0:
            raise InterpreterError("reached eof when scanning for input")
        char = ord(raw)

    return char


def tag_lookahead(source, index):
    """
    Given the index of an opening bracket, find its matched closing bracket.
    """
    cursor = index + 1
    nest_level = 1
    while cursor < len(source):
        char = source[cursor]
        if char == "[":
            nest_level += 1
        if char == "]":
            nest_level -= 1
            if nest_level == 0:
                return cursor

        cursor += 1

    raise InterpreterError("mismatched bracket at index %d" % index)


def construct_tags(source):
    """
    Creates a map of tags, used to evaluate loop behavior instead of
    performing ad-hoc searches every time a [ or ] is encountered.
    """
    tags = {}
    for index in range(len(source)):
        char = source[index]
        if char == '[':
            next_index = tag_lookahead(source, index)
            tags[index] = next_index
            tags[next_index] = index
        elif char == ']':
            # should already be populated, but if not, this
            # indicates a bracket mismatch
            if index not in tags:
                raise InterpreterError("mismatched bracket at index %d" % index)

    return tags


def clean_source(source):
    """
    Strip out irrelevant characters to optimize performance.
    """
    return "".join([c for c in source if c in VALID_TOKENS])


def interpret(source, cells: int = MINIMUM_TARGET_SIZE):
    """
    Interpret the program.
    """
    source = clean_source(source)
    loop_tags = construct_tags(source)

    machine = bytearray(cells)
    pointer = 0

    cursor = 0
    while cursor < len(source):
        char = source[cursor]
        match char:
            case ">":
                pointer += 1
                if pointer == cells:
                    raise InterpreterError("pointer out of range (%d)" % cells)
            case "<":
                pointer -= 1
                if pointer < 0:
                    raise InterpreterError("pointer out of range (-1)")
            case "+":
                machine[pointer] = (machine[pointer] + 1) & 0xFF
            case "-":
                machine[pointer] = (machine[pointer] - 1) & 0xFF
            case "[":
                if machine[pointer] == 0:
                    cursor = loop_tags[cursor]
            case "]":
                if machine[pointer] != 0:
                    cursor = loop_tags[cursor]
            case ".":
                sys.stdout.write(chr(machine[pointer]))
            case ",":
                machine[pointer] = io_getchar()
            case _:
                pass
        cursor += 1


# entry point
def read_until_char(char):
    result = ""

    chunk_size = 1024
    chunk = sys.stdin.read(chunk_size)
    while char not in result:
        result += chunk
        chunk = sys.stdin.read(chunk_size)
    result += chunk

    first_occurrence = result.index(char)
    io_rebuffer(result[first_occurrence:])
    result = result[:first_occurrence]

    return result


def read_options():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=pathlib.Path, help="The file to interpret.", nargs="?")

    return parser.parse_args()


def main():
    options = read_options()

    if options.source is None:
        source = read_until_char('!')
    else:
        with open(options.source, "r") as fp:
            source = fp.read()

    try:
        interpret(source)
    except InterpreterError as err:
        sys.stderr.write("fatal: %s\n" % str(err))
        sys.exit(1)


if __name__ == '__main__':
    main()

