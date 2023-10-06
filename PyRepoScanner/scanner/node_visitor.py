import ast
import logging
import astpretty
from dataclasses import dataclass, field
from typing import List, Set, Dict, Tuple
import PyRepoScanner.utils.issue as prs_issue


LOGGER = logging.getLogger()


@dataclass
class TaintNodeVisitor:
    """实现ast.NodeVisitor的Taint Analysis版"""
    rules: dict = None
    filepath: str = ""
    imports: Set = field(default_factory=lambda: set())             # set(module)
    import_aliases: Dict = field(default_factory=lambda: dict())    # [from] import as alias -> module, function, class, variable, ...
    variables: Dict = field(default_factory=lambda: dict())         # 变量表，以namespace为key维护命名空间内的变量
    constants: Dict = field(default_factory=lambda: dict())         # 常量表，维护常量的taint情况
    context: Dict = field(default_factory=lambda: dict())           # 用于在函数间传递信息
    depth: int = 0
    namespace: str = None
    namespace_list: List = field(default_factory=lambda: [])
    # 污点传播不保证发现所有问题，结合敏感操作顺序也可以发现一些问题
    sensitive_serial: int = 0            # 敏感行为序号
    sensitive_info_acquisition_serial: Tuple = None
    network_receiver_serial: Tuple = None
    network_sender_serial: Tuple = None
    file_operation_serial: Tuple = None
    encoder_serial: Tuple = None
    decoder_serial: Tuple = None
    command_execution_serial: Tuple = None
    results: List = field(default_factory=lambda: [])

    def __post_init__(self):
        # 初始化namespace
        self._add_name_to_namespace(self._get_namespace_from_filename(self.filepath))

    def pre_visit(self, node):
        self.depth += 1
        node._prs_taints = []
        node._prs_sinks = []
        node._prs_namespace = self.namespace

        # 每个节点初始都被赋予*(任意内容)taint
        self._add_taint_to_node(node, prs_issue.Taint(
            id="0000",
            accordance="type",
            type="*",
            lineno=node.lineno if hasattr(node, "lineno") else -1,
            col_offset=node.col_offset if hasattr(node, "col_offset") else -1,
            end_lineno=node.end_lineno if hasattr(node, "end_lineno") else -1,
            end_col_offset=node.end_col_offset if hasattr(node, "end_col_offset") else -1
        ))

    def visit(self, node):
        """visit指定node，根据node类型决定具体的visit方法"""
        # print(self.depth)
        # print(ast.dump(node))
        name = node.__class__.__name__
        method = "visit_" + name
        visitor = getattr(self, method, None)
        if visitor is not None:
            visitor(node)
        else:
            # print(f"not support access node {id(node)} type {name} temporarily")
            LOGGER.debug(f"not support access node {id(node)} type {name} temporarily")
            # self.update_scores(self.tester.run_tests(self.context, name))
            # astpretty.pprint(node, show_offsets=False)

    def post_visit(self, node):
        self.depth -= 1
        # 检查并消掉本层namespace
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            self._pop_name_from_namespace()

    def visit_Import(self, node):
        """访问ast.Import节点"""
        for alias in node.names:
            if alias.asname is not None:
                self.import_aliases[alias.asname] = alias.name
            self.imports.add(alias.name)

    def visit_ImportFrom(self, node):
        """访问ast.ImportFrom节点"""
        # from . import xxx，相对导入时module显示为None
        if node.module is None:
            return self.visit_Import(node)

        for alias in node.names:
            member = node.module + "." + alias.name
            if alias.asname is not None:
                self.import_aliases[alias.asname] = member
            else:
                self.import_aliases[alias.name] = member
            self.imports.add(member)

    def visit_ClassDef(self, node):
        """访问ast.ClassDef节点

        将class name添加到namespace
        """
        self._add_name_to_namespace(node.name)

    def visit_FunctionDef(self, node):
        """访问ast.FunctionDef节点

        将function name添加到namespace，
        分析函数体内部的数据流，对函数传入参数/内部执行过程/返回内容做
        """
        self.context["function_def"] = node
        self._add_name_to_namespace(node.name)

        # 处理函数的形参
        self._handle_functiondef_arguments(node)

    def visit_Assign(self, node):
        """访问ast.Assign节点

        具体分析value实现taint传播分析
        """
        self.context["assign"] = node
        targets = self.get_assign_targets(node)
        self.context["assign_targets"] = targets
        # 将targets附加在node上
        node._prs_assign_targets = targets

        # 当赋值发生后，变量在当前命名空间之前的属性失去意义
        for target_name in node._prs_assign_targets:
            self.variables[self.namespace][target_name] = {"taints": []}

        # 根据等号右侧(node.value)节点类型做出相应改变
        # 常量赋值直接记录到表
        if isinstance(node.value, ast.Constant):
            value = node.value.value
            for target_name in node._prs_assign_targets:
                self.variables[self.namespace][target_name]["value"] = value
        # 变量赋值尝试get常量/指向的根variable 记录到表
        elif isinstance(node.value, ast.Name):
            value = self._get_value_by_var_id(node.value.id)
            if value is not None:
                for target_name in node._prs_assign_targets:
                    self.variables[self.namespace][target_name]["value"] = value
            else:
                # node.value(等号右侧变量)无value记录，检查是否存在，如果存在进行硬拷贝
                copy_flag = True
                for target_name in node._prs_assign_targets:
                    if not self._copy_var_to_var(node.value.id, target_name):
                        copy_flag = False
                        break
                # 硬拷贝失败（变量不存在于变量表中）
                if not copy_flag:
                    variable = self._get_variable_by_var_id(node.value.id)
                    if variable is not None:
                        for target_name in node._prs_assign_targets:
                            self.variables[self.namespace][target_name]["variable"] = variable
        # attribute赋值尝试获取attribute的完整值，记录到表variable内容
        elif isinstance(node.value, ast.Attribute):
            attribute = self._get_attr_real_name(node.value)
            for target_name in node._prs_assign_targets:
                self.variables[self.namespace][target_name]["variable"] = attribute

    def visit_Call(self, node):
        """访问ast.Call节点

        分析实际函数调用的节点，重点在明确实际调用的函数全称、
        明确函数是否存在sink点、明确是否有taint数据流入sink
        """
        # astpretty.pprint(node, show_offsets=False)
        self.context["call"] = node
        real_call = self.get_real_call(node)

        node._prs_call_func = real_call
        self.context["call_func"] = real_call

        self.mark_spread_taint(node)

    def visit_Subscript(self, node):
        """访问ast.Subscript节点"""
        if isinstance(node.value, ast.Attribute):
            target = self._get_attr_real_name(node.value)
            node._prs_subscript_target = target
        elif isinstance(node.value, ast.Name):
            node._prs_subscript_target = node.value.id

    def visit_Constant(self, node):
        """访问ast.Constant节点

        从常量表中获取taint添加到节点
        """
        self.mark_spread_taint(node)

    def visit_Tuple(self, node):
        """在其他节点中处理"""
        pass

    def visit_List(self, node):
        """在其他节点中处理"""
        pass

    def visit_Dict(self, node):
        """在其他节点中处理"""
        pass

    def visit_alias(self, node):
        """在其他节点中处理"""
        pass

    def visit_Name(self, node):
        """访问ast.Name节点

        根据node.ctx不同，进行不同处理:

        - ast.Load: 根据变量表中记载，将变量taint附加到节点上
        - ast.Store: 不进行任何操作
        - ast.Del: 将变量从变量表中删除
        """
        if isinstance(node.ctx, ast.Load):
            self.mark_spread_taint(node)
        elif isinstance(node.ctx, ast.Store):
            pass
        elif isinstance(node.ctx, ast.Del):
            self._del_var_from_variables(node.id)

    def visit_Load(self, node):
        """在其他节点中处理"""
        pass

    def visit_Store(self, node):
        """在其他节点中处理"""
        pass

    def visit_Del(self, node):
        """在其他节点中处理"""
        pass

    def visit_arg(self, node):
        """在其他节点中处理"""
        pass

    def visit_keyword(self, node):
        """在其他节点中处理"""
        pass

    def visit_Expr(self, node):
        """在其他节点中处理"""
        pass

    def visit_Attribute(self, node):
        """访问ast.Attribute节点

        解析Attribute全称，赋值到_prs_attribute
        """
        node._prs_attribute = self._get_attr_real_name(node)

        if isinstance(node.ctx, ast.Load):
            self.mark_spread_taint(node)

    def visit_arguments(self, node):
        """"""
        pass

    def visit_With(self, node):
        """在其他节点中处理"""
        pass

    def visit_withitem(self, node):
        """访问ast.withitem节点

        将optional_vars加入变量表
        """
        node._prs_withitem_target = None
        if isinstance(node.optional_vars, ast.Name):
            if isinstance(node.optional_vars.ctx, ast.Store):
                self.variables[self.namespace][node.optional_vars.id] = {"taints": []}
                node._prs_withitem_target = node.optional_vars.id

    def visit_If(self, node):
        """在其他节点中处理"""
        pass

    def visit_Compare(self, node):
        """在其他节点中处理"""
        pass

    def visit_Eq(self, node):
        """在其他节点中处理"""
        pass

    def generic_visit(self, node):
        """驱动visitor递归访问所有ast节点

        从ast.parse返回的第一个ast.Module节点开始
        """
        # 第一轮访问
        # 进行污点标记和污点传播
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for idx, item in enumerate(value):
                    if isinstance(item, ast.AST):
                        self.pre_visit(item)
                        item._prs_parent = node
                        self.visit(item)
                        self.generic_visit(item)
                        self.post_visit(item)
            elif isinstance(value, ast.AST):
                self.pre_visit(value)
                value._prs_parent = node
                self.visit(value)
                self.generic_visit(value)
                self.post_visit(value)

        # 第二轮访问
        # 进行污点分析，taint-sink匹配
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for idx, item in enumerate(value):
                    if isinstance(item, ast.AST):
                        self.check_taint(item)
            elif isinstance(value, ast.AST):
                self.check_taint(value)

    def analyze(self, node):
        self.generic_visit(node)

    def _handle_functiondef_arguments(self, node):
        """处理ast.FunctionDef节点的形参

        将形参加入当前namespace的变量表，并添加相关信息，
        目前仅处理posonlyargs, args, kwonlyargs
        """
        arguments = node.args
        pos = 0
        # 仅凭位置传递的参数
        # def test_func(a, b, /, c) => a,b仅可以通过位置传递
        for arg in arguments.posonlyargs:
            self.variables[self.namespace][arg.arg] = {"taints": [], "position": pos}
            pos += 1
            self._add_taint_to_var(
                arg.arg,
                prs_issue.Taint(
                    id="0000", accordance="type", type="input"
                )
            )
        # 位置/关键字均可传递的参数
        for arg in arguments.args:
            self.variables[self.namespace][arg.arg] = {"taints": [], "position": pos, "keyword": arg.arg}
            pos += 1
            self._add_taint_to_var(
                arg.arg,
                prs_issue.Taint(
                    id="0000", accordance="type", type="input"
                )
            )
        # 仅凭关键字传递的参数
        # def test_func(a, *args, b, c, **kwargs) => b,c仅可以通过关键字传递
        for arg in arguments.kwonlyargs:
            self.variables[self.namespace][arg.arg] = {"taints": [], "keyword": arg.arg}
            self._add_taint_to_var(
                arg.arg,
                prs_issue.Taint(
                    id="0000", accordance="type", type="input"
                )
            )

    def get_assign_targets(self, node):
        """分析并返回ast.Assign节点的赋值目标

        :return list: [ target1, target2, ... ]
        """
        assign_targets = []
        for target in node.targets:
            assign_targets.extend(self._get_assign_single_target_list(target))
        return assign_targets

    def _get_assign_single_target_list(self, node) -> list:
        """解析ast.Assign.targets中的单个节点

        :return 节点中所有变量的名称（targets中的节点可以是tuple/list）
        """
        target_list = []

        if isinstance(node.ctx, ast.Store):
            if isinstance(node, ast.Name):
                target_list.append(node.id)
            elif isinstance(node, ast.Tuple) or isinstance(node, ast.List):
                for tuple_elem in node.elts:
                    target_list.extend(self._get_assign_single_target_list(tuple_elem))
            elif isinstance(node, ast.Attribute):
                target_list.append(self._get_attr_real_name(node))
        else:
            LOGGER.debug("ast.Assign.targets not load as ast.Store:", ast.dump(node))

        return target_list

    def get_real_call(self, node):
        """分析并返回ast.Call节点实际调用的函数

        仅考虑func字段Attribute和Name嵌套结构(a.b.c.d())，对于函数间的链式调用不做分析(a.b().c.d())

        - node.func为ast.Attribute:
            调用self._get_attr_real_name获取ast.Attribute节点对应的实际属性全称
        - node.func为ast.Name:
            检查self.variables和self.import_aliases字典，获取func的实际名称

        :return: str: ast.Call节点调用的函数, e.g. os.system
        """
        if isinstance(node.func, ast.Attribute):
            return self._get_attr_real_name(node.func)
        elif isinstance(node.func, ast.Name):
            real_name = node.func.id
            # 检查self.variables/self.import_aliases表，其内可能有函数赋值
            var_value = self._get_variable_by_var_id(real_name)
            if var_value is not None:
                return var_value
            return real_name
        else:
            return ""

    def _get_attr_real_name(self, node):
        """递归分析ast.Attribute节点的实际内容

        会深入解析出函数调用链条中由函数导入的模块中包含的函数的调用行为
        - ast.Name:
            检查self.variables和self.import_aliases字典中是否包含node.id，
            如果包含，返回其值
        - ast.Attribute:
            递归解析ast.Attribute节点内容(向上递归)
        - ast.Call:
            三种函数__import__, importlib.__import__, importlib.import_module的调用，
            相当于模块的引入，解析出真实的模块名并返回。e.g. __import__("base64").b64decode -> base64.b64decode
        :return: str: ast.Attribute属性全称, e.g. a.b.c
        """
        if isinstance(node, ast.Name):
            name = node.id
            variable = self._get_variable_by_var_id(name)
            if variable is not None:
                return variable
            elif name in self.import_aliases:
                return self.import_aliases[name]
            return name

        elif isinstance(node, ast.Attribute):
            upper_func = self._get_attr_real_name(node.value)
            return f"{upper_func}.{node.attr}" if upper_func is not None else node.attr

        elif isinstance(node, ast.Call):
            upstream_func_name = self.get_real_call(node)
            if upstream_func_name == "__import__" or upstream_func_name == "importlib.__import__"\
                    or upstream_func_name == "importlib.import_module":
                return self.get_imported_module_from_function_call(node, upstream_func_name)

            # deprecated: 不需要函数调用链，对Call主要关注__import__函数即可
            # Call返回函数调用链，对函数名后加()
            # return f"{self._get_real_call(node)}()"

    def get_imported_module_from_function_call(self, node, func):
        """解析由函数调用引入的模块/函数

        根据传入参数解析由__import__, importlib.__import__,
        importlib.import_module导入的模块中的函数
        :return: str: 实际导入的模块名
        """
        if func == "__import__" or func == "importlib.__import__":
            return self.get_call_parameter(node, "name", 0)
        elif func == "importlib.import_module":
            # importlib.import_module导入时分为name和package
            # name: 实际导入的模块
            # package: 实际导入模块的父模块
            name = self.get_call_parameter(node, "name", 0)
            package = self.get_call_parameter(node, "package", 1)
            # astpretty.pprint(node, show_offsets=False)
            if package is not None:
                return f"{package}{name}"
            else:
                return name

    def get_call_parameter(self, node, name, arg=-1):
        """获取ast.Call节点的指定参数值"""
        if arg >= 0:
            if len(node.args) > arg:
                return self.get_node_value(node.args[arg])
        for keyword in node.keywords:
            if keyword.arg == name:
                return self.get_node_value(keyword.value)
        return None

    def _get_namespace_from_filename(self, filename):
        """TODO: 根据完整的文件路径filename解析module的namespace

        TODO: 后续可以做个初始namespace将多个文件的数据流串接
        """
        return ""

    def _add_name_to_namespace(self, name):
        self.namespace_list.append(name)
        self._update_namespace()

    def _pop_name_from_namespace(self, ):
        self.namespace_list.pop()
        self._update_namespace()

    def _update_namespace(self):
        """根据namespace_list更新当前namespace

        为初次访问的namespace在variables中开辟存储字典空间
        """
        self.namespace = ".".join(self.namespace_list)
        self.variables.setdefault(self.namespace, {})

    def get_node_value(self, node):
        """获取ast.Constant/ast.Name节点的真实value

        - ast.Constant
            节点记录的常量值
        - ast.Name
            当前namespace及父辈namespace中记录的变量值

        :return: 节点值(基本数据类型)/None
        """
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            return self._get_value_by_var_id(node.id)
        else:
            return None

    def _copy_var_to_var(self, src_var, dest_var):
        """在当前namespace下将src变量信息硬拷贝到dest变量中

        :return: True: 成功 / False: src_var不存在
        """
        namespace = self._get_namespace_by_var(src_var)
        if namespace is None:
            return False

        self.variables[self.namespace][dest_var] = self.variables[namespace][src_var].copy()
        return True

    def _get_variable_by_var_id(self, var):
        """获取变量的variable内容

        如果存在variable内容，返回variable；
        否则如果在import表中，返回import内容；
        否则返回None。
        :return: str: var的variable内容 / None
        """
        namespace = self._get_namespace_by_var(var)
        if namespace is None:
            if var in self.import_aliases:
                return self.import_aliases[var]
            elif var in self.imports:
                return var
            else:
                return None

        if "variable" in self.variables[namespace][var]:
            return self.variables[namespace][var]["variable"]
        return None

    def _get_value_by_var_id(self, var):
        """获取变量对应的静态值

        self.variables从当前namespace开始，迭代向父namespace查找，
        检查变量名所在的namespace，如果已被静态赋值，且为基本数据类型，返回其静态值，
        否则返回None（代表var的值不是Constant或本身值为None）

        :return: 变量静态值(基本数据类型)，None(其他赋值类型)
        """
        #
        namespace = self._get_namespace_by_var(var)
        if namespace is None:
            return

        if "value" in self.variables[namespace][var]:
            return self.variables[namespace][var]["value"]
        else:
            return None

    def _get_namespace_by_var(self, var):
        """定位变量所在的namespace

        根据变量名从当前namespace开始迭代向父namespace查找
        :return: str: namespace
        """
        if var in self.variables[self.namespace]:
            return self.namespace
        for i in list(range(len(self.namespace_list)))[::-1]:
            namespace = ".".join(self.namespace_list[:i])
            if var in self.variables[namespace]:
                return namespace
        return None

    def _del_var_from_variables(self, var):
        """从变量表中删除指定变量"""
        namespace = self._get_namespace_by_var(var)
        if namespace is None:
            return

        del self.variables[namespace][var]
        return

    def mark_spread_taint(self, node):
        """对节点进行污点分析，包括污点标记、污点传播"""
        self.mark_taint(node)
        self.spread_taint(node)

    def mark_taint(self, node):
        """污点标记，标记taints和sinks

        根据规则检查:
        - ast.Call节点调用的函数，如果函数引入taint，
            则向对应node._prs_tainted_by中添加taint信息
        """
        # 对于ast.Call节点，根据规则集中sinks下的function
        if isinstance(node, ast.Call):
            # 遍历每个文件(id)对应的规则集
            for _id, rule in self.rules.items():
                # 检查taint规则
                if "taints" in rule:
                    for taint_rule in rule["taints"]:
                        if taint_rule["accordance"] == "function":
                            if taint_rule["function"] == node._prs_call_func:
                                taint = prs_issue.Taint(
                                    id=_id,
                                    accordance=taint_rule["accordance"],
                                    type=rule["type"] if "type" in rule else "",
                                    function=taint_rule["function"],
                                    position=taint_rule["position"] if "position" in taint_rule else None,
                                    keyword=taint_rule["keyword"] if "keyword" in taint_rule else None,
                                    lineno=node.lineno,
                                    col_offset=node.col_offset,
                                    end_lineno=node.end_lineno,
                                    end_col_offset=node.end_col_offset,
                                )

                                # 根据type标记敏感函数调用顺序
                                taint_type = rule["type"] if "type" in rule else ""
                                if taint_type != "":
                                    self._add_sensitive_operation(taint_type, taint)

                                # 污染函数的返回值，将taint标记到节点
                                if taint_rule["position"] == "ret":
                                    self._add_taint_to_node(node, taint)
                                # 污染函数的参数，将taint标记到参数对应的变量/常量上
                                else:
                                    expected_node = self._get_call_arg_node(
                                        node,
                                        position=taint_rule["position"] if "position" in taint_rule else None,
                                        keyword=taint_rule["keyword"] if "keyword" in taint_rule else None
                                    )
                                    if expected_node is not None:
                                        if isinstance(expected_node, ast.Name):
                                            self._add_taint_to_var(expected_node.id, taint)
                                        elif isinstance(expected_node, ast.Attribute):
                                            self._add_taint_to_var(self._get_attr_real_name(expected_node), taint)
                                        elif isinstance(expected_node, ast.Constant):
                                            self._add_taint_to_constant(expected_node.value, taint)
                # 检查sink规则
                if "sinks" in rule:
                    for sink in rule["sinks"]:
                        if sink["accordance"] == "function":
                            if sink["function"] == node._prs_call_func:
                                self._add_sink_to_node(node, prs_issue.Sink(
                                    id=_id,
                                    accordance=sink["accordance"],
                                    function=sink["function"],
                                    type=rule["type"] if "type" in rule else "",
                                    position=sink["position"] if "position" in sink else None,
                                    keyword=sink["keyword"] if "keyword" in sink else None,
                                    lineno=node.lineno,
                                    col_offset=node.col_offset,
                                    end_lineno=node.end_lineno,
                                    end_col_offset=node.end_col_offset
                                ))
        # 根据变量表将污点传播到ast.Name节点
        elif isinstance(node, ast.Name):
            var = node.id
            namespace = self._get_namespace_by_var(var)
            if namespace is None:
                return
            for taint_rule in self.variables[namespace][var]["taints"]:
                self._add_taint_to_node(node, taint_rule)
        # 根据常量表将污点传播到ast.Constant节点
        elif isinstance(node, ast.Constant):
            if node.value in self.constants:
                for taint in self.constants[node.value]["taints"]:
                    self._add_taint_to_node(node, taint)
        # 根据变量表以及attribute实际值将污点传播到ast.Attribute节点
        elif isinstance(node, ast.Attribute):
            # 如果变量表中有变量记录，将变量taint mark到节点
            var = node._prs_attribute
            namespace = self._get_namespace_by_var(var)
            if namespace is not None:
                for taint_rule in self.variables[namespace][var]["taints"]:
                    self._add_taint_to_node(node, taint_rule)

            # 遍历每个文件(id)对应的规则集
            for _id, rule in self.rules.items():
                # 检查taint规则
                if "taints" in rule:
                    for taint_rule in rule["taints"]:
                        if taint_rule["accordance"] == "attribute":
                            if taint_rule["attribute"] == node._prs_attribute:
                                if taint_rule["position"] == "ret":
                                    self._add_taint_to_node(node, prs_issue.Taint(
                                        id=_id,
                                        accordance="attribute",
                                        type=rule["type"] if "type" in rule else "",
                                        attribute=taint_rule["attribute"],
                                        position="ret",
                                        lineno=node.lineno,
                                        col_offset=node.col_offset,
                                        end_lineno=node.end_lineno,
                                        end_col_offset=node.end_col_offset,
                                    ))

    def spread_taint(self, node):
        """污点传播

        迭代向父节点进行污点传播，不传播"*"taint，对以下情况进行处理:

        - 父节点为ast.Module，停止污点传播
        - 父节点发生命名空间切换，停止污点传播
        - 父节点为ast.Assign，向赋值变量进行污点传播
        """

        # 根据ast.Assign赋值目标将taint传播到变量表
        if isinstance(node, ast.Assign):
            for taint in node._prs_taints:
                if taint.accordance == "type" and taint.type == "*":
                    continue
                for target in node._prs_assign_targets:
                    self._add_taint_to_var(target, taint)
        # 根据ast.withitem将taint传播到optional_vars属性的变量上
        elif isinstance(node, ast.withitem):
            if node._prs_withitem_target is not None:
                for taint in node._prs_taints:
                    if taint.accordance == "type" and taint.type == "*":
                        continue
                    self._add_taint_to_var(node._prs_withitem_target, taint)

        # 切换到父命名空间/到达根节点结束传播
        if not hasattr(node, "_prs_parent") or \
                isinstance(node._prs_parent, ast.Module) or \
                node._prs_namespace != node._prs_parent._prs_namespace:
            return

        # 向父节点传播污点
        for taint in node._prs_taints:
            if taint.accordance == "type" and taint.type == "*":
                continue
            # 函数参数引入的taint不应在本行被传播
            elif (taint.position != "ret" or taint.keyword is not None) and \
                    hasattr(node, "lineno") and taint.lineno == node.lineno:
                continue
            self._add_taint_to_node(node._prs_parent, taint)

        self.spread_taint(node._prs_parent)
    
    def check_taint(self, node):
        """污点检测

        - ast.Call: 可能抵达sink，根据规则检查是否存在安全问题;
            对于taint=input的变量传入函数参数的行为，将当前
            FunctionDef声明的函数注册到self.rules中
        """
        if isinstance(node, ast.Call):
            for _id, rule in self.rules.items():
                # 00开头的规则预留给敏感函数分类规则，不用于污点检测的taint-sink匹配部分
                if _id.startswith("00"):
                    continue

                taint_list = list()
                sink_list = list()

                # 从节点属性中发现与规则匹配的sink放入集合
                for sink_rule in rule["sinks"]:
                    accordance = sink_rule["accordance"]
                    for s in node._prs_sinks:
                        if sink_rule[accordance] == getattr(s, accordance):
                            sink_list.append((sink_rule, s))

                # 根据函数的实际sink参数位置匹配taint规则
                for s in sink_list:
                    sink = s[1]
                    # 根据sink的实际参数位置检查该参数是否被污染
                    expected_tainted_node = self._get_call_arg_node(node, sink.position, sink.keyword)

                    # 从节点属性中发现与规则匹配的taint放入集合
                    if expected_tainted_node is not None:
                        for taint_rule in rule["taints"]:
                            accordance = taint_rule["accordance"]
                            for t in expected_tainted_node._prs_taints:
                                if taint_rule[accordance] == getattr(t, accordance):
                                    self.add_issue_to_result(
                                        prs_issue.Issue(
                                            id=_id,
                                            name=rule["name"],
                                            taint=t,
                                            sink=sink,
                                            severity=taint_rule["severity"] if taint_rule["severity"] > s[0]["severity"] else s[0]["severity"],
                                            confidence=taint_rule["confidence"] if taint_rule["confidence"] > s[0][
                                                "confidence"] else s[0]["confidence"],
                                            msg=rule["template"].replace(
                                                "{SINK}", getattr(sink, sink.accordance)
                                            ).replace(
                                                "{TAINT}", getattr(t, t.accordance)
                                            ),
                                            file_path=self.filepath
                                        )
                                    )

        # TODO: 根据敏感函数顺序判断问题

    @staticmethod
    def _add_taint_to_node(node, taint: prs_issue.Taint):
        """向node._prs_taints添加taint"""
        for t in node._prs_taints:
            if t == taint:
                return
        node._prs_taints.append(taint)

    def _add_taint_to_var(self, var, taint: prs_issue.Taint):
        """向变量添加taint

        从当前namespace开始向上遍历命名空间，向第一次遇到的variable中添加taint
        """
        namespace = self._get_namespace_by_var(var)
        if namespace is None:
            return
        for t in self.variables[namespace][var]["taints"]:
            if t == taint:
                return
        self.variables[namespace][var]["taints"].append(taint)

    def _add_taint_to_constant(self, constant, taint: prs_issue.Taint):
        """向常量添加taint"""
        self.constants.setdefault(constant, {"taints": []})
        for t in self.constants[constant]["taints"]:
            if t == taint:
                return
        self.constants[constant]["taints"].append(taint)

    @staticmethod
    def _add_sink_to_node(node, sink: prs_issue.Sink):
        """向node._prs_sinks添加sink"""
        for s in node._prs_sinks:
            if s == sink:
                return
        node._prs_sinks.append(sink)

    def _add_sensitive_operation(self, sensitive_type: str, taint: prs_issue.Taint):
        """根据污点标记时发现的敏感行为类型标记顺序"""
        if sensitive_type == "command-execution":
            if self.command_execution_serial is None:
                self.command_execution_serial = (self.sensitive_serial, taint)
                self.sensitive_serial += 1
        elif sensitive_type == "encoder":
            if self.encoder_serial is None:
                self.encoder_serial = (self.sensitive_serial, taint)
                self.sensitive_serial += 1
        elif sensitive_type == "decoder":
            if self.decoder_serial is None:
                self.decoder_serial = (self.sensitive_serial, taint)
                self.sensitive_serial += 1
        elif sensitive_type == "network-receiver":
            if self.network_receiver_serial is None:
                self.network_receiver_serial = (self.sensitive_serial, taint)
                self.sensitive_serial += 1
        elif sensitive_type == "network-sender":
            if self.network_sender_serial is None:
                self.network_sender_serial = (self.sensitive_serial, taint)
                self.sensitive_serial += 1
        elif sensitive_type == "sensitive-info-acquisition":
            if self.sensitive_info_acquisition_serial is None:
                self.sensitive_info_acquisition_serial = (self.sensitive_serial, taint)
                self.sensitive_serial += 1
        elif sensitive_type == "file-operation":
            if self.file_operation_serial is None:
                self.file_operation_serial = (self.sensitive_serial, taint)
                self.sensitive_serial += 1

    @staticmethod
    def _get_call_arg_node(node, position, keyword):
        """根据position, keyword获取ast.Call调用函数的参数节点"""
        if isinstance(node, ast.Call):
            if position is not None:
                if len(node.args) > position:
                    return node.args[position]
            if keyword is not None:
                for k in node.keywords:
                    if k.arg == keyword:
                        return k.value
        return None

    def add_issue_to_result(self, issue: prs_issue.Issue):
        """向self.results中添加一条issue dict"""
        for i in self.results:
            if issue == i:
                return
        self.results.append(issue.dict())
