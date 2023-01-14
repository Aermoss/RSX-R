import llvmlite.ir as ir
import llvmlite.binding as llvm

from rsxpy import *

import os, sys, hashlib

module = ir.Module()

class Context:
    def __init__(self, file):
        self.reset(file)

    def reset(self, file):
        self.version = None
        self.scope = {}
        self.current_scope = "global"
        self.included = []
        self.include_folders = []
        self.main_file = file
        self.file = file
        self.include_cache = {}
        self.parent_scopes = []
        self.prevent_str = False
        self.ptr_state = False
        self.namespaces = []
        self.unique = 0

    def update(self):
        ...

    def set_scope(self, scope):
        self.current_scope = scope

    def get_scope(self):
        return self.current_scope

    def add_scope(self, scope):
        index = 0
        name = scope

        while name in self.scope:
            name = scope + ">" + str(index)
            index += 1
        
        self.scope[name] = {}
        return name

    def delete_scope(self, scope, builder, pass_free = False):
        if scope not in self.scope: return

        if not pass_free:
            for i in self.scope[scope]:
                if "stack" in self.scope[scope][i] and self.scope[scope][i]["stack"] == True: continue
                if self.scope[scope][i]["type"] in ["var", "str", "arr"]:
                    if self.scope[scope][i]["type"] == "var" and self.scope[scope][i]["ptr_tracked"]: continue
                    ptr = builder.bitcast(self.scope[scope][i]["ptr"], ir.IntType(8).as_pointer())
                    builder.call(self.get("free")["func"], [ptr])

        del self.scope[scope]

    def add_parent_scope(self, scope):
        self.parent_scopes.append(scope)

    def rem_parent_scope(self, scope):
        self.parent_scopes.remove(scope)

    def get_current_elements(self):
        tmp = self.scope["global"].copy()

        if self.current_scope != "global":
            tmp.update(self.scope[self.current_scope])

        parent_scopes = self.parent_scopes.copy()
        parent_scopes.reverse()

        for i in parent_scopes:
            tmp.update(self.scope[i])

        return tmp

    def is_exists(self, key):
        tmp = self.scope["global"].copy()

        if self.current_scope != "global":
            tmp.update(self.scope[self.current_scope])

        for i in self.parent_scopes:
            tmp.update(self.scope[i])

        return key in tmp

    def append_namespace(self, namespace):
        self.namespaces.append(namespace)

    def pop_namespace(self):
        self.namespaces.pop(len(self.namespaces) - 1)

    def set(self, key, value, force = False):
        if self.current_scope == "global":
            key = "::".join(self.namespaces + [key])

        if value["type"] == "str" and self.prevent_str: return
        if force:
            self.scope[self.current_scope][key] = value
            return

        tmp = self.parent_scopes.copy()
        tmp.reverse()

        if key in self.scope[self.current_scope]:
            self.scope[self.current_scope][key] = value
            return

        elif key in self.scope["global"]:
            self.scope["global"][key] = value
            return
        
        for i in tmp:
            if key in self.scope[i]:
                self.scope[i][key] = value
                return

        self.scope[self.current_scope][key] = value

    def get(self, key):
        if self.is_exists(key):
            if self.current_scope != "global":
                if key in self.scope[self.current_scope]:
                    return self.scope[self.current_scope][key]

            for i in self.parent_scopes[::-1]:
                if key in self.scope[i]:
                    return self.scope[i][key]

            return self.scope["global"][key]

        else:
            tools.error(f"'{key}' was not declared in this scope", self.file)

    def delete(self, key, builder):
        if self.is_exists(key):
            if self.current_scope != "global":
                if key in self.scope[self.current_scope]:
                    if self.scope[self.current_scope][key]["type"] in ["var", "str"]:
                        ptr = builder.bitcast(self.scope[self.current_scope][key]["ptr"], ir.IntType(8).as_pointer())
                        builder.call(self.get("free")["func"], [ptr])
                    del self.scope[self.current_scope][key]
                    return

            for i in self.parent_scopes:
                if key in self.scope[i]:
                    if self.scope[i][key]["type"] in ["var", "str"]:
                        ptr = builder.bitcast(self.scope[i][key]["ptr"], ir.IntType(8).as_pointer())
                        builder.call(self.get("free")["func"], [ptr])
                    del self.scope[i][key]
                    return

            if self.scope["global"][key]["type"] in ["var", "str"]:
                ptr = builder.bitcast(self.scope["global"][key]["ptr"], ir.IntType(8).as_pointer())
                builder.call(self.get("free")["func"], [ptr])
            del self.scope["global"][key]

        else:
            tools.error(f"'{key}' was not declared in this scope", self.file)

    def is_main_file(self):
        return self.main_file == self.file

    def is_in_function(self):
        return self.current_scope != "global"

    def is_included(self, key):
        return key in self.included

    def prepare_to_include(self, file):
        self.include_cache[len(self.include_cache)] = {"file": self.file}
        self.file = file

    def end_include(self):
        self.file = self.include_cache[len(self.include_cache) - 1]["file"]
        self.include_cache.pop(len(self.include_cache) - 1)

    def is_base(self):
        return self.current_scope == "global"

    def get_sizeof_t(self, type):
        if type == ir.IntType(32): return 4
        elif type == ir.FloatType(): return 4
        elif type == ir.DoubleType(): return 8
        elif type == ir.IntType(1): return 1
        elif type == ir.IntType(8): return 1
        elif type == ir.IntType(8).as_pointer(): return 1
        elif type.is_pointer and isinstance(type.pointee, ir.ArrayType):
            return len(type.pointee) * self.get_sizeof_t(type.pointee.element)
        elif isinstance(type, ir.ArrayType): return len(type) * self.get_sizeof_t(type.element)
        else: tools.error("invalid type", "rsxr")

    def get_sizeof(self, val):
        return self.get_sizeof_t(val.type)

    def get_alignof_t(self, type):
        if type == ir.IntType(32): return 4
        elif type == ir.FloatType(): return 4
        elif type == ir.DoubleType(): return 8
        elif type == ir.IntType(1): return 1
        elif type == ir.IntType(8): return 1
        elif type == ir.IntType(8).as_pointer(): return 1
        elif type.is_pointer and isinstance(type.pointee, ir.ArrayType):
            return self.get_sizeof_t(type.pointee.element)
        elif isinstance(type, ir.ArrayType): return self.get_sizeof_t(type.element)
        else: tools.error("invalid type", "rsxr")

    def get_alignof(self, val):
        return self.get_alignof_t(val.type)

    def get_unique_name(self):
        self.unique += 1
        return f"unique>{self.unique - 1}"

    def malloc(self, builder, size, align):
        return builder.call(self.get("malloc")["func"], [ir.Constant(ir.IntType(32), size), ir.Constant(ir.IntType(32), align)])
    
    def free(self, builder, ptr):
        return builder.call(self.get("free")["func"], [ptr])

