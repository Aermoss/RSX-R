import llvmlite.ir as ir
import llvmlite.binding as llvm

from ctypes import CFUNCTYPE, c_int32, c_int8

import os, sys, subprocess, tempfile

sys.dont_write_bytecode = True

from rsxpy import *

try:
    import rsxr.compiler as compiler

except ImportError:
    sys.path.append(os.getcwd())

    import rsxr.compiler as compiler

def main():
    argv = sys.argv
    main_dir = os.getcwd()
    mode = "build"
    flag = "default"
    capture = None
    output = None
    getmod = False
    files = []
    libs = []
    lib_dirs = []

    for i in argv[1:]:
        if i[0] == "-":
            i = i[1:]
            
            if i in ["c", "S", "emit-llvm"]:
                flag = i
                tools.error("not implemented", "rsxr")

            elif i == "o":
                capture = "output"

            elif i.split("=")[0] == "getmod":
                if i.split("=")[1] == "true": getmod = True
                elif i.split("=")[1] == "false": getmod = False
                else: tools.error("unknown value: '" + i.split("=")[1] + "'")
            
            elif i[0] == "l":
                if i[1:] == "": capture = "lib"
                else: libs.append(i[1:])

            elif i[0] == "L":
                if i[1:] == "": capture = "lib_dir"
                else: lib_dirs.append(i[1:])

            else:
                tools.error(f"unknown argument '{i}'", "rsxr")

        elif i in ["run", "build"]:
            mode = i

        else:
            if capture != None:
                if capture == "output": output = i
                elif capture == "lib": libs.append(i)
                elif capture == "lib_dir": lib_dirs.append(i)
                else: tools.error("unknown capture type", "rsxr")
                capture = None

            else: files.append(i)

    if len(files) == 0: tools.error("no input files", "rsxr")
    if len(libs) > 0: libs = " -l".join([""] + libs)[1:].split(" ")
    if len(lib_dirs) > 0: lib_dirs = " -L".join([""] + lib_dirs)[1:].split(" ")

    file = None

    for i in files:
        if os.path.splitext(i)[1] == ".rsxr":
            if file != None: tools.error("multiple source files are not supported", "rsxr")
            else: file = i
        else: tools.error("invalid file extension", "rsxr")

    if file == None: tools.error("no input files", "rsxr")
    file_name = os.path.split(os.path.splitext(file)[0])[1]

    context = compiler.Context(file)
    module = compiler.compiler(core.parser(core.lexer(tools.read_file(file), file), file), context)

    llvm.initialize()
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()

    target = llvm.Target.from_default_triple()
    target_machine = target.create_target_machine()
    module.triple = target_machine.triple

    if getmod: print(str(module))

    if mode == "build":
        os.chdir(tempfile.gettempdir())
        with open(f"{file_name}.llvm", "w") as file: file.write(str(module))
        subprocess.run(["opt", f"{file_name}.llvm", "-o", f"{file_name}.bc"])
        os.remove(f"{file_name}.llvm")
        subprocess.run(["llvm-dis", f"{file_name}.bc", "-o", f"{file_name}.llvm"])
        os.remove(f"{file_name}.bc")
        subprocess.run(["llc", "-filetype=obj", f"{file_name}.llvm", "-o", f"{file_name}.o"])
        os.remove(f"{file_name}.llvm")
        os.chdir(os.path.split(__file__)[0] + "/obj")
        subprocess.run(["g++", os.path.split(__file__)[0] + "/asm/__chkstk.s", "-c", "-o", "__chkstk.o"])
        os.chdir(main_dir)
        subprocess.run(["g++", tempfile.gettempdir() + f"/{file_name}.o", os.path.split(__file__)[0] + "/obj/__chkstk.o", "-o", output, "-static-libgcc", "-static-libstdc++"] + lib_dirs + libs)
        os.remove(tempfile.gettempdir() + f"/{file_name}.o")
        with open(output, "rb") as file: data = file.read()
        os.remove(output)
        with open(output, "wb") as file: file.write(data)

    elif mode == "run":
        if flag != "default": tools.error(f"unknown argument '{flag}'", "rsxr")
        if output != None: tools.error(f"unknown argument 'o'", "rsxr")
        llvm_module = llvm.parse_assembly(str(module))
        target_machine = llvm.Target.from_default_triple().create_target_machine()

        with llvm.create_mcjit_compiler(llvm_module, target_machine) as engine:
            engine.finalize_object()
            main_func = CFUNCTYPE(c_int32)(engine.get_function_address("main"))
            print("program exit with code", main_func())
    
    else:
        tools.error(f"unknown mode '{mode}'", "rsxr")

if __name__ == "__main__":
    sys.exit(main())