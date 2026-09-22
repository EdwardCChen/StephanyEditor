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

"""隨套件一起安裝的資源檔（圖示等）。"""

from pathlib import Path

RESOURCE_DIR = Path(__file__).parent
ICON_SVG = RESOURCE_DIR / "stephany-editor.svg"

#: 工具列的單色圖示（SRS-007）。應用程式圖示是彩色的，用途不同，分開放。
ICON_DIR = RESOURCE_DIR / "icons"
