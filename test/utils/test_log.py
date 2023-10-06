import logging
from PyRepoScanner.scanner.node_visitor import TaintNodeVisitor
import PyRepoScanner.utils.log_utils as prs_log


def test_logging():
    l = TaintNodeVisitor()
    l.log_test()
