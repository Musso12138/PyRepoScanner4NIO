import ast
import logging
import PyRepoScanner.scanner.node_visitor as prs_node_visitor


def test_visit_Import():
    tnv = prs_node_visitor.TaintNodeVisitor()
    with open("../../example/node_visitor_tests/import.py", "r") as f:
        node = ast.parse(f.read())
        tnv.generic_visit(node)
    print(tnv.imports)
    print(tnv.import_aliases)


def test_visit_Call():
    tnv = prs_node_visitor.TaintNodeVisitor()
    with open("../../example/node_visitor_tests/call.py", "r") as f:
        node = ast.parse(f.read())
        tnv.generic_visit(node)


def test_visit_ClassDef():
    tnv = prs_node_visitor.TaintNodeVisitor()
    with open("../../sample/packages/setup/datadog-agent-20.3.4/setup.py", "r") as f:
        node = ast.parse(f.read())
        tnv.generic_visit(node)


def test_visit_FunctionDef():
    tnv = prs_node_visitor.TaintNodeVisitor()
    with open("../../example/node_visitor_tests/functiondef.py", "r") as f:
        node = ast.parse(f.read())
        tnv.generic_visit(node)
        for k, v in tnv.variables.items():
            print(k, v)


def test_visit_Assign():
    tnv = prs_node_visitor.TaintNodeVisitor()
    with open("../../example/node_visitor_tests/assign.py", "r") as f:
        node = ast.parse(f.read())
        tnv.generic_visit(node)
        print(tnv.variables)
