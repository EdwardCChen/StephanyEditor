"""巨集核心邏輯測試。對應 SRS-002 F-MC-*、BR-MC-*、NF-02、NF-03。"""

import json

import pytest

from stephany.core.macro import (
    Macro,
    MacroRecorder,
    MacroStep,
    MacroStore,
    ReplayState,
    coalesce,
    should_continue,
)


# -- 錄製 ---------------------------------------------------------------
def test_f_mc_01_recorder_starts_and_stops():
    rec = MacroRecorder()
    assert rec.recording is False
    rec.start()
    assert rec.recording is True
    rec.record("insert_text", text="a")
    macro = rec.stop()
    assert rec.recording is False
    assert macro.steps == [MacroStep("insert_text", {"text": "a"})]


def test_record_is_a_noop_when_not_recording():
    rec = MacroRecorder()
    rec.record("insert_text", text="a")
    assert rec.stop().steps == []


def test_br_mc_1_consecutive_text_input_is_coalesced():
    rec = MacroRecorder()
    rec.start()
    for ch in "你好世界":
        rec.record("insert_text", text=ch)
    macro = rec.stop()
    assert len(macro) == 1
    assert macro.steps[0].args["text"] == "你好世界"


def test_coalescing_stops_at_a_different_command():
    steps = [
        MacroStep("insert_text", {"text": "a"}),
        MacroStep("insert_text", {"text": "b"}),
        MacroStep("move", {"op": "right"}),
        MacroStep("insert_text", {"text": "c"}),
    ]
    got = coalesce(steps)
    assert [s.command for s in got] == ["insert_text", "move", "insert_text"]
    assert got[0].args["text"] == "ab"
    assert got[2].args["text"] == "c"


def test_cancel_discards_recorded_steps():
    rec = MacroRecorder()
    rec.start()
    rec.record("insert_text", text="x")
    rec.cancel()
    assert rec.recording is False
    assert rec.pending_count == 0


def test_pending_count_tracks_progress_during_recording():
    rec = MacroRecorder()
    rec.start()
    rec.record("move", op="down")
    rec.record("move", op="down")
    assert rec.pending_count == 2


# -- 序列化（NF-02）-----------------------------------------------------
def test_nf_02_step_round_trips_through_json():
    step = MacroStep("block_extend", {"dline": 3, "dcol": -2})
    assert MacroStep.from_dict(json.loads(json.dumps(step.to_dict()))) == step


def test_macro_round_trips_through_json():
    macro = Macro("加前綴", [MacroStep("insert_text", {"text": "※"})])
    assert Macro.from_dict(json.loads(json.dumps(macro.to_dict()))) == macro


def test_step_without_command_is_rejected():
    with pytest.raises(ValueError):
        MacroStep.from_dict({"args": {}})


def test_step_with_non_dict_args_is_rejected():
    with pytest.raises(ValueError):
        MacroStep.from_dict({"command": "x", "args": [1, 2]})


def test_describe_is_human_readable():
    assert MacroStep("move", {"op": "down"}).describe() == "move(op='down')"
    assert MacroStep("bookmark_toggle").describe() == "bookmark_toggle"


# -- 儲存（F-MC-06、NF-03）--------------------------------------------
def test_f_mc_06_store_persists_across_instances(tmp_path):
    path = tmp_path / "macros.json"
    store = MacroStore(path)
    store.add(Macro("加星號", [MacroStep("insert_text", {"text": "★"})]))

    reloaded = MacroStore(path)
    reloaded.load()
    assert reloaded.names() == ["加星號"]
    assert reloaded.macros["加星號"].steps[0].args["text"] == "★"


def test_store_file_is_human_readable_utf8(tmp_path):
    path = tmp_path / "macros.json"
    store = MacroStore(path)
    store.add(Macro("中文名稱", [MacroStep("insert_text", {"text": "測試"})]))
    text = path.read_text(encoding="utf-8")
    assert "中文名稱" in text  # 沒有被 \uXXXX 逃逸掉
    assert "測試" in text


def test_nf_03_corrupt_file_degrades_to_empty_without_raising(tmp_path):
    path = tmp_path / "macros.json"
    path.write_text("{ 這不是合法的 JSON", encoding="utf-8")
    store = MacroStore(path)
    assert store.load() == {}
    assert store.load_error is not None


def test_nf_03_wrong_shape_file_degrades_to_empty(tmp_path):
    path = tmp_path / "macros.json"
    path.write_text(json.dumps({"macros": "不是陣列"}), encoding="utf-8")
    store = MacroStore(path)
    assert store.load() == {}
    assert store.load_error is not None


def test_missing_file_loads_as_empty_without_error(tmp_path):
    store = MacroStore(tmp_path / "nope.json")
    assert store.load() == {}
    assert store.load_error is None


def test_f_mc_05_rename_and_delete(tmp_path):
    store = MacroStore(tmp_path / "m.json")
    store.add(Macro("舊名", [MacroStep("move", {"op": "down"})]))
    store.rename("舊名", "新名")
    assert store.names() == ["新名"]
    assert store.macros["新名"].name == "新名"
    store.delete("新名")
    assert store.names() == []


def test_rename_missing_macro_raises(tmp_path):
    store = MacroStore(tmp_path / "m.json")
    with pytest.raises(KeyError):
        store.rename("不存在", "x")


def test_unnamed_macro_cannot_be_saved(tmp_path):
    store = MacroStore(tmp_path / "m.json")
    with pytest.raises(ValueError):
        store.add(Macro("", []))


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "m.json"
    store = MacroStore(path)
    store.add(Macro("a", []))
    assert list(p.name for p in tmp_path.iterdir()) == ["m.json"]


# -- 重播控制（BR-MC-3）------------------------------------------------
def test_br_mc_3_stops_at_end_of_document():
    state = ReplayState(position=100, length=100, line_count=5)
    assert should_continue(1, state, None) is False


def test_br_mc_3_stops_when_macro_makes_no_progress():
    state = ReplayState(position=10, length=100, line_count=5)
    assert should_continue(1, state, state) is False


def test_br_mc_3_continues_while_advancing():
    prev = ReplayState(position=10, length=100, line_count=5)
    state = ReplayState(position=20, length=100, line_count=5)
    assert should_continue(1, state, prev) is True


def test_br_mc_3_iteration_cap_is_a_hard_stop():
    prev = ReplayState(position=1, length=100, line_count=5)
    state = ReplayState(position=2, length=100, line_count=5)
    assert should_continue(10, state, prev, max_iterations=10) is False
    assert should_continue(9, state, prev, max_iterations=10) is True
