from PyRepoScanner.utils.poison_detection_tools import *


def test_detect_levenshtein():
    assert detect_levenshtein("alice", "alic3") == True
    assert detect_levenshtein("alice", "allice") == True
    assert detect_levenshtein("alice", "alie") == True
    assert detect_levenshtein("alice", "aice") == True
    assert detect_levenshtein("alice", "aalice") == True
    assert detect_levenshtein("alice", "aallice") == False
    assert detect_levenshtein("alice", "alice") == False


def test_detect_permutation():
    assert detect_permutation("alice", "ailce") == True
    assert detect_permutation("alice", "alice") == False
    assert detect_permutation("alice", "alcie") == True
    assert detect_permutation("alice", "alice1") == False
    assert detect_permutation("alice", "cliae") == True
    assert detect_permutation("alice", "aicle") == False

    assert detect_permutation("aaabbb", "ababba") == True
    assert detect_permutation("aaabbb", "baabab") == True
    assert detect_permutation("aaabbb", "aabbba") == True
