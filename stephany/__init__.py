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

"""Stephany Editor — 支援中文欄（直行）模式的文字編輯器。"""

__version__ = "0.9.0"

#: 應用程式識別碼。三個平台都拿它當身分的根：
#: Linux 的 `.desktop` 檔名與 Wayland `app_id`（SRS-004 D-01）、
#: macOS 的 `CFBundleExecutable`（SRS-005 D-01）、
#: Windows 的執行檔名稱（SRS-006 D-W1）。
APP_ID = "stephany-editor"

#: 反向網域名稱形式的識別碼。macOS 的 `CFBundleIdentifier` 與 Windows 的
#: `AppUserModelID` 必須是同一個字串（BR-MAC-5、BR-WIN-3）——兩邊各寫一次
#: 字面值遲早會漂移，所以來源只有這裡一個。
BUNDLE_ID = f"io.github.edwardcchen.{APP_ID}"
