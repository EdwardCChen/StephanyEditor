# Stephany Editor — 支援中文欄（直行）模式的文字編輯器
# Copyright (C) 2026 Edward Chen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""巨集：語意命令的錄製、序列化與重播控制。

規格：SRS-002 F-MC-01 ~ F-MC-08、BR-MC-1 ~ BR-MC-6、D-01、D-02、D-04、NF-02、NF-03

D-01 —— 為什麼錄「語意命令」而不是原始鍵盤事件：
  原始事件重播會被焦點、輸入法組字狀態、視窗大小影響，換一台機器就跑不出
  同樣結果。改錄「插入文字 X」「游標右移一格」「矩形往下展開 3 行」這種
  語意命令，就能序列化存檔、跨 session 重播，也才有辦法正確重播欄模式操作。

這一層完全不依賴 Qt：它只知道「命令的名字和參數」，怎麼執行是 UI 層的事。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

#: BR-MC-3 的保險絲：避免「直到檔尾」模式在巨集空轉時無窮迴圈
MAX_ITERATIONS = 10_000

#: 可合併的命令（D-02 / BR-MC-1）。目前只有純文字輸入。
COALESCING_COMMANDS = frozenset({"insert_text"})


@dataclass(frozen=True)
class MacroStep:
    """一個語意命令。`args` 必須是可 JSON 序列化的純資料（NF-02）。"""

    command: str
    args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"command": self.command, "args": dict(self.args)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MacroStep":
        command = data.get("command")
        if not isinstance(command, str) or not command:
            raise ValueError("步驟缺少 command 欄位")
        args = data.get("args") or {}
        if not isinstance(args, dict):
            raise ValueError(f"步驟 {command} 的 args 不是物件")
        return cls(command=command, args=args)

    def describe(self) -> str:
        """給巨集管理對話框顯示用的人話描述。"""
        if not self.args:
            return self.command
        parts = ", ".join(f"{k}={v!r}" for k, v in self.args.items())
        return f"{self.command}({parts})"


@dataclass
class Macro:
    """一串命令。name 為空代表「目前錄製的暫存巨集」，尚未命名儲存。"""

    name: str = ""
    steps: list[MacroStep] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.steps)

    def __bool__(self) -> bool:
        return bool(self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "steps": [s.to_dict() for s in self.steps]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Macro":
        steps_data = data.get("steps")
        if not isinstance(steps_data, list):
            raise ValueError("巨集缺少 steps 陣列")
        return cls(
            name=str(data.get("name", "")),
            steps=[MacroStep.from_dict(s) for s in steps_data],
        )

    def renamed(self, name: str) -> "Macro":
        return replace(self, name=name)


def coalesce(steps: Iterable[MacroStep]) -> list[MacroStep]:
    """把連續的文字輸入併成一步（D-02 / BR-MC-1）。

    打 10 個字如果留成 10 個步驟，巨集清單會難以閱讀，重播也要跑 10 次
    文件異動。合併之後「插入『你好世界』」就是一步。
    """
    out: list[MacroStep] = []
    for step in steps:
        if (
            out
            and step.command in COALESCING_COMMANDS
            and out[-1].command == step.command
        ):
            merged = dict(out[-1].args)
            merged["text"] = merged.get("text", "") + step.args.get("text", "")
            out[-1] = MacroStep(step.command, merged)
            continue
        out.append(step)
    return out


class MacroRecorder:
    """錄製中的狀態機（F-MC-01、F-MC-08、BR-MC-5）。"""

    def __init__(self):
        self._recording = False
        self._steps: list[MacroStep] = []
        self.current: Macro = Macro()

    @property
    def recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        self._recording = True
        self._steps = []

    def record(self, command: str, **args: Any) -> None:
        """錄一個命令。沒在錄製時是 no-op，呼叫端不必每次都判斷。"""
        if not self._recording:
            return
        self._steps.append(MacroStep(command, args))

    def stop(self) -> Macro:
        """停止並把錄到的步驟收成 `current`，同時回傳它。"""
        self._recording = False
        self.current = Macro(steps=coalesce(self._steps))
        self._steps = []
        return self.current

    def cancel(self) -> None:
        self._recording = False
        self._steps = []

    @property
    def pending_count(self) -> int:
        """錄製中已經錄到幾步（狀態列顯示用）。"""
        return len(self._steps)


@dataclass(frozen=True)
class ReplayState:
    """一次迭代結束後的文件狀態，用來判斷巨集是否還在前進。"""

    position: int
    length: int
    line_count: int


def should_continue(
    iteration: int,
    state: ReplayState,
    previous: ReplayState | None,
    *,
    max_iterations: int = MAX_ITERATIONS,
) -> bool:
    """「直到檔尾」模式的續跑判斷（BR-MC-3）。

    停止條件有三個，任一成立就停：
      1. 迭代次數達上限（保險絲，防巨集空轉造成無窮迴圈）
      2. 游標已到文件結尾——再跑也沒有東西可處理
      3. 這一輪跑完游標位置、文件長度、行數全都沒變——巨集在空轉
    """
    if iteration >= max_iterations:
        return False
    if state.position >= state.length:
        return False
    if previous is not None and state == previous:
        return False
    return True


class MacroStore:
    """把已命名的巨集存成 JSON（D-04、F-MC-06、NF-02、NF-03）。"""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.macros: dict[str, Macro] = {}
        self.load_error: str | None = None

    def load(self) -> dict[str, Macro]:
        """載入。檔案損毀時退回空清單並記下錯誤，絕不讓程式無法啟動（NF-03）。"""
        self.load_error = None
        self.macros = {}
        if not self.path.exists():
            return self.macros
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            entries = raw["macros"] if isinstance(raw, dict) else raw
            if not isinstance(entries, list):
                raise ValueError("頂層的 macros 不是陣列")
            for entry in entries:
                macro = Macro.from_dict(entry)
                if macro.name:
                    self.macros[macro.name] = macro
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.load_error = f"{self.path} 無法讀取（{exc}），已略過已存巨集。"
            self.macros = {}
        return self.macros

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "macros": [m.to_dict() for m in self.macros.values()],
        }
        # 先寫暫存檔再置換，避免寫到一半斷電留下半個檔案
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self.path)

    def add(self, macro: Macro) -> None:
        if not macro.name:
            raise ValueError("巨集必須有名稱才能儲存")
        self.macros[macro.name] = macro
        self.save()

    def rename(self, old: str, new: str) -> None:
        if old not in self.macros:
            raise KeyError(old)
        if not new:
            raise ValueError("巨集名稱不可為空")
        macro = self.macros.pop(old)
        self.macros[new] = macro.renamed(new)
        self.save()

    def delete(self, name: str) -> None:
        self.macros.pop(name, None)
        self.save()

    def names(self) -> list[str]:
        return sorted(self.macros)


def default_store_path() -> Path:
    """D-04：巨集存在使用者設定目錄，人類可讀可手改。

    目錄位置各平台不同（SRS-005 D-06），由 `stephany.platforms` 決定；
    那個模組同樣不相依 Qt，所以 core 仍然是純邏輯。
    """
    from ..platforms import config_dir

    return config_dir() / "macros.json"
