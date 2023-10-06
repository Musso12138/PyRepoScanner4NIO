import os
import re
import ast
import json
import time
import yaml
import logging
import shutil
import astpretty
from dataclasses import dataclass, field
from typing import List

import PyRepoScanner.scanner.metrics as prs_metrics
import PyRepoScanner.scanner.node_visitor as prs_node_visitor
import PyRepoScanner.utils.basic_tools as prs_utils
import PyRepoScanner.utils.issue as prs_issue


LOGGER = logging.getLogger()


@dataclass
class PypiScanner:
    rule_path: str
    file_rules_path: str = None
    print_flag: bool = False
    file_rules = {}
    rules = {}

    def __post_init__(self):
        if self.print_flag:
            print("\nLoading pypi scanner rules...")
        self.load_rules()
        self.load_file_rules()

    def load_rules(self):
        """加载规则文件

        如果rule_path是目录，则遍历尝试加载其内文件；如果是文件，配置Scanner规则self.rules
        """
        if os.path.isdir(self.rule_path):
            for file_name in os.listdir(self.rule_path):
                rule_file = os.path.join(self.rule_path, file_name)
                if os.path.isfile(rule_file):
                    self.load_rule(rule_file)
        elif os.path.isfile(self.rule_path):
            self.load_rule(self.rule_path)
        else:
            LOGGER.error("invalid rule path, rule path needs to be a directory or file")
            print("invalid rule path, rule path needs to be a directory or file")
            exit(-1)

    def load_rule(self, rule_path):
        """加载特定的文件"""
        with open(rule_path, "r") as f:
            rule = yaml.safe_load(f.read())
        if "id" not in rule:
            return
        else:
            self.rules[rule["id"]] = rule

    def load_file_rules(self):
        """加载文件规则集

        结构为：
        file_rules:
          file_name:
            - match: "setup.py"
            - match: "__init__.py"
        支持三种位置：file_dir, file_name, file_path
        支持两种规则：match, regex
        """
        self.file_rules = {
            "file_dir": {"match": [], "regex": []},
            "file_name": {"match": [], "regex": []},
            "file_path": {"match": [], "regex": []},
        }
        if self.file_rules_path is not None:
            if os.path.isfile(self.file_rules_path):
                try:
                    with open(self.file_rules_path, "r") as f:
                        rules = yaml.safe_load(f.read())
                except:
                    LOGGER.error("invalid format for file_rules_path: " + self.file_rules_path)
                    exit(-1)
                if "file_dir" in rules:
                    for dir_rule in rules["file_dir"]:
                        if "match" in dir_rule:
                            self.file_rules["file_dir"]["match"].append(dir_rule["match"])
                        if "regex" in dir_rule:
                            try:
                                self.file_rules["file_dir"]["regex"].append(re.compile(dir_rule["regex"]))
                            except Exception as e:
                                LOGGER.error("pypi scanner compile file_dir regex " + str(dir_rule["regex"]) + " failed with: " + str(e))
                                continue
                if "file_name" in rules:
                    for name_rule in rules["file_name"]:
                        if "match" in name_rule:
                            self.file_rules["file_name"]["match"].append(name_rule["match"])
                        if "regex" in name_rule:
                            try:
                                self.file_rules["file_name"]["regex"].append(re.compile(name_rule["regex"]))
                            except Exception as e:
                                LOGGER.error("epypi scanner compile file_name rgex " + str(name_rule["regex"]) + " failed with: " + str(e))
                                continue
                if "file_path" in rules:
                    for path_rule in rules["file_path"]:
                        if "match" in path_rule:
                            self.file_rules["file_path"]["match"].append(path_rule["match"])
                        if "regex" in path_rule:
                            try:
                                self.file_rules["file_path"]["regex"].append(re.compile(path_rule["regex"]))
                            except Exception as e:
                                LOGGER.error("pypi scanner compile file_path regex " + str(path_rule["regex"]) + " failed with: " + str(e))
                                continue
            else:
                LOGGER.error("invalid file_rules_path: file does not exist: " + self.file_rules_path)
                exit(-1)
        else:
            self.file_rules["file_name"]["match"].extend(["setup.py", "__init__.py"])

    def scan_local_file(self, file_path: str):
        """扫描本地文件"""
        if self.print_flag:
            print("Parsing file:", file_path)
        if os.path.isfile(file_path):
            base_name, ext = os.path.splitext(file_path)
            if ext == ".gz":
                base_name, ext = os.path.splitext(base_name)
                if ext == ".tar":
                    return self.scan_local_tar_gz_file(file_path)
            elif ext == ".whl":
                return self.scan_local_whl_file(file_path)
            elif ext == ".py":
                return self.scan_local_py_file(file_path)
        elif os.path.isdir(file_path):
            return self.scan_local_dir(file_path)
        else:
            LOGGER.error(f"invalid local file path, file not exists: {file_path}")
            exit(-1)

    def scan_local_tar_gz_file(self, file_path: str):
        """扫描本地的tar.gz文件"""

        _, file_name = os.path.split(file_path)
        file_base_name, _ = os.path.splitext(file_name)
        file_base_name, _ = os.path.splitext(file_base_name)
        tgz_root_dir = os.path.join(prs_utils.TMP_PATH, file_base_name)

        try:
            tgz_root_dir = prs_utils.extract_tar_gz_to_dir(file_path, prs_utils.TMP_PATH)
        except Exception as e:
            LOGGER.error(f"scanner extract tgz file {file_path} failed with: {e}")
            try:
                shutil.rmtree(tgz_root_dir)
            except Exception as e2:
                return None
            return None

        results = self.scan_local_dir(tgz_root_dir)
        # 检测后删除解压出的内容
        shutil.rmtree(tgz_root_dir)

        return results

    def scan_local_whl_file(self, file_path: str):
        """扫描本地的whl文件"""

        _, file_name = os.path.split(file_path)
        file_base_name, _ = os.path.splitext(file_name)
        whl_root_dir = os.path.join(prs_utils.TMP_PATH, file_base_name)

        try:
            whl_root_dir = prs_utils.extract_whl_to_dir(file_path, prs_utils.TMP_PATH)
        except Exception as e:
            LOGGER.error(f"scanner extract whl file {file_path} failed with: {e}")
            try:
                shutil.rmtree(whl_root_dir)
            except Exception as e2:
                return None
            return None

        results = self.scan_local_dir(whl_root_dir)
        # 检测后删除解压出的内容
        shutil.rmtree(whl_root_dir)

        return results

    def scan_local_dir(self, dir_path: str):
        """扫描本地的项目文件夹"""
        begin_time = time.time()
        results = {
            "import_name": self.parse_import_name(dir_path),
            "scanned_files": [],
            "metrics": {"total": {"files": 0, "lines": 0, "cnt": 0, "low": 0, "medium": 0, "high": 0}},
            "issues": {}
        }

        for home, dirs, files in os.walk(dir_path):
            for filename in files:
                if self._file_need_scan(home, filename):
                    file_path = os.path.join(home, filename)
                    result = self.scan_local_py_file(file_path)

                    # 处理检测结果
                    results["scanned_files"].append(file_path)
                    for key, value in result["metrics"]["total"].items():
                        results["metrics"]["total"][key] += value
                    results["metrics"][file_path] = result["metrics"]
                    results["issues"][file_path] = result["issues"][file_path]

        results["total_time"] = time.time() - begin_time

        return results

    def scan_local_py_file(self, file_path: str):
        """扫描本地的单个python文件"""
        if self.print_flag:
            print("Scanning file:", file_path)

        begin_time = time.time()

        results = {
            "metrics": {"total": {"files": 1, "lines": 0, "cnt": 0, "low": 0, "medium": 0, "high": 0}},
            "issues": {}
        }

        with open(file_path, "rb") as f:
            fdata = f.read()

        # 计算文件统计数据
        metrics = self._parse_metrics(file_path, fdata)
        results["metrics"]["total"]["lines"] += metrics["lines"]

        # 解析AST，使用TaintNodeVisitor分析AST
        node = self._parse_ast(fdata=fdata)
        node_visitor = prs_node_visitor.TaintNodeVisitor(
            rules=self.rules,
            filepath=file_path,
        )
        node_visitor.generic_visit(node)

        # 将文件扫描结果加入results
        result = node_visitor.results
        results["issues"][file_path] = result
        for issue in result:
            results["metrics"]["total"]["cnt"] += 1
            if issue["severity"] >= prs_issue.SEVERITY.HIGH:
                results["metrics"]["total"]["high"] += 1
            elif issue["severity"] >= prs_issue.SEVERITY.MEDIUM:
                results["metrics"]["total"]["medium"] += 1
            elif issue["severity"] >= prs_issue.SEVERITY.LOW:
                results["metrics"]["total"]["low"] += 1

        results["metrics"][file_path] = results["metrics"].copy()
        results["total_time"] = time.time() - begin_time

        return results

    @staticmethod
    def parse_import_name(dir_path: str):
        """根据项目文件夹的组织形式解析project的import name

        :return: list: return list of import names,
        because some projects have more than one import name
        """
        import_name = []
        cur_top_dir_path = None

        for dir_path, dir_names, file_names in os.walk(dir_path):
            if "__init__.py" in file_names:
                # 检查当前文件夹是否为最顶文件夹
                is_subfolder = False
                if cur_top_dir_path is not None and dir_path.startswith(cur_top_dir_path):
                    is_subfolder = True
                if not is_subfolder:
                    import_name.append(os.path.basename(dir_path))
                    cur_top_dir_path = dir_path

        return import_name

    def _file_need_scan(self, file_dir, file_name):
        """根据self.file_rules检查文件是否需要被检测"""
        file_path = os.path.join(file_dir, file_name)
        if not file_name.endswith(".py"):
            return False
        for match in self.file_rules["file_dir"]["match"]:
            if file_dir == match:
                return True
        for regex in self.file_rules["file_dir"]["regex"]:
            if regex.search(file_dir):
                return True
        for match in self.file_rules["file_name"]["match"]:
            if file_name == match:
                return True
        for regex in self.file_rules["file_name"]["regex"]:
            if regex.search(file_name):
                return True
        for match in self.file_rules["file_path"]["match"]:
            if file_path == match:
                return True
        for regex in self.file_rules["file_path"]["regex"]:
            if regex.search(file_path):
                return True
        return False

    @staticmethod
    def _parse_metrics(file_path, fdata):
        """统计py文件有效代码行数"""
        metrics = {
            "lines": 0
        }

        lines = fdata.splitlines()

        def proc(line):
            tmp = line.strip()
            return bool(tmp and not tmp.startswith(b"#"))

        metrics["lines"] += sum(proc(line) for line in lines)

        return metrics

    @staticmethod
    def _parse_ast(fdata):
        """将指定python文件内容解析为ast并返回

        :param fdata: 待解析.py文件内容
        :return: (ast.Module) .py文件的ast
        """
        node = ast.parse(fdata)

        return node

    def print_results_beautiful(self, results: dict):
        """在命令行模式下美观打印结果"""
        print("Scan finished")
        print("Total time used:", results["total_time"])
        print("Totally scanned files:", results["metrics"]["total"]["files"],
              ", lines:", results["metrics"]["total"]["lines"])
        print("Totally found issues:", results["metrics"]["total"]["cnt"], ", low:", results["metrics"]["total"]["low"],
              ", medium:", results["metrics"]["total"]["medium"], ", high:", results["metrics"]["total"]["high"])
        if results["metrics"]["total"]["cnt"] == 0:
            print("\nNo issue is found.")
        else:
            print("\nResults are as below:")
            for file_path, issues in results["issues"].items():
                if issues:
                    print("=====================================================================")
                    print("File name:", file_path)
                    print("Scanned lines:", results["metrics"][file_path]["total"]["lines"],
                          ", found issues:", results["metrics"][file_path]["total"]["cnt"],
                          ", low:", results["metrics"][file_path]["total"]["low"],
                          ", medium:", results["metrics"][file_path]["total"]["medium"],
                          ", high:", results["metrics"][file_path]["total"]["high"])
                    for issue in issues:
                        self._print_issue_beautiful(issue)

    def _print_issue_beautiful(self, issue: dict):
        """美观打印issue"""
        print("Issue:")
        print("\tid:".expandtabs(4), issue["id"])
        print("\tname:".expandtabs(4), issue["name"])
        print("\tseverity:".expandtabs(4), prs_issue.SEVERITY.rank_number_to_str(issue["severity"]))
        print("\tconfidence:".expandtabs(4), prs_issue.CONFIDENCE.rank_number_to_str(issue["confidence"]))
        print("\tmessage:".expandtabs(4), issue["msg"])

        print("\ttaint:".expandtabs(4))
        print("\t\tid:".expandtabs(4), issue["taint"]["id"])
        print("\t\taccordance:".expandtabs(4), issue["taint"]["accordance"])
        print("\t\ttainted by:".expandtabs(4), issue["taint"][issue["taint"]["accordance"]])
        print("\t\tlineno:".expandtabs(4), issue["taint"]["lineno"], ", col offset:", issue["taint"]["col_offset"])
        print("\t\tend lineno:".expandtabs(4), issue["taint"]["end_lineno"], ", end col offset:", issue["taint"]["end_col_offset"])

        print("\tsink:".expandtabs(4))
        print("\t\tid:".expandtabs(4), issue["sink"]["id"])
        print("\t\taccordance:".expandtabs(4), issue["sink"]["accordance"])
        print("\t\tsinked at:".expandtabs(4), issue["sink"][issue["sink"]["accordance"]])
        print("\t\tlineno:".expandtabs(4), issue["sink"]["lineno"], ", col offset:", issue["sink"]["col_offset"])
        print("\t\tend lineno:".expandtabs(4), issue["sink"]["end_lineno"], ", end col offset:", issue["sink"]["end_col_offset"])
