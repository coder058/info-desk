from infodesk.store import Store


def test_reject_writes_zero_notes():
    store = Store()
    draft = store.insert_draft("c", "publish_draft", "h", "body", "heuristic")
    assert store.reject(draft)
    assert store.note_count() == 0
    assert store.approved_write_count() == 0


def test_approve_only_for_publish_draft():
    store = Store()
    held = store.insert_draft("c", "hold", "h", "nope", "heuristic")
    assert store.approve(held) is False
    assert store.note_count() == 0
    publish = store.insert_draft("c", "publish_draft", "h", "ok", "heuristic")
    assert store.approve(publish)
    assert store.note_count() == 1
    assert store.approved_write_count() == 1


def test_duplicate_body_does_not_insert_second_draft():
    store = Store()
    first = store.insert_draft("c", "verify_first", "h", "same", "heuristic")
    second = store.insert_draft("c", "verify_first", "h", "same", "heuristic")
    assert first == second
    rows = store.conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
    assert rows == 1
