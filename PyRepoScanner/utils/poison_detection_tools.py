import itertools


def detect_levenshtein(str1: str, str2: str, distance: int = 1):
    """比较两个字符串间的Levenshtein距离

    :param str1: 待比较的第一个字符串
    :param str2: 待比较的第二个字符串
    :param distance: 规定的字符间距
    :return: True/False: 在/不在距离内
    """
    if 0 < cal_levenshtein_distance(str1, str2) <= distance:
        return True
    return False


def cal_levenshtein_distance(str1: str, str2: str):
    """动态规划计算两个字符串间的Levenshtein距离

    :param str1: 第一个字符串
    :param str2: 第二个字符串
    :return: 字符编辑距离
    """
    m = len(str1)
    n = len(str2)
    # 初始化(m+1)*(n+1)距离矩阵, d[i][j]表示str1的前i位到str2的前j位间的编辑距离
    d = [[0] * (n + 1) for i in range(m + 1)]
    # 初始化第一行和第一列
    for i in range(m + 1):
        d[i][0] = i
    for j in range(n + 1):
        d[0][j] = j
    # 计算距离矩阵
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            # str1的第i位和str2的第j位字符相同，则d[i][j]=d[i-1][j-1]
            if str1[i - 1] == str2[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            # 如果不同，则可以由任一位置加1位变化而来
            else:
                d[i][j] = min(d[i - 1][j], d[i][j - 1], d[i - 1][j - 1]) + 1
    # 返回距离矩阵最后一个元素即为最终的距离
    return d[m][n]


def detect_permutation(str1: str, str2: str):
    """检测两个字符串间的一位置换关系

    :return: True/False
    """
    if len(str1) != len(str2):
        return False
    diff_cnt = 0
    perm1 = None
    perm2 = None
    for i in range(len(str1)):
        if str1[i] != str2[i]:
            diff_cnt += 1
            if diff_cnt == 1:
                perm1 = str1[i]
                perm2 = str2[i]
            elif diff_cnt == 2:
                if str1[i] != perm2:
                    return False
                if str2[i] != perm1:
                    return False
            elif diff_cnt > 2:
                return False

    if diff_cnt == 2:
        return True
    return False
