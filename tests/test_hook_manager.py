from inbox_mcp.hook import decide_stop, start_context


def message(id, severity, announced=False, body="text"):
    return {
        "id": id,
        "from": "alice",
        "severity": severity,
        "body": body,
        "thread_id": id,
        "announced": announced,
    }


def test_stop_is_allowed_with_an_empty_inbox():
    assert decide_stop("sid-b", []) == (None, [])


def test_stop_is_blocked_while_a_blocking_message_is_open():
    messages = [message(1, "blocking", body="fix the build")]

    for _ in range(2):  # blocks every time, announced or not
        output, announced = decide_stop("sid-b", messages)
        assert output["decision"] == "block"
        assert "[#1] blocking" in output["reason"] and "fix the build" in output["reason"]
        assert "sid-b" in output["reason"]
        assert announced == []
        messages[0]["announced"] = True


def test_new_non_blocking_messages_are_announced_without_blocking():
    messages = [message(1, "important", body="review this"), message(2, "normal", body="fyi")]

    output, announced = decide_stop("sid-b", messages)

    assert "decision" not in output
    specific = output["hookSpecificOutput"]
    assert specific["hookEventName"] == "Stop"
    assert "2 new message(s)" in specific["additionalContext"]
    assert "review this" in specific["additionalContext"] and "fyi" in specific["additionalContext"]
    assert announced == [1, 2]


def test_announced_messages_do_not_hold_the_session_again():
    messages = [message(1, "important", announced=True), message(2, "normal", announced=True)]
    assert decide_stop("sid-b", messages) == (None, [])


def test_only_the_new_messages_are_announced():
    messages = [message(1, "normal", announced=True, body="old one"), message(2, "normal")]

    output, announced = decide_stop("sid-b", messages)

    assert announced == [2]
    assert "old one" not in output["hookSpecificOutput"]["additionalContext"]


def test_block_reason_also_announces_new_non_blocking_messages():
    messages = [message(1, "blocking", body="stop now"), message(2, "normal", body="by the way")]

    output, announced = decide_stop("sid-b", messages)

    assert output["decision"] == "block"
    assert "stop now" in output["reason"] and "by the way" in output["reason"]
    assert announced == [2]


def test_start_context_for_new_and_registered_sessions():
    new = start_context({"session_id": "sid-n", "registered": False, "name": None, "messages": []})
    assert "sid-n" in new and "not registered" in new

    known = start_context(
        {"session_id": "sid-b", "registered": True, "name": "bob", "messages": [message(1, "normal")]}
    )
    assert "registered as 'bob'" in known and "1 open" in known and "`pick`" in known
