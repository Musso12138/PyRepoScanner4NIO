# monitor用于组件仓库监控
from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class BasicMonitor(ABC):
    """
    BasicMonitor
    为组件仓库监控提供基本模板类
    要求Monitor至少实现以下能力:
    - 获取组件仓库package index
    - 更新已收集的package index
    """

    @abstractmethod
    def monitor(self):
        """
        自动化监控组件仓库的更新状态，应当包括初次全量爬取与后续监控更新。
        """
        pass

    @abstractmethod
    def update(self):
        """
        获取组件仓库距离本地状态的更新，更新本地状态。
        """
        pass
