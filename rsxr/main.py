import llvmlite.ir as ir
import llvmlite.binding as llvm

from ctypes import *

import os, sys, subprocess, tempfile, pickle, hashlib

sys.dont_write_bytecode = True

from rsxpy import *

try:
    import rsxr.compiler as compiler

except ImportError:
    sys.path.append(os.getcwd())
    sys.path.append(os.path.split(os.getcwd())[0])

    import rsxr.compiler as compiler

def main():
    argv = sys.argv
    version = "0.0.2"
    main_dir = os.getcwd()
    mode = "build"
    flag = "default"
    capture = None
    output = None
    bytecode = True
    optimize = True
    gettok = False
    getmod = False
    getmod_pure = False
    getcmd = False
    files = []
    libs = []
    lib_dirs = []
    inc_dirs = [".", os.path.split(__file__)[0] + "/include"]

    for i in argv[1:]:
        if i[0] == "-":
            i = i[1:]
            
            if i in ["c", "S", "emit-llvm"]:
                flag = i
                tools.error("not implemented", "rsxr")

            elif i == "o":
                capture = "output"

            elif i.split("=")[0] == "bytecode":
                if i.split("=")[1] == "true": bytecode = True
                elif i.split("=")[1] == "false": bytecode = False
                else: tools.error("unknown value: '" + i.split("=")[1] + "'")

            elif i.split("=")[0] == "optimize":
                if i.split("=")[1] == "true": optimize = True
                elif i.split("=")[1] == "false": optimize = False
                else: tools.error("unknown value: '" + i.split("=")[1] + "'")

            elif i.split("=")[0] == "gettok":
                if i.split("=")[1] == "true": gettok = True
                elif i.split("=")[1] == "false": gettok = False
                else: tools.error("unknown value: '" + i.split("=")[1] + "'")

            elif i.split("=")[0] == "getmod":
                if i.split("=")[1] == "true": getmod = True
                elif i.split("=")[1] == "false": getmod = False
                else: tools.error("unknown value: '" + i.split("=")[1] + "'")

            elif i.split("=")[0] == "getmod_pure":
                if i.split("=")[1] == "true": getmod_pure = True
                elif i.split("=")[1] == "false": getmod_pure = False
                else: tools.error("unknown value: '" + i.split("=")[1] + "'")

            elif i.split("=")[0] == "getcmd":
                if i.split("=")[1] == "true": getcmd = True
                elif i.split("=")[1] == "false": getcmd = False
                else: tools.error("unknown value: '" + i.split("=")[1] + "'")
            
            elif i[0] == "l":
                if i[1:] == "": capture = "lib"
                else: libs.append(i[1:])

            elif i[0] == "L":
                if i[1:] == "": capture = "lib_dir"
                else: lib_dirs.append(i[1:])

            elif i[0] == "I":
                if i[1:] == "": capture = "inc_dir"
                else: inc_dirs.append(i[1:])

            else:
                tools.error(f"unknown argument '{i}'", "rsxr")

        elif i in ["run", "build"]:
            mode = i

        else:
            if capture != None:
                if capture == "output": output = i
                elif capture == "lib": libs.append(i)
                elif capture == "lib_dir": lib_dirs.append(i)
                elif capture == "inc_dir": inc_dirs.append(i)
                else: tools.error("unknown capture type", "rsxr")
                capture = None

            else: files.append(i)

    if len(files) == 0: tools.error("no input files", "rsxr")
    if len(libs) > 0: libs = " -l".join([""] + libs)[1:].split(" ")
    if len(lib_dirs) > 0: lib_dirs = " -L".join([""] + lib_dirs)[1:].split(" ")

    file = None

    for i in files:
        if os.path.splitext(i)[1] in [".rsxr", ".rsxrc"]:
            if file != None: tools.error("multiple source files are not supported", "rsxr")
            else: file = i
        else: tools.error("invalid file extension", "rsxr")

    if file == None: tools.error("no input files", "rsxr")
    file_name = os.path.split(os.path.splitext(file)[0])[1]
    ast = None

    if os.path.splitext(file)[1] == ".rsxrc":
        with open(os.path.splitext(file)[0] + ".rsxrc", "rb") as f:
            content = pickle.loads(f.read())

            if "version" not in content:
                tools.error("broken bytecode file", file)

            if content["version"] != version:
                tools.error("bytecode version didn't match [bytecode: " + content["version"] + f", current: {version}]", file)

            ast = content["ast"]

    else:
        file_content = tools.read_file(file)

        if os.path.splitext(file)[0] + ".rsxrc" in os.listdir() and bytecode:
            with open(os.path.splitext(file)[0] + ".rsxrc", "rb") as f:
                content = tools.load_bytecode(f.read())

                if "version" in content:
                    if content["version"] == version:
                        if content["file_content"] == hashlib.sha256(file_content.encode()).digest():
                            ast = content["ast"]

        if ast == None:
            tokens = core.lexer(file_content, file)
            if gettok: print(tokens)
            ast = core.parser(tokens, file)

            if bytecode:
                with open(os.path.splitext(file)[0] + ".rsxrc", "wb") as f: f.write(tools.dump_bytecode(ast, file_content, version))

    context = compiler.Context(file)
    context.include_folders = inc_dirs
    module = compiler.compiler(ast, context)

    llvm.initialize()
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()

    target = llvm.Target.from_default_triple()
    target_machine = target.create_target_machine()
    module.triple = target_machine.triple

    if getmod_pure: print(str(module))

    if mode == "build":
        if output == None: output = file_name + ".exe" if sys.platform == "win32" else ""
        os.chdir(tempfile.gettempdir())
        with open(f"{file_name}.llvm", "w") as file: file.write(str(module))
        if optimize:
            subprocess.run(["opt", f"{file_name}.llvm", "-o", f"{file_name}.bc"])
            os.remove(f"{file_name}.llvm")
            subprocess.run(["llvm-dis", f"{file_name}.bc", "-o", f"{file_name}.llvm"])
            os.remove(f"{file_name}.bc")
        if getmod: print(open(f"{file_name}.llvm", "r").read())
        subprocess.run(["llc", "-filetype=obj", f"{file_name}.llvm", "-o", f"{file_name}.o"])
        os.remove(f"{file_name}.llvm")
        subprocess.run(["g++", os.path.split(__file__)[0] + "/asm/__chkstk.s", "-c", "-o", "__chkstk.o"])
        os.chdir(main_dir)
        code = ["g++", tempfile.gettempdir() + f"/{file_name}.o", tempfile.gettempdir() + "/__chkstk.o", "-o", output, "-static-libgcc", "-static-libstdc++"] + lib_dirs + libs
        if getcmd: print(" ".join(code))
        subprocess.run(code)
        os.remove(tempfile.gettempdir() + f"/{file_name}.o")
        os.remove(tempfile.gettempdir() + "/__chkstk.o")

    elif mode == "run":
        if flag != "default": tools.error(f"unknown argument '{flag}'", "rsxr")
        if output != None: tools.error(f"unknown argument 'o'", "rsxr")
        if getcmd: tools.error(f"unknown argument 'getcmd'", "rsxr")
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