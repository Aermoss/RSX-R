import llvmlite.ir as ir
import llvmlite.binding as llvm

from rsxpy import *

module = ir.Module()

class Context:
    def __init__(self, file):
        self.reset(file)

    def reset(self, file):
        self.version = None
        self.scope = {}
        self.args = []
        self.current_scope = "global"
        self.included = []
        self.include_folders = []
        self.main_file = file
        self.file = file
        self.current_return_type = None
        self.current_array_type = None
        self.cache = {}
        self.include_cache = {}
        self.parent_scopes = []

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

    def delete_scope(self, scope, builder):
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

        return key in tmp

    def set(self, key, value, force = False):
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

            return self.scope["global"][key]

        else:
            if len(self.parent_scopes) != 0:
                tmp_scope = self.current_scope
                self.current_scope = self.parent_scopes[len(self.parent_scopes) - 1]
                tmp = self.parent_scopes.copy()
                self.parent_scopes.pop(len(self.parent_scopes) - 1)
                res = self.get(key)
                self.parent_scopes = tmp
                self.current_scope = tmp_scope
                return res

            else:
                tools.error(f"'{key}' was not declared in this scope", self.file)

    def delete(self, key, record_pass = False):
        if self.is_exists(key):
            if not record_pass and self.current_scope == "global":
                if len(self.recorded) != 0:
                    for i in self.recorded:
                        del self.recorded[i][key]

            if self.current_scope != "global":
                if key in self.scope[self.current_scope]:
                    del self.scope[self.current_scope][key]
                    return

            del self.scope["global"][key]

        else:
            tools.error(f"'{key}' was not declared in this scope", self.file)

    def is_main_file(self):
        return self.main_file == self.file

    def is_in_function(self):
        return self.current_scope != "global"

    def prepare_to_execute(self, key):
        tmp = self.current_scope
        self.current_scope = self.add_scope(key)
        self.cache[self.current_scope] = {"current_return_type": self.current_return_type, "current_array_type": self.current_array_type, "current_scope": tmp, "parent_scopes": self.parent_scopes}
        self.parent_scopes = []
        self.current_return_type = self.get(key)["return_type"]
        self.current_array_type = self.get(key)["array_type"]
        return self.current_scope

    def end_execute(self):
        self.delete_scope(self.current_scope)
        tmp = self.current_scope
        self.current_return_type, self.current_array_type = self.cache[self.current_scope]["current_return_type"], self.cache[self.current_scope]["current_array_type"]
        self.current_scope, self.parent_scopes = self.cache[self.current_scope]["current_scope"], self.cache[self.current_scope]["parent_scopes"]
        del self.cache[tmp]

    def is_included(self, key):
        return key in self.included

    def prepare_to_include(self, ast, file):
        self.include_cache[len(self.include_cache)] = {"file": self.file}
        self.file = file

    def end_include(self):
        self.file = self.include_cache[len(self.include_cache) - 1]["file"]
        self.include_cache.pop(len(self.include_cache) - 1)

    def is_base(self):
        return self.current_scope == "global"

def compiler(ast, context: Context, builder = None):
    pass_list = []

    if context.scope == {}:
        context.scope = {
            "global": {
                "system": {"type": "func", "func": ir.Function(module, ir.FunctionType(ir.IntType(32), [], var_arg = True), name = "system"), "builder": None},
                "free": {"type": "func", "func": ir.Function(module, ir.FunctionType(ir.VoidType(), [], var_arg = True), name = "_aligned_free"), "builder": None}
            }
        }

    for index, i in enumerate(ast):
        if i["type"] == "func":
            if context.current_scope != "global":
                tools.error("a function-definition is not allowed here before", context.file)

            if context.is_exists(i["name"]):
                tools.error("can't overload a function", context.file)

            if i["return_type"] not in ["VOID", "FLOAT", "INT", "STRING", "BOOL", "ARRAY"]:
                tools.error("unknown type for a function: '" + i["return_type"].lower() + "'", context.file)

            args = []

            for j in i["args"]:
                args.append(compiler([{"type": i["args"][j]}], context, builder))

            tmp_builder = None
            func = ir.Function(module, ir.FunctionType(compiler([{"type": i["return_type"]}], context, builder), args, var_arg = i["var_arg"]), name = i["name"])
            if i["ast"] != None: tmp_builder = ir.IRBuilder(func.append_basic_block("entry"))
            context.set(i["name"], {"type": "func", "func": func, "builder": tmp_builder})
            if i["ast"] != None:
                tmp_scope = context.get_scope()
                context.add_scope(i["name"])
                context.set_scope(i["name"])

                for _index, j in enumerate(i["args"]):
                    ptr = tmp_builder.alloca(func.args[_index].type)
                    tmp_builder.store(func.args[_index], ptr)
                    context.set(j, {"type": "var", "value_type": i["args"][j], "ptr": ptr})

                compiler(i["ast"], context, tmp_builder)
                context.delete_scope(i["name"], builder)
                context.set_scope(tmp_scope)

        elif i["type"] == "return":
            if i["value"] == {"type": "NULL", "value": "NULL"}:
                return builder.ret_void()

            return builder.ret(compiler([i["value"]], context, builder))
        
        elif i["type"] == "neg":
            value = compiler([i["value"]], context, builder)
            return builder.neg(value)

        elif i["type"] == "bitwise not":
            value = compiler([i["value"]], context, builder)
            if value.type not in [ir.IntType(1), ir.IntType(32)]: tools.error("couldn't use '~' with '" + str(value.type).lower() + "'", context.file)
            return builder.not_(value)

        elif i["type"] == "not":
            value = compiler([i["value"]], context, builder)
            if value.type not in [ir.IntType(1), ir.IntType(32)]: tools.error("couldn't use '!' with '" + str(value.type).lower() + "'", context.file)
            if value.type == ir.IntType(32): value = builder.trunc(value, ir.IntType(1))
            return builder.not_(value)

        elif i["type"] in ["notequals", "equalsequals", "less", "greater", "lessequals", "greaterequals"]:
            left = compiler([i["left"]], context, builder)
            right = compiler([i["right"]], context, builder)
            return builder.icmp_signed(i["type"].replace("notequals", "!=").replace("equalsequals", "==").replace("less", "<").replace("greater", ">").replace("lessequals", "<=").replace("greaterequals", ">="), left, right)

        elif i["type"] == "delete":
            builder.call(context.get("free")["func"], [context.get(i["value"])["ptr"]])

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
            compiler(i["update"], context, builder)
            builder.cbranch(compiler([i["condition"]], context, builder), body_block, end_block)
            context.rem_parent_scope(tmp)
            context.delete_scope(cur, builder)
            context.set_scope(tmp)
            builder.position_at_end(end_block)

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
            builder.branch(end_block)
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
            builder.cbranch(compiler([i["condition"]], context, builder), body_block, end_block)
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
            builder.cbranch(compiler([i["condition"]], context, builder), body_block, end_block)
            builder.position_at_end(end_block)

        elif i["type"] == "if":
            temp_pos = 1
            temp_ast = [ast[index]]

            while len(ast) - 1 >= index + temp_pos and ast[index + temp_pos]["type"] in ["else", "else if"]:
                temp_ast.append(ast[index + temp_pos])
                pass_list.append(index + temp_pos)
                if ast[index + temp_pos]["type"] == "else": break
                else: temp_pos += 1

            endif = builder.append_basic_block()

            for index, j in enumerate(temp_ast):
                if j["type"] == "if":
                    intermediate_check = endif

                    if len(temp_ast) - 1 >= index + 1:
                        if temp_ast[index + 1]["type"] in ["else if", "else"]:
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
                    builder.branch(endif)
                    builder.position_at_end(intermediate_check)

                if j["type"] == "else if":
                    intermediate_check = endif

                    if len(temp_ast) - 1 >= index + 1:
                        if temp_ast[index + 1]["type"] in ["else if", "else"]:
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
                    builder.branch(endif)

            builder.position_at_end(endif)

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
                val = compiler([i["value"]], context, builder)
                if val.type != compiler([{"type": i["value_type"]}], context, builder) and not val.type.is_pointer: tools.error("type mismatch for '" + i["name"] + "'", context.file)
                ptr = builder.alloca(val.type)
                builder.store(val, ptr)
                context.set(i["name"], {"type": "var", "value_type": i["value_type"], "ptr": ptr})

            else:
                if i["value_type"] != None: tools.error("redefinition of '" + i["name"] + "'", context.file)
                val = compiler([i["value"]], context, builder)
                if val.type != compiler([{"type": context.get(i["name"])["value_type"]}], context, builder) and not val.type.is_pointer: tools.error("type mismatch for '" + i["name"] + "'", context.file)
                builder.store(val, context.get(i["name"])["ptr"])

        elif i["type"] in ["add", "sub", "mul", "div"]:
            left, right = compiler([i["left"]], context, builder), compiler([i["right"]], context, builder)
            if left.type != right.type and (str(left.type) in ["i32", "float"] and str(right.type) in ["i32", "float"]):
                if str(left.type) == "i32": left = builder.sitofp(left, right.type)
                elif str(right.type) == "i32": right = builder.sitofp(right, left.type)

            if i["type"] == "div":
                if str(left.type) == "i32": left = builder.sitofp(left, ir.FloatType())
                if str(right.type) == "i32": right = builder.sitofp(right, ir.FloatType())

            if left.type != right.type: tools.error("operands must be the same type", context.file)
            if str(left.type) == "i32": return {"add": builder.add, "sub": builder.sub, "mul": builder.mul, "div": builder.fdiv}[i["type"]](left, right)
            elif str(left.type) == "float": return {"add": builder.fadd, "sub": builder.fsub, "mul": builder.fmul, "div": builder.fdiv}[i["type"]](left, right)
            else: tools.error(f"type error ({left.type}, {right.type})", context.file)

        elif i["type"] == "call":
            value = compiler([i["value"]], context, builder)
            func = context.get(value)
            args = []

            for j in i["args"]:
                if func["builder"] != None: ...
                args.append(compiler([j], context, builder))

            res = builder.call(func["func"], args)
            if len(ast) == 1: return res

        elif i["type"] in ["INT", "FLOAT", "BOOL", "STRING", "VOID", "CHAR", "IDENTIFIER"]:
            if "value" not in i:
                if i["type"] == "STRING": return ir.IntType(8).as_pointer()
                elif i["type"] == "CHAR": return ir.IntType(8)
                elif i["type"] == "BOOL": return ir.IntType(1)
                elif i["type"] == "FLOAT": return ir.FloatType()
                elif i["type"] == "INT": return ir.IntType(32)
                elif i["type"] == "VOID": return ir.VoidType()
                else: tools.error("unknown type '" + i["type"] + "'", context.file)

            else:
                if i["type"] == "STRING":
                    fmt = bytearray((i["value"] + "\0").encode("utf8"))
                    c_str_val = ir.Constant(ir.ArrayType(ir.IntType(8), len(fmt)), fmt)
                    c_str = builder.alloca(c_str_val.type)
                    builder.store(c_str_val, c_str)
                    return c_str

                elif i["type"] == "CHAR": return ir.Constant(ir.IntType(8), int(i["value"]))
                elif i["type"] == "BOOL": return ir.Constant(ir.IntType(1), int(i["value"].replace("TRUE", "1").replace("FALSE", "0")))
                elif i["type"] == "FLOAT": return ir.Constant(ir.FloatType(), float(i["value"].replace("f", "")))
                elif i["type"] == "INT": return ir.Constant(ir.IntType(32), int(i["value"]))
                elif i["type"] == "IDENTIFIER":
                    value = context.get(i["value"])

                    if value["type"] == "var":
                        return builder.load(value["ptr"])

                    else:
                        return i["value"]
                else: tools.error("unknown type '" + i["type"] + "'", context.file)

        else:
            tools.error("undefined: '" + i["type"] + "'", context.file)

    return module