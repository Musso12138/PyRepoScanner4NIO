"""
提供包安全检测的基本模板类
"""


from abc import abstractmethod


class BasicScanner:
    """
    BasicScanner为扫描器提供基本模板类。
    要求扫描器至少具备以下能力：
    - 加载规则集
    - 扫描本地包
    """
    @abstractmethod
    def load_rules(self, rule_path, form):
        """
        加载规则集
        :param rule_path: 规则文件地址
        :param form: 规则集格式
        """
        pass

    @abstractmethod
    def scan_local_file(self, file_path):
        """
        检测已存储在本地的包文件
        :param file_path: 本地包文件地址
        """
        pass

