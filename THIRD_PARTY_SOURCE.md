# 對應第三方來源與替換方式 · alpha24

官方發布位置：[OverGreen996/Babelander2 · v2.0.0a24](https://github.com/OverGreen996/Babelander2/releases/tag/v2.0.0a24)。

同版 Release 提供以下未修改上游來源，與免安裝二進位檔一起保留。下載不需付費或另行索取許可。來源網址、大小與 SHA-256 見 [third_party_sources.json](third_party_sources.json)，Release 另附 `SHA256SUMS.txt`。

| 對應元件 | 來源附件 |
|---|---|
| Qt Core / Gui / Widgets / Network / OpenGL、基礎外掛 · 6.11.2 | [qtbase-everywhere-src-6.11.2.tar.xz](https://github.com/OverGreen996/Babelander2/releases/download/v2.0.0a24/qtbase-everywhere-src-6.11.2.tar.xz) |
| Qt SVG / SVG 外掛 · 6.11.2 | [qtsvg-everywhere-src-6.11.2.tar.xz](https://github.com/OverGreen996/Babelander2/releases/download/v2.0.0a24/qtsvg-everywhere-src-6.11.2.tar.xz) |
| 額外圖像外掛 · 6.11.2 | [qtimageformats-everywhere-src-6.11.2.tar.xz](https://github.com/OverGreen996/Babelander2/releases/download/v2.0.0a24/qtimageformats-everywhere-src-6.11.2.tar.xz) |
| PySide6 / Shiboken6、生成器、typesystems、建置腳本 · 6.11.2 | [pyside-setup-everywhere-src-6.11.2.tar.xz](https://github.com/OverGreen996/Babelander2/releases/download/v2.0.0a24/pyside-setup-everywhere-src-6.11.2.tar.xz) |
| Shapely wheel 內的 GEOS · 3.14.1 | [geos-3.14.1.tar.bz2](https://github.com/OverGreen996/Babelander2/releases/download/v2.0.0a24/geos-3.14.1.tar.bz2) |

各附件包含上游授權及建置入口。本程式未修改這些第三方函式庫來源。

## 建置與替換

1. 關閉 Babelander，備份整個免安裝資料夾；在測試副本操作。
2. 使用相同版本、Windows x64 與相容 MSVC／Windows SDK，依 source archive 的 README、CMakeLists.txt 與 configure／setup.py 建置共享函式庫。保留 ABI 與模組相依一致。參考 [Qt Windows 建置](https://doc.qt.io/qt-6/windows-building.html)、[Qt for Python 建置](https://doc.qt.io/qtforpython-6/building_from_source/index.html) 與 GEOS archive 的 README。
3. Qt DLL、PySide `.pyd` 與 `pyside6.abi3.dll` 位於 `_internal/PySide6/`，外掛位於其 `plugins/`；Shiboken 位於 `_internal/shiboken6/`。GEOS DLL 位於 `_internal/shapely.libs/`；wheel 的雜湊檔名需與 loader 相符，或依 Shapely 上游方法重建相容 binding。
4. 替換測試副本中的相容檔案；不要混用不相容的 Qt DLL 與外掛。應用程式沒有鎖定這些函式庫的簽章、校驗值或啟動還原機制。
5. 執行 `Babelander2.exe` 測試介面與 OCR。本機模型設定完成後，可執行 `Babelander2.exe --self-test --report self-test.json`，檢查封裝功能。

LGPL 允許的函式庫修改、替換、重新連結與為除錯該等修改的逆向工程，不受 Babelander 自有內容授權縮減。第三方元件的合法散布依各自授權辦理。下載或來源附件有問題，可在官方儲存庫開 Issue。