def compiler(ast, context: Context, builder = None):
    pass_list = []

    if context.scope == {}:
        context.scope = {
            "global": {
                "sizeof": {"type": "compiletimefunc"},
                "system": {"type": "func", "func": ir.Function(module, ir.FunctionType(ir.IntType(32), [], var_arg = True), name = "system"), "builder": None},
                "malloc": {"type": "func", "func": ir.Function(module, ir.FunctionType(ir.IntType(8).as_pointer(), [ir.IntType(32), ir.IntType(32)]), name = "_aligned_malloc"), "builder": None},
                "free": {"type": "func", "func": ir.Function(module, ir.FunctionType(ir.VoidType(), [ir.IntType(8).as_pointer()]), name = "_aligned_free"), "builder": None}
            }
        }

    for index, i in enumerate(ast):
        if i["type"] == "func":
            if context.current_scope != "global":
                tools.error("a function-definition is not allowed here before", context.file)

            if context.is_exists(i["name"]) and (context.get(i["name"])["type"] == "compiletimefunc" or context.get(i["name"])["args"] != i["args"] or context.get(i["name"])["ast"] != None):
                tools.error("can't overload a function: '" + i["name"] + "'", context.file)

            if i["return_type"] not in ["VOID", "FLOAT", "INT", "DOUBLE", "CHAR", "STRING", "BOOL", "ARRAY"]:
                tools.error("unknown type for a function: '" + i["return_type"].lower() + "'", context.file)

            args = []

            for j in i["args"]:
                args.append(compiler([{"type": i["args"][j]}], context, builder))

            tmp_builder = None
            if context.is_exists(i["name"]) and context.get(i["name"])["args"] == i["args"] and context.get(i["name"])["ast"] == None: func = context.get(i["name"])["func"]
            else: func = ir.Function(module, ir.FunctionType(compiler([{"type": i["return_type"]}], context, builder), args, var_arg = i["var_arg"]), name = i["name"])
            if i["ast"] != None: tmp_builder = ir.IRBuilder(func.append_basic_block("entry"))
            context.set(i["name"], {"type": "func", "ast": i["ast"], "func": func, "builder": tmp_builder, "args": i["args"]})
            if i["ast"] != None:
                tmp_scope = context.get_scope()
                context.add_scope(i["name"])
                context.set_scope(i["name"])

                for _index, j in enumerate(i["args"]):
                    ptr = tmp_builder.alloca(func.args[_index].type)
                    tmp_builder.store(func.args[_index], ptr)
                    context.set(j, {"type": "var", "value_type": i["args"][j], "ptr": ptr, "stack": True})

                compiler(i["ast"], context, tmp_builder)
                context.delete_scope(i["name"], tmp_builder, True)
                context.set_scope(tmp_scope)

        elif i["type"] == "include":
            for lib in i["libs"]:
                if context.is_included(lib) and not context.is_compiled():
                    tools.warning("trying to include '" + lib + "' twice", context.file)
                    continue

                context.included.append(lib)
                name, ext = os.path.splitext(lib)
                file_path = None

                if ext == ".rsxrh":
                    for j in context.include_folders:
                        if os.path.exists(j + "/" + lib):
                            file_path = j + "/" + lib
                            break

                else:
                    for j in context.include_folders:
                        if os.path.exists(j + "/" + lib + "/" + "init.rsxrh"):
                            file_path = j + "/" + lib + "/" + "init.rsxrh"
                            break

                if file_path == None:
                    tools.error("'" + lib + "'" + " " + "was not found", context.file)

                file_content = open(file_path, "r").read()
                ast = None

                if os.path.splitext(os.path.split(file_path)[1])[0] + ".rsxrc" in os.listdir(os.path.split(file_path)[0]):
                    with open(os.path.splitext(file_path)[0] + ".rsxrc", "rb") as file:
                        content = tools.load_bytecode(file.read())

                        if "version" in content:
                            if content["version"] == context.version:
                                if content["file_content"] == hashlib.sha256(file_content.encode()).digest():
                                    ast = content["ast"]

                if ast is None:
                    ast = core.parser(core.lexer(tools.read_file(file_path), file_path), file_path)

                    with open(os.path.splitext(file_path)[0] + ".rsxrc", "wb") as file:
                        file.write(tools.dump_bytecode(ast, [], file_content))

                context.prepare_to_include(file_path)
                tmp_parent_scopes = context.parent_scopes
                context.parent_scopes = []
                if i["namespace"]: context.append_namespace(lib if i["special_namespace"] == None else i["special_namespace"])
                compiler(ast, context, builder)
                if i["namespace"]: context.pop_namespace()
                context.parent_scopes = tmp_parent_scopes
                context.end_include()
                if i["names"] != None: tools.error("include names are not implemented", context.file)

        elif i["type"] == "namespace":
            if context.get_scope() != "global":
                tools.error("invalid use of 'namespace'", context.file)

            context.append_namespace(i["name"])
            compiler(i["ast"], context, builder)
            context.pop_namespace()

        elif i["type"] == "using namespace":
            if context.get_scope() != "global":
                tools.error("invalid use of 'using namespace'", context.file)

            for j in context.scope["global"].copy():
                if j.startswith(i["name"]):
                    name = j[len(i["name"]):]
                    if name.startswith("::"): name = name[2:]
                    context.set(name, context.scope["global"][j])
                    del context.scope["global"][j]

        elif i["type"] == "return":
            if i["value"] != {"type": "NULL", "value": "NULL"}:
                val = compiler([i["value"]], context, builder)

                if val.type.is_pointer and isinstance(val.type.pointee, ir.ArrayType):
                    val = builder.gep(val, [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 0)])

            context.delete_scope(context.current_scope, builder)

            if i["value"] == {"type": "NULL", "value": "NULL"}:
                return builder.ret_void()

            return builder.ret(val)
        
        elif i["type"] == "neg":
            if "type" in i["value"] and i["value"]["type"] in ["INT", "FLOAT", "DOUBLE"]:
                return compiler([{"type": i["value"]["type"], "value": "-" + i["value"]["value"]}], context, builder)

            else:
                value = compiler([i["value"]], context, builder)
                if value.type.is_pointer and not isinstance(value.type.pointee, ir.ArrayType):
                    value = builder.load(value)
                if value.type == ir.IntType(32): return builder.neg(value)
                elif value.type == ir.FloatType(): return builder.fneg(value)
                else: tools.error("invalid type for 'neg' operator")

        elif i["type"] in ["notequals", "equalsequals", "less", "greater", "lessequals", "greaterequals"]:
            operator = i["type"].replace("notequals", "!=").replace("equalsequals", "==").replace("lessequals", "<=").replace("greaterequals", ">=").replace("less", "<").replace("greater", ">")
            left, right = compiler([i["left"]], context, builder), compiler([i["right"]], context, builder)
            if left.type.is_pointer and not isinstance(left.type.pointee, ir.ArrayType):
                left = builder.load(left)
            if right.type.is_pointer and not isinstance(right.type.pointee, ir.ArrayType):
                right = builder.load(right)
            if not (left.type in [ir.IntType(32), ir.FloatType()] and right.type in [ir.IntType(32), ir.FloatType()]): tools.error(f"invalid type for '{operator}' operator")
            if left.type == ir.FloatType() or right.type == ir.FloatType():
                if left.type != ir.FloatType(): left = builder.sitofp(left, ir.FloatType())
                if right.type != ir.FloatType(): right = builder.sitofp(right, ir.FloatType())
                return builder.fcmp_ordered(operator, left, right)

            return builder.icmp_signed(operator, left, right)

        elif i["type"] == "delete":
            context.delete(i["value"], builder)

        elif i["type"] == "for":
            body_block = builder.append_basic_block()
            end_block = builder.append_basic_block()

            cur = context.add_scope("__for__")
            tmp = context.get_scope()
            context.set_scope(cur)
            context.add_parent_scope(tmp)
            compiler(i["init"], context, builder)
            builder.cbranch(compiler([i["condition"]], context, builder), body_block, end_block)

            builder.position_at_end(body_block)
            tmp_scp = context.add_scope("__for_inner__")
            context.add_parent_scope(cur)
            context.set_scope(tmp_scp)
            compiler(i["ast"], context, builder)
            context.delete_scope(tmp_scp, builder)
            context.rem_parent_scope(cur)
            context.set_scope(cur)

            if not builder.block.is_terminated:
                compiler(i["update"], context, builder)
                builder.cbranch(compiler([i["condition"]], context, builder), body_block, end_block)

            builder.position_at_end(end_block)
            context.rem_parent_scope(tmp)
            context.delete_scope(cur, builder)
            context.set_scope(tmp)

        elif i["type"] == "do":
            body_block = builder.append_basic_block()
            end_block = builder.append_basic_block()
            builder.branch(body_block)
            builder.position_at_end(body_block)
            cur = context.add_scope("__do__")
            tmp = context.get_scope()
            context.add_parent_scope(tmp)
            context.set_scope(cur)
            compiler(i["ast"], context, builder)
            context.delete_scope(cur, builder)
            context.set_scope(tmp)
            context.rem_parent_scope(tmp)
            if not builder.block.is_terminated: builder.branch(end_block)
            builder.position_at_end(end_block)

        elif i["type"] == "do while":
            body_block = builder.append_basic_block()
            end_block = builder.append_basic_block()
            builder.branch(body_block)
            builder.position_at_end(body_block)
            cur = context.add_scope("__do_while__")
            tmp = context.get_scope()
            context.add_parent_scope(tmp)
            context.set_scope(cur)
            compiler(i["ast"], context, builder)
            context.delete_scope(cur, builder)
            context.set_scope(tmp)
            context.rem_parent_scope(tmp)
            if not builder.block.is_terminated: builder.cbranch(compiler([i["condition"]], context, builder), body_block, end_block)
            builder.position_at_end(end_block)

        elif i["type"] == "while":
            body_block = builder.append_basic_block()
            end_block = builder.append_basic_block()
            builder.cbranch(compiler([i["condition"]], context, builder), body_block, end_block)
            builder.position_at_end(body_block)
            cur = context.add_scope("__while__")
            tmp = context.get_scope()
            context.add_parent_scope(tmp)
            context.set_scope(cur)
            compiler(i["ast"], context, builder)
            context.delete_scope(cur, builder)
            context.set_scope(tmp)
            context.rem_parent_scope(tmp)
            if not builder.block.is_terminated: builder.cbranch(compiler([i["condition"]], context, builder), body_block, end_block)
            builder.position_at_end(end_block)

        elif i["type"] == "if":
            temp_pos = 1
            temp_ast = [ast[index]]

            while len(ast) - 1 >= index + temp_pos and ast[index + temp_pos]["type"] in ["else", "else if"]:
                temp_ast.append(ast[index + temp_pos])
                pass_list.append(index + temp_pos)
                if ast[index + temp_pos]["type"] == "else": break
                else: temp_pos += 1

            endif = None

            for index, j in enumerate(temp_ast):
                if j["type"] == "if":
                    intermediate_check = builder.append_basic_block()
                    if_block = builder.append_basic_block()
                    builder.cbranch(compiler([j["condition"]], context, builder), if_block, intermediate_check)
                    builder.position_at_end(if_block)
                    cur = context.add_scope("__if__")
                    tmp = context.get_scope()
                    context.add_parent_scope(tmp)
                    context.set_scope(cur)
                    compiler(j["ast"], context, builder)
                    context.set_scope(tmp)
                    context.delete_scope(cur, builder)
                    context.rem_parent_scope(tmp)
                    if not builder.block.is_terminated:
                        if len(temp_ast) == index + 1: endif = intermediate_check
                        elif endif == None: endif = builder.append_basic_block()
                        builder.branch(endif)
                    builder.position_at_end(intermediate_check)

                if j["type"] == "else if":
                    intermediate_check = builder.append_basic_block()
                    else_if_block = builder.append_basic_block()
                    builder.cbranch(compiler([j["condition"]], context, builder), else_if_block, intermediate_check)
                    builder.position_at_end(else_if_block)
                    cur = context.add_scope("__else_if__")
                    tmp = context.get_scope()
                    context.add_parent_scope(tmp)
                    context.set_scope(cur)
                    compiler(j["ast"], context, builder)
                    context.set_scope(tmp)
                    context.delete_scope(cur, builder)
                    context.rem_parent_scope(tmp)
                    if not builder.block.is_terminated:
                        if len(temp_ast) == index + 1: endif = intermediate_check
                        if endif == None: endif = builder.append_basic_block()
                        builder.branch(endif)
                    builder.position_at_end(intermediate_check)

                if j["type"] == "else":
                    cur = context.add_scope("__else__")
                    tmp = context.get_scope()
                    context.add_parent_scope(tmp)
                    context.set_scope(cur)
                    compiler(j["ast"], context, builder)
                    context.set_scope(tmp)
                    context.delete_scope(cur, builder)
                    context.rem_parent_scope(tmp)
                    if not builder.block.is_terminated:
                        if endif == None: endif = builder.append_basic_block()
                        builder.branch(endif)
            
            if endif != None: builder.position_at_end(endif)

        elif i["type"] == "else if":
            if index in pass_list:
                pass_list.remove(index)
                continue

            tools.error("expected 'if' before 'else if'", context.file)

        elif i["type"] == "else":
            if index in pass_list:
                pass_list.remove(index)
                continue

            tools.error("expected 'if' before 'else'", context.file)

        elif i["type"] == "var":
            if not context.is_exists(i["name"]):
                if i["value_type"] == None: tools.error("'" + i["name"] + "' was not declared in this scope", context.file)
                if i["value"] == None: i["value"] = {"type": i["value_type"], "array_type": i["array_type"], "value": i["value"]}
                val = compiler([i["value"]], context, builder)
                if val.type != compiler([{"type": i["value_type"], "array_type": i["array_type"]}], context, builder) and not val.type.is_pointer: tools.error("type mismatch for '" + i["name"] + "'", context.file)
                global_var = False
                ptr_tracked = False

                if not val.type.is_pointer:
                    if builder == None:
                        ptr = ir.GlobalVariable(module, val.type, i["name"])
                        ptr.initializer = val
                        global_var = True
                    
                    else:
                        ptr = context.malloc(builder, context.get_sizeof(val), context.get_alignof(val))
                        ptr = builder.bitcast(ptr, val.type.as_pointer())
                        builder.store(val, ptr, align = context.get_alignof(val))

                else:
                    ptr_tracked = True
                    ptr = val

                context.set(i["name"], {"type": "var", "ptr_tracked": ptr_tracked, "global": global_var, "array_type": i["array_type"], "value_type": i["value_type"], "ptr": ptr})

            else:
                if i["value_type"] != None: tools.error("redefinition of '" + i["name"] + "'", context.file)
                val = compiler([i["value"]], context, builder)
                if val.type != compiler([{"type": context.get(i["name"])["value_type"], "array_type": context.get(i["name"])["array_type"]}], context, builder) and not val.type.is_pointer: tools.error("type mismatch for '" + i["name"] + "'", context.file)
                builder.store(val, context.get(i["name"])["ptr"], align = context.get_alignof(val))

        elif i["type"] in ["add", "sub", "mul", "div", "mod"]:
            left, right = compiler([i["left"]], context, builder), compiler([i["right"]], context, builder)
            if left.type.is_pointer and not isinstance(left.type.pointee, ir.ArrayType):
                left = builder.load(left)
            if right.type.is_pointer and not isinstance(right.type.pointee, ir.ArrayType):
                right = builder.load(right)
            if not (left.type in [ir.IntType(32), ir.FloatType(), ir.DoubleType()] and right.type in [ir.IntType(32), ir.FloatType(), ir.DoubleType()]): tools.error(f"invalid type for '" + i["type"] + "' operator", context.file)
            if left.type == ir.DoubleType() or right.type == ir.DoubleType():
                if left.type != ir.DoubleType(): left = builder.sitofp(left, ir.DoubleType())
                if right.type != ir.DoubleType(): right = builder.sitofp(right, ir.DoubleType())
                return {"add": builder.fadd, "sub": builder.fsub, "mul": builder.fmul, "div": builder.fdiv, "mod": builder.frem}[i["type"]](left, right)
            elif left.type == ir.FloatType() or right.type == ir.FloatType():
                if left.type != ir.FloatType(): left = builder.sitofp(left, ir.FloatType())
                if right.type != ir.FloatType(): right = builder.sitofp(right, ir.FloatType())
                return {"add": builder.fadd, "sub": builder.fsub, "mul": builder.fmul, "div": builder.fdiv, "mod": builder.frem}[i["type"]](left, right)
            return {"add": builder.add, "sub": builder.sub, "mul": builder.mul, "div": builder.sdiv, "mod": builder.srem}[i["type"]](left, right)
        
        elif i["type"] == "not":
            value = compiler([i["value"]], context, builder)
            if value.type.is_pointer and not isinstance(value.type.pointee, ir.ArrayType):
                value = builder.load(value)
            if value.type not in [ir.IntType(1), ir.IntType(32)]: tools.error("invalid type for '" + i["type"] + "' operator", context.file)
            if value.type == ir.IntType(32): value = builder.trunc(value, ir.IntType(1))
            return builder.not_(value)

        elif i["type"] in ["or", "and"]:
            left, right = compiler([i["left"]], context, builder), compiler([i["right"]], context, builder)
            if left.type not in [ir.IntType(1)] or right.type not in [ir.IntType(1)]: tools.error("invalid type for '" + i["type"] + "' operator", context.file)
            return {"or": builder.or_, "and": builder.and_}[i["type"]](left, right)

        elif i["type"] == "bitwise not":
            value = compiler([i["value"]], context, builder)
            if value.type not in [ir.IntType(1), ir.IntType(32)]: tools.error("invalid type for '" + i["type"] + "' operator", context.file)
            return builder.not_(value)

        elif i["type"] in ["bitwise or", "bitwise xor", "bitwise and"]:
            left, right = compiler([i["left"]], context, builder), compiler([i["right"]], context, builder)
            if left.type not in [ir.IntType(32), ir.IntType(1)] or right.type not in [ir.IntType(32), ir.IntType(1)]: tools.error("invalid type for '" + i["type"] + "' operator", context.file)
            return {"bitwise or": builder.or_, "bitwise xor": builder.xor, "bitwise and": builder.and_}[i["type"]](left, right)

        elif i["type"] == "cast":
            value = compiler([i["value"]], context, builder)
            if value.type.is_pointer and not isinstance(value.type.pointee, ir.ArrayType):
                value = builder.load(value)

            if i["cast_type"] == "INT":
                if value.type == ir.IntType(32): return value
                elif value.type == ir.FloatType(): return builder.sitofp(value, ir.FloatType())
                elif value.type == ir.DoubleType(): return builder.sitofp(value, ir.DoubleType())
                else: tools.error("invalid type for integer casting")

            elif i["cast_type"] == "FLOAT":
                if value.type == ir.IntType(32): return builder.fptosi(value, ir.IntType(32))
                elif value.type == ir.FloatType(): return value
                elif value.type == ir.DoubleType(): return value
                else: tools.error("invalid type for float casting")

            elif i["cast_type"] == "DOUBLE":
                if value.type == ir.IntType(32): return builder.fptosi(value, ir.IntType(32))
                elif value.type == ir.FloatType(): return value
                elif value.type == ir.DoubleType(): return value
                else: tools.error("invalid type for float casting")

            else:
                tools.error("invalid cast type: '" + i["cast_type"] + "'")

        elif i["type"] == "call":
            if i["value"]["value"] == "sizeof":
                if len(i["args"]) != 1:
                    tools.error("invalid argument count", context.file)

                if i["args"][0]["type"] != "IDENTIFIER":
                    tools.error("invalid argument type", context.file)

                value = context.get(i["args"][0]["value"])["ptr"]
                if value.type.is_pointer and not isinstance(value.type.pointee, ir.ArrayType):
                    value = builder.load(value)
                res = ir.Constant(ir.IntType(32), int(context.get_sizeof(value) / 8))
                if len(ast) == 1: return res
                continue

            func = context.get(compiler([i["value"]], context, builder))
            args = []

            for j in i["args"]:
                if func["builder"] != None: ...
                val = compiler([j], context, builder)
                if val.type.is_pointer and isinstance(val.type.pointee, ir.ArrayType):
                    val = builder.gep(val, [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 0)])
                args.append(val)

            res = builder.call(func["func"], args)
            if len(ast) == 1: return res

        elif i["type"] == "addrof":
            context.ptr_state = True
            tmp = compiler([i["value"]], context, builder)
            context.ptr_state = False
            if tmp.type.is_pointer: return tmp
            tools.error("not implemented", context.file)

        elif i["type"] == "get":
            context.ptr_state = True
            ptr = compiler([i["target"]], context, builder)
            context.ptr_state = False
            return builder.load(builder.gep(ptr, [ir.Constant(ir.IntType(32), 0), compiler([i["index"]], context, builder)]))

        elif i["type"] == "set":
            context.ptr_state = True
            ptr = compiler([i["target"]], context, builder)
            context.ptr_state = False
            val = compiler([i["value"]], context, builder)
            builder.store(val, builder.gep(ptr, [ir.Constant(ir.IntType(32), 0), compiler([i["index"]], context, builder)]), align = context.get_alignof(val))

        elif i["type"] in ["NULL", "INT", "FLOAT", "BOOL", "STRING", "VOID", "DOUBLE", "CHAR", "IDENTIFIER", "ARRAY"]:
            if "value" not in i:
                if i["type"] == "STRING": return ir.IntType(8).as_pointer()
                elif i["type"] == "ARRAY": return compiler([{"type": i["array_type"]}], context, builder).as_pointer()
                elif i["type"] == "DOUBLE": return ir.DoubleType()
                elif i["type"] == "CHAR": return ir.IntType(8)
                elif i["type"] == "BOOL": return ir.IntType(1)
                elif i["type"] == "FLOAT": return ir.FloatType()
                elif i["type"] == "INT": return ir.IntType(32)
                elif i["type"] == "VOID": return ir.VoidType()
                else: tools.error("unknown type '" + i["type"] + "'", context.file)

            else:
                if i["type"] == "STRING":
                    fmt = bytearray(((i["value"] if i["value"] != None else "") + "\0").encode("utf8"))
                    val = ir.Constant(ir.ArrayType(ir.IntType(8), len(fmt)), fmt)
                    # ptr = context.malloc(builder, context.get_sizeof(val), context.get_alignof(val))
                    # ptr = builder.bitcast(ptr, val.type.as_pointer())
                    # builder.store(val, ptr, align = context.get_alignof(val))
                    tmp = context.get_scope()
                    context.set_scope("global")
                    name = context.get_unique_name()
                    global_fmt = ir.GlobalVariable(module, val.type, name)
                    context.set(name, {"type": "globalvar", "ptr": global_fmt})
                    context.set_scope(tmp)
                    global_fmt.align = context.get_alignof(val)
                    global_fmt.initializer = val
                    global_fmt.linkage = "internal"
                    global_fmt.global_constant = True
                    return global_fmt
                    # return ptr
                elif i["type"] == "ARRAY":
                    size = i["size"]
                    array_type = i["size"]
                    array = [compiler([i], context, builder) for i in i["value"]]
                    if size == None: size = len(array)
                    if array_type == None: array_type = array[0].type
                    else: array_type = compiler([array_type], context, builder)
                    val = ir.Constant(ir.ArrayType(array_type, size), array)
                    # ptr = context.malloc(builder, context.get_sizeof(val), context.get_alignof(val))
                    # ptr = builder.bitcast(ptr, val.type.as_pointer())
                    # builder.store(val, ptr, align = context.get_alignof(val))
                    # context.set(context.get_unique_name(), {"type": "arr", "ptr": ptr})
                    tmp = context.get_scope()
                    context.set_scope("global")
                    name = context.get_unique_name()
                    global_fmt = ir.GlobalVariable(module, val.type, name)
                    context.set(name, {"type": "globalvar", "ptr": global_fmt})
                    context.set_scope(tmp)
                    global_fmt.align = context.get_alignof(val)
                    global_fmt.initializer = val
                    global_fmt.linkage = "internal"
                    global_fmt.global_constant = True
                    return global_fmt
                    # return ptr
                elif i["type"] == "NULL": return ir.Constant(ir.IntType(8), 0)
                elif i["type"] == "CHAR": return ir.Constant(ir.IntType(8), int(ord(i["value"]) if i["value"] != None else 0))
                elif i["type"] == "BOOL": return ir.Constant(ir.IntType(1), int(i["value"].replace("TRUE", "1").replace("FALSE", "0") if i["value"] != None else "FALSE"))
                elif i["type"] == "FLOAT": return ir.Constant(ir.FloatType(), float(i["value"].replace("f", "") if i["value"] != None else "0.0"))
                elif i["type"] == "DOUBLE": return ir.Constant(ir.DoubleType(), float(i["value"].replace("f", "") if i["value"] != None else "0.0"))
                elif i["type"] == "INT": return ir.Constant(ir.IntType(32), int(i["value"] if i["value"] != None else "0"))
                elif i["type"] == "IDENTIFIER":
                    value = context.get(i["value"])

                    if value["type"] == "var":
                        value = value["ptr"]
                        if not context.ptr_state and not isinstance(value.type.pointee, ir.ArrayType) and value.type != ir.IntType(8).as_pointer():
                            value = builder.load(value)
                        return value

                    else:
                        return i["value"]
                else: tools.error("unknown type '" + i["type"] + "'", context.file)

        else:
            tools.error("undefined: '" + i["type"] + "'", context.file)

    return module