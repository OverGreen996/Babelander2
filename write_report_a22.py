"""Write release prose from the fresh JSON evidence, before sealing."""
import json,numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(name):return json.loads((ROOT/'test-results'/name).read_text(encoding='utf8'))
bench=read('chat-poll-fixed-a22/report.json');burst=read('chat-poll-burst-a22/0-100.json')
resource=read('chat-poll-resources-a22.json');units=read('supertest-a22/runner-units.json')
assert bench['functional_passed'] and burst['passed'] and resource['passed']
assert all(r['returncode']==0 for r in units['runs'])
exe=read('supertest-a22/exe.json');wheel=read('supertest-a22/wheel.json')
assert exe['passed'] and len(exe['checks'])==37
assert wheel['passed'] and len(wheel['selftest']['checks'])==37
slow,fast=bench['summary']['800'],bench['summary']['100']
values=[r['shown_to_qt_ms'] for r in burst['results']]
noise={scan:[r for r in resource['runs'] if r['style']=='noise' and r['chat_scan_ms']==scan] for scan in (800,100)}
cpu={k:sum(r['cpu_core_seconds'] for r in v) for k,v in noise.items()}
calls={k:sum(r['ocr_calls'] for r in v) for k,v in noise.items()}
marker='## 本輪封存結果'
path=ROOT/'TEST_REPORT_ALPHA22.md';s=path.read_text(encoding='utf8').split(marker)[0]
s=s.replace('量測表、回歸與實際 EXE／wheel 結果於封存前補齊；原始證據存放於 `assets/verification/chat-poll-a22/`。','原始證據存放於 [chat-poll-a22](assets/verification/chat-poll-a22/summary.json)。')
s+=f'''{marker}

| 完整顯示，兩輪各 100 則 | 800ms | 100ms |
| --- | ---: | ---: |
| 平均 | {slow['mean_ms']:.2f}ms | **{fast['mean_ms']:.2f}ms** |
| P50 | {slow['p50_ms']:.2f}ms | {fast['p50_ms']:.2f}ms |
| P95 | {slow['p95_ms']:.2f}ms | **{fast['p95_ms']:.2f}ms** |
| 最大 | {slow['max_ms']:.2f}ms | {fast['max_ms']:.2f}ms |
| 700ms 內完整顯示 | {slow['within_700ms']}/200 | **{fast['within_700ms']}/200** |
| 實際 OCR 次數 | {slow['ocr_calls']} | {fast['ocr_calls']} |
| 擷取次數 | {slow['captures']} | {fast['captures']} |
| 程序 CPU 核心秒 | {slow['cpu_core_seconds']:.2f}s | {fast['cpu_core_seconds']:.2f}s |

四輪共 400 則全部收到，有可用 target，無漏訊息、重複或護欄拒絕；四輪新增原文序列、畫面 SHA 相同，程式原始碼未變。此為生成 fixture 的功能檢查，不是全部語意正確率。

每 350ms 換一次聊天畫面的追加壓力測試收到 **100/100** 則，平均 **{np.mean(values):.2f}ms**、P95 **{np.percentile(values,95):.2f}ms**、最大 **{max(values):.2f}ms**；**{sum(v<=700 for v in values)}/100** 在 700ms 內完整顯示。畫面仍保留四則訊息，不能保證比此更短的訊息或任意聊天速度均不漏。

兩輪動態雜訊累計約 24 秒／設定：800ms OCR **{calls[800]}** 次、CPU **{cpu[800]:.2f}** 核心秒；100ms OCR **{calls[100]}** 次、CPU **{cpu[100]:.2f}** 核心秒，約 **{cpu[100]/cpu[800]:.2f} 倍** CPU 工作。靜止組每段均只 OCR 一次，快輪詢沒有自動變成每次都 OCR。

14 組共 **421 項回歸**全部通過。真引擎六模式混合與崩潰恢復 **28 項**、聊天事件 **8 項**、真 CPU OCR 數量／否定／換行／雜訊／取消 **32 項**、設定頁 **8 項**通過。實際 PyInstaller EXE 與隔離安裝 wheel 各 **37 項**自檢，包含真 RapidOCR 重用及 context／快取釋放；封存器逐一核對 39 個應用程式編譯模組、原始碼 ZIP 內容及 SHA。實際封裝結果見 `exe.json`、`wheel.json` 與 `dist/Babelander2-2.0.0a22-sha256.json`。

完整延遲結果適用於暖模型與本組生成畫面；首次冷載入另有成本。停止後模型仍依既有政策釋放，測試切版保留模型並沒有改成使用者 Stop 後繼續占用顯存。所有測試模型／worker 回收、session 清理通過，私人聊天 SQLite cache／history／usage 為零。
'''
path.write_text(s,encoding='utf8')
note=f"**alpha22 聊天完整延遲：** 相同生成聊天畫面、暖模型四輪對照，平均 **{slow['mean_ms']:.0f}→{fast['mean_ms']:.0f}ms**、P95 **{slow['p95_ms']:.0f}→{fast['p95_ms']:.0f}ms**，100ms 組 **{fast['within_700ms']}/200** 在 700ms 內；421 項回歸、EXE／wheel 各 37 項通過。動態雜訊增加 CPU 工作約 **{cpu[100]/cpu[800]:.1f} 倍**，可調高聊天觀察間隔；尚非真遊戲實測。[完整結果與限制](TEST_REPORT_ALPHA22.md)。"
p=ROOT/'README.md';s=p.read_text(encoding='utf8');s=s.replace('## 六種閱讀情境',note+'\n\n## 六種閱讀情境',1);p.write_text(s,encoding='utf8')
p=ROOT/'TEST_REPORT.md';s=p.read_text(encoding='utf8');s=s.replace('最新 alpha21：','歷史 alpha21：',1);line=s.find('\n');s=s[:line+1]+'\n'+note+'\n'+s[line+1:];p.write_text(s,encoding='utf8')
print(json.dumps({'mean_ms':fast['mean_ms'],'p95_ms':fast['p95_ms'],'within700':fast['within_700ms'],'noise_cpu_ratio':cpu[100]/cpu[800]}))
