# MiniDecaf Python Framework
This is a compiler developed in Python. It compiles a new language MiniDecaf, a subset of C language into assamble language of RISC-V.

## dependencies

- **Python >= 3.9**
- python libraries in requirements.txt, including ply and argparse.
- RISC-V operating environment (see lab guide)

## run

````
python3 main.py --input <testcase.c> [--riscv/--tac/--parse]
````

The meaning of each parameter is as follows:

| Parameters | Meaning |
| --- | --- |
| `input` | Minidecaf code location for input |
| `riscv` | output RISC-V assembly |
| `tac` | output three-address code |
| `parse` | output abstract syntax tree |

## code structure

````
minidecaf/
    frontend/ front end (and middle end)
        ast/ syntax tree definition
        lexer/ lexical analysis
        parser/ parsing
        type/ type definition
        symbol/ symbol definition
        scope/ scope definition
        typecheck/ semantic analysis (symbol table construction, type checking)
        tacgen/ intermediate code TAC generation
    backend/ backend
        dataflow/ data flow analysis
        reg/register allocation
        riscv/ RISC-V platform related
    utils/ low-level classes
        label/ label definition
        tac/TAC definitions and base classes
````