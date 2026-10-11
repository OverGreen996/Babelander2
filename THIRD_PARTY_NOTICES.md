# 第三方元件與授權聲明 · alpha24

Babelander 自有內容依 [LICENSE](LICENSE) 提供。第三方著作權仍屬原作者，其原始授權不因本程式的 All Rights Reserved 條款而縮減。

## Qt / PySide / Shiboken

Qt、PySide6 與 Shiboken6 版本為 **6.11.2**。Copyright The Qt Company Ltd. and other contributors。本發行版使用 LGPLv3 授權選項；原文與上游聲明保留在 [assets/licenses/Qt](assets/licenses/Qt)、[PySide6_Essentials](assets/licenses/PySide6_Essentials)、[shiboken6](assets/licenses/shiboken6)。免安裝包另在 `licenses/` 保留副本。

免安裝版動態載入 Qt Core、Gui、Widgets、Network、Svg、OpenGL 以及平台／圖像／樣式／TLS 外掛。自有介面使用 Widgets 與 QPainter。公開免安裝包移除了開發建置帶入、應用程式未使用的 Qt PDF、QML／Quick、Virtual Keyboard 及軟體 OpenGL DLL；不修改應用程式 EXE 或第三方函式庫內容。

使用者可依適用 LGPL 條款修改、替換及重新連結相容函式庫，並為除錯此類修改進行逆向工程。來源、建置入口及替換方式見 [THIRD_PARTY_SOURCE.md](THIRD_PARTY_SOURCE.md)。

## GEOS 與 Shapely

Shapely **2.2.0** 的 Windows wheel 包含 GEOS **3.14.1** 動態函式庫。GEOS 使用 LGPLv2.1；Shapely 使用其上游 BSD 授權。原始聲明見 [assets/licenses/shapely](assets/licenses/shapely)，GEOS 對應來源隨同版 Release 提供。

## OCR、Python 與其他相依元件

- Python：PSF 與其所含第三方授權，見 [assets/licenses/Python](assets/licenses/Python)。
- RapidOCR **3.9.2** 及內附 OCR 資產：保留上游 Apache-2.0、模型聲明與來源資訊。來源：[RapidOCR](https://github.com/RapidAI/RapidOCR)、[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)。
- ONNX Runtime：MIT；OpenCC：Apache-2.0；OpenCV：Apache-2.0 及所含元件聲明；NumPy：BSD 與其所含元件授權。
- PyInstaller **6.22.3**：GPL 與 bootloader distribution exception；原文見 [assets/licenses/pyinstaller](assets/licenses/pyinstaller)。
- 其餘元件的版本與保留文本入口列於 [assets/dependencies.json](assets/dependencies.json)，完整原文位於 [assets/licenses](assets/licenses)。這是建置環境清單，不表示每個建置工具都會在使用者電腦執行。公開免安裝包另附 `BUNDLED_DEPENDENCIES.json`，從封裝輸入建立實際套件清單。

Windows／Microsoft runtime 依原始散布條款提供；不屬於 Babelander 自有內容。

## 使用者主動下載的模型與 runtime

免安裝包**不含 Qwen 翻譯模型或 llama.cpp／CUDA runtime**。使用者在設定內明確下載後，從上游取得對應檔案：

| 元件 | 上游 |
|---|---|
| Qwen3-1.7B · Q4_K_M 轉換 | [Qwen 模型與授權](https://huggingface.co/Qwen/Qwen3-1.7B)、[bartowski GGUF](https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF) |
| llama.cpp b10896 | [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp)，MIT |
| CUDA runtime | [NVIDIA CUDA 條款](https://docs.nvidia.com/cuda/eula/index.html) |

相關資產網址與校驗值由應用程式的 [資源清單](babelander/assets.py) 固定；上游授權與聲明仍適用。

## 原創素材

README 封面是程式生成的 SVG／PNG，介面截圖與卡片圖的製作方式見 [ASSET_PROVENANCE.md](ASSET_PROVENANCE.md)。測試字典的一般短詞不因本專案授權成為專有著作。
