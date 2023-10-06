import PyRepoScanner.utils.issue as prs_issue


def test_SEVERITY():
    i = prs_issue.Issue(
        id="1001",
        name="exec",
        taint=prs_issue.Taint(
            id="0000",
            accordance="type",
            type="input",
            lineno=10,
            end_lineno=10
        ),
        sink=prs_issue.Sink(
            id="0001",
            accordance="function",
            function="exec",
            lineno=10,
            end_lineno=10
        ),
        severity=prs_issue.SEVERITY.MEDIUM
    )

    j = prs_issue.Issue(
        id="1001",
        name="exec",
        taint=prs_issue.Taint(
            id="0000",
            accordance="type",
            type="input",
            lineno=10,
            end_lineno=10
        ),
        sink=prs_issue.Sink(
            id="0001",
            accordance="function",
            function="exec",
            lineno=10,
            end_lineno=10
        ),
        severity=prs_issue.SEVERITY.MEDIUM
    )

    print(i == j)
