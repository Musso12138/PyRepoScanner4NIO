from enum import Enum
from dataclasses import dataclass


class SEVERITY:
    UNDEFINED = 0
    LOW = 0
    MEDIUM = 4
    HIGH = 7

    @staticmethod
    def rank_number_to_str(rank: float):
        if rank >= SEVERITY.HIGH:
            return "high"
        elif rank >= SEVERITY.MEDIUM:
            return "medium"
        elif rank >= SEVERITY.LOW:
            return "low"


class CONFIDENCE:
    UNDEFINED = 0
    LOW = 0
    MEDIUM = 4
    HIGH = 7

    @staticmethod
    def rank_number_to_str(rank: float):
        if rank >= CONFIDENCE.HIGH:
            return "high"
        elif rank >= CONFIDENCE.MEDIUM:
            return "medium"
        elif rank >= CONFIDENCE.LOW:
            return "low"


@dataclass
class Taint:
    """存放taint信息"""
    id: str
    accordance: str
    type: str = None
    function: str = None
    attribute: str = None
    position: str = None
    keyword: str = None
    lineno: int = -1
    col_offset: int = -1
    end_lineno: int = -1
    end_col_offset: int = -1

    def __eq__(self, other):
        if isinstance(other, Taint):
            return self.__dict__ == other.__dict__
        return False

@dataclass
class Sink:
    """存放sink信息，仅存放ast.Call function对应的具体sink"""
    id: str
    accordance: str
    function: str = ""
    type: str = ""
    position: int = None
    keyword: str = None
    lineno: int = 0
    col_offset: int = 0
    end_lineno: int = 0
    end_col_offset: int = 0

    def __eq__(self, other):
        if isinstance(other, Sink):
            return self.__dict__ == other.__dict__
        return False


@dataclass
class Issue:
    """用于存放一条检测结果"""
    id: str
    name: str
    taint: Taint
    sink: Sink
    severity: float = SEVERITY.UNDEFINED
    confidence: float = CONFIDENCE.UNDEFINED
    msg: str = ""
    file_path: str = ""

    def __eq__(self, other):
        if isinstance(other, Issue):
            return self.dict() == other.dict()
        elif isinstance(other, dict):
            return self.dict() == other
        return False

    def dict(self):
        issue_dict = self.__dict__
        if isinstance(issue_dict["taint"], Taint):
            issue_dict["taint"] = self.taint.__dict__
        if isinstance(issue_dict["sink"], Sink):
            issue_dict["sink"] = self.sink.__dict__
        return issue_dict
