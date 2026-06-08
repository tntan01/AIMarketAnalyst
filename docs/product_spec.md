# AI Market Analyst â€" Äáo·c táo£ sáo£n pháo©m v12

> **PhiÃan báo£n:** v1.0 | **Cáo­p nháo­t:** 2026-05-29 | **Bá»• sung:** nguyÃan táo ̄c giao diá»‡n full-screen responsive
>
> **NgÆ°á»i dÃ1ng:** 1 ngÆ°á»i dÃ1ng cÃ¡ nhÃ¢n.
>
> **Má»¥c tiÃau:** XÃ¢y dá»±ng cÃ ́ng cá»¥ cÃ¡ nhÃ¢n giÃop phÃ¢n tÃ­ch Forex (thá»‹ trÆ°á»ng ngoáo¡i há»'i) nhanh hÆ¡n, cÃ3 há»‡ thá»'ng hÆ¡n, giáo£m cáo£m tÃ­nh khi ra quyáo¿t Ä'á»‹nh.
>
> **NguyÃan táo ̄c cá»'t lÃμi:** Dá» ̄ liá»‡u giÃ¡ vÃ  chá»‰ bÃ¡o ká»1 thuáo­t pháo£i Ä'Æ°á»£c tá»± tÃ­nh tá»« raw data (dá» ̄ liá»‡u thÃ ́). AI (trÃ­ tuá»‡ nhÃ¢n táo¡o) chá»‰ dÃ1ng Ä'á»ƒ diá»...n giáo£i, tÃ3m táo ̄t tin tá»©c, Ä'Ã¡nh giÃ¡ bá»'i cáo£nh vÄ© mÃ ́ vÃ  viáo¿t nháo­n Ä'á»‹nh. AI khÃ ́ng Ä'Æ°á»£c tá»± bá»‹a giÃ¡, chá»‰ bÃ¡o, entry (Ä'iá»ƒm vÃ o lá»‡nh), SL (stop loss â€" cáo ̄t lá»-), TP (take profit â€" chá»'t lá»i) hoáo·c lot (khá»'i lÆ°á»£ng giao dá»‹ch).

---

## 1. Äá»‹nh vá»‹ sáo£n pháo©m

### 1.1 TÃan sáo£n pháo©m

**AI Market Analyst**

### 1.2 Chá»©c nÄƒng chÃ­nh

NgÆ°á»i dÃ1ng cÃ3 thá»ƒ chá»n má»TMt trong hai cháo¿ Ä'á»TM phÃ¢n tÃ­ch:

- **Single Analysis Mode (cháo¿ Ä'á»TM phÃ¢n tÃ­ch má»TMt mÃ£):** chá»n 1 mÃ£ giao dá»‹ch Forex hoáo·c XAU/USD Ä'á»ƒ phÃ¢n tÃ­ch Ä'áo§y Ä'á»§.
- **Scanner Mode (cháo¿ Ä'á»TM quÃ©t thá»‹ trÆ°á»ng):** quÃ©t nhanh toÃ n bá»TM danh sÃ¡ch mÃ£ MVP Ä'á»ƒ tÃ¬m mÃ£ cÃ3 setup (thiáo¿t láo­p giao dá»‹ch) Ä'Ã¡ng chÃo Ã1⁄2.

á»ž Single Analysis Mode, há»‡ thá»'ng sáo1⁄2:

1. Láo¥y OHLCV (Open/High/Low/Close/Volume â€" giÃ¡ má»Ÿ cá»­a/cao nháo¥t/tháo¥p nháo¥t/Ä'Ã3ng cá»­a/khá»'i lÆ°á»£ng) tá»« API (giao diá»‡n láo­p trÃ¬nh á»©ng dá»¥ng).
2. Tá»± tÃ­nh cÃ¡c chá»‰ bÃ¡o ká»1 thuáo­t báo±ng Python.
3. XÃ¡c Ä'á»‹nh Market Regime (tráo¡ng thÃ¡i thá»‹ trÆ°á»ng).
4. XÃ¡c Ä'á»‹nh Direction Bias (thiÃan hÆ°á»›ng giao dá»‹ch).
5. Cháo¥m Ä'iá»ƒm riÃang tá»«ng ká»‹ch báo£n buy (mua), sell (bÃ¡n), hoáo·c stand aside (Ä'á»©ng ngoÃ i).
6. Táo¡o Trade Plan (káo¿ hoáo¡ch giao dá»‹ch) gá»"m entry zone (vÃ1ng vÃ o lá»‡nh), stop loss (cáo ̄t lá»-), take profit (chá»'t lá»i), risk/reward (tá»· lá»‡ rá»§i ro/lá»£i nhuáo­n), position sizing (tÃ­nh khá»'i lÆ°á»£ng vÃ o lá»‡nh).
7. DÃ1ng AI Ä'á»ƒ viáo¿t nháo­n Ä'á»‹nh dá»... hiá»ƒu báo±ng tiáo¿ng Viá»‡t dá»±a trÃan dá» ̄ liá»‡u Ä'Ã£ Ä'Æ°á»£c há»‡ thá»'ng tÃ­nh sáoμn.
8. Hiá»ƒn thá»‹ káo¿t quáo£ trÃan giao diá»‡n desktop PyQt6 vÃ  lÆ°u journal (nháo­t kÃ1⁄2 giao dá»‹ch) vÃ o SQLite.

á»ž Scanner Mode, há»‡ thá»'ng sáo1⁄2 quÃ©t nhanh toÃ n bá»TM 28 cáo·p Forex vÃ  XAU/USD báo±ng Rule Engine trÆ°á»›c, chá»‰ gá»i AI Ä'á»ƒ viáo¿t nháo­n Ä'á»‹nh chi tiáo¿t cho cÃ¡c mÃ£ tháo­t sá»± Ä'Ã¡ng chÃo Ã1⁄2.

### 1.3 Nhá» ̄ng viá»‡c sáo£n pháo©m khÃ ́ng lÃ m

- KhÃ ́ng auto trade (tá»± Ä'á»TMng giao dá»‹ch).
- KhÃ ́ng gá»­i lá»‡nh trá»±c tiáo¿p lÃan sÃ n.
- KhÃ ́ng cam káo¿t tháo ̄ng lá»‡nh.
- KhÃ ́ng Ä'á»ƒ AI tá»± láo¥y giÃ¡ hoáo·c tá»± tÃ­nh chá»‰ bÃ¡o báo±ng cÃ¡ch Ä'oÃ¡n.
- KhÃ ́ng dÃ1ng dá» ̄ liá»‡u ngoÃ i MT5/broker Ä'á»ƒ táo¡o tráo¡ng thÃ¡i READY TO ENTER (sáoμn sÃ ng vÃ o lá»‡nh).

### 1.4 NguyÃan táo ̄c hiá»ƒn thá»‹ báo ̄t buá»TMc

Má»-i káo¿t quáo£ phÃ¢n tÃ­ch luÃ ́n pháo£i cÃ3:

- Ká»‹ch báo£n Æ°u tiÃan.
- Ká»‹ch báo£n thay tháo¿ náo¿u cÃ3.
- LÃ1⁄2 do nÃan Ä'á»©ng ngoÃ i náo¿u Ä'iá»u kiá»‡n xáo¥u.
- Äiá»ƒm cháo¥t lÆ°á»£ng tá»«ng ká»‹ch báo£n.
- Äiá»u kiá»‡n kÃ­ch hoáo¡t lá»‡nh.
- Äiá»u kiá»‡n vÃ ́ hiá»‡u ká»‹ch báo£n.
- VÃ1ng giÃ¡ vÃ o lá»‡nh, cáo ̄t lá»-, chá»'t lá»i.
- Tá»· lá»‡ risk/reward (rá»§i ro/lá»£i nhuáo­n).
- Position sizing (khá»'i lÆ°á»£ng vÃ o lá»‡nh) theo tÃ i khoáo£n vÃ  má»©c rá»§i ro.
- Cáo£nh bÃ¡o dá» ̄ liá»‡u chá»‰ mang tÃ­nh phÃ¢n tÃ­ch, khÃ ́ng pháo£i giÃ¡ broker (sÃ n giao dá»‹ch) tháo­t náo¿u Ä'ang dÃ1ng nguá»"n MVP.



### 1.4.1 NguyÃan táo ̄c thiáo¿t káo¿ giao diá»‡n full-screen vÃ  responsive

Pháo§n má»m pháo£i Ä'Æ°á»£c thiáo¿t káo¿ theo nguyÃan táo ̄c **full-screen responsive layout (bá»' cá»¥c toÃ n mÃ n hÃ¬nh cÃ3 kháo£ nÄƒng co giÃ£n)**, nghÄ©a lÃ  giao diá»‡n pháo£i táo­n dá»¥ng toÃ n bá»TM chiá»u rá»TMng vÃ  chiá»u cao kháo£ dá»¥ng cá»§a mÃ n hÃ¬nh ngÆ°á»i dÃ1ng.

Má»¥c tiÃau báo ̄t buá»TMc:

- Khi má»Ÿ chÆ°Æ¡ng trÃ¬nh, cá»­a sá»• chÃ­nh pháo£i tá»± Ä'á»TMng má»Ÿ á»Ÿ tráo¡ng thÃ¡i maximized báo±ng `showMaximized()`, chiáo¿m toÃ n bá»TM vÃ1ng lÃ m viá»‡c kháo£ dá»¥ng trÃan mÃ n hÃ¬nh hiá»‡n táo¡i.
- HÃ nh vi má»Ÿ toÃ n mÃ n hÃ¬nh pháo£i Ä'Ãong trÃan má»i kÃ­ch thÆ°á»›c mÃ n hÃ¬nh phá»• biáo¿n vÃ  má»i má»©c Windows scaling nhÆ° 100%, 125%, 150%.
- KhÃ ́ng dÃ1ng cháo¿ Ä'á»TM borderless/exclusive fullscreen trá»« khi cÃ3 yÃau cáo§u riÃang; app váo«n pháo£i giá» ̄ taskbar, Alt+Tab vÃ  nÃot thu nhá»/phÃ3ng to/Ä'Ã3ng theo chuáo©n desktop.
- Má»-i mÃ n hÃ¬nh chá»©c nÄƒng pháo£i hiá»ƒn thá»‹ trá»n ná»TMi dung chÃ­nh trong **má»TMt mÃ n hÃ¬nh lÃ m viá»‡c**, háo¡n cháo¿ tá»'i Ä'a viá»‡c ngÆ°á»i dÃ1ng pháo£i dÃ1ng thanh scroll (cuá»TMn) dá»c hoáo·c scroll ngang.
- KhÃ ́ng Ä'Æ°á»£c thiáo¿t káo¿ giao diá»‡n dáo¡ng trang web dÃ i pháo£i kÃ©o xuá»'ng nhiá»u láo§n má»›i xem háo¿t ná»TMi dung quan trá»ng.
- KhÃ ́ng Ä'Æ°á»£c Ä'á»ƒ báo£ng, card (tháo» thÃ ́ng tin), biá»ƒu Ä'á»" hoáo·c control (thÃ nh pháo§n Ä'iá»u khiá»ƒn) bá»‹ trÃ n ngang khiáo¿n ngÆ°á»i dÃ1ng pháo£i kÃ©o thanh scroll ngang.
- Giao diá»‡n pháo£i tá»± scale (co giÃ£n tá»· lá»‡) theo nhiá»u kÃ­ch thÆ°á»›c mÃ n hÃ¬nh phá»• biáo¿n: **14 inch, 15.6 inch, 17 inch, 24 inch, 27 inch vÃ  32 inch**.
- TÃ1y kÃ­ch thÆ°á»›c mÃ n hÃ¬nh, cÃ¡c vÃ1ng dá» ̄ liá»‡u, báo£ng, card, biá»ƒu Ä'á»", control vÃ  cá»TMt thÃ ́ng tin pháo£i tá»± co giÃ£n Ä'á»ƒ vá»«a mÃ n hÃ¬nh.
- NgÆ°á»i dÃ1ng pháo£i cÃ3 thá»ƒ Ä'á»c nhanh toÃ n bá»TM tráo¡ng thÃ¡i quan trá»ng mÃ  khÃ ́ng cáo§n kÃ©o chuá»TMt nhiá»u.

#### NguyÃan táo ̄c bá»' cá»¥c theo kÃ­ch thÆ°á»›c mÃ n hÃ¬nh

| KÃ­ch thÆ°á»›c mÃ n hÃ¬nh | NguyÃan táo ̄c bá»' cá»¥c |
|---|---|
| 14 inch | Æ ̄u tiÃan bá»' cá»¥c cÃ ́ Ä'á»ng, giáo£m sá»' cá»TMt hiá»ƒn thá»‹ cÃ1ng lÃoc, dÃ1ng tab hoáo·c accordion (khá»'i má»Ÿ rá»TMng/thu gá»n) cho thÃ ́ng tin phá»¥ |
| 15.6 inch | Bá»' cá»¥c tiÃau chuáo©n cho MVP, chia 2â€"3 cá»TMt há»£p lÃ1⁄2, hiá»ƒn thá»‹ Ä'á»§ cÃ¡c khá»'i quan trá»ng |
| 17 inch | CÃ3 thá»ƒ tÄƒng chiá»u rá»TMng báo£ng vÃ  thÃam vÃ1ng tÃ3m táo ̄t phá»¥ |
| 24 inch | DÃ1ng layout rá»TMng, chia nhiá»u panel (khung ná»TMi dung) Ä'á»ƒ xem Ä'Æ°á»£c nhiá»u dá» ̄ liá»‡u cÃ1ng lÃoc |
| 27 inch | Æ ̄u tiÃan dashboard nhiá»u cá»TMt, báo£ng scanner rá»TMng hÆ¡n, háo¡n cháo¿ popup khÃ ́ng cáo§n thiáo¿t |
| 32 inch | CÃ3 thá»ƒ hiá»ƒn thá»‹ dáo¡ng command center (báo£ng Ä'iá»u khiá»ƒn lá»›n), nhiá»u card vÃ  báo£ng cÃ1ng lÃoc nhÆ°ng váo«n pháo£i giá» ̄ khoáo£ng cÃ¡ch rÃμ rÃ ng |

#### NguyÃan táo ̄c thiáo¿t káo¿ má»TMt mÃ n hÃ¬nh khÃ ́ng cáo§n scroll

Má»-i mÃ n hÃ¬nh pháo£i phÃ¢n biá»‡t rÃμ:

1. **ThÃ ́ng tin chÃ­nh báo ̄t buá»TMc hiá»ƒn thá»‹ ngay**.
2. **ThÃ ́ng tin phá»¥ cÃ3 thá»ƒ thu gá»n**.
3. **ThÃ ́ng tin chi tiáo¿t sÃ¢u cÃ3 thá»ƒ Ä'Æ°a vÃ o tab hoáo·c modal (há»TMp thoáo¡i ná»•i)**.

VÃ­ dá»¥ vá»›i **Single Analysis Result (káo¿t quáo£ phÃ¢n tÃ­ch má»TMt mÃ£)**:

- Pháo£i hiá»ƒn thá»‹ ngay:
  - Symbol (mÃ£ giao dá»‹ch).
  - Decision (káo¿t luáo­n).
  - Direction Bias (thiÃan hÆ°á»›ng giao dá»‹ch).
  - Trade Permission (quyá»n cho phÃ©p giao dá»‹ch).
  - Buy Score (Ä'iá»ƒm mua).
  - Sell Score (Ä'iá»ƒm bÃ¡n).
  - Entry Zone (vÃ1ng vÃ o lá»‡nh).
  - Stop Loss â€" SL (cáo ̄t lá»-).
  - Take Profit â€" TP (chá»'t lá»i).
  - Risk/Reward â€" R:R (tá»· lá»‡ rá»§i ro/lá»£i nhuáo­n).
  - Position Sizing (tÃ­nh khá»'i lÆ°á»£ng vÃ o lá»‡nh).
  - Data Quality (cháo¥t lÆ°á»£ng dá» ̄ liá»‡u).

- CÃ3 thá»ƒ Ä'Æ°a vÃ o tab hoáo·c khá»'i thu gá»n:
  - AI Commentary (nháo­n Ä'á»‹nh AI) dÃ i.
  - Raw JSON (dá» ̄ liá»‡u JSON thÃ ́).
  - Chi tiáo¿t tá»«ng component score (thÃ nh pháo§n Ä'iá»ƒm).
  - Log ká»1 thuáo­t.
  - Danh sÃ¡ch náo¿n hoáo·c báo£ng dá» ̄ liá»‡u dÃ i.

#### NguyÃan táo ̄c vá»›i báo£ng dá» ̄ liá»‡u

CÃ¡c báo£ng trong pháo§n má»m, Ä'áo·c biá»‡t lÃ  Scanner Mode (cháo¿ Ä'á»TM quÃ©t thá»‹ trÆ°á»ng), pháo£i trÃ¡nh trÃ n ngang.

Quy táo ̄c:

- KhÃ ́ng hiá»ƒn thá»‹ quÃ¡ nhiá»u cá»TMt náo¿u mÃ n hÃ¬nh nhá».
- Vá»›i mÃ n hÃ¬nh nhá», chá»‰ giá» ̄ cÃ¡c cá»TMt quan trá»ng:
  - Symbol (mÃ£ giao dá»‹ch)
  - Action (hÃ nh Ä'á»TMng)
  - Bias (thiÃan hÆ°á»›ng)
  - Permission (quyá»n giao dá»‹ch)
  - Best Score (Ä'iá»ƒm tá»'t nháo¥t)
  - View Detail (xem chi tiáo¿t)
- CÃ¡c cá»TMt phá»¥ nhÆ° Buy Score, Sell Score, R:R, Main Reason cÃ3 thá»ƒ Ä'Æ°a vÃ o tooltip (chÃo thÃ­ch), expandable row (dÃ2ng má»Ÿ rá»TMng) hoáo·c panel chi tiáo¿t.
- Vá»›i mÃ n hÃ¬nh lá»›n, cÃ3 thá»ƒ hiá»ƒn thá»‹ thÃam nhiá»u cá»TMt hÆ¡n.
- KhÃ ́ng Ä'Æ°á»£c Ä'á»ƒ ngÆ°á»i dÃ1ng pháo£i kÃ©o ngang Ä'á»ƒ xem háo¿t báo£ng.

#### NguyÃan táo ̄c vá»›i control vÃ  input

CÃ¡c control (thÃ nh pháo§n Ä'iá»u khiá»ƒn) nhÆ° selectbox (há»TMp chá»n), input (Ã ́ nháo­p), button (nÃot báo¥m), checkbox (Ã ́ chá»n), tab (tháo» chuyá»ƒn ná»TMi dung) pháo£i:

- CÃ3 kÃ­ch thÆ°á»›c co giÃ£n theo container (khung chá»©a).
- KhÃ ́ng bá»‹ cáo ̄t chá» ̄.
- KhÃ ́ng bá»‹ xáo¿p chá»"ng lÃan nhau.
- KhÃ ́ng táo¡o layout quÃ¡ cao khiáo¿n ngÆ°á»i dÃ1ng pháo£i kÃ©o dá»c.
- Vá»›i nhiá»u lá»±a chá»n, Æ°u tiÃan dÃ1ng tab, popover (khung ná»•i), modal hoáo·c sidebar thay vÃ¬ dÃ n toÃ n bá»TM trÃan mÃ n hÃ¬nh chÃ­nh.

#### NguyÃan táo ̄c triá»ƒn khai trong PyQt6

á» ̈ng dá»¥ng pháo£i triá»ƒn khai dÆ°á»›i dáo¡ng desktop app PyQt6, khá»Ÿi cháo¡y qua `QApplication` trong `main.py` vÃ  má»Ÿ `MainWindow` lÃ m cá»­a sá»• chÃ­nh.

CÃ¡c mÃ n hÃ¬nh nÃan dÃ1ng:

- `QMainWindow` cho khung á»©ng dá»¥ng chÃ­nh, gá»"m navigation (Ä'iá»u hÆ°á»›ng), top bar vÃ  vÃ1ng ná»TMi dung.
- `QStackedWidget` hoáo·c router/controller tÆ°Æ¡ng Ä'Æ°Æ¡ng Ä'á»ƒ chuyá»ƒn giá» ̄a cÃ¡c mÃ n hÃ¬nh Dashboard, Single Analysis, Scanner, Journal vÃ  Settings.
- `QSplitter`, `QGridLayout`, `QHBoxLayout`, `QVBoxLayout` vÃ  stretch factor Ä'á»ƒ chia layout nhiá»u vÃ1ng mÃ  váo«n co giÃ£n theo mÃ n hÃ¬nh.
- `QTabWidget` cho Settings vÃ  cÃ¡c pháo§n ná»TMi dung dÃ i.
- `QDialog` hoáo·c panel chi tiáo¿t cho raw JSON, log ká»1 thuáo­t vÃ  giáo£i thÃ­ch dÃ i.
- `QTableView`/`QAbstractTableModel` cho báo£ng Scanner vÃ  Journal, trÃ¡nh render báo£ng thá»§ cÃ ́ng trong UI.
- QSS (`styles.qss`) vÃ  component dÃ1ng chung Ä'á»ƒ thá»'ng nháo¥t style, spacing, mÃ u sáo ̄c vÃ  tráo¡ng thÃ¡i.
- `QThread`, `QRunnable` hoáo·c `QThreadPool` cho tÃ¡c vá»¥ náo·ng nhÆ° láo¥y dá» ̄ liá»‡u MT5, gá»i AI, quÃ©t nhiá»u symbol vÃ  tÃ­nh toÃ¡n lá»›n.

#### NguyÃan táo ̄c Æ°u tiÃan thÃ ́ng tin theo mÃ n hÃ¬nh

Má»-i mÃ n hÃ¬nh pháo£i cÃ3 má»TMt vÃ1ng **Above the Fold (vÃ1ng nhÃ¬n tháo¥y ngay khÃ ́ng cáo§n cuá»TMn)** chá»©a thÃ ́ng tin quan trá»ng nháo¥t.

| MÃ n hÃ¬nh | ThÃ ́ng tin báo ̄t buá»TMc pháo£i tháo¥y ngay |
|---|---|
| Dashboard (báo£ng Ä'iá»u khiá»ƒn) | Tráo¡ng thÃ¡i MT5, tráo¡ng thÃ¡i AI, tráo¡ng thÃ¡i broker, nÃot vÃ o Single Analysis vÃ  Scanner |
| Single Analysis Input (nháo­p phÃ¢n tÃ­ch má»TMt mÃ£) | Symbol, broker symbol, account balance, risk percent, tráo¡ng thÃ¡i MT5, nÃot Analyze |
| Single Analysis Result (káo¿t quáo£ phÃ¢n tÃ­ch má»TMt mÃ£) | Decision, bias, permission, score, entry, SL, TP, R:R, lot |
| Scanner (quÃ©t thá»‹ trÆ°á»ng) | Báo£ng xáo¿p háo¡ng 28 cáo·p Forex vÃ  XAU/USD, action, best score, permission, nÃot View Detail |
| Scanner Detail (chi tiáo¿t scanner) | Rank, best score, ká»‹ch báo£n Æ°u tiÃan, trade plan tÃ3m táo ̄t |
| Journal (nháo­t kÃ1⁄2) | Bá»TM lá»c, danh sÃ¡ch journal gáo§n nháo¥t, nÃot má»Ÿ chi tiáo¿t |
| Settings (cÃ i Ä'áo·t) | CÃ¡c tab cáo¥u hÃ¬nh chÃ­nh, tráo¡ng thÃ¡i lÆ°u, nÃot Save |

#### NguyÃan táo ̄c kiá»ƒm thá»­ giao diá»‡n

TrÆ°á»›c khi nghiá»‡m thu UI, pháo£i kiá»ƒm tra Ã­t nháo¥t cÃ¡c kÃ­ch thÆ°á»›c mÃ n hÃ¬nh sau:

```text
1366 x 768   # Laptop 14 inch phá»• biáo¿n
1536 x 864   # Laptop 15.6 inch phá»• biáo¿n
1920 x 1080  # Laptop/monitor Full HD
2560 x 1440  # Monitor 27 inch QHD
3840 x 2160  # Monitor 32 inch 4K
```

TiÃau chÃ­ Ä'áo¡t:

- KhÃ ́ng xuáo¥t hiá»‡n thanh scroll ngang.
- Ná»TMi dung chÃ­nh cá»§a tá»«ng mÃ n hÃ¬nh náo±m gá»n trong má»TMt mÃ n hÃ¬nh lÃ m viá»‡c.
- CÃ¡c control khÃ ́ng bá»‹ vá»¡ layout.
- Báo£ng khÃ ́ng bá»‹ máo¥t cá»TMt quan trá»ng.
- NgÆ°á»i dÃ1ng khÃ ́ng pháo£i kÃ©o dá»c Ä'á»ƒ xem cÃ¡c quyáo¿t Ä'á»‹nh quan trá»ng nhÆ° Decision, Score, Entry, SL, TP, Lot.
- CÃ¡c thÃ ́ng tin dÃ i Ä'Æ°á»£c Ä'Æ°a vÃ o tab, expander hoáo·c modal thay vÃ¬ chiáo¿m toÃ n bá»TM chiá»u cao mÃ n hÃ¬nh.

#### NguyÃan táo ̄c Æ°u tiÃan khi thiáo¿u khÃ ́ng gian

Khi mÃ n hÃ¬nh nhá» vÃ  khÃ ́ng Ä'á»§ khÃ ́ng gian hiá»ƒn thá»‹ táo¥t cáo£ thÃ ́ng tin, thá»© tá»± Æ°u tiÃan lÃ :

1. Decision (káo¿t luáo­n).
2. Trade Permission (quyá»n cho phÃ©p giao dá»‹ch).
3. Direction Bias (thiÃan hÆ°á»›ng giao dá»‹ch).
4. Buy/Sell Score (Ä'iá»ƒm mua/bÃ¡n).
5. Entry Zone (vÃ1ng vÃ o lá»‡nh).
6. Stop Loss â€" SL (cáo ̄t lá»-).
7. Take Profit â€" TP (chá»'t lá»i).
8. Risk/Reward â€" R:R (tá»· lá»‡ rá»§i ro/lá»£i nhuáo­n).
9. Position Sizing (tÃ­nh khá»'i lÆ°á»£ng vÃ o lá»‡nh).
10. AI Commentary (nháo­n Ä'á»‹nh AI).
11. Raw JSON vÃ  log ká»1 thuáo­t.

Náo¿u buá»TMc pháo£i áo©n bá»›t thÃ ́ng tin trÃan mÃ n hÃ¬nh nhá», chá»‰ Ä'Æ°á»£c áo©n cÃ¡c nhÃ3m thÃ ́ng tin phá»¥, khÃ ́ng Ä'Æ°á»£c áo©n quyáo¿t Ä'á»‹nh giao dá»‹ch, quyá»n giao dá»‹ch, Ä'iá»ƒm sá»', Entry, SL, TP vÃ  Lot.

### 1.5 Hai cháo¿ Ä'á»TM sá»­ dá»¥ng

Sáo£n pháo©m cÃ3 2 cháo¿ Ä'á»TM sá»­ dá»¥ng Ä'á»ƒ trÃ¡nh viá»‡c ngÆ°á»i dÃ1ng pháo£i thao tÃ¡c nhiá»u láo§n khi muá»'n xem toÃ n thá»‹ trÆ°á»ng.

| Cháo¿ Ä'á»TM | TÃan tiáo¿ng Viá»‡t | Má»¥c Ä'Ã­ch | Khi nÃ o dÃ1ng |
|---|---|---|---|
| `single_analysis` | PhÃ¢n tÃ­ch má»TMt mÃ£ | PhÃ¢n tÃ­ch Ä'áo§y Ä'á»§ 1 mÃ£ vá»›i output JSON chi tiáo¿t, trade plan, position sizing vÃ  nháo­n Ä'á»‹nh AI | Khi ngÆ°á»i dÃ1ng Ä'Ã£ biáo¿t mÃ£ muá»'n xem ká»1 |
| `scanner` | QuÃ©t thá»‹ trÆ°á»ng | QuÃ©t nhanh táo¥t cáo£ mÃ£ trong MVP, xáo¿p háo¡ng setup tá»'t nháo¥t, khÃ ́ng viáo¿t nháo­n Ä'á»‹nh dÃ i cho má»i mÃ£ | Khi ngÆ°á»i dÃ1ng muá»'n biáo¿t hÃ ́m nay mÃ£ nÃ o Ä'Ã¡ng chÃo Ã1⁄2 |

NguyÃan táo ̄c quan trá»ng:

- Single Analysis Mode táo¡o bÃ¡o cÃ¡o Ä'áo§y Ä'á»§ cho má»TMt mÃ£.
- Scanner Mode chá»‰ táo¡o báo£ng tá»•ng há»£p nhanh trÆ°á»›c.
- Scanner Mode khÃ ́ng gá»i AI cho toÃ n bá»TM mÃ£ ngay tá»« Ä'áo§u Ä'á»ƒ trÃ¡nh cháo­m vÃ  tá»'n token.
- AI chá»‰ Ä'Æ°á»£c gá»i cho cÃ¡c mÃ£ cÃ3 setup Ä'Ã¡ng chÃo Ã1⁄2, vÃ­ dá»¥ `best_score >= 75` vÃ  `trade_permission != blocked`.
- Tá»« báo£ng scanner, ngÆ°á»i dÃ1ng cÃ3 thá»ƒ báo¥m `View Detail` Ä'á»ƒ má»Ÿ phÃ¢n tÃ­ch Ä'áo§y Ä'á»§ cá»§a má»TMt mÃ£.


### 1.6 Settings (cÃ i Ä'áo·t há»‡ thá»'ng)

Sáo£n pháo©m pháo£i cÃ3 má»TMt khu vá»±c **Settings (cÃ i Ä'áo·t)** Ä'á»ƒ ngÆ°á»i dÃ1ng tá»± chá»n nhÃ  cung cáo¥p AI, model AI, cáo¥u hÃ¬nh MT5, timezone vÃ  cÃ¡c tham sá»' váo­n hÃ nh. Settings pháo£i dá»... hiá»ƒu vá»›i ngÆ°á»i khÃ ́ng chuyÃan láo­p trÃ¬nh.

CÃ¡c nhÃ3m cÃ i Ä'áo·t báo ̄t buá»TMc:

| NhÃ3m settings | NghÄ©a tiáo¿ng Viá»‡t | Má»¥c Ä'Ã­ch |
|---|---|---|
| AI Provider Settings | CÃ i Ä'áo·t nhÃ  cung cáo¥p AI | Chá»n DeepSeek, OpenAI, Anthropic/Claude, chá»n model, nháo­p API key vÃ  test |
| AI Model Settings | CÃ i Ä'áo·t model AI | Náo±m trong cÃ1ng mÃ n hÃ¬nh AI Provider, chá»‰ hiá»ƒn thá»‹ dropdown model |
| MT5 Data Settings | CÃ i Ä'áo·t dá» ̄ liá»‡u MT5 | Káo¿t ná»'i terminal MT5, kiá»ƒm tra broker login, map symbol broker, kiá»ƒm tra spread vÃ  contract info |
| Trading Settings | CÃ i Ä'áo·t giao dá»‹ch | Account balance, risk percent, contract config, lot step |
| Display Settings | CÃ i Ä'áo·t hiá»ƒn thá»‹ | Timezone, ngÃ ́n ngá» ̄, cÃ¡ch hiá»ƒn thá»‹ thuáo­t ngá» ̄ |

Settings pháo£i lÆ°u Ä'Æ°á»£c vÃ o file local, vÃ­ dá»¥ `settings.json`, hoáo·c lÆ°u vÃ o SQLite. KhÃ ́ng báo ̄t ngÆ°á»i dÃ1ng nháo­p láo¡i má»-i láo§n má»Ÿ app.

### 1.7 NguyÃan táo ̄c ngÃ ́n ngá» ̄ vÃ  thuáo­t ngá» ̄ trong pháo§n má»m

Giao diá»‡n pháo§n má»m pháo£i Æ°u tiÃan tiáo¿ng Viá»‡t. Táo¥t cáo£ thuáo­t ngá» ̄ hiá»ƒn thá»‹ cho ngÆ°á»i dÃ1ng pháo£i **cá»' gáo ̄ng tá»'i Ä'a Ä'á»ƒ dá»‹ch sang tiáo¿ng Viá»‡t ngáo ̄n gá»n, dá»... hiá»ƒu**.

NguyÃan táo ̄c báo ̄t buá»TMc:

- Æ ̄u tiÃan nhÃ£n tiáo¿ng Viá»‡t ngáo ̄n gá»n trÃan UI chÃ­nh.
- Chá»‰ giá» ̄ thuáo­t ngá» ̄ tiáo¿ng Anh khi Ä'Ã3 lÃ  tÃan chuáo©n khÃ3 dá»‹ch, mÃ£ ká»1 thuáo­t, hoáo·c ngÆ°á»i dÃ1ng giao dá»‹ch thÆ°á»ng nháo­n diá»‡n báo±ng tiáo¿ng Anh.
- Náo¿u giá» ̄ tiáo¿ng Anh, pháo£i cÃ3 tiáo¿ng Viá»‡t Ä'i kÃ ̈m á»Ÿ láo§n hiá»ƒn thá»‹ Ä'áo§u tiÃan, trong tooltip, hoáo·c trong mÃ ́ táo£ phá»¥.
- KhÃ ́ng Ä'á»ƒ mÃ n hÃ¬nh toÃ n thuáo­t ngá» ̄ tiáo¿ng Anh khi cÃ3 thá»ƒ dá»‹ch Ä'Æ°á»£c.
- Báo£ng dá» ̄ liá»‡u cÃ3 thá»ƒ dÃ1ng nhÃ£n ngáo ̄n, nhÆ°ng váo«n pháo£i Æ°u tiÃan tiáo¿ng Viá»‡t, vÃ­ dá»¥ `Äiá»ƒm mua`, `Äiá»ƒm bÃ¡n`, `Quyá»n giao dá»‹ch`, `VÃ1ng vÃ o lá»‡nh`.

Táo¥t cáo£ thuáo­t ngá» ̄ tiáo¿ng Anh cÃ2n hiá»ƒn thá»‹ trong giao diá»‡n pháo§n má»m pháo£i cÃ3 giáo£i thÃ­ch tiáo¿ng Viá»‡t Ä'i kÃ ̈m ngay bÃan cáo¡nh, tá»'i thiá»ƒu á»Ÿ láo§n hiá»ƒn thá»‹ Ä'áo§u tiÃan trong má»-i mÃ n hÃ¬nh.

Quy táo ̄c hiá»ƒn thá»‹:

```text
Thuáo­t ngá» ̄ tiáo¿ng Viá»‡t ngáo ̄n gá»n (English Term náo¿u cáo§n)
```

VÃ­ dá»¥ báo ̄t buá»TMc:

| Thuáo­t ngá» ̄ hiá»ƒn thá»‹ | CÃ¡ch hiá»ƒn thá»‹ Ä'Ãong trong pháo§n má»m |
|---|---|
| Market Regime | Market Regime (tráo¡ng thÃ¡i thá»‹ trÆ°á»ng) |
| Direction Bias | Direction Bias (thiÃan hÆ°á»›ng giao dá»‹ch) |
| Setup Quality Score | Setup Quality Score (Ä'iá»ƒm cháo¥t lÆ°á»£ng ká»‹ch báo£n) |
| Trade Permission | Trade Permission (quyá»n cho phÃ©p giao dá»‹ch) |
| Entry Zone | Entry Zone (vÃ1ng vÃ o lá»‡nh) |
| Stop Loss | Stop Loss â€" SL (cáo ̄t lá»-) |
| Take Profit | Take Profit â€" TP (chá»'t lá»i) |
| Risk/Reward | Risk/Reward â€" R:R (tá»· lá»‡ rá»§i ro/lá»£i nhuáo­n) |
| Position Sizing | Position Sizing (tÃ­nh khá»'i lÆ°á»£ng vÃ o lá»‡nh) |
| Lot | Lot (khá»'i lÆ°á»£ng giao dá»‹ch) |
| Spread | Spread (chÃanh lá»‡ch giÃ¡ mua-bÃ¡n) |
| Volatility | Volatility (biáo¿n Ä'á»TMng) |
| Momentum | Momentum (Ä'á»TMng lÆ°á»£ng) |
| Support | Support (há»- trá»£) |
| Resistance | Resistance (khÃ¡ng cá»±) |
| Scanner Mode | Scanner Mode (cháo¿ Ä'á»TM quÃ©t thá»‹ trÆ°á»ng) |
| Single Analysis Mode | Single Analysis Mode (cháo¿ Ä'á»TM phÃ¢n tÃ­ch má»TMt mÃ£) |
| AI Provider | AI Provider (nhÃ  cung cáo¥p AI) |
| Model | Model (mÃ ́ hÃ¬nh AI) |
| Base URL | Cáo¥u hÃ¬nh ngáo§m, khÃ ́ng hiá»ƒn thá»‹ trÃan UI chÃ­nh |
| API Key | API Key (khÃ3a truy cáo­p API) |

KhÃ ́ng dÃ1ng giao diá»‡n toÃ n thuáo­t ngá» ̄ tiáo¿ng Anh nhÆ° `Bias`, `Permission`, `Score`, `Entry`, `SL`, `TP` mÃ  khÃ ́ng cÃ3 chÃo thÃ­ch. Náo¿u dÃ1ng báo£ng ngáo ̄n Ä'á»ƒ tiáo¿t kiá»‡m diá»‡n tÃ­ch, tiÃau Ä'á» cá»TMt váo«n pháo£i cÃ3 tiáo¿ng Viá»‡t, vÃ­ dá»¥:

```text
Bias (thiÃan hÆ°á»›ng)
Permission (quyá»n giao dá»‹ch)
Buy Score (Ä'iá»ƒm mua)
Sell Score (Ä'iá»ƒm bÃ¡n)
```

### 1.8 AI Provider Settings (cÃ i Ä'áo·t nhÃ  cung cáo¥p AI)

Pháo§n Settings chá»‰ hiá»ƒn thá»‹ cáo¥u hÃ¬nh AI tháo­t Ä'Æ¡n giáo£n cho ngÆ°á»i dÃ1ng phá»• thÃ ́ng.

NgÆ°á»i dÃ1ng chá»‰ cáo§n:

1. Chá»n nhÃ  cung cáo¥p AI.
2. Chá»n model.
3. Nháo­p API key.
4. Báo¥m `Test API Key` Ä'á»ƒ kiá»ƒm tra.
5. Báo¥m `Save` Ä'á»ƒ lÆ°u.

ToÃ n bá»TM cáo¥u hÃ¬nh ká»1 thuáo­t khÃ¡c nhÆ° Base URL, API format, temperature, max tokens, timeout, retry, model macro/model writer tÃ¡ch riÃang pháo£i cháo¡y ngáo§m theo default cá»§a á»©ng dá»¥ng.

#### NhÃ  cung cáo¥p cÃ3 sáoμn

| NhÃ  cung cáo¥p | Ghi chÃo |
|---|---|
| DeepSeek | Æ ̄u tiÃan cho chi phÃ­ tháo¥p vÃ  OpenAI-compatible API |
| OpenAI | DÃ1ng OpenAI API |
| Anthropic | DÃ1ng Anthropic API |
| Claude | TÃan hiá»ƒn thá»‹ thÃ¢n thiá»‡n cho Anthropic Claude |

KhÃ ́ng hiá»ƒn thá»‹ custom provider trong MVP náo¿u chÆ°a tháo­t sá»± cáo§n. Náo¿u sau nÃ y cáo§n custom provider, Ä'Æ°a vÃ o pháo§n Advanced áo©n, khÃ ́ng Ä'áo·t á»Ÿ UI chÃ­nh.

#### TrÆ°á»ng ngÆ°á»i dÃ1ng nhÃ¬n tháo¥y

```json
{
  "ai_settings": {
    "enabled": true,
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "api_key_storage": "keyring_or_local_encrypted",
    "api_key_masked_preview": "sk-****abcd"
  }
}
```

| TrÆ°á»ng | NghÄ©a tiáo¿ng Viá»‡t | Hiá»ƒn thá»‹ trÃan UI |
|---|---|---|
| `provider` | NhÃ  cung cáo¥p AI | CÃ3 |
| `model` | Model AI | CÃ3 |
| `api_key` | KhÃ3a API | CÃ3, dáo¡ng password/masked |
| `enabled` | Báo­t/táo ̄t AI | CÃ3 thá»ƒ lÃ  cÃ ́ng táo ̄c Ä'Æ¡n giáo£n |
| `base_url` | Äá»‹a chá»‰ API gá»'c | KhÃ ́ng hiá»ƒn thá»‹, app tá»± cáo¥u hÃ¬nh theo provider |
| `api_format` | Äá»‹nh dáo¡ng API | KhÃ ́ng hiá»ƒn thá»‹, app tá»± cáo¥u hÃ¬nh theo provider |
| `temperature` | Äá»TM sÃ¡ng táo¡o | KhÃ ́ng hiá»ƒn thá»‹, dÃ1ng default tháo¥p |
| `max_tokens` | Giá»›i háo¡n token | KhÃ ́ng hiá»ƒn thá»‹, dÃ1ng default theo tÃ¡c vá»¥ |
| `timeout_seconds` | Thá»i gian chá» | KhÃ ́ng hiá»ƒn thá»‹, dÃ1ng default |
| `retry_count` | Sá»' láo§n thá»­ láo¡i | KhÃ ́ng hiá»ƒn thá»‹, dÃ1ng default |

#### Model gá»£i Ã1⁄2 theo provider

| NhÃ  cung cáo¥p | Model gá»£i Ã1⁄2 |
|---|---|
| DeepSeek | `deepseek-v4-flash`, `deepseek-v4-pro` |
| OpenAI | `gpt-4.1-mini`, `gpt-4.1`, `gpt-4o-mini` |
| Anthropic / Claude | `claude-3-5-sonnet`, `claude-3-5-haiku` |

Danh sÃ¡ch model cÃ3 thá»ƒ Ä'Æ°á»£c cáo¥u hÃ¬nh trong code hoáo·c file config, nhÆ°ng UI chá»‰ hiá»ƒn thá»‹ dropdown model tÆ°Æ¡ng á»©ng vá»›i provider Ä'Ã£ chá»n.

#### NguyÃan táo ̄c báo£o máo­t API key

- KhÃ ́ng hiá»ƒn thá»‹ API Key Ä'áo§y Ä'á»§ trÃan giao diá»‡n.
- Ã" nháo­p API key pháo£i dÃ1ng dáo¡ng password/masked.
- Sau khi lÆ°u chá»‰ hiá»ƒn thá»‹ dáo¡ng `sk-****abcd` hoáo·c tÆ°Æ¡ng tá»±.
- KhÃ ́ng lÆ°u API Key dáo¡ng plain text trong SQLite.
- Æ ̄u tiÃan keyring há»‡ Ä'iá»u hÃ nh hoáo·c file local Ä'Æ°á»£c báo£o vá»‡.
- KhÃ ́ng ghi API Key vÃ o log.

#### Test API Key

NÃot `Test API Key` pháo£i:

- Gá»i má»TMt request kiá»ƒm tra nháo1 tá»›i provider/model Ä'Ã£ chá»n.
- Hiá»ƒn thá»‹ káo¿t quáo£ Ä'Æ¡n giáo£n: `Káo¿t ná»'i thÃ nh cÃ ́ng` hoáo·c `KhÃ ́ng kiá»ƒm tra Ä'Æ°á»£c API key`.
- Náo¿u lá»-i, chá»‰ nÃ3i nguyÃan nhÃ¢n dá»... hiá»ƒu: sai API key, háo¿t credit, model khÃ ́ng há»£p lá»‡, máo¡ng lá»-i, provider khÃ ́ng pháo£n há»"i.
- KhÃ ́ng hiá»ƒn thá»‹ traceback ká»1 thuáo­t trÃan UI.
- Ghi chi tiáo¿t lá»-i vÃ o log, nhÆ°ng khÃ ́ng ghi API key.
#### Náo¿u AI bá»‹ táo ̄t hoáo·c chÆ°a cáo¥u hÃ¬nh

Náo¿u `ai_settings.enabled = false` hoáo·c thiáo¿u API Key:

- Macro Alignment (má»©c Ä'á»TM vÄ© mÃ ́ á»§ng há»TM ká»‹ch báo£n) fallback vá» 7 Ä'iá»ƒm trung tÃ­nh.
- AI Writer (AI viáo¿t nháo­n Ä'á»‹nh) dÃ1ng template cá»' Ä'á»‹nh.
- Scanner Mode váo«n cháo¡y Ä'Æ°á»£c báo±ng Rule Engine.
- UI pháo£i hiá»ƒn thá»‹ cáo£nh bÃ¡o: `AI chÆ°a Ä'Æ°á»£c cáo¥u hÃ¬nh, há»‡ thá»'ng Ä'ang dÃ1ng cháo¿ Ä'á»TM rule-based (dá»±a trÃan luáo­t tÃ­nh toÃ¡n).`

---

## 2. Chiáo¿n lÆ°á»£c dá» ̄ liá»‡u

### 2.1 NguyÃan táo ̄c dá» ̄ liá»‡u

GiÃ¡ vÃ  chá»‰ bÃ¡o ká»1 thuáo­t lÃ  pháo§n khÃ ́ng Ä'Æ°á»£c giao cho AI suy Ä'oÃ¡n. Há»‡ thá»'ng pháo£i láo¥y dá» ̄ liá»‡u thÃ ́ rá»"i tá»± tÃ­nh toÃ¡n.

```
[API dá» ̄ liá»‡u giÃ¡] â†' [OHLCV thÃ ́] â†' [Tá»± tÃ­nh chá»‰ bÃ¡o] â†' [Scoring Engine]
                                                         â†"
             [AI chá»‰ nháo­n dá» ̄ liá»‡u Ä'Ã£ tÃ­nh + tin tá»©c + vÄ© mÃ ́ Ä'á»ƒ diá»...n giáo£i]
```

### 2.2 Nguá»"n dá» ̄ liá»‡u giÃ¡ trong MVP: MetaTrader5

Trong MVP, nguá»"n dá» ̄ liá»‡u giÃ¡ chÃ­nh vÃ  báo ̄t buá»TMc cho phÃ¢n tÃ­ch thá»±c chiáo¿n lÃ  **MetaTrader5 Python API (API Python cá»§a MetaTrader 5)**.

Há»‡ thá»'ng láo¥y dá» ̄ liá»‡u thÃ ́ng qua **terminal MT5 (pháo§n má»m MetaTrader 5) Ä'ang má»Ÿ trÃan mÃ¡y ngÆ°á»i dÃ1ng**. NgÆ°á»i dÃ1ng pháo£i Ä'Äƒng nháo­p sáoμn tÃ i khoáo£n broker (sÃ n giao dá»‹ch) trong MT5.

| Loáo¡i dá» ̄ liá»‡u | Nguá»"n MVP | Ghi chÃo |
|---|---|---|
| OHLCV (giÃ¡ má»Ÿ/cao/tháo¥p/Ä'Ã3ng/khá»'i lÆ°á»£ng) | MetaTrader5 Python API | Láo¥y trá»±c tiáo¿p tá»« terminal MT5 Ä'ang Ä'Äƒng nháo­p broker |
| Bid/Ask (giÃ¡ mua/giÃ¡ bÃ¡n hiá»‡n táo¡i) | MT5 symbol tick | DÃ1ng Ä'á»ƒ kiá»ƒm tra spread vÃ  giÃ¡ hiá»‡n táo¡i |
| Spread (chÃanh lá»‡ch giÃ¡ mua-bÃ¡n) | MT5 symbol info / tick | DÃ1ng trong Risk Condition (Ä'iá»u kiá»‡n rá»§i ro) |
| Digits/Point (sá»' chá» ̄ sá»' tháo­p phÃ¢n/bÆ°á»›c giÃ¡ nhá» nháo¥t) | MT5 symbol info | DÃ1ng Ä'á»ƒ chuáo©n hÃ3a giÃ¡ |
| Contract Size (quy mÃ ́ há»£p Ä'á»"ng) | MT5 symbol info | DÃ1ng cho Position Sizing (tÃ­nh khá»'i lÆ°á»£ng vÃ o lá»‡nh) |
| Tick Size/Tick Value (kÃ­ch thÆ°á»›c tick/giÃ¡ trá»‹ tick) | MT5 symbol info | DÃ1ng Ä'á»ƒ tÃ­nh rá»§i ro sÃ¡t broker hÆ¡n náo¿u cáo§n |
| Chá»‰ bÃ¡o ká»1 thuáo­t | Tá»± tÃ­nh báo±ng Python, pandas, numpy | KhÃ ́ng Ä'á»ƒ AI tá»± tÃ­nh hoáo·c Ä'oÃ¡n |
| Lá»‹ch kinh táo¿ | TradingEconomics API náo¿u cÃ3; fallback lÃ  Forex Factory scraping hoáo·c nháo­p tay | KhÃ ́ng dÃ1ng Ä'á»ƒ láo¥y giÃ¡ |
| Dá» ̄ liá»‡u vÄ© mÃ ́ | AI search web hoáo·c nguá»"n cÃ ́ng khai | Chá»‰ dÃ1ng cho Macro Alignment (má»©c Ä'á»TM thuáo­n vÄ© mÃ ́) |
| Tin tá»©c | AI search web hoáo·c nguá»"n tin tÃ i chÃ­nh | Chá»‰ dÃ1ng Ä'á»ƒ diá»...n giáo£i, khÃ ́ng táo¡o giÃ¡ |
| Äáo·c tÃ­nh tá»«ng cáo·p tiá»n | Hardcoded/config file | CÃ3 thá»ƒ override theo broker |

**KhÃ ́ng sá»­ dá»¥ng MT5/MT5 lÃ m nguá»"n dá» ̄ liá»‡u trong sáo£n pháo©m.** LÃ1⁄2 do: vá»›i Forex vÃ  Ä'áo·c biá»‡t cÃ¡c khung intraday (dá» ̄ liá»‡u trong ngÃ y) nhÆ° H1/H4, dá» ̄ liá»‡u cÃ3 thá»ƒ trá»..., thiáo¿u náo¿n, lá»‡ch rÃ¢u náo¿n vÃ  khÃ ́ng cÃ3 spread tháo­t so vá»›i broker ngÆ°á»i dÃ1ng Ä'ang giao dá»‹ch.

### 2.3 Äiá»u kiá»‡n báo ̄t buá»TMc khi dÃ1ng MT5

Äá»ƒ pháo§n má»m hoáo¡t Ä'á»TMng á»Ÿ cháo¿ Ä'á»TM thá»±c chiáo¿n, ngÆ°á»i dÃ1ng cáo§n:

1. CÃ i MetaTrader 5 trÃan mÃ¡y.
2. Má»Ÿ terminal MT5 trÆ°á»›c khi cháo¡y pháo§n má»m.
3. ÄÄƒng nháo­p sáoμn tÃ i khoáo£n broker trong MT5.
4. Äáo£m báo£o symbol (mÃ£ giao dá»‹ch) cáo§n phÃ¢n tÃ­ch cÃ3 trong Market Watch (báo£ng theo dÃμi thá»‹ trÆ°á»ng) cá»§a MT5.
5. Cáo¥u hÃ¬nh Ä'Ãong broker symbol (mÃ£ trÃan broker), vÃ¬ má»-i broker cÃ3 thá»ƒ Ä'áo·t tÃan khÃ¡c nhau.

VÃ­ dá»¥ mapping (Ã¡nh xáo¡ mÃ£):

| MÃ£ hiá»ƒn thá»‹ trong pháo§n má»m | Broker symbol cÃ3 thá»ƒ gáo·p |
|---|---|
| EUR/USD | EURUSD, EURUSDm, EURUSDc, EURUSD.a |
| GBP/USD | GBPUSD, GBPUSDm, GBPUSDc, GBPUSD.a |
| AUD/USD | AUDUSD, AUDUSDm, AUDUSDc, AUDUSD.a |
| NZD/USD | NZDUSD, NZDUSDm, NZDUSDc, NZDUSD.a |
| USD/JPY | USDJPY, USDJPYm, USDJPYc, USDJPY.a |
| USD/CHF | USDCHF, USDCHFm, USDCHFc, USDCHF.a |
| USD/CAD | USDCAD, USDCADm, USDCADc, USDCAD.a |
| EUR/GBP | EURGBP, EURGBPm, EURGBPc, EURGBP.a |
| EUR/JPY | EURJPY, EURJPYm, EURJPYc, EURJPY.a |
| EUR/CHF | EURCHF, EURCHFm, EURCHFc, EURCHF.a |
| EUR/AUD | EURAUD, EURAUDm, EURAUDc, EURAUD.a |
| EUR/NZD | EURNZD, EURNZDm, EURNZDc, EURNZD.a |
| EUR/CAD | EURCAD, EURCADm, EURCADc, EURCAD.a |
| GBP/JPY | GBPJPY, GBPJPYm, GBPJPYc, GBPJPY.a |
| GBP/CHF | GBPCHF, GBPCHFm, GBPCHFc, GBPCHF.a |
| GBP/AUD | GBPAUD, GBPAUDm, GBPAUDc, GBPAUD.a |
| GBP/NZD | GBPNZD, GBPNZDm, GBPNZDc, GBPNZD.a |
| GBP/CAD | GBPCAD, GBPCADm, GBPCADc, GBPCAD.a |
| CHF/JPY | CHFJPY, CHFJPYm, CHFJPYc, CHFJPY.a |
| AUD/JPY | AUDJPY, AUDJPYm, AUDJPYc, AUDJPY.a |
| NZD/JPY | NZDJPY, NZDJPYm, NZDJPYc, NZDJPY.a |
| CAD/JPY | CADJPY, CADJPYm, CADJPYc, CADJPY.a |
| AUD/CHF | AUDCHF, AUDCHFm, AUDCHFc, AUDCHF.a |
| NZD/CHF | NZDCHF, NZDCHFm, NZDCHFc, NZDCHF.a |
| CAD/CHF | CADCHF, CADCHFm, CADCHFc, CADCHF.a |
| AUD/NZD | AUDNZD, AUDNZDm, AUDNZDc, AUDNZD.a |
| AUD/CAD | AUDCAD, AUDCADm, AUDCADc, AUDCAD.a |
| NZD/CAD | NZDCAD, NZDCADm, NZDCADc, NZDCAD.a |
| XAU/USD | XAUUSD, GOLD, XAUUSDm, XAUUSDc, XAUUSD.a |

LÆ°u Ã1⁄2 Ä'áo·c biá»‡t khi láo­p trÃ¬nh MT5:

- Nhiá»u broker thÃam háo­u tá»' `m` hoáo·c `c` sau tÃan cáo·p, vÃ­ dá»¥ `USDCADm`, `USDCADc`, `NZDUSDm`, `NZDUSDc`.
- KhÃ ́ng Ä'Æ°á»£c hard-code máo·c Ä'á»‹nh chá»‰ cÃ3 symbol khÃ ́ng háo­u tá»'.
- `mt5_service` nÃan cÃ3 cÆ¡ cháo¿ auto-detect theo thá»© tá»± Æ°u tiÃan: symbol Ä'Ã£ lÆ°u trong Settings â†' symbol gá»'c khÃ ́ng dáo¥u `/` â†' háo­u tá»' phá»• biáo¿n `m`, `c` â†' danh sÃ¡ch symbol thá»±c táo¿ trong Market Watch.
- Náo¿u auto-detect tháo¥t báo¡i, UI pháo£i yÃau cáo§u ngÆ°á»i dÃ1ng sá»­a Symbol Mapping trong Settings.

Cáo¥u hÃ¬nh gá»£i Ã1⁄2:

```python
SYMBOL_MAPPING = {
    "EUR/USD": "EURUSD",
    "GBP/USD": "GBPUSD",
    "AUD/USD": "AUDUSD",
    "NZD/USD": "NZDUSD",
    "USD/JPY": "USDJPY",
    "USD/CHF": "USDCHF",
    "USD/CAD": "USDCAD",
    "EUR/GBP": "EURGBP",
    "EUR/JPY": "EURJPY",
    "EUR/CHF": "EURCHF",
    "EUR/AUD": "EURAUD",
    "EUR/NZD": "EURNZD",
    "EUR/CAD": "EURCAD",
    "GBP/JPY": "GBPJPY",
    "GBP/CHF": "GBPCHF",
    "GBP/AUD": "GBPAUD",
    "GBP/NZD": "GBPNZD",
    "GBP/CAD": "GBPCAD",
    "CHF/JPY": "CHFJPY",
    "AUD/JPY": "AUDJPY",
    "NZD/JPY": "NZDJPY",
    "CAD/JPY": "CADJPY",
    "AUD/CHF": "AUDCHF",
    "NZD/CHF": "NZDCHF",
    "CAD/CHF": "CADCHF",
    "AUD/NZD": "AUDNZD",
    "AUD/CAD": "AUDCAD",
    "NZD/CAD": "NZDCAD",
    "XAU/USD": "XAUUSD"
}
```

UI (giao diá»‡n ngÆ°á»i dÃ1ng) pháo£i cho phÃ©p ngÆ°á»i dÃ1ng sá»­a mapping nÃ y trong Settings (cÃ i Ä'áo·t), vÃ­ dá»¥:

```text
Display Symbol (mÃ£ hiá»ƒn thá»‹): XAU/USD
Broker Symbol (mÃ£ trÃan broker): XAUUSDm
```

### 2.4 Cáo£nh bÃ¡o khi MT5 chÆ°a sáoμn sÃ ng

Náo¿u terminal MT5 chÆ°a má»Ÿ, chÆ°a Ä'Äƒng nháo­p broker, khÃ ́ng chá»n Ä'Æ°á»£c symbol, hoáo·c khÃ ́ng láo¥y Ä'Æ°á»£c dá» ̄ liá»‡u, há»‡ thá»'ng pháo£i dá»«ng phÃ¢n tÃ­ch vÃ  hiá»ƒn thá»‹ cáo£nh bÃ¡o rÃμ rÃ ng.

KhÃ ́ng Ä'Æ°á»£c táo¡o tráo¡ng thÃ¡i `ready_to_enter` (sáoμn sÃ ng vÃ o lá»‡nh) khi MT5 lá»-i.

VÃ­ dá»¥ cáo£nh bÃ¡o trÃan UI:

```text
ðŸ" ́ KhÃ ́ng káo¿t ná»'i Ä'Æ°á»£c MT5.

Vui lÃ2ng:
1. Má»Ÿ MetaTrader 5.
2. ÄÄƒng nháo­p tÃ i khoáo£n broker.
3. Kiá»ƒm tra symbol trong Market Watch.
4. Báo¥m Retry (thá»­ láo¡i).

Há»‡ thá»'ng khÃ ́ng táo¡o ká»‹ch báo£n vÃ o lá»‡nh cho Ä'áo¿n khi dá» ̄ liá»‡u MT5 há»£p lá»‡.
```

Logic báo ̄t buá»TMc:

```python
if not mt5_terminal_connected:
    trade_permission = "blocked"
    decision_action = "mt5_required"
    show_warning("KhÃ ́ng káo¿t ná»'i Ä'Æ°á»£c MT5. HÃ£y má»Ÿ MT5 vÃ  Ä'Äƒng nháo­p broker.")
    stop_analysis()

if not broker_logged_in:
    trade_permission = "blocked"
    decision_action = "broker_login_required"
    show_warning("MT5 chÆ°a Ä'Äƒng nháo­p broker. HÃ£y Ä'Äƒng nháo­p tÃ i khoáo£n giao dá»‹ch.")
    stop_analysis()

if symbol_not_available:
    trade_permission = "blocked"
    decision_action = "symbol_mapping_required"
    show_warning("KhÃ ́ng tÃ¬m tháo¥y mÃ£ broker. HÃ£y kiá»ƒm tra Symbol Mapping trong Settings.")
    stop_analysis()
```

### 2.5 Code máo«u láo¥y dá» ̄ liá»‡u tá»« MT5

Code máo«u tá»'i thiá»ƒu láo¥y OHLCV (Open/High/Low/Close/Volume â€" giÃ¡ má»Ÿ/cao/tháo¥p/Ä'Ã3ng/khá»'i lÆ°á»£ng):

```python
import MetaTrader5 as mt5
import pandas as pd

TIMEFRAME_MAP = {
    "D1": mt5.TIMEFRAME_D1,
    "H4": mt5.TIMEFRAME_H4,
    "H1": mt5.TIMEFRAME_H1,
}


def get_mt5_ohlcv(symbol: str, timeframe: str, bars: int = 500) -> pd.DataFrame:
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Cannot select MT5 symbol: {symbol}")

    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME_MAP[timeframe], 0, bars)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No MT5 OHLCV data for {symbol} {timeframe}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(columns={"tick_volume": "volume"})

    return df[["time", "open", "high", "low", "close", "volume", "spread", "real_volume"]]
```

Code máo«u láo¥y thÃ ́ng tin symbol (mÃ£ giao dá»‹ch) vÃ  spread:

```python
def get_mt5_symbol_info(symbol: str) -> dict:
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)

    if info is None:
        raise RuntimeError(f"Cannot get MT5 symbol info: {symbol}")
    if tick is None:
        raise RuntimeError(f"Cannot get MT5 tick: {symbol}")

    return {
        "symbol": symbol,
        "bid": tick.bid,
        "ask": tick.ask,
        "spread_points": info.spread,
        "spread_price": info.spread * info.point,
        "digits": info.digits,
        "point": info.point,
        "contract_size": info.trade_contract_size,
        "tick_size": info.trade_tick_size,
        "tick_value": info.trade_tick_value,
        "currency_profit": info.currency_profit,
        "currency_margin": info.currency_margin,
    }
```

### 2.6 Data Quality (cháo¥t lÆ°á»£ng dá» ̄ liá»‡u)

Má»-i láo§n phÃ¢n tÃ­ch pháo£i tráo£ vá» thÃ ́ng tin cháo¥t lÆ°á»£ng dá» ̄ liá»‡u tá»« MT5:

```json
{
  "data_quality": {
    "price_source": "MT5",
    "terminal_connected": true,
    "broker_logged_in": true,
    "broker": "Broker name from MT5 if available",
    "display_symbol": "XAU/USD",
    "broker_symbol": "XAUUSDm",
    "last_candle_time_utc": "2026-05-29T07:00:00Z",
    "last_candle_time_vn": "2026-05-29T14:00:00+07:00",
    "is_delayed": false,
    "missing_candles": 0,
    "spread_points": 22,
    "spread_status": "normal",
    "digits": 2,
    "point": 0.01,
    "contract_size": 100,
    "tick_size": 0.01,
    "tick_value": 1.0,
    "warning": null
  }
}
```

Náo¿u dá» ̄ liá»‡u lá»-i, thiáo¿u náo¿n, spread báo¥t thÆ°á»ng hoáo·c náo¿n cuá»'i quÃ¡ cÅ©, há»‡ thá»'ng pháo£i cáo£nh bÃ¡o vÃ  khÃ ́ng táo¡o ká»‹ch báo£n `ready_to_enter`.

---

## 3. Pháo¡m vi MVP

### 3.1 TÃ i sáo£n giao dá»‹ch

MVP phÃ¢n tÃ­ch **28 cáo·p Forex phá»• biáo¿n + XAU/USD (vÃ ng giao ngay so vá»›i USD)**, tá»•ng cá»TMng 29 mÃ£:

| MÃ£ | Ã nghÄ©a |
|---|---|
| EUR/USD | Euro so vá»›i Ä'Ã ́ la Má»1 |
| GBP/USD | Báo£ng Anh so vá»›i Ä'Ã ́ la Má»1 |
| AUD/USD | ÄÃ ́ la Ãšc so vá»›i Ä'Ã ́ la Má»1 |
| NZD/USD | ÄÃ ́ la New Zealand so vá»›i Ä'Ã ́ la Má»1 |
| USD/JPY | ÄÃ ́ la Má»1 so vá»›i YÃan Nháo­t |
| USD/CHF | ÄÃ ́ la Má»1 so vá»›i Franc Thá»¥y SÄ© |
| USD/CAD | ÄÃ ́ la Má»1 so vá»›i Ä'Ã ́ la Canada |
| EUR/GBP | Euro so vá»›i Báo£ng Anh |
| EUR/JPY | Euro so vá»›i YÃan Nháo­t |
| EUR/CHF | Euro so vá»›i Franc Thá»¥y SÄ© |
| EUR/AUD | Euro so vá»›i Ä'Ã ́ la Ãšc |
| EUR/NZD | Euro so vá»›i Ä'Ã ́ la New Zealand |
| EUR/CAD | Euro so vá»›i Ä'Ã ́ la Canada |
| GBP/JPY | Báo£ng Anh so vá»›i YÃan Nháo­t |
| GBP/CHF | Báo£ng Anh so vá»›i Franc Thá»¥y SÄ© |
| GBP/AUD | Báo£ng Anh so vá»›i Ä'Ã ́ la Ãšc |
| GBP/NZD | Báo£ng Anh so vá»›i Ä'Ã ́ la New Zealand |
| GBP/CAD | Báo£ng Anh so vá»›i Ä'Ã ́ la Canada |
| CHF/JPY | Franc Thá»¥y SÄ© so vá»›i YÃan Nháo­t |
| AUD/JPY | ÄÃ ́ la Ãšc so vá»›i YÃan Nháo­t |
| NZD/JPY | ÄÃ ́ la New Zealand so vá»›i YÃan Nháo­t |
| CAD/JPY | ÄÃ ́ la Canada so vá»›i YÃan Nháo­t |
| AUD/CHF | ÄÃ ́ la Ãšc so vá»›i Franc Thá»¥y SÄ© |
| NZD/CHF | ÄÃ ́ la New Zealand so vá»›i Franc Thá»¥y SÄ© |
| CAD/CHF | ÄÃ ́ la Canada so vá»›i Franc Thá»¥y SÄ© |
| AUD/NZD | ÄÃ ́ la Ãšc so vá»›i Ä'Ã ́ la New Zealand |
| AUD/CAD | ÄÃ ́ la Ãšc so vá»›i Ä'Ã ́ la Canada |
| NZD/CAD | ÄÃ ́ la New Zealand so vá»›i Ä'Ã ́ la Canada |
| XAU/USD | VÃ ng giao ngay so vá»›i Ä'Ã ́ la Má»1 |

KhÃ ́ng thÃam cá»• phiáo¿u Má»1, crypto (tiá»n mÃ£ hÃ3a) hoáo·c indices (chá»‰ sá»' chá»©ng khoÃ¡n) trong MVP. CÃ¡c cáo·p tiá»n chÃ©o trong danh sÃ¡ch trÃan thuá»TMc pháo¡m vi MVP.

### 3.2 Khung thá»i gian

MVP dÃ1ng 3 khung thá»i gian:

| Khung | Ã nghÄ©a |
|---|---|
| D1 | Daily â€" náo¿n ngÃ y, dÃ1ng Ä'á»ƒ xÃ¡c Ä'á»‹nh xu hÆ°á»›ng chÃ­nh |
| H4 | 4-hour â€" náo¿n 4 giá», dÃ1ng Ä'á»ƒ xÃ¡c Ä'á»‹nh cáo¥u trÃoc trung háo¡n |
| H1 | 1-hour â€" náo¿n 1 giá», dÃ1ng Ä'á»ƒ tÃ¬m Ä'iá»u kiá»‡n vÃ o lá»‡nh |

KhÃ ́ng lÃ m scalping (giao dá»‹ch lÆ°á»›t sÃ3ng siÃau ngáo ̄n) trÃan M1/M5/M15 trong MVP vÃ¬ cáo§n dá» ̄ liá»‡u real-time (thá»i gian thá»±c), spread thá»±c táo¿ vÃ  tá»'c Ä'á»TM xá»­ lÃ1⁄2 tá»'t hÆ¡n.

### 3.3 Chá»‰ bÃ¡o ká»1 thuáo­t trong MVP

| NhÃ3m | Chá»‰ bÃ¡o / cÃ ́ng cá»¥ | Má»¥c Ä'Ã­ch |
|---|---|---|
| Trend (xu hÆ°á»›ng) | EMA 50, EMA 200 | XÃ¡c Ä'á»‹nh xu hÆ°á»›ng chÃ­nh |
| Momentum (Ä'á»TMng lÆ°á»£ng) | RSI 14 | Äo tráo¡ng thÃ¡i quÃ¡ mua/quÃ¡ bÃ¡n vÃ  sá»©c máo¡nh Ä'á»TMng lÆ°á»£ng |
| Momentum (Ä'á»TMng lÆ°á»£ng) | MACD 12/26/9 | Äo Ä'á»TM máo¡nh/yáo¿u vÃ  kháo£ nÄƒng Ä'áo£o chiá»u Ä'á»TMng lÆ°á»£ng |
| Volatility (biáo¿n Ä'á»TMng) | ATR 14 | Äo biÃan Ä'á»TM dao Ä'á»TMng trung bÃ¬nh |
| Structure (cáo¥u trÃoc giÃ¡) | Pivot point (Ä'iá»ƒm xoay) tuáo§n/thÃ¡ng | XÃ¡c Ä'á»‹nh vÃ1ng há»- trá»£/khÃ¡ng cá»± cÆ¡ báo£n |
| Structure (cáo¥u trÃoc giÃ¡) | Swing high/swing low (Ä'á»‰nh/Ä'Ã¡y dao Ä'á»TMng) | XÃ¡c Ä'á»‹nh cáo¥u trÃoc HH/HL hoáo·c LH/LL |
| Structure (cáo¥u trÃoc giÃ¡) | ATR zone (vÃ1ng Ä'á»‡m theo ATR) | Táo¡o vÃ1ng giÃ¡ thay vÃ¬ má»TMt má»©c giÃ¡ cá»©ng |

### 3.4 Dá» ̄ liá»‡u vÄ© mÃ ́ theo dÃμi

CÃ¡c dá» ̄ liá»‡u vÄ© mÃ ́ quan trá»ng:

- Fed Funds Rate (lÃ£i suáo¥t Quá»1 Dá»± trá» ̄ LiÃan bang Má»1).
- US 10Y Yield (lá»£i suáo¥t trÃ¡i phiáo¿u Má»1 ká»3 háo¡n 10 nÄƒm).
- US 2Y Yield (lá»£i suáo¥t trÃ¡i phiáo¿u Má»1 ká»3 háo¡n 2 nÄƒm).
- Yield spread (chÃanh lá»‡ch lá»£i suáo¥t).
- CPI (Consumer Price Index â€" chá»‰ sá»' giÃ¡ tiÃau dÃ1ng).
- Core CPI (CPI lÃμi).
- PCE (Personal Consumption Expenditures â€" chá»‰ sá»' chi tiÃau tiÃau dÃ1ng cÃ¡ nhÃ¢n).
- NFP (Nonfarm Payrolls â€" báo£ng lÆ°Æ¡ng phi nÃ ́ng nghiá»‡p Má»1).
- Unemployment Rate (tá»· lá»‡ tháo¥t nghiá»‡p).
- DXY (US Dollar Index â€" chá»‰ sá»' Ä'Ã ́ la Má»1).
- VIX (Volatility Index â€" chá»‰ sá»' biáo¿n Ä'á»TMng/sá»£ hÃ£i).
- Gold (vÃ ng).
- Oil (dáo§u).

### 3.5 TÃ­nh nÄƒng MVP vÃ  tÃ­nh nÄƒng Ä'á»ƒ sau

| LÃ m trong MVP | Äá»ƒ sau |
|---|---|
| Single Analysis Mode: nháo­p 1 mÃ£ vÃ  phÃ¢n tÃ­ch Ä'áo§y Ä'á»§ | Scanner nÃ¢ng cao: alert tá»± Ä'á»TMng, xáo¿p háo¡ng theo nhiá»u thá»‹ trÆ°á»ng |
| Giao diá»‡n desktop PyQt6 | Web app phá»©c táo¡p vá»›i Ä'Äƒng nháo­p |
| Output JSON cÃ3 cáo¥u trÃoc | API riÃang cho á»©ng dá»¥ng khÃ¡c |
| Scanner Mode cÆ¡ báo£n: quÃ©t 28 cáo·p Forex + XAU/USD báo±ng Rule Engine, chá»‰ gá»i AI cho mÃ£ Ä'Ã¡ng chÃo Ã1⁄2 | Scanner Ä'a tÃ i sáo£n, Ä'a khung thá»i gian, cháo¡y theo lá»‹ch |
| Tá»± tÃ­nh chá»‰ bÃ¡o ká»1 thuáo­t | Backtest (kiá»ƒm tra chiáo¿n lÆ°á»£c báo±ng dá» ̄ liá»‡u quÃ¡ khá»©) |
| Market Regime + Direction Bias | Paper Trading (giao dá»‹ch giáo£ láo­p) |
| Buy/Sell scoring riÃang | Alert (cáo£nh bÃ¡o tá»± Ä'á»TMng) |
| Position sizing | Auto trade (náo¿u cÃ3, Ä'á»ƒ ráo¥t xa vÃ  cáo§n kiá»ƒm soÃ¡t rá»§i ro cháo·t) |
| Journal SQLite | Multi-user (Ä'a ngÆ°á»i dÃ1ng) |
| Settings chá»n AI Provider/Model vÃ  custom provider | Quáo£n lÃ1⁄2 nhiá»u profile cáo¥u hÃ¬nh |
| Giáo£i thÃ­ch thuáo­t ngá» ̄ Anh - Viá»‡t trong UI | Tooltip/glossary nÃ¢ng cao |

---

## 4. Kiáo¿n trÃoc phÃ¢n tÃ­ch tá»•ng thá»ƒ

### 4.1 NguyÃan táo ̄c chÃ­nh

Score (Ä'iá»ƒm sá»') khÃ ́ng tráo£ lá»i trá»±c tiáo¿p â€œmua hay bÃ¡nâ€. Score tráo£ lá»i: **ká»‹ch báo£n nÃ y cÃ3 cháo¥t lÆ°á»£ng bao nhiÃau**.

Do Ä'Ã3 há»‡ thá»'ng pháo£i cháo¥m riÃang:

- Buy Scenario Score (Ä'iá»ƒm ká»‹ch báo£n mua).
- Sell Scenario Score (Ä'iá»ƒm ká»‹ch báo£n bÃ¡n).
- Stand Aside Reason (lÃ1⁄2 do Ä'á»©ng ngoÃ i náo¿u khÃ ́ng nÃan giao dá»‹ch).

### 4.2 Luá»"ng phÃ¢n tÃ­ch 4 bÆ°á»›c

```
BÆ°á»›c 1: Market Regime      â†' XÃ¡c Ä'á»‹nh tráo¡ng thÃ¡i thá»‹ trÆ°á»ng
BÆ°á»›c 2: Direction Bias     â†' XÃ¡c Ä'á»‹nh thiÃan hÆ°á»›ng giao dá»‹ch
BÆ°á»›c 3: Setup Quality Score â†' Cháo¥m Ä'iá»ƒm cháo¥t lÆ°á»£ng tá»«ng ká»‹ch báo£n
BÆ°á»›c 4: Trade Plan         â†' Táo¡o káo¿ hoáo¡ch giao dá»‹ch, quáo£n trá»‹ rá»§i ro, position sizing
```

### 4.3 Vai trÃ2 cá»§a Rule Engine vÃ  AI

| ThÃ nh pháo§n | Viá»‡c Ä'Æ°á»£c lÃ m | Viá»‡c khÃ ́ng Ä'Æ°á»£c lÃ m |
|---|---|---|
| Rule Engine (bá»TM luáo­t tÃ­nh toÃ¡n) | TÃ­nh chá»‰ bÃ¡o, xÃ¡c Ä'á»‹nh vÃ1ng giÃ¡, cháo¥m Ä'iá»ƒm, tÃ­nh entry/SL/TP, tÃ­nh lot | KhÃ ́ng viáo¿t nháo­n Ä'á»‹nh dÃ i báo±ng ngÃ ́n ngá» ̄ tá»± nhiÃan |
| AI (trÃ­ tuá»‡ nhÃ¢n táo¡o) | TÃ3m táo ̄t vÄ© mÃ ́, diá»...n giáo£i tin tá»©c, viáo¿t nháo­n Ä'á»‹nh dá»... hiá»ƒu, giáo£i thÃ­ch ká»‹ch báo£n | KhÃ ́ng tá»± táo¡o giÃ¡, khÃ ́ng tá»± bá»‹a chá»‰ bÃ¡o, khÃ ́ng tá»± táo¡o entry/SL/TP ngoÃ i dá» ̄ liá»‡u Ä'Ã£ cáo¥p |

NguyÃan táo ̄c báo ̄t buá»TMc:

> AI khÃ ́ng Ä'Æ°á»£c táo¡o sá»' giÃ¡ má»›i náo¿u sá»' Ä'Ã3 khÃ ́ng náo±m trong technical context (bá»'i cáo£nh ká»1 thuáo­t) do Rule Engine cung cáo¥p. AI chá»‰ Ä'Æ°á»£c chá»n, giáo£i thÃ­ch hoáo·c diá»...n Ä'áo¡t láo¡i cÃ¡c vÃ1ng giÃ¡ Ä'Ã£ Ä'Æ°á»£c há»‡ thá»'ng tÃ­nh toÃ¡n.

### 4.4 Luá»"ng Scanner Mode (cháo¿ Ä'á»TM quÃ©t thá»‹ trÆ°á»ng)

Scanner Mode khÃ ́ng thay tháo¿ Single Analysis Mode. NÃ3 lÃ  lá»›p lá»c nhanh Ä'á»ƒ ngÆ°á»i dÃ1ng khÃ ́ng pháo£i báo¥m Analyze nhiá»u láo§n.

Luá»"ng xá»­ lÃ1⁄2 Ä'á» xuáo¥t:

```text
User chá»n Scanner Mode
  â†"
Chá»n danh sÃ¡ch mÃ£: All supported Forex symbols + XAU/USD hoáo·c chá»n thá»§ cÃ ́ng
  â†"
Rule Engine quÃ©t nhanh tá»«ng mÃ£
  â†"
TÃ­nh market_regime, direction_bias, buy_score, sell_score, trade_permission
  â†"
Lá»c ra mÃ£ Ä'Ã¡ng chÃo Ã1⁄2
  â†"
Chá»‰ gá»i AI cho 1â€"3 mÃ£ tá»'t nháo¥t hoáo·c khi ngÆ°á»i dÃ1ng báo¥m View Detail
  â†"
Hiá»ƒn thá»‹ báo£ng scanner
```

Scanner Mode pháo£i Æ°u tiÃan tá»'c Ä'á»TM vÃ  tÃ­nh thá»±c dá»¥ng:

- KhÃ ́ng viáo¿t nháo­n Ä'á»‹nh AI dÃ i cho toÃ n bá»TM 28 cáo·p Forex + XAU/USD trong láo§n quÃ©t Ä'áo§u.
- KhÃ ́ng táo¡o trade plan quÃ¡ chi tiáo¿t cho mÃ£ cÃ3 score tháo¥p.
- KhÃ ́ng Ä'Æ°a tÃ­n hiá»‡u kiá»ƒu â€œmua ngayâ€ náo¿u chÆ°a cÃ3 Ä'iá»u kiá»‡n xÃ¡c nháo­n.
- Chá»‰ Ä'Ã¡nh dáo¥u `ready`, `watch`, `wait`, `skip` Ä'á»ƒ ngÆ°á»i dÃ1ng lá»c nhanh.

Quy táo ̄c gá»i AI trong Scanner Mode:

```python
if best_score >= 75 and trade_permission in ["allowed", "caution"]:
    ai_detail_allowed = True
else:
    ai_detail_allowed = False
```

Náo¿u cÃ3 nhiá»u mÃ£ Ä'áo¡t Ä'iá»u kiá»‡n, MVP chá»‰ gá»i AI cho tá»'i Ä'a 3 mÃ£ cÃ3 `best_score` cao nháo¥t Ä'á»ƒ tiáo¿t kiá»‡m token vÃ  giáo£m thá»i gian chá».

---

## 5. BÆ°á»›c 1 â€" Market Regime (tráo¡ng thÃ¡i thá»‹ trÆ°á»ng)

### 5.1 CÃ¡c regime chÃ­nh

| Regime | NghÄ©a tiáo¿ng Viá»‡t | Äiá»u kiá»‡n Ä'iá»ƒn hÃ¬nh |
|---|---|---|
| `trend_up` | Xu hÆ°á»›ng tÄƒng | EMA50 > EMA200, giÃ¡ trÃan EMA50, cáo¥u trÃoc D1/H4 cÃ3 HH/HL rÃμ |
| `trend_down` | Xu hÆ°á»›ng giáo£m | EMA50 < EMA200, giÃ¡ dÆ°á»›i EMA50, cáo¥u trÃoc D1/H4 cÃ3 LH/LL rÃμ |
| `range` | Äi ngang | EMA50 vÃ  EMA200 Ä'an xen, ATR tháo¥p, giÃ¡ dao Ä'á»TMng giá» ̄a há»- trá»£/khÃ¡ng cá»± rÃμ |
| `volatile` | Biáo¿n Ä'á»TMng máo¡nh | ATR hiá»‡n táo¡i > 1.5 láo§n ATR trung bÃ¬nh 14 ngÃ y |
| `news_sensitive` | Nháo¡y tin tá»©c | CÃ3 tin Ä'á» trong vÃ2ng 3 giá» tá»›i hoáo·c vá»«a cÃ ́ng bá»' tin lá»›n |
| `unknown` | KhÃ ́ng Ä'á»§ dá» ̄ liá»‡u/káo¿t luáo­n | Dá» ̄ liá»‡u thiáo¿u, cáo¥u trÃoc khÃ ́ng rÃμ, tÃ­n hiá»‡u mÃ¢u thuáo«n |

`volatile` vÃ  `news_sensitive` cÃ3 thá»ƒ lÃ  regime phá»¥, chá»"ng lÃan `trend_up`, `trend_down` hoáo·c `range`.

VÃ­ dá»¥:

```json
{
  "primary": "trend_up",
  "secondary": ["news_sensitive"]
}
```

### 5.2 CÃ¡ch xÃ¡c Ä'á»‹nh swing high/swing low

Äá»ƒ trÃ¡nh mÆ¡ há»", MVP dÃ1ng Ä'á»‹nh nghÄ©a Ä'Æ¡n giáo£n:

- Swing high (Ä'á»‰nh dao Ä'á»TMng): má»TMt náo¿n cÃ3 high (giÃ¡ cao nháo¥t) cao hÆ¡n Ã­t nháo¥t N náo¿n trÆ°á»›c vÃ  N náo¿n sau.
- Swing low (Ä'Ã¡y dao Ä'á»TMng): má»TMt náo¿n cÃ3 low (giÃ¡ tháo¥p nháo¥t) tháo¥p hÆ¡n Ã­t nháo¥t N náo¿n trÆ°á»›c vÃ  N náo¿n sau.
- MVP dÃ1ng `N = 2` hoáo·c `N = 3`.

### 5.3 CÃ¡ch xÃ¡c Ä'á»‹nh cáo¥u trÃoc HH/HL vÃ  LH/LL

| KÃ1⁄2 hiá»‡u | Tiáo¿ng Viá»‡t | CÃ¡ch xÃ¡c Ä'á»‹nh |
|---|---|---|
| HH | Higher High â€" Ä'á»‰nh cao hÆ¡n | Swing high gáo§n nháo¥t cao hÆ¡n swing high trÆ°á»›c Ä'Ã3 |
| HL | Higher Low â€" Ä'Ã¡y cao hÆ¡n | Swing low gáo§n nháo¥t cao hÆ¡n swing low trÆ°á»›c Ä'Ã3 |
| LH | Lower High â€" Ä'á»‰nh tháo¥p hÆ¡n | Swing high gáo§n nháo¥t tháo¥p hÆ¡n swing high trÆ°á»›c Ä'Ã3 |
| LL | Lower Low â€" Ä'Ã¡y tháo¥p hÆ¡n | Swing low gáo§n nháo¥t tháo¥p hÆ¡n swing low trÆ°á»›c Ä'Ã3 |

Quy táo ̄c:

- `trend_up`: cÃ3 Ã­t nháo¥t 2 swing high tÄƒng dáo§n vÃ  2 swing low tÄƒng dáo§n.
- `trend_down`: cÃ3 Ã­t nháo¥t 2 swing high giáo£m dáo§n vÃ  2 swing low giáo£m dáo§n.
- Náo¿u chÆ°a Ä'á»§ swing point (Ä'iá»ƒm dao Ä'á»TMng), Ä'áo·t `structure = "unknown"`.

### 5.4 Logic riÃang cho thá»‹ trÆ°á»ng range

Range (thá»‹ trÆ°á»ng Ä'i ngang) pháo£i cÃ3 logic riÃang, khÃ ́ng xá»­ lÃ1⁄2 giá»'ng trend-following (giao dá»‹ch thuáo­n xu hÆ°á»›ng máo¡nh).

#### CÃ¡ch xÃ¡c Ä'á»‹nh range trong MVP

MVP dÃ1ng quy táo ̄c Ä'Æ¡n giáo£n Ä'á»ƒ trÃ¡nh mÆ¡ há»":

- DÃ1ng 10â€"20 náo¿n D1 gáo§n nháo¥t Ä'á»ƒ quan sÃ¡t vÃ1ng Ä'i ngang.
- `range_high` = swing high cao nháo¥t trong giai Ä'oáo¡n quan sÃ¡t.
- `range_low` = swing low tháo¥p nháo¥t trong giai Ä'oáo¡n quan sÃ¡t.
- `mid_range = (range_high + range_low) / 2`.
- Range chá»‰ há»£p lá»‡ náo¿u EMA50 vÃ  EMA200 Ä'i ngang/Ä'an xen, ATR tháo¥p hÆ¡n hoáo·c xáo¥p xá»‰ trung bÃ¬nh, vÃ  khÃ ́ng cÃ3 cáo¥u trÃoc HH/HL hoáo·c LH/LL rÃμ.
- Náo¿u chÆ°a Ä'á»§ swing point Ä'á»ƒ xÃ¡c Ä'á»‹nh `range_high` vÃ  `range_low`, Ä'áo·t `market_regime = unknown` hoáo·c `neutral`, khÃ ́ng Ã©p thÃ nh range.

Code máo«u:

```python
def detect_range(swing_highs, swing_lows, ema50_slope, ema200_slope, atr_current, atr_avg_14d):
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None

    range_high = max(swing_highs[-5:])
    range_low = min(swing_lows[-5:])
    mid_range = (range_high + range_low) / 2

    ema_flat = abs(ema50_slope) < 0.001 and abs(ema200_slope) < 0.001
    atr_not_expanding = atr_current <= 1.2 * atr_avg_14d

    if ema_flat and atr_not_expanding:
        return {
            "range_high": range_high,
            "range_low": range_low,
            "mid_range": mid_range,
        }

    return None
```

#### Logic giao dá»‹ch trong range

Náo¿u `market_regime = range`:

- KhÃ ́ng Æ°u tiÃan trend-following.
- Chá»‰ cÃ¢n nháo ̄c buy gáo§n `range_low` hoáo·c support zone á»Ÿ biÃan dÆ°á»›i.
- Chá»‰ cÃ¢n nháo ̄c sell gáo§n `range_high` hoáo·c resistance zone á»Ÿ biÃan trÃan.
- Náo¿u giÃ¡ náo±m quanh `mid_range Â± ATR/4`, Æ°u tiÃan `stand_aside` vÃ¬ risk/reward thÆ°á»ng kÃ©m.
- TP nÃan gáo§n hÆ¡n: Æ°u tiÃan `mid_range` hoáo·c biÃan Ä'á»'i diá»‡n, khÃ ́ng ká»3 vá»ng breakout náo¿u chÆ°a cÃ3 tÃ­n hiá»‡u phÃ¡ vá»¡ rÃμ.

Quy táo ̄c tham chiáo¿u:

```python
if market_regime == "range":
    if abs(price - range_low) <= atr_h4 * 0.5:
        allowed_direction = "buy"
    elif abs(price - range_high) <= atr_h4 * 0.5:
        allowed_direction = "sell"
    elif abs(price - mid_range) <= atr_h4 * 0.25:
        allowed_direction = "stand_aside"
    else:
        allowed_direction = "neutral"
```

### 5.5 Äá»‹nh nghÄ©a strength (Ä'á»TM máo¡nh) cá»§a support/resistance zone

Support zone (vÃ1ng há»- trá»£) vÃ  resistance zone (vÃ1ng khÃ¡ng cá»±) khÃ ́ng Ä'Æ°á»£c Ä'á»ƒ AI tá»± gÃ¡n strength. Code pháo£i xÃ¡c Ä'á»‹nh strength theo rule (quy táo ̄c) rÃμ rÃ ng.

| Strength | NghÄ©a tiáo¿ng Viá»‡t | Äiá»u kiá»‡n gá»£i Ã1⁄2 |
|---|---|---|
| `strong` | Máo¡nh | Pivot tuáo§n/thÃ¡ng quan trá»ng; hoáo·c vÃ1ng Ä'Ã£ Ä'Æ°á»£c test (kiá»ƒm tra) Ã­t nháo¥t 3 láo§n mÃ  chÆ°a bá»‹ phÃ¡ rÃμ; hoáo·c cÃ3 confluence (há»TMi tá»¥) tá»« Ã­t nháo¥t 2 nguá»"n nhÆ° pivot + swing high/low + ATR zone |
| `moderate` | Trung bÃ¬nh | Swing high/swing low gáo§n nháo¥t; hoáo·c vÃ1ng Ä'Æ°á»£c test 1â€"2 láo§n; hoáo·c pivot ngÃ y/tuáo§n nhÆ°ng chÆ°a cÃ3 nhiá»u pháo£n á»©ng giÃ¡ |
| `weak` | Yáo¿u | ATR zone thuáo§n, vÃ1ng má»›i hÃ¬nh thÃ nh, chÆ°a Ä'Æ°á»£c test, hoáo·c chá»‰ cÃ3 má»TMt tÃ­n hiá»‡u ká»1 thuáo­t Ä'Æ¡n láo» |

Quy táo ̄c triá»ƒn khai:

```python
def classify_zone_strength(zone):
    score = 0

    if zone.type in ["pivot_monthly", "pivot_weekly"]:
        score += 2
    if zone.test_count >= 3:
        score += 2
    elif zone.test_count >= 1:
        score += 1
    if zone.confluence_count >= 2:
        score += 2
    if zone.type in ["recent_swing_high", "recent_swing_low"]:
        score += 1

    if score >= 4:
        return "strong"
    if score >= 2:
        return "moderate"
    return "weak"
```

AI (trÃ­ tuá»‡ nhÃ¢n táo¡o) chá»‰ Ä'Æ°á»£c diá»...n giáo£i strength Ä'Ã£ Ä'Æ°á»£c code tÃ­nh sáoμn, khÃ ́ng tá»± Ä'áo·t `strong`, `moderate`, `weak`.

---

## 6. BÆ°á»›c 2 â€" Direction Bias (thiÃan hÆ°á»›ng giao dá»‹ch)

### 6.1 CÃ¡c loáo¡i bias

| Bias | NghÄ©a tiáo¿ng Viá»‡t | Äiá»u kiá»‡n Ä'iá»ƒn hÃ¬nh |
|---|---|---|
| `buy` | Æ ̄u tiÃan tÃ¬m lá»‡nh mua | `trend_up`, momentum thuáo­n tÄƒng, giÃ¡ gáo§n há»- trá»£ hoáo·c pullback há»£p lÃ1⁄2 |
| `sell` | Æ ̄u tiÃan tÃ¬m lá»‡nh bÃ¡n | `trend_down`, momentum thuáo­n giáo£m, giÃ¡ gáo§n khÃ¡ng cá»± hoáo·c há»"i lÃan há»£p lÃ1⁄2 |
| `neutral` | Trung láo­p | Range, trend yáo¿u, tÃ­n hiá»‡u hai chiá»u chÆ°a rÃμ |
| `stand_aside` | Äá»©ng ngoÃ i | Tin lá»›n sáo ̄p ra, spread báo¥t thÆ°á»ng, dá» ̄ liá»‡u lá»-i, giÃ¡ á»Ÿ vá»‹ trÃ­ xáo¥u, Ä'iá»ƒm cáo£ buy/sell Ä'á»u tháo¥p |

### 6.2 Trade Permission (quyá»n cho phÃ©p giao dá»‹ch)

NgoÃ i bias, há»‡ thá»'ng cáo§n tráo£ vá» `trade_permission`:

| Tráo¡ng thÃ¡i | NghÄ©a | Khi nÃ o dÃ1ng |
|---|---|---|
| `allowed` | CÃ3 thá»ƒ cÃ¢n nháo ̄c giao dá»‹ch | Dá» ̄ liá»‡u á»•n, khÃ ́ng cÃ3 tin lá»›n sÃ¡t giá», cÃ3 setup rÃμ |
| `caution` | Cáo©n trá»ng | CÃ3 yáo¿u tá»' rá»§i ro nhÆ° tin trong ngÃ y, ATR cao, spread chÆ°a cháo ̄c cháo ̄n |
| `blocked` | KhÃ ́ng nÃan giao dá»‹ch | Tin Ä'á» ráo¥t gáo§n, dá» ̄ liá»‡u lá»-i, spread báo¥t thÆ°á»ng, setup khÃ ́ng rÃμ |

VÃ­ dá»¥:

```json
{
  "trade_permission": {
    "status": "caution",
    "reason": "CÃ3 CPI trong 3 giá» tá»›i, nÃan giáo£m khá»'i lÆ°á»£ng hoáo·c chá» sau tin.",
    "resume_after": "2026-05-29T20:00:00+07:00"
  }
}
```

### 6.3 Logic tÃ­nh resume_after (thá»i Ä'iá»ƒm cÃ3 thá»ƒ xem xÃ©t láo¡i giao dá»‹ch)

`resume_after` khÃ ́ng Ä'Æ°á»£c Ä'á»ƒ AI tá»± Ä'áo·t. Code pháo£i tÃ­nh tá»« thá»i Ä'iá»ƒm cÃ ́ng bá»' tin tá»©c hoáo·c thá»i Ä'iá»ƒm dá» ̄ liá»‡u/rá»§i ro háo¿t hiá»‡u lá»±c.

Quy táo ̄c MVP:

```python
if high_impact_event_within_30_minutes:
    trade_permission = "blocked"
    resume_after = event_time + timedelta(minutes=30)
elif high_impact_event_within_3_hours:
    trade_permission = "caution"
    resume_after = event_time + timedelta(minutes=30)
elif spread_abnormal:
    trade_permission = "blocked"
    resume_after = None  # cáo§n kiá»ƒm tra láo¡i spread theo dá» ̄ liá»‡u má»›i
elif data_quality_bad:
    trade_permission = "blocked"
    resume_after = None  # cáo§n táo£i láo¡i dá» ̄ liá»‡u
else:
    trade_permission = "allowed"
    resume_after = None
```

CÃ3 thá»ƒ cáo¥u hÃ¬nh buffer (vÃ1ng Ä'á»‡m thá»i gian) theo má»©c Ä'á»TM tin:

| Loáo¡i sá»± kiá»‡n | Buffer sau tin |
|---|---:|
| CPI (chá»‰ sá»' giÃ¡ tiÃau dÃ1ng), FOMC (cuá»TMc há»p chÃ­nh sÃ¡ch Fed), NFP (báo£ng lÆ°Æ¡ng phi nÃ ́ng nghiá»‡p) | 30â€"60 phÃot |
| Tin trung bÃ¬nh | 15â€"30 phÃot |
| Tin tháo¥p | KhÃ ́ng cáo§n cháo·n, chá»‰ cáo£nh bÃ¡o |

MVP dÃ1ng máo·c Ä'á»‹nh: `resume_after = event_time + 30 phÃot` vá»›i tin Ä'á».

Trong triá»ƒn khai hiá»‡n táo¡i, controller pháo£i láo¥y lá»‹ch tin kinh táo¿ trÆ°á»›c khi gá»i `analyze_symbol()` vÃ  cáo­p nháo­t cÃ¡c trÆ°á»ng sau vÃ o `data_quality`:

```json
{
  "news_in_3h": true,
  "high_impact_event_within_30m": false,
  "next_high_impact_event": {
    "source": "Forex Factory",
    "currency": "USD",
    "event": "CPI",
    "impact": "High",
    "time_utc": "2026-06-01T12:30Z",
    "hours_until": 2.4
  },
  "resume_after": "2026-06-01T13:00:00+00:00"
}
```

`risk_engine.calc_trade_permission()` dÃ1ng `high_impact_event_within_30m` Ä'á»ƒ cháo·n giao dá»‹ch vÃ  dÃ1ng `news_in_3h` Ä'á»ƒ chuyá»ƒn sang `caution`. AI chá»‰ Ä'Æ°á»£c diá»...n giáo£i cÃ¡c trÆ°á»ng nÃ y, khÃ ́ng tá»± Ä'áo·t `resume_after`.

NgoÃ i lá»‹ch kinh táo¿, app pháo£i láo¥y thÃam macro context má»›i nháo¥t:

```json
{
  "latest_headlines": [
    {
      "source": "Reuters",
      "title": "BOJ tightening bets rise as Japan wages and Tokyo CPI stay firm",
      "url": "https://...",
      "published_utc": "2026-05-15T08:00Z",
      "tags": ["central_bank", "inflation", "labor"]
    }
  ],
  "macro_themes": [
    {
      "currency": "JPY",
      "stance": "hawkish",
      "headline_count": 3,
      "key_points": ["BOJ tightening...", "Tokyo CPI..."]
    }
  ],
  "geopolitical_hotspots": [
    {
      "source": "Investing.com",
      "title": "Oil jumps on Middle East geopolitical risk",
      "published_utc": "2026-05-15T09:00Z"
    }
  ],
  "macro_alignment_scores": {
    "buy": 4,
    "sell": 11
  },
  "macro_alignment_reasons": {
    "buy": "USD stance=neutral, JPY stance=hawkish.",
    "sell": "JPY stance=hawkish, USD stance=neutral."
  }
}
```

`macro_alignment_scores` pháo£i Ä'Æ°á»£c truyá»n vÃ o `analyze_symbol()` Ä'á»ƒ Ä'iá»ƒm mua/bÃ¡n pháo£n Ã¡nh bá»'i cáo£nh vÄ© mÃ ́. VÃ­ dá»¥ USD/JPY: náo¿u headline cho tháo¥y BOJ hawkish, Nháo­t cÃ3 lÆ°Æ¡ng/CPI/Tankan máo¡nh, nguy cÆ¡ intervention cao vÃ  Fed trung tÃ­nh/dovish, Ä'iá»ƒm macro cho ká»‹ch báo£n bÃ¡n USD/JPY pháo£i tá»'t hÆ¡n ká»‹ch báo£n mua. Náo¿u khÃ ́ng cÃ3 dá» ̄ liá»‡u headline hoáo·c nguá»"n lá»-i, Ä'iá»ƒm macro quay vá» trung tÃ­nh vÃ  káo¿t quáo£ pháo£i ghi rÃμ khÃ ́ng cÃ3 dá» ̄ liá»‡u.

Náo¿u nguá»"n lá»‹ch kinh táo¿ tráo£ lá»-i rate limit nhÆ° HTTP 429, há»‡ thá»'ng pháo£i xá»­ lÃ1⁄2 nhÆ° sau:

- KhÃ ́ng dá»«ng phÃ¢n tÃ­ch.
- KhÃ ́ng káo¿t luáo­n lÃ  khÃ ́ng cÃ3 sá»± kiá»‡n vÄ© mÃ ́, chá»‰ ghi rÃμ lÃ  chÆ°a cáo­p nháo­t Ä'Æ°á»£c lá»‹ch kinh táo¿ chi tiáo¿t.
- DÃ1ng cache lá»‹ch kinh táo¿ gáo§n nháo¥t náo¿u cÃ3.
- Váo«n láo¥y headline vÄ© mÃ ́ má»›i nháo¥t, macro theme, Ä'iá»ƒm nÃ3ng tháo¿ giá»›i vÃ  `macro_alignment_scores`.
- KhÃ ́ng dÃ1ng cá»¥m â€œdá» ̄ liá»‡u AI ná»TMi bá»TMâ€. Pháo£i ghi Ä'Ãong lÃ  dá» ̄ liá»‡u rule engine, dá» ̄ liá»‡u vÄ© mÃ ́/headline cá»§a app hoáo·c nháo­n Ä'á»‹nh AI.

---

## 7. BÆ°á»›c 3 â€" Setup Quality Score (Ä'iá»ƒm cháo¥t lÆ°á»£ng ká»‹ch báo£n)

### 7.1 NguyÃan táo ̄c scoring

Há»‡ thá»'ng cháo¥m riÃang tá»«ng ká»‹ch báo£n:

```python
buy_scenario_score = score_buy_scenario(data)
sell_scenario_score = score_sell_scenario(data)
```

Äiá»ƒm cao khÃ ́ng cÃ3 nghÄ©a lÃ  cháo ̄c tháo ̄ng. Äiá»ƒm cao chá»‰ cÃ3 nghÄ©a lÃ  ká»‹ch báo£n Ä'Ã3 cÃ3 nhiá»u yáo¿u tá»' Ä'á»"ng thuáo­n.

Má»-i component (thÃ nh pháo§n Ä'iá»ƒm) pháo£i Ä'Æ°á»£c clamp (káo1p giá»›i háo¡n) riÃang trÆ°á»›c khi cá»TMng tá»•ng. KhÃ ́ng Ä'á»ƒ má»TMt thÃ nh pháo§n vÆ°á»£t quÃ¡ Ä'iá»ƒm tá»'i Ä'a cá»§a nÃ3.

### 7.2 Cáo¥u trÃoc Ä'iá»ƒm Ä'á» xuáo¥t (v12.1 â€" Macro 3 táo§ng)

| Component | Max points | Meaning |
|---|---:|---|
| Trend Alignment | 18 | Direction/trend supports the scenario. |
| Momentum Alignment | 15 | RSI/MACD momentum supports the scenario. |
| Location Quality | 17 | Price is at a sensible support/resistance or POI location. |
| SMC Quality | 15 | BOS/CHOCH/displacement, premium/discount, liquidity sweep and zone quality support the scenario. |
| Risk Condition | 15 | ATR, spread and nearby news risk are acceptable. |
| Macro Alignment | 30 | Three-tier macro context: T1 rates/policy (12), T2 calendar (10), T3 risk/geopolitics (8). |
| **Total** | **100** | Scenario quality score. |

**Trá»ng sá»' Ä'á»TMng theo cháo¥t lÆ°á»£ng dá» ̄ liá»‡u vÄ© mÃ ́:**
- `macro_confidence âˆˆ [0.10, 1.0]`: há»‡ sá»' nhÃ¢n vá»›i macro_raw dá»±a trÃan Ä'á»TM má»›i cá»§a headline, sá»' lÆ°á»£ng headline, cÃ3 calendar data khÃ ́ng
- `macro_effective = macro_raw Ã- macro_confidence`
- Khi dá» ̄ liá»‡u vÄ© mÃ ́ kÃ©m cháo¥t lÆ°á»£ng, Ä'iá»ƒm vÄ© mÃ ́ tá»± Ä'á»TMng giáo£m, pháo§n cÃ2n láo¡i do ká»1 thuáo­t vÃ  risk quyáo¿t Ä'á»‹nh

---

## 8. Chi tiáo¿t scoring cho tá»«ng thÃ nh pháo§n

### 8.1 Trend Alignment â€" 0 Ä'áo¿n 25 Ä'iá»ƒm

#### Vá»›i ká»‹ch báo£n BUY (mua)

| Äiá»u kiá»‡n | Äiá»ƒm |
|---|---:|
| EMA50 D1 > EMA200 D1 | +8 |
| GiÃ¡ D1 > EMA200 D1 | +5 |
| GiÃ¡ D1 hoáo·c H4 > EMA50 | +5 |
| H4 cÃ3 cáo¥u trÃoc HH/HL rÃμ | +5 |
| D1 vÃ  H4 cÃ1ng á»§ng há»TM xu hÆ°á»›ng tÄƒng | +2 |
| **Tá»'i Ä'a** | **25** |

#### Vá»›i ká»‹ch báo£n SELL (bÃ¡n)

| Äiá»u kiá»‡n | Äiá»ƒm |
|---|---:|
| EMA50 D1 < EMA200 D1 | +8 |
| GiÃ¡ D1 < EMA200 D1 | +5 |
| GiÃ¡ D1 hoáo·c H4 < EMA50 | +5 |
| H4 cÃ3 cáo¥u trÃoc LH/LL rÃμ | +5 |
| D1 vÃ  H4 cÃ1ng á»§ng há»TM xu hÆ°á»›ng giáo£m | +2 |
| **Tá»'i Ä'a** | **25** |

Náo¿u thá»‹ trÆ°á»ng range (Ä'i ngang), trend score thÆ°á»ng tháo¥p. Khi Ä'Ã3 Location Quality quan trá»ng hÆ¡n.

### 8.2 Momentum Alignment â€" 0 Ä'áo¿n 20 Ä'iá»ƒm

NguyÃan táo ̄c quan trá»ng: RSI conditions (cÃ¡c Ä'iá»u kiá»‡n RSI) vÃ  MACD conditions (cÃ¡c Ä'iá»u kiá»‡n MACD) Ä'á»u lÃ  nhÃ3m chá»n **má»TMt Ä'iá»u kiá»‡n phÃ1 há»£p nháo¥t**, khÃ ́ng cá»TMng chá»"ng nhiá»u Ä'iá»u kiá»‡n cÃ1ng lÃoc. Tá»•ng momentum score (Ä'iá»ƒm Ä'á»TMng lÆ°á»£ng) = RSI score + MACD score, sau Ä'Ã3 clamp (káo1p Ä'iá»ƒm) vá» tá»'i Ä'a 20.

Äá»ƒ giáo£m nhiá»...u, MACD histogram (biá»ƒu Ä'á»" cá»TMt MACD) chá»‰ Ä'Æ°á»£c coi lÃ  â€œÄ'ang tÄƒng rÃμâ€ hoáo·c â€œÄ'ang giáo£m rÃμâ€ khi biáo¿n Ä'á»TMng cÃ1ng hÆ°á»›ng Ã­t nháo¥t **2 náo¿n liÃan tiáo¿p**. Náo¿u chá»‰ tÄƒng/giáo£m 1 náo¿n, coi lÃ  tÃ­n hiá»‡u sá»›m/yáo¿u vÃ  cho Ä'iá»ƒm tháo¥p hÆ¡n.

#### Vá»›i ká»‹ch báo£n BUY (mua)

| Äiá»u kiá»‡n | Äiá»ƒm |
|---|---:|
| RSI 30-50 and rising vs previous H4 candle | +8 |
| RSI 40-60 and not falling | +6 |
| RSI 60-70 and not falling | +3 |
| RSI > 75, quÃ¡ mua máo¡nh | +0 |
| MACD histogram > 0 vÃ  tÄƒng Ã­t nháo¥t 2 náo¿n liÃan tiáo¿p | +10 |
| MACD histogram < 0 nhÆ°ng tÄƒng Ã­t nháo¥t 2 náo¿n liÃan tiáo¿p, cÃ3 kháo£ nÄƒng cáo ̄t lÃan | +6 |
| MACD histogram chá»‰ tÄƒng 1 náo¿n | +3 |
| MACD histogram > 0 nhÆ°ng giáo£m nháo1 | +5 |
| **Tá»'i Ä'a** | **20** |


#### Vá»›i ká»‹ch báo£n SELL (bÃ¡n)

| Äiá»u kiá»‡n | Äiá»ƒm |
|---|---:|
| RSI 50-70 and falling vs previous H4 candle | +8 |
| RSI 40-60 and not rising | +6 |
| RSI 30-40 and not rising | +3 |
| RSI < 25, quÃ¡ bÃ¡n máo¡nh | +0 |
| MACD histogram < 0 vÃ  giáo£m Ã­t nháo¥t 2 náo¿n liÃan tiáo¿p | +10 |
| MACD histogram > 0 nhÆ°ng giáo£m Ã­t nháo¥t 2 náo¿n liÃan tiáo¿p, cÃ3 kháo£ nÄƒng cáo ̄t xuá»'ng | +6 |
| MACD histogram chá»‰ giáo£m 1 náo¿n | +3 |
| MACD histogram < 0 nhÆ°ng há»"i nháo1 | +5 |
| **Tá»'i Ä'a** | **20** |

Code máo«u:

```python
def momentum_score_buy(rsi, rsi_prev, macd_hist_now, macd_hist_prev, macd_hist_prev2):
    rsi_score = choose_one([
        (30 <= rsi <= 50 and rsi > rsi_prev, 8),
        (40 <= rsi <= 60 and rsi >= rsi_prev, 6),
        (60 < rsi <= 70 and rsi >= rsi_prev, 3),
        (rsi > 75, 0),
    ])

    macd_increasing_2_bars = macd_hist_now > macd_hist_prev > macd_hist_prev2
    macd_increasing_1_bar = macd_hist_now > macd_hist_prev
    macd_decreasing_1_bar = macd_hist_now < macd_hist_prev

    macd_score = choose_one([
        (macd_hist_now > 0 and macd_increasing_2_bars, 10),
        (macd_hist_now < 0 and macd_increasing_2_bars, 6),
        (macd_increasing_1_bar, 3),
        (macd_hist_now > 0 and macd_decreasing_1_bar, 5),
    ])

    return clamp(rsi_score + macd_score, 0, 20)


def momentum_score_sell(rsi, rsi_prev, macd_hist_now, macd_hist_prev, macd_hist_prev2):
    rsi_score = choose_one([
        (50 <= rsi <= 70 and rsi < rsi_prev, 8),
        (40 <= rsi <= 60 and rsi <= rsi_prev, 6),
        (30 <= rsi < 40 and rsi <= rsi_prev, 3),
        (rsi < 25, 0),
    ])

    macd_decreasing_2_bars = macd_hist_now < macd_hist_prev < macd_hist_prev2
    macd_decreasing_1_bar = macd_hist_now < macd_hist_prev
    macd_increasing_1_bar = macd_hist_now > macd_hist_prev

    macd_score = choose_one([
        (macd_hist_now < 0 and macd_decreasing_2_bars, 10),
        (macd_hist_now > 0 and macd_decreasing_2_bars, 6),
        (macd_decreasing_1_bar, 3),
        (macd_hist_now < 0 and macd_increasing_1_bar, 5),
    ])

    return clamp(rsi_score + macd_score, 0, 20)
```

### 8.3 Location Quality â€" 0 Ä'áo¿n 25 Ä'iá»ƒm

Location Quality pháo£i cháo¥m riÃang buy/sell. Há»- trá»£ tá»'t cho buy nhÆ°ng xáo¥u cho sell. KhÃ¡ng cá»± tá»'t cho sell nhÆ°ng xáo¥u cho buy.

#### Vá»›i ká»‹ch báo£n BUY (mua)

NhÃ3m Ä'iá»ƒm vá»‹ trÃ­ chÃ­nh lÃ  mutually exclusive (loáo¡i trá»« nhau), chá»‰ chá»n má»TMt:

| Äiá»u kiá»‡n chÃ­nh | Äiá»ƒm |
|---|---:|
| GiÃ¡ á»Ÿ vÃ1ng há»- trá»£ rÃμ rÃ ng | +15 |
| GiÃ¡ gáo§n há»- trá»£, cÃ¡ch dÆ°á»›i ATR/2 | +10 |
| GiÃ¡ lÆ¡ lá»­ng giá» ̄a cÃ¡c vÃ1ng | +3 |
| GiÃ¡ Ä'ang á»Ÿ vÃ1ng khÃ¡ng cá»± | +0 |

Äiá»ƒm cá»TMng thÃam:

| Äiá»u kiá»‡n cá»TMng thÃam | Äiá»ƒm |
|---|---:|
| CÃ3 confluence (há»TMi tá»¥ nhiá»u vÃ1ng há»- trá»£) | +5 |
| CÃ3 consolidation (tÃ­ch lÅ©y) Ã­t nháo¥t 3 náo¿n táo¡i há»- trá»£ | +5 |
| **Tá»'i Ä'a sau clamp** | **25** |

#### Vá»›i ká»‹ch báo£n SELL (bÃ¡n)

NhÃ3m Ä'iá»ƒm vá»‹ trÃ­ chÃ­nh lÃ  mutually exclusive (loáo¡i trá»« nhau), chá»‰ chá»n má»TMt:

| Äiá»u kiá»‡n chÃ­nh | Äiá»ƒm |
|---|---:|
| GiÃ¡ á»Ÿ vÃ1ng khÃ¡ng cá»± rÃμ rÃ ng | +15 |
| GiÃ¡ gáo§n khÃ¡ng cá»±, cÃ¡ch dÆ°á»›i ATR/2 | +10 |
| GiÃ¡ lÆ¡ lá»­ng giá» ̄a cÃ¡c vÃ1ng | +3 |
| GiÃ¡ Ä'ang á»Ÿ vÃ1ng há»- trá»£ | +0 |

Äiá»ƒm cá»TMng thÃam:

| Äiá»u kiá»‡n cá»TMng thÃam | Äiá»ƒm |
|---|---:|
| CÃ3 confluence (há»TMi tá»¥ nhiá»u vÃ1ng khÃ¡ng cá»±) | +5 |
| CÃ3 consolidation (tÃ­ch lÅ©y) Ã­t nháo¥t 3 náo¿n táo¡i khÃ¡ng cá»± | +5 |
| **Tá»'i Ä'a sau clamp** | **25** |

Code máo«u cÃ3 priority order (thá»© tá»± Æ°u tiÃan) rÃμ rÃ ng Ä'á»ƒ trÃ¡nh cá»TMng chá»"ng Ä'iá»u kiá»‡n:

```python
def price_in_zone(price, zone):
    return zone["low"] <= price <= zone["high"]


def distance_to_zone(price, zone):
    if price < zone["low"]:
        return zone["low"] - price
    if price > zone["high"]:
        return price - zone["high"]
    return 0


def nearest_zone(price, zones):
    if not zones:
        return None
    return min(zones, key=lambda z: distance_to_zone(price, z))


def location_score_buy(price, support_zones, resistance_zones, atr):
    nearest_support = nearest_zone(price, support_zones)
    nearest_resistance = nearest_zone(price, resistance_zones)

    # NhÃ3m Ä'iá»ƒm chÃ­nh: mutually exclusive, chá»‰ chá»n 1 nhÃ¡nh.
    if nearest_support and price_in_zone(price, nearest_support):
        base_score = 15
    elif nearest_support and distance_to_zone(price, nearest_support) <= atr * 0.5:
        base_score = 10
    elif nearest_resistance and price_in_zone(price, nearest_resistance):
        base_score = 0
    else:
        base_score = 3

    bonus = 0
    if nearest_support and nearest_support.get("confluence_count", 0) >= 2:
        bonus += 5
    if nearest_support and nearest_support.get("consolidation_bars", 0) >= 3:
        bonus += 5

    return clamp(base_score + bonus, 0, 25)


def location_score_sell(price, support_zones, resistance_zones, atr):
    nearest_support = nearest_zone(price, support_zones)
    nearest_resistance = nearest_zone(price, resistance_zones)

    # NhÃ3m Ä'iá»ƒm chÃ­nh: mutually exclusive, chá»‰ chá»n 1 nhÃ¡nh.
    if nearest_resistance and price_in_zone(price, nearest_resistance):
        base_score = 15
    elif nearest_resistance and distance_to_zone(price, nearest_resistance) <= atr * 0.5:
        base_score = 10
    elif nearest_support and price_in_zone(price, nearest_support):
        base_score = 0
    else:
        base_score = 3

    bonus = 0
    if nearest_resistance and nearest_resistance.get("confluence_count", 0) >= 2:
        bonus += 5
    if nearest_resistance and nearest_resistance.get("consolidation_bars", 0) >= 3:
        bonus += 5

    return clamp(base_score + bonus, 0, 25)
```

### 8.4 Risk Condition â€" 0 Ä'áo¿n 15 Ä'iá»ƒm

Risk Condition Ä'o má»©c Ä'á»TM an toÃ n Ä'á»ƒ cÃ¢n nháo ̄c giao dá»‹ch táo¡i thá»i Ä'iá»ƒm phÃ¢n tÃ­ch. ThÃ nh pháo§n nÃ y khÃ ́ng dÃ1ng Ä'iá»ƒm Ã¢m. Äiá»u kiá»‡n xáo¥u thÃ¬ khÃ ́ng Ä'Æ°á»£c Ä'iá»ƒm.

**LÆ°u Ã1⁄2:** Risk Condition lÃ  thÃ nh pháo§n dÃ1ng chung cho cáo£ buy scenario (ká»‹ch báo£n mua) vÃ  sell scenario (ká»‹ch báo£n bÃ¡n), vÃ¬ nÃ3 Ä'o mÃ ́i trÆ°á»ng thá»‹ trÆ°á»ng táo¡i thá»i Ä'iá»ƒm phÃ¢n tÃ­ch nhÆ° ATR, spread vÃ  tin tá»©c sÃ¡t giá», khÃ ́ng Ä'o hÆ°á»›ng giao dá»‹ch.

| Äiá»u kiá»‡n | Äiá»ƒm |
|---|---:|
| ATR hiá»‡n táo¡i trong khoáo£ng bÃ¬nh thÆ°á»ng, tá»©c Â±20% ATR trung bÃ¬nh 14 ngÃ y | +6 |
| ATR cao nhÆ°ng cÃ3 lÃ1⁄2 do rÃμ rÃ ng, vÃ­ dá»¥ vá»«a má»Ÿ cá»­a tuáo§n hoáo·c sau tin lá»›n | +3 |
| ATR cao báo¥t thÆ°á»ng khÃ ́ng rÃμ lÃ1⁄2 do | +0 |
| KhÃ ́ng cÃ3 tin Ä'á» trong 3 giá» tá»›i | +6 |
| CÃ3 tin Ä'á» trong 3 giá» tá»›i | +0 |
| Spread bÃ¬nh thÆ°á»ng náo¿u láo¥y Ä'Æ°á»£c dá» ̄ liá»‡u | +3 |
| Spread báo¥t thÆ°á»ng hoáo·c khÃ ́ng láo¥y Ä'Æ°á»£c spread | +0 |
| **Tá»'i Ä'a** | **15** |

Code máo«u:

```python
def calc_risk_condition(atr_current, atr_avg_14d, news_in_3h, spread_status):
    score = 0

    if 0.8 * atr_avg_14d <= atr_current <= 1.2 * atr_avg_14d:
        score += 6
    elif atr_current <= 1.5 * atr_avg_14d:
        score += 3
    else:
        score += 0

    score += 0 if news_in_3h else 6
    score += 3 if spread_status == "normal" else 0

    return clamp(score, 0, 15)
```

### 8.5 Macro Alignment â€" 0 Ä'áo¿n 30 Ä'iá»ƒm (3 táo§ng, v12.1)

Macro Alignment Ä'o bá»'i cáo£nh vÄ© mÃ ́ cÃ3 thuáo­n vá»›i ká»‹ch báo£n buy hoáo·c sell hay khÃ ́ng. Tá»« v12.1, macro Ä'Æ°á»£c tÃ­nh báo±ng **Rule Engine 3 táo§ng** thay vÃ¬ AI cháo¥m thá»§ cÃ ́ng, Ä'áo£m báo£o tÃ­nh nháo¥t quÃ¡n vÃ  khÃ ́ng tá»'n token AI.

**Cáo¥u trÃoc 3 táo§ng:**

| Táo§ng | Ná»TMi dung | Äiá»ƒm tá»'i Ä'a | Nguá»"n dá» ̄ liá»‡u |
|---|---:|---|---|
| T1 â€" LÃ£i suáo¥t & ChÃ­nh sÃ¡ch tiá»n tá»‡ | Rate differential, rate trend (hike/hold/cut), stance tá»« headline | 12 | `config/interest_rates.json` + Google News RSS headline |
| T2 â€" Lá»‹ch kinh táo¿ | Sá»' lÆ°á»£ng + má»©c Ä'á»TM quan trá»ng cá»§a sá»± kiá»‡n 72h tá»›i cho base vÃ  quote currency | 10 | Forex Factory calendar |
| T3 â€" TÃ¢m lÃ1⁄2 rá»§i ro & Äá»‹a chÃ­nh trá»‹ | Risk-on/risk-off sentiment, Ä'iá»ƒm nÃ3ng Ä'á»‹a chÃ­nh trá»‹, safe haven demand | 8 | Google News RSS headline |
| **Tá»•ng** | | **30** | |

**Trá»ng sá»' Ä'á»TMng theo cháo¥t lÆ°á»£ng dá» ̄ liá»‡u (macro_confidence):**

Há»‡ sá»' `macro_confidence âˆˆ [0.10, 1.0]` Ä'Æ°á»£c tÃ­nh tá»«:
- Äá»TM má»›i cá»§a headline (headline > 12h â†' -0.15, > 6h â†' -0.10)
- Sá»' lÆ°á»£ng headline (< 3 â†' -0.10, = 0 â†' thÃam -0.10)
- CÃ3 calendar data khÃ ́ng (khÃ ́ng cÃ3 â†' -0.10)

`macro_effective = macro_raw Ã- macro_confidence`

Khi thiáo¿u dá» ̄ liá»‡u vÄ© mÃ ́, Ä'iá»ƒm vÄ© mÃ ́ tá»± Ä'á»TMng giáo£m, pháo§n cÃ2n láo¡i do ká»1 thuáo­t + risk quyáo¿t Ä'á»‹nh.

**Chi tiáo¿t tá»«ng táo§ng (xem `services/news_service.py`):**

T1 â€" LÃ£i suáo¥t & ChÃ­nh sÃ¡ch tiá»n tá»‡ (0-12):
- Rate differential (0-2): chÃanh lá»‡ch lÃ£i suáo¥t tuyá»‡t Ä'á»'i base - quote
- Rate trend (0-5): xu hÆ°á»›ng thay Ä'á»•i lÃ£i suáo¥t (hike=5, hold=2, cut=0)
- Stance tá»« headline (0-5): hawkish/dovish sentiment thá»i gian thá»±c

T2 â€" Lá»‹ch kinh táo¿ (0-10):
- Base 5 Ä'iá»ƒm má»-i bÃan
- Má»-i high-impact event cho 1 currency â†' -1 Ä'iá»ƒm cho bÃan tiáo¿p xÃoc vá»›i currency Ä'Ã3
- Má»-i high-impact event cho currency Ä'á»'i diá»‡n â†' +1 Ä'iá»ƒm (tá»'i Ä'a Â±2)

T3 â€" TÃ¢m lÃ1⁄2 rá»§i ro & Äá»‹a chÃ­nh trá»‹ (0-8):
- Risk sentiment (0-4): risk-on â†' lá»£i cho risk currencies (AUD/NZD/CAD), risk-off â†' lá»£i cho safe havens (USD/JPY/CHF/XAU)
- Geopolitical (0-4): sá»' lÆ°á»£ng + má»©c Ä'á»TM nghiÃam trá»ng cá»§a Ä'iá»ƒm nÃ3ng

KhÃ ́ng trá»TMn Macro Alignment vá»›i Event Risk (rá»§i ro tin tá»©c sÃ¡t giá»). Tin Ä'á» trong 3 giá» tá»›i Ä'Ã£ Ä'Æ°á»£c tÃ­nh á»Ÿ Risk Condition (Ä'iá»u kiá»‡n rá»§i ro).

AI chá»‰ Ä'Æ°á»£c chá»n má»TMt trong nÄƒm má»©c Ä'iá»ƒm: **0, 4, 7, 11, 15**. Náo¿u thiáo¿u dá» ̄ liá»‡u hoáo·c dá» ̄ liá»‡u mÃ¢u thuáo«n, Æ°u tiÃan cháo¥m **7 Ä'iá»ƒm** thay vÃ¬ Ä'oÃ¡n.

| Äiá»ƒm | Ã nghÄ©a | Khi dÃ1ng |
|---:|---|---|
| 15 | VÄ© mÃ ́ thuáo­n máo¡nh vá»›i ká»‹ch báo£n | Nhiá»u yáo¿u tá»' chÃ­nh cÃ1ng á»§ng há»TM rÃμ rÃ ng, cÃ3 dá» ̄ liá»‡u Ä'á»‹nh lÆ°á»£ng xÃ¡c nháo­n |
| 11 | VÄ© mÃ ́ hÆ¡i thuáo­n | CÃ3 1â€"2 yáo¿u tá»' chÃ­nh á»§ng há»TM, khÃ ́ng cÃ3 yáo¿u tá»' lá»›n Ä'i ngÆ°á»£c |
| 7 | Trung tÃ­nh, khÃ ́ng rÃμ rÃ ng | Dá» ̄ liá»‡u trÃ¡i chiá»u, Ä'i ngang, thiáo¿u dá» ̄ liá»‡u quan trá»ng, hoáo·c khÃ ́ng cÃ3 catalyst (cháo¥t xÃoc tÃ¡c) rÃμ |
| 4 | HÆ¡i mÃ¢u thuáo«n | CÃ3 yáo¿u tá»' chÃ­nh Ä'i ngÆ°á»£c nhÆ°ng chÆ°a quÃ¡ máo¡nh |
| 0 | MÃ¢u thuáo«n máo¡nh vá»›i ká»‹ch báo£n | Nhiá»u yáo¿u tá»' chÃ­nh Ä'i ngÆ°á»£c rÃμ rÃ ng |

#### NgÆ°á»¡ng tham chiáo¿u cho XAU/USD (vÃ ng giao ngay so vá»›i USD)

CÃ¡c ngÆ°á»¡ng dÆ°á»›i Ä'Ã¢y lÃ  ngÆ°á»¡ng tham chiáo¿u Ä'á»ƒ AI cháo¥m nháo¥t quÃ¡n hÆ¡n, khÃ ́ng pháo£i chÃ¢n lÃ1⁄2 tuyá»‡t Ä'á»'i. Há»‡ thá»'ng nÃan Ä'Æ°a vÃ o prompt cÃ¡c dá» ̄ liá»‡u nhÆ° DXY change 5 phiÃan, US10Y change theo basis points (bps â€" Ä'iá»ƒm cÆ¡ báo£n), real yield (lá»£i suáo¥t thá»±c), VIX vÃ  ghi chÃo Fed.

**Vá»›i ká»‹ch báo£n BUY XAU/USD:**

| Äiá»ƒm | Äiá»u kiá»‡n tham chiáo¿u |
|---:|---|
| 15 | DXY giáo£m > 0.5% trong 5 phiÃan gáo§n nháo¥t **AND** US10Y giáo£m > 5 bps **AND** real yield khÃ ́ng tÄƒng **AND** khÃ ́ng cÃ3 sá»± kiá»‡n Fed sÃ¡t giá» |
| 11 | DXY giáo£m nháo1 0.1%â€"0.5% **OR** US10Y Ä'i ngang/giáo£m nháo1; khÃ ́ng cÃ3 yáo¿u tá»' lá»›n Ä'i ngÆ°á»£c |
| 7 | DXY biáo¿n Ä'á»TMng trong khoáo£ng Â±0.1% **AND** US10Y biáo¿n Ä'á»TMng dÆ°á»›i Â±3 bps; hoáo·c dá» ̄ liá»‡u thiáo¿u/khÃ ́ng rÃμ |
| 4 | DXY tÄƒng nháo1 0.1%â€"0.5% **OR** US10Y tÄƒng nháo1 3â€"5 bps; nhÆ°ng chÆ°a cÃ3 Ä'á»"ng thuáo­n máo¡nh chá»'ng láo¡i vÃ ng |
| 0 | DXY tÄƒng > 0.5% **AND** US10Y tÄƒng > 5 bps **AND** real yield tÄƒng hoáo·c Fed tone hawkish (giá»ng Ä'iá»‡u cá»©ng ráo ̄n) gáo§n Ä'Ã¢y |

**Vá»›i ká»‹ch báo£n SELL XAU/USD:**

| Äiá»ƒm | Äiá»u kiá»‡n tham chiáo¿u |
|---:|---|
| 15 | DXY tÄƒng > 0.5% trong 5 phiÃan gáo§n nháo¥t **AND** US10Y tÄƒng > 5 bps **AND** real yield tÄƒng **AND** nhu cáo§u trÃo áo©n khÃ ́ng tÄƒng |
| 11 | DXY tÄƒng nháo1 0.1%â€"0.5% **OR** US10Y Ä'i ngang/tÄƒng nháo1; khÃ ́ng cÃ3 yáo¿u tá»' lá»›n há»- trá»£ vÃ ng |
| 7 | DXY vÃ  lá»£i suáo¥t Ä'i ngang, dá» ̄ liá»‡u trÃ¡i chiá»u hoáo·c thiáo¿u dá» ̄ liá»‡u |
| 4 | DXY giáo£m nháo1 0.1%â€"0.5% **OR** US10Y giáo£m nháo1 3â€"5 bps; nhÆ°ng chÆ°a Ä'á»§ máo¡nh Ä'á»ƒ phá»§ Ä'á»‹nh sell |
| 0 | DXY giáo£m > 0.5% **AND** US10Y giáo£m > 5 bps **AND** real yield giáo£m hoáo·c cÃ3 rá»§i ro Ä'á»‹a chÃ­nh trá»‹ há»- trá»£ vÃ ng |

#### NgÆ°á»¡ng tham chiáo¿u cho cÃ¡c cáo·p Forex chÃ­nh

Vá»›i cÃ¡c cáo·p cÃ3 USD Ä'á»©ng sau nhÆ° EUR/USD, GBP/USD, AUD/USD, NZD/USD:

| Äiá»ƒm | VÃ­ dá»¥ cho ká»‹ch báo£n BUY EUR/USD hoáo·c BUY GBP/USD |
|---:|---|
| 15 | DXY giáo£m > 0.5% trong 5 phiÃan **AND** US10Y giáo£m > 5 bps **AND** dá» ̄ liá»‡u khu vá»±c Ä'á»"ng tiá»n Ä'á»'i á»©ng tá»'t hÆ¡n ká»3 vá»ng |
| 11 | DXY giáo£m nháo1 0.1%â€"0.5% **OR** lá»£i suáo¥t Má»1 khÃ ́ng tÄƒng; khÃ ́ng cÃ3 tin xáo¥u lá»›n tá»« Ä'á»"ng tiá»n Ä'á»'i á»©ng |
| 7 | DXY Ä'i ngang trong Â±0.1%, dá» ̄ liá»‡u Má»1 vÃ  dá» ̄ liá»‡u Ä'á»"ng tiá»n Ä'á»'i á»©ng trÃ¡i chiá»u |
| 4 | DXY tÄƒng nháo1 0.1%â€"0.5% **OR** dá» ̄ liá»‡u Má»1 tá»'t hÆ¡n ká»3 vá»ng má»TMt pháo§n |
| 0 | DXY tÄƒng > 0.5% **AND** lá»£i suáo¥t Má»1 tÄƒng > 5 bps **AND** dá» ̄ liá»‡u Má»1 máo¡nh rÃμ |

Vá»›i USD/JPY:

| Äiá»ƒm | VÃ­ dá»¥ cho ká»‹ch báo£n BUY USD/JPY |
|---:|---|
| 15 | US10Y tÄƒng > 5 bps **AND** chÃanh lá»‡ch lá»£i suáo¥t Má»1-Nháo­t má»Ÿ rá»TMng **AND** BOJ dovish (Ã ́n hÃ2a) |
| 11 | US10Y tÄƒng nháo1 3â€"5 bps hoáo·c Ä'i ngang á»Ÿ má»©c cao, khÃ ́ng cÃ3 rá»§i ro BOJ can thiá»‡p |
| 7 | US10Y Ä'i ngang, Fed/BOJ khÃ ́ng cÃ3 tÃ­n hiá»‡u má»›i |
| 4 | US10Y giáo£m nháo1 3â€"5 bps hoáo·c xuáo¥t hiá»‡n cáo£nh bÃ¡o can thiá»‡p yáo¿u tá»« Nháo­t |
| 0 | US10Y giáo£m > 5 bps **OR** BOJ hawkish/cÃ3 rá»§i ro can thiá»‡p rÃμ |

#### NgÆ°á»¡ng tham chiáº¿u cho cÃ¡c cáº·p chÃ©o (Cross Pairs) khÃ´ng cÃ³ USD

CÃ¡c cáº·p chÃ©o khÃ´ng chá»‹u áº£nh hÆ°á»Ÿng trá»±c tiáº¿p tá»« DXY. Thay vÃ o Ä'Ã³, cáº§n theo dÃµi cÃ¡c yáº¿u tá»' riÃªng cho tá»«ng nhÃ³m.

##### NguyÃªn táº¯c chung cho Cross Pairs

- **Yield spread giá»¯a 2 bÃªn lÃ  yáº¿u tá»' sá»' 1** — má»—i cáº·p cÃ³ má»™t spread lÃ£i suáº¥t riÃªng (VD: EUR/GBP â†' DE10Y vs UK10Y; EUR/JPY â†' DE10Y vs JP10Y). Spread má»Ÿ rá»™ng cÃ³ lá»£i cho Ä'á»"ng tiá»n cÃ³ lÃ£i suáº¥t cao hÆ¡n.
- **Stance cá»§a 2 ngÃ¢n hÃ ng trung Æ°Æ¡ng** — divergence giá»¯a ECB/BOE/BOJ/SNB/RBA/RBNZ/BOC lÃ  Ä'á»™ng lá»±c chÃ­nh cho xu hÆ°á»›ng dÃ i háº¡n.
- **Risk sentiment** — risk-on cÃ³ lá»£i cho cÃ¡c cáº·p cÃ³ Ä'á»"ng tiá»n yield cao (AUD, NZD, GBP); risk-off cÃ³ lá»£i cho safe havens (JPY, CHF).
- **Commodity prices** — quan trá»ng vá»›i CAD (dáº§u WTI), AUD (quáº·ng sáº¯t, Ä'á»"ng), NZD (sá»¯a GDT).
- **Dá»¯ liá»‡u kinh táº¿ khu vá»±c** — China data áº£nh hÆ°á»Ÿng AUD/NZD máº¡nh; EU data áº£nh hÆ°á»Ÿng EUR; UK data áº£nh hÆ°á»Ÿng GBP.

##### Tham chiáº¿u theo nhÃ³m cáº·p

**NhÃ³m EUR Crosses (EUR/GBP, EUR/JPY, EUR/CHF, EUR/AUD, EUR/NZD, EUR/CAD):**

| Yáº¿u tá»' cáº§n check | Má»©c Ä'á»™ quan trá»ng | Ghi chÃº |
|---|---|---|
| ECB stance + DE10Y Bund yield | Ráº¥t cao | Base currency driver |
| Yield spread giá»¯a 2 bÃªn | Ráº¥t cao | DE10Y vs UK10Y/JP10Y/CH10Y... |
| Eurozone CPI / Core CPI / PMI / GDP | Cao | Dá»¯ liá»‡u khu vá»±c Eurozone |
| Sentiment chÃ¢u Ã‚u (ZEW, IFO, Sentix) | Trung bÃ¬nh | Leading indicators |
| Risk sentiment (risk-on/risk-off) | Cao vá»›i EUR/JPY, EUR/AUD | Risk-on â†' EUR máº¡nh vs JPY/CHF; risk-off â†' EUR yáº¿u vs JPY/CHF |

**NhÃ³m GBP Crosses (GBP/JPY, GBP/AUD, GBP/NZD, GBP/CAD, GBP/CHF):**

| Yáº¿u tá»' cáº§n check | Má»©c Ä'á»™ quan trá»ng | Ghi chÃº |
|---|---|---|
| BOE stance + UK10Y Gilt yield | Ráº¥t cao | Base currency driver |
| UK CPI / wage growth / PMI / GDP | Ráº¥t cao | UK economic health |
| Yield spread (UK10Y vs JP10Y/AU10Y/NZ10Y/CA10Y) | Ráº¥t cao | Quyáº¿t Ä'á»‹nh dÃ²ng vá»'n |
| Risk sentiment | Ráº¥t cao vá»›i GBP/JPY | "Barometer of risk" — GBP/JPY lÃ  ná»•i tiáº¿ng nháº¡y vá»›i risk |
| Brexit-related / UK political risks | Tháº¥p (náº¿u khÃ´ng cÃ³ sá»± kiá»‡n) | Chá»‰ check khi cÃ³ tin má»›i |

**NhÃ³m JPY Crosses (EUR/JPY, GBP/JPY, AUD/JPY, NZD/JPY, CAD/JPY, CHF/JPY):**

| Yáº¿u tá»' cáº§n check | Má»©c Ä'á»™ quan trá»ng | Ghi chÃº |
|---|---|---|
| BOJ stance + JP10Y JGB yield | Ráº¥t cao | Quote currency driver |
| US-Japan yield spread (US10Y - JP10Y) | Ráº¥t cao | áº¢nh hÆ°á»Ÿng carry trade, dÃ¹ khÃ´ng cÃ³ USD trong cáº·p |
| Intervention risk (MOF/BOJ) | Cao | Äáº·c biá»‡t khi JPY yáº¿u quÃ¡ nhanh |
| Risk sentiment (VIX, S&P 500) | Ráº¥t cao | JPY lÃ  safe haven sá»' 1 — risk-off â†' JPY máº¡nh |
| JGB yield curve control changes | Trung bÃ¬nh | BOJ policy shifts |

**NhÃ³m CHF Crosses (EUR/CHF, GBP/CHF, USD/CHF, CHF/JPY):**

| Yáº¿u tá»' cáº§n check | Má»©c Ä'á»™ quan trá»ng | Ghi chÃº |
|---|---|---|
| SNB stance + Swiss CPI | Cao | Quote currency driver |
| Safe haven demand / Risk sentiment | Ráº¥t cao | CHF lÃ  safe haven #2 sau JPY |
| Gold correlation | Trung bÃ¬nh | CHF cÃ³ tÆ°Æ¡ng quan dÆ°Æ¡ng vá»›i XAU |
| SNB intervention risk | Trung bÃ¬nh | SNB cÃ³ lá»‹ch sá»­ can thiá»‡p thá»‹ trÆ°á»
ng FX |

**NhÃ³m AUD/NZD Crosses (AUD/NZD, AUD/CAD, AUD/CHF, NZD/CAD, NZD/CHF):**

| Yáº¿u tá»' cáº§n check | Má»©c Ä'á»™ quan trá»ng | Ghi chÃº |
|---|---|---|
| RBA/RBNZ stance + rate differential | Ráº¥t cao | AUD vs NZD: RBA vs RBNZ divergence |
| Commodity prices | Ráº¥t cao | Iron ore/copper cho AUD; Dairy (GDT) cho NZD; Oil cho CAD |
| China data (PMI, GDP, trade balance) | Ráº¥t cao | China lÃ  Ä'á»'i tÃ¡c thÆ°Æ¡ng máº¡i #1 cá»§a cáº£ AU vÃ  NZ |
| Risk sentiment | Cao | AUD vÃ  NZD lÃ  "risk currencies" — risk-on má»›i máº¡nh |

**NhÃ³m CAD Crosses (EUR/CAD, GBP/CAD, AUD/CAD, NZD/CAD, CAD/CHF, CAD/JPY):**

| Yáº¿u tá»' cáº£n check | Má»©c Ä'á»™ quan trá»ng | Ghi chÃº |
|---|---|---|
| BOC stance + Canada CPI/Jobs/GDP | Ráº¥t cao | Quote currency driver |
| WTI Crude Oil price | Ráº¥t cao | Canada lÃ  nÆ°á»›c xuáº¥t kháº©u dáº§u lá»›n — oil up â†' CAD máº¡nh |
| Oil-DXY correlation dynamics | Trung bÃ¬nh | Dáº§u tÄƒng + USD yáº¿u â†' CAD double boost |
| Canada-US trade relations | Trung bÃ¬nh | US lÃ  Ä'á»'i tÃ¡c thÆ°Æ¡ng máº¡i #1 cá»§a Canada |

##### Correlation Data Payload cho Cross Pairs

Khi phÃ¢n tÃ­ch má»™t cross pair, payload gá»­i vÃ o prompt cáº§n bá»• sung cÃ¡c trÆ°á»
ng sau (ngoÃ i cÃ¡c trÆ°á»
ng chung Ä'Ã£ cÃ³):

```json
{
  "correlation_data": {
    "base_yield_name": "DE10Y Bund",
    "base_yield_change_bps": 3,
    "quote_yield_name": "UK10Y Gilt",
    "quote_yield_change_bps": 1,
    "yield_spread_change_bps": 2,
    "yield_spread_direction": "widening",
    "favoring_currency": "EUR",
    "base_cb_stance": "ECB on hold, dovish tilt",
    "quote_cb_stance": "BOE cut expected in next 2 meetings",
    "cb_divergence": "slightly EUR-positive",
    "risk_sentiment": "risk-on",
    "risk_impact_on_pair": "supports base if base is risk currency",
    "commodity_relevant": false,
    "commodity_details": null
  }
}
```

VÃ­ dá»¥ cá»¥ thá»ƒ cho EUR/JPY:

```json
{
  "correlation_data": {
    "base_yield_name": "DE10Y Bund",
    "base_yield_change_bps": -2,
    "quote_yield_name": "JP10Y JGB",
    "quote_yield_change_bps": 0,
    "yield_spread_change_bps": -2,
    "yield_spread_direction": "narrowing",
    "favoring_currency": "JPY",
    "base_cb_stance": "ECB dovish, cut expected",
    "quote_cb_stance": "BOJ on hold, slowly normalizing",
    "cb_divergence": "JPY-positive",
    "risk_sentiment": "risk-off",
    "risk_impact_on_pair": "risk-off favors JPY (safe haven) â‡' EUR/JPY bearish",
    "us10y_change_bps": -6,
    "us_jp_yield_spread_change_bps": -6,
    "intervention_risk": "low",
    "commodity_relevant": false
  }
}
```

VÃ­ dá»¥ cá»¥ thá»ƒ cho AUD/NZD:

```json
{
  "correlation_data": {
    "base_yield_name": "AU10Y",
    "base_yield_change_bps": 2,
    "quote_yield_name": "NZ10Y",
    "quote_yield_change_bps": 0,
    "yield_spread_change_bps": 2,
    "yield_spread_direction": "widening",
    "favoring_currency": "AUD",
    "base_cb_stance": "RBA on hold, hawkish bias",
    "quote_cb_stance": "RBNZ cut expected",
    "cb_divergence": "AUD-positive",
    "risk_sentiment": "risk-on",
    "risk_impact_on_pair": "risk-on supports both AUD and NZD, neutral for the pair",
    "commodity_relevant": true,
    "commodity_details": {
      "iron_ore_change_pct": 1.2,
      "copper_change_pct": 0.5,
      "dairy_gdt_change_pct": -0.8,
      "commodity_net_impact": "mildly AUD-positive (iron ore up > dairy down)",
      "china_pmi_manufacturing": 50.3,
      "china_pmi_services": 51.2
    }
  }
}
```

##### Quy táº¯c Ä'á»'i vá»›i AI khi cháº¥m Macro Alignment cho Cross Pairs

Khi khÃ´ng cÃ³ DXY Ä'á»ƒ tham chiáº¿u, AI pháº£i dá»±a vÃ o:

1. **Yield spread direction vÃ  magnitude** (thay cho DXY) — Ä'Ã¢y lÃ  chá»‰ bÃ¡o sá»' 1
2. **CB divergence** — stance cá»§a 2 ngÃ¢n hÃ ng trung Æ°Æ¡ng cÃ³ thuáº­n chiá»u vá»›i ká»‹ch báº£n?
3. **Risk sentiment impact** — risk-on/off cÃ³ lá»£i cho base hay quote currency?
4. **Commodity prices** (náº¿u liÃªn quan) — hÆ°á»›ng commodity cÃ³ thuáº­n vá»›i ká»‹ch báº£n?
5. **China data** (náº¿u lÃ  AUD/NZD pairs)

Thang Ä'iá»ƒm váº«n dÃ¹ng 0/4/7/11/15 nhÆ° cÃ¡c cáº·p cÃ³ USD.
Khi thiáº¿u dá»¯ liá»‡u yield spread hoáº·c CB stance, Æ°u tiÃªn score 7.

#### System Prompt máº«u cho AI

```text
Báº¡n lÃ  bá»™ pháº­n Ä'Ã¡nh giÃ¡ vÄ© mÃ´ cho há»‡ thá»'ng phÃ¢n tÃ­ch giao dá»‹ch.

Nhiá»‡m vá»¥: cháo¥m macro_score cho má»TMt ká»‹ch báo£n giao dá»‹ch cá»¥ thá»ƒ.
Chá»‰ Ä'Æ°á»£c tráo£ vá» má»TMt trong nÄƒm Ä'iá»ƒm: 0, 4, 7, 11, 15.

Dá» ̄ liá»‡u Ä'áo§u vÃ o cÃ3 thá»ƒ gá»"m:
- symbol: mÃ£ giao dá»‹ch
- scenario: buy hoáo·c sell
- dxy_change_5d_pct: % thay Ä'á»•i DXY trong 5 phiÃan
- us10y_change_bps: thay Ä'á»•i lá»£i suáo¥t trÃ¡i phiáo¿u Má»1 ká»3 háo¡n 10 nÄƒm theo bps
- real_yield_change_bps: thay Ä'á»•i lá»£i suáo¥t thá»±c theo bps náo¿u cÃ3
- vix_change_pct: % thay Ä'á»•i VIX náo¿u cÃ3
- central_bank_note: ghi chÃo Fed/ECB/BOJ/BOE/RBA/RBNZ/BOC/SNB náo¿u cÃ3
- macro_events_note: ghi chÃo sá»± kiá»‡n vÄ© mÃ ́ Ä'Ã£ cÃ ́ng bá»' náo¿u cÃ3

Quy táo ̄c chung:
- 15: vÄ© mÃ ́ thuáo­n máo¡nh vá»›i ká»‹ch báo£n. Cáo§n nhiá»u yáo¿u tá»' chÃ­nh cÃ1ng á»§ng há»TM vÃ  cÃ3 dá» ̄ liá»‡u Ä'á»‹nh lÆ°á»£ng rÃμ.
- 11: vÄ© mÃ ́ hÆ¡i thuáo­n. CÃ3 1â€"2 yáo¿u tá»' chÃ­nh á»§ng há»TM vÃ  khÃ ́ng cÃ3 yáo¿u tá»' lá»›n Ä'i ngÆ°á»£c.
- 7: trung tÃ­nh. Dá» ̄ liá»‡u trÃ¡i chiá»u, Ä'i ngang, thiáo¿u dá» ̄ liá»‡u quan trá»ng, hoáo·c khÃ ́ng cÃ3 catalyst rÃμ.
- 4: hÆ¡i mÃ¢u thuáo«n. CÃ3 yáo¿u tá»' chÃ­nh Ä'i ngÆ°á»£c nhÆ°ng chÆ°a quÃ¡ máo¡nh.
- 0: mÃ¢u thuáo«n máo¡nh. Nhiá»u yáo¿u tá»' chÃ­nh Ä'i ngÆ°á»£c rÃμ rÃ ng.

NgÆ°á»¡ng tham chiáo¿u cho BUY XAU/USD:
- 15: DXY giáo£m > 0.5% trong 5 phiÃan AND US10Y giáo£m > 5 bps AND real yield khÃ ́ng tÄƒng.
- 11: DXY giáo£m 0.1%â€"0.5% OR US10Y Ä'i ngang/giáo£m nháo1, khÃ ́ng cÃ3 yáo¿u tá»' lá»›n Ä'i ngÆ°á»£c.
- 7: DXY trong khoáo£ng Â±0.1% AND US10Y biáo¿n Ä'á»TMng dÆ°á»›i Â±3 bps, hoáo·c thiáo¿u dá» ̄ liá»‡u.
- 4: DXY tÄƒng 0.1%â€"0.5% OR US10Y tÄƒng 3â€"5 bps.
- 0: DXY tÄƒng > 0.5% AND US10Y tÄƒng > 5 bps AND real yield tÄƒng hoáo·c Fed hawkish.

NgÆ°á»¡ng tham chiáo¿u cho SELL XAU/USD lÃ  chiá»u ngÆ°á»£c láo¡i:
- 15: DXY tÄƒng > 0.5% AND US10Y tÄƒng > 5 bps AND real yield tÄƒng.
- 11: DXY tÄƒng 0.1%â€"0.5% OR US10Y Ä'i ngang/tÄƒng nháo1.
- 7: DXY/yield Ä'i ngang hoáo·c thiáo¿u dá» ̄ liá»‡u.
- 4: DXY giáo£m 0.1%â€"0.5% OR US10Y giáo£m 3â€"5 bps.
- 0: DXY giáo£m > 0.5% AND US10Y giáo£m > 5 bps AND real yield giáo£m hoáo·c cÃ3 risk-off há»- trá»£ vÃ ng.

KhÃ ́ng tá»± bá»‹a sá»' liá»‡u. Chá»‰ dÃ1ng dá» ̄ liá»‡u Ä'Æ°á»£c cung cáo¥p trong input.
KhÃ ́ng cháo¥m rá»§i ro tin tá»©c sÃ¡t giá» trong macro_score, vÃ¬ pháo§n Ä'Ã3 Ä'Ã£ náo±m á»Ÿ risk_condition.
Náo¿u khÃ ́ng Ä'á»§ dá» ̄ liá»‡u, Æ°u tiÃan score 7 thay vÃ¬ Ä'oÃ¡n.

Output báo ̄t buá»TMc:
{"macro_score": <0|4|7|11|15>, "reason": "<1 cÃ¢u tiáo¿ng Viá»‡t>"}
```

### 8.5.1 Tá»'i Æ°u prompt Macro Alignment Ä'á»ƒ tiáo¿t kiá»‡m token

Prompt Macro Alignment khÃ ́ng nÃan gá»­i toÃ n bá»TM quy táo ̄c cá»§a má»i mÃ£ giao dá»‹ch trong má»-i láo§n gá»i AI. NÃan tÃ¡ch thÃ nh 2 pháo§n:

**System prompt cá»' Ä'á»‹nh:**

- Vai trÃ2 cá»§a AI trong há»‡ thá»'ng.
- Quy táo ̄c khÃ ́ng bá»‹a sá»'.
- Thang Ä'iá»ƒm cá»' Ä'á»‹nh 0/4/7/11/15.
- Output JSON báo ̄t buá»TMc.

**User prompt thay Ä'á»•i theo tá»«ng láo§n phÃ¢n tÃ­ch:**

- Symbol (mÃ£ giao dá»‹ch).
- Scenario (ká»‹ch báo£n buy/sell).
- Dá» ̄ liá»‡u vÄ© mÃ ́ Ä'Ã£ láo¥y Ä'Æ°á»£c.
- Chá»‰ gá»­i ngÆ°á»¡ng tham chiáo¿u liÃan quan Ä'áo¿n symbol Ä'ang phÃ¢n tÃ­ch.

VÃ­ dá»¥ user prompt ngáo ̄n cho XAU/USD:

```json
{
  "symbol": "XAU/USD",
  "scenario": "buy",
  "dxy_change_5d_pct": -0.42,
  "us10y_change_bps": -4,
  "real_yield_change_bps": -2,
  "vix_change_pct": 1.5,
  "central_bank_note": "Fed khÃ ́ng cÃ3 phÃ¡t biá»ƒu má»›i trong 24h",
  "threshold_profile": "xauusd"
}
```

Má»¥c tiÃau: giáo£m token, giáo£m nhiá»...u prompt vÃ  giÃop AI cháo¥m nháo¥t quÃ¡n hÆ¡n.

### 8.5.2 Prompt Template theo tá»«ng cáo·p tiá»n

Há»‡ thá»'ng cáo§n há»- trá»£ sinh prompt phÃ¢n tÃ­ch chi tiáo¿t cho tá»«ng cáo·p trong danh sÃ¡ch 28 cáo·p Forex + XAU/USD. KhÃ ́ng hard-code 29 prompt riÃang. CÃ¡ch Ä'Ãong lÃ  dÃ1ng:

```text
Base Prompt Template
+ Currency Drivers
+ Symbol Profile
+ Market/Macro Snapshot
+ Technical Context do Python tÃ­nh
+ SMC Context do Python tÃ­nh
+ Output Schema
= Prompt cuá»'i gá»­i AI
```

#### Cáo¥u trÃoc file Ä'á» xuáo¥t

```text
config/
  currency_drivers.json
  symbol_profiles.json

prompts/
  full_analysis_prompt.md
  sections/
    macro_flow.md
    behavior_model.md
    technical_smc.md
    output_schema.md

core/
  prompt_builder.py
  technical_context.py
  smc_context.py
  entry_engine.py
  backtest_engine.py
```

#### Currency Drivers (yáo¿u tá»' theo tá»«ng Ä'á»"ng tiá»n)

`currency_drivers.json` Ä'á»‹nh nghÄ©a cÃ¡c yáo¿u tá»' vÄ© mÃ ́ cáo§n theo dÃμi cho tá»«ng Ä'á»"ng tiá»n:

```json
{
  "USD": ["DXY", "UST 2Y", "UST 10Y", "Fed expectations", "US CPI", "US PCE", "US NFP", "US PMI", "US Retail Sales", "US GDP", "US equities", "VIX", "risk-on/risk-off"],
  "EUR": ["ECB expectations", "Bund yield", "US-Germany yield spread", "Eurozone CPI", "Eurozone core CPI", "Eurozone PMI", "Eurozone GDP", "Eurozone sentiment", "ECB speakers", "European equities"],
  "GBP": ["BOE expectations", "UK CPI", "UK wage growth", "UK PMI", "UK GDP", "UK Retail Sales"],
  "JPY": ["BOJ expectations", "JGB yields", "US-Japan yield spread", "intervention risk", "risk sentiment"],
  "CHF": ["SNB expectations", "safe haven demand", "Swiss CPI", "risk sentiment"],
  "AUD": ["RBA expectations", "Australia CPI/jobs", "China data", "iron ore", "risk sentiment"],
  "NZD": ["RBNZ expectations", "New Zealand CPI/jobs", "Global Dairy Trade", "China data", "risk sentiment"],
  "CAD": ["BOC expectations", "Canada CPI/jobs/GDP", "WTI Oil", "risk sentiment"],
  "XAU": ["real yield", "DXY", "Fed expectations", "US yields", "inflation expectations", "geopolitics", "safe haven demand"]
}
```

#### Symbol Profile (há»" sÆ¡ tá»«ng cáo·p)

`symbol_profiles.json` khai bÃ¡o base/quote, nhÃ3m driver Ä'áo·c biá»‡t vÃ  cÃ¢u há»i behavior model cho tá»«ng cáo·p.

VÃ­ dá»¥ EUR/USD:

```json
{
  "EUR/USD": {
    "base": "EUR",
    "quote": "USD",
    "special_drivers": [
      "DXY",
      "UST 2Y / 10Y",
      "Bund yield",
      "US-Germany yield spread",
      "Fed expectations",
      "ECB expectations",
      "US data: CPI, PCE, NFP, PMI, Retail Sales, GDP",
      "Eurozone data: CPI, core CPI, PMI, GDP, sentiment, ECB speakers",
      "US/EU equities",
      "VIX",
      "risk-on/risk-off"
    ],
    "behavior_questions": [
      "EUR Ä'ang Ä'Æ°á»£c giao dá»‹ch theo ECB/rates, growth, hay USD weakness?",
      "USD Ä'ang Ä'Æ°á»£c giao dá»‹ch nhÆ° safe haven hay rate currency?",
      "EUR/USD hiá»‡n bá»‹ chi phá»'i bá»Ÿi Fed/ECB divergence, yield, DXY hay risk sentiment?"
    ]
  }
}
```

VÃ­ dá»¥ GBP/JPY:

```json
{
  "GBP/JPY": {
    "base": "GBP",
    "quote": "JPY",
    "special_drivers": [
      "BOE expectations",
      "UK CPI/wage growth/PMI",
      "BOJ expectations",
      "JGB yields",
      "US-Japan yield spread",
      "risk sentiment",
      "VIX"
    ],
    "behavior_questions": [
      "GBP Ä'ang Ä'Æ°á»£c giao dá»‹ch theo BOE/rates hay UK growth?",
      "JPY Ä'ang Ä'Æ°á»£c giao dá»‹ch nhÆ° safe haven hay funding currency?",
      "GBP/JPY hiá»‡n bá»‹ chi phá»'i bá»Ÿi yield spread hay risk sentiment?"
    ]
  }
}
```

#### Template ná»TMi dung prompt

Prompt phÃ¢n tÃ­ch Ä'áo§y Ä'á»§ nÃan gá»"m 3 pháo§n:

```text
PHáo¦N 1 â€" MACRO & FLOW
- Cáo­p nháo­t yáo¿u tá»' má»›i nháo¥t áo£nh hÆ°á»Ÿng {{symbol}}.
- Chá»‰ rÃμ yáo¿u tá»' Ä'ang chi phá»'i máo¡nh nháo¥t hiá»‡n táo¡i.
- Káo¿t luáo­n nghiÃang bullish hay bearish cho {{symbol}}.
- NÃau catalyst 24-72h tá»›i.

PHáo¦N 2 â€" BEHAVIOR MODEL
- {{base_currency}} Ä'ang Ä'Æ°á»£c giao dá»‹ch theo cÃ¢u chuyá»‡n nÃ o?
- {{quote_currency}} Ä'ang Ä'Æ°á»£c giao dá»‹ch theo cÃ¢u chuyá»‡n nÃ o?
- Káo¿t luáo­n {{symbol}} bá»‹ chi phá»'i bá»Ÿi yield/rates, central bank divergence, DXY, commodity, safe haven hay risk sentiment.

PHáo¦N 3 â€" MULTI-TIMEFRAME TECHNICAL + SMC
- PhÃ¢n tÃ­ch D1, H4, H1.
- NÃau xu hÆ°á»›ng chÃ­nh.
- NÃau HH/HL hoáo·c LH/LL.
- NÃau BOS / CHOCH náo¿u technical_context cÃ3.
- NÃau displacement, supply/demand zones, order block, breaker/mitigation, FVG/imbalance náo¿u smc_context cÃ3.
- NÃau liquidity pools: EQH/EQL/swing high/swing low náo¿u cÃ3.
- NÃau premium/discount vÃ  vá»‹ trÃ­ hiá»‡n táo¡i cá»§a giÃ¡ trong cáo¥u trÃoc lá»›n.
```

#### RÃ ng buá»TMc báo ̄t buá»TMc vá»›i AI

AI chá»‰ Ä'Æ°á»£c diá»...n giáo£i dá»±a trÃan dá» ̄ liá»‡u Ä'Æ°á»£c cung cáo¥p:

- KhÃ ́ng tá»± táo¡o giÃ¡ hiá»‡n táo¡i.
- KhÃ ́ng tá»± táo¡o indicator.
- KhÃ ́ng tá»± táo¡o entry, SL, TP, lot.
- KhÃ ́ng tá»± táo¡o supply/demand zone, order block, FVG, BOS, CHOCH náo¿u `technical_context` hoáo·c `smc_context` khÃ ́ng cÃ3.
- Náo¿u thiáo¿u dá» ̄ liá»‡u, pháo£i ghi rÃμ: `ChÆ°a Ä'á»§ dá» ̄ liá»‡u Ä'á»ƒ káo¿t luáo­n`.
- KhÃ ́ng Ä'Æ°á»£c biáo¿n nháo­n Ä'á»‹nh thÃ nh khuyáo¿n nghá»‹ cháo ̄c cháo ̄n tháo ̄ng.

#### Phong cÃ¡ch tráo£ lá»i báo ̄t buá»TMc

AI Writer pháo£i tráo£ lá»i theo phong cÃ¡ch:

- Ngáo ̄n gá»n nhÆ°ng sÃ¢u.
- Äáo­m cháo¥t bank trader / macro trader / SMC trader.
- KhÃ ́ng dÃ i dÃ2ng lÃ1⁄2 thuyáo¿t.
- Æ ̄u tiÃan má»©c giÃ¡, vÃ1ng vÃ o lá»‡nh, stop loss, take profit vÃ  invalidation.
- LuÃ ́n nÃ3i rÃμ setup chÃ­nh, setup phá»¥ hoáo·c lÃ1⁄2 do Ä'á»©ng ngoÃ i.
- Náo¿u khÃ ́ng cÃ3 setup sáo¡ch, pháo£i nÃ3i tháo3ng: `No clean setup / Ä'á»©ng ngoÃ i tá»'t hÆ¡n`.

KhÃ ́ng viáo¿t kiá»ƒu giÃ¡o trÃ¬nh, khÃ ́ng giáo£i thÃ­ch Ä'á»‹nh nghÄ©a dÃ i vá» indicator/SMC/macro. NgÆ°á»i dÃ1ng cáo§n káo¿t luáo­n giao dá»‹ch, vÃ1ng giÃ¡ vÃ  Ä'iá»u kiá»‡n vÃ ́ hiá»‡u.

Output nÃan cÃ3 cáo¥u trÃoc ngáo ̄n:

```text
Bias:
- ...

Macro/flow:
- ...

Technical/SMC:
- ...

Plan:
- Entry:
- SL:
- TP:
- Invalidation:

Conclusion:
- No clean setup / Ä'á»©ng ngoÃ i tá»'t hÆ¡n
```

Náo¿u `trade_permission = blocked`, `risk_condition` xáo¥u, hoáo·c giÃ¡ náo±m giá» ̄a vÃ1ng khÃ ́ng cÃ3 lá»£i tháo¿, pháo§n Conclusion pháo£i Æ°u tiÃan Ä'á»©ng ngoÃ i thay vÃ¬ cá»' táo¡o lá»‡nh.

#### Technical/SMC Context do Python táo¡o

TrÆ°á»›c khi gá»i AI, core Python pháo£i táo¡o context dáo¡ng JSON:

```json
{
  "symbol": "EUR/USD",
  "timeframes": {
    "D1": {
      "trend": "downtrend",
      "structure": "LH/LL",
      "bos": true,
      "choch": false,
      "displacement": "bearish",
      "premium_discount": "discount",
      "supply_zones": ["1.0920-1.0960"],
      "demand_zones": ["1.0710-1.0750"],
      "order_blocks": ["1.0880-1.0910"],
      "fvg": ["1.0830-1.0850"],
      "liquidity_pools": {
        "equal_highs": ["1.0880"],
        "equal_lows": [],
        "swing_highs": ["1.0960"],
        "swing_lows": ["1.0710"]
      },
      "liquidity_sweeps": {
        "swept_highs": [],
        "swept_lows": []
      },
      "premium_discount_range": {
        "status": "ok",
        "high": 1.0960,
        "low": 1.0710,
        "midpoint": 1.0835
      }
    }
  }
}
```

Náo¿u Python chÆ°a tÃ­nh Ä'Æ°á»£c má»TMt thÃ nh pháo§n SMC, trÆ°á»ng Ä'Ã3 pháo£i Ä'á»ƒ máo£ng rá»-ng hoáo·c `null`; AI khÃ ́ng Ä'Æ°á»£c tá»± bÃ1.

CÃ¡c vÃ1ng SMC nhÆ° supply/demand, order block vÃ  FVG pháo£i cÃ3 metadata cháo¥t lÆ°á»£ng do code tÃ­nh:

- `zone_score`: Ä'iá»ƒm 0-100.
- `strength`: `strong`, `moderate` hoáo·c `weak`.
- `freshness_bars`: sá»' náo¿n Ä'Ã£ trÃ ́i qua tá»« khi vÃ1ng hÃ¬nh thÃ nh.
- `mitigated`: vÃ1ng Ä'Ã£ bá»‹ cháo¡m/giáo£m hiá»‡u lá»±c hay chÆ°a.
- `broken`: vÃ1ng Ä'Ã£ bá»‹ phÃ¡ báo±ng giÃ¡ Ä'Ã3ng cá»­a hay chÆ°a.
- `test_count`: sá»' láo§n giÃ¡ quay láo¡i kiá»ƒm tra vÃ1ng.
- `displacement_multiple`: Ä'á»TM máo¡nh impulse so vá»›i biÃan Ä'á»TM trung bÃ¬nh.
- `liquidity_sweep`: cÃ3 quÃ©t thanh khoáo£n liÃan quan hay khÃ ́ng.
- `zone_location`: `premium`, `discount`, `equilibrium` hoáo·c `unknown`.

Rule Engine pháo£i Æ°u tiÃan vÃ1ng chÆ°a broken, cÃ2n fresh, displacement tá»'t, Ã­t bá»‹ test láo¡i, cÃ3 sweep thanh khoáo£n vÃ  náo±m Ä'Ãong premium/discount theo hÆ°á»›ng lá»‡nh.

#### Prompt builder

VÃ­ dá»¥ hÃ m build prompt:

```python
def build_analysis_prompt(symbol, symbol_profile, currency_drivers, macro_snapshot, technical_context, smc_context):
    return render_template(
        "prompts/full_analysis_prompt.md",
        {
            "symbol": symbol,
            "base_currency": symbol_profile["base"],
            "quote_currency": symbol_profile["quote"],
            "base_drivers": currency_drivers[symbol_profile["base"]],
            "quote_drivers": currency_drivers[symbol_profile["quote"]],
            "special_drivers": symbol_profile.get("special_drivers", []),
            "behavior_questions": symbol_profile.get("behavior_questions", []),
            "macro_snapshot": macro_snapshot,
            "technical_context": technical_context,
            "smc_context": smc_context,
        },
    )
```

Má»¥c tiÃau: AI á»Ÿ bÆ°á»›c code tiáo¿p theo cÃ3 thá»ƒ tá»± sinh prompt phÃ1 há»£p cho má»i cáo·p báo±ng mÃ ́ táo£, thay vÃ¬ viáo¿t tay tá»«ng prompt riÃang.
### 8.6 CÃ¡ch tÃ­nh tá»•ng Ä'iá»ƒm (v12.1)

def calc_scenario_score(trend, momentum, location, smc_quality, risk, macro_raw, macro_confidence):
    trend_scaled = int(clamp(trend, 0, 25) * 18 / 25)
    momentum_scaled = int(clamp(momentum, 0, 20) * 15 / 20)
    location_scaled = int(clamp(location, 0, 25) * 17 / 25)
    smc_scaled = clamp(smc_quality, 0, 15)

    macro_effective = int(clamp(macro_raw, 0, 30) * clamp(macro_confidence, 0.0, 1.0))
    total = clamp(trend_scaled + momentum_scaled + location_scaled + smc_scaled + clamp(risk, 0, 15) + macro_effective, 0, 100)
    return {
        "trend_scaled": trend_scaled,
        "momentum_scaled": momentum_scaled,
        "location_scaled": location_scaled,
        "smc_quality": smc_scaled,
        "macro_effective": macro_effective,
        "macro_confidence": macro_confidence,
        "total": total,
    }
```

### 8.7 Ã nghÄ©a Ä'iá»ƒm sá»'

| Äiá»ƒm | Ã nghÄ©a |
|---:|---|
| 80â€"100 | Ká»‹ch báo£n cháo¥t lÆ°á»£ng cao, nhiá»u yáo¿u tá»' Ä'á»"ng thuáo­n |
| 65â€"79 | CÃ3 thá»ƒ cÃ¢n nháo ̄c, nhÆ°ng váo«n cáo§n Ä'iá»u kiá»‡n xÃ¡c nháo­n |
| 50â€"64 | ChÆ°a rÃμ rÃ ng, nÃan chá» thÃam tÃ­n hiá»‡u |
| DÆ°á»›i 50 | KhÃ ́ng nÃan giao dá»‹ch theo ká»‹ch báo£n nÃ y |

---

## 9. BÆ°á»›c 4 â€" Trade Plan (káo¿ hoáo¡ch giao dá»‹ch)

### 9.1 NguyÃan táo ̄c táo¡o Trade Plan

Rule Engine táo¡o cÃ¡c con sá»' ká»1 thuáo­t. AI chá»‰ diá»...n giáo£i.

CÃ¡c sá»' sau pháo£i do code táo¡o ra:

- Entry zone (vÃ1ng vÃ o lá»‡nh).
- Stop loss (cáo ̄t lá»-).
- Take profit (chá»'t lá»i).
- Risk/reward (tá»· lá»‡ rá»§i ro/lá»£i nhuáo­n).
- Stop distance (khoáo£ng cÃ¡ch tá»« entry Ä'áo¿n SL).
- Suggested lot (khá»'i lÆ°á»£ng Ä'á» xuáo¥t).

AI khÃ ́ng Ä'Æ°á»£c tá»± táo¡o cÃ¡c sá»' nÃ y.

Trade Plan pháo£i tÃ¡ch rÃμ hai lá»›p:

- `watch_zone`: wider monitoring area built from support/resistance, supply/demand, order block/FVG and ATR.
- `entry_zone`: narrow confirmation area around the selected level; only this zone is used by `core/entry_engine.py` for `price_in_entry_zone` and `ready_to_trade`.
- `entry_status`: tráo¡ng thÃ¡i xÃ¡c nháo­n do `core/entry_engine.py` tÃ­nh, khÃ ́ng do AI hoáo·c UI tá»± Ä'áo·t.

Chá»‰ khi `entry_status = confirmed_entry` vÃ  `ready_to_trade = true` thÃ¬ há»‡ thá»'ng má»›i coi lÃ  lá»‡nh sáoμn sÃ ng. Náo¿u chÆ°a cÃ3 xÃ¡c nháo­n, há»‡ thá»'ng váo«n Ä'Æ°á»£c hiá»ƒn thá»‹ vÃ1ng theo dÃμi nhÆ°ng pháo£i ghi rÃμ `watch_zone` hoáo·c `waiting_confirmation`, khÃ ́ng Ä'Æ°á»£c trÃ¬nh bÃ y nhÆ° má»TMt lá»‡nh ready.

`entry_engine.py` nháo­n `technical`, `smc`, náo¿n H1 vÃ  `entry_zone`, sau Ä'Ã3 tráo£ vá»:

```json
{
  "watch_zone": [0, 0],
  "entry_zone": [0, 0],
  "entry_status": "confirmed_entry | waiting_confirmation | watch_zone | invalidated | no_setup",
  "trigger_type": "h1_bullish_rejection | h1_bearish_rejection | h1_bullish_engulfing | h1_bearish_engulfing | h1_bullish_break | h1_bearish_break | h1_bos_bullish | h1_choch_bearish | liquidity_sweep_low | liquidity_sweep_high | none",
  "confirmation_score": 0,
  "invalid_reason": "",
  "price_in_entry_zone": false,
  "h1_confirmation": false,
  "ready_to_trade": false
}
```

### 9.2 CÃ¡ch táo¡o entry/SL/TP cho BUY

Vá»›i ká»‹ch báo£n buy:

- Entry zone (vÃ1ng vÃ o lá»‡nh) Æ°u tiÃan gáo§n support zone (vÃ1ng há»- trá»£), pivot (Ä'iá»ƒm xoay), swing low (Ä'Ã¡y dao Ä'á»TMng) hoáo·c ATR zone (vÃ1ng dá»±a trÃan biÃan Ä'á»TM dao Ä'á»TMng trung bÃ¬nh).
- Stop loss (cáo ̄t lá»-) Ä'áo·t dÆ°á»›i support/swing low má»TMt khoáo£ng buffer (vÃ1ng Ä'á»‡m).
- Take profit (chá»'t lá»i) Ä'áo·t táo¡i resistance zone (vÃ1ng khÃ¡ng cá»±) gáo§n nháo¥t hoáo·c vÃ1ng khÃ¡ng cá»± káo¿ tiáo¿p.
- KhÃ ́ng buy náo¿u giÃ¡ Ä'ang sÃ¡t khÃ¡ng cá»± mÃ  khÃ ́ng cÃ3 breakout (phÃ¡ vá»¡) rÃμ rÃ ng.

CÃ ́ng thá»©c tham chiáo¿u cho BUY:

```python
# atr_entry nÃan dÃ1ng ATR cá»§a timeframe vÃ o lá»‡nh, vÃ­ dá»¥ H1 hoáo·c H4.
# MVP máo·c Ä'á»‹nh dÃ1ng ATR_H4 náo¿u phÃ¢n tÃ­ch D1/H4/H1.
atr_entry = atr_h4

# Chá»n support há»£p lá»‡:
# 1. Æ ̄u tiÃan strength cao hÆ¡n: strong > moderate > weak
# 2. Náo¿u cÃ1ng strength, chá»n vÃ1ng gáo§n current_price nháo¥t
# 3. Chá»‰ chá»n support náo±m dÆ°á»›i hoáo·c gáo§n current_price, khÃ ́ng chá»n vÃ1ng quÃ¡ xa
support_level = select_best_support(
    support_zones=support_zones,
    current_price=current_price,
    max_distance=atr_entry * 1.5
)

watch_low  = support_level - atr_entry * 0.10
watch_high = support_level + atr_entry * 0.50

entry_low  = support_level - atr_entry * 0.20
entry_high = support_level + atr_entry * 0.20

stop_loss = support_level - max(atr_entry * 0.30, min_stop_distance)

take_profit_1 = nearest_resistance_above(entry_high, resistance_zones)
take_profit_2 = next_resistance_above(take_profit_1, resistance_zones)

# KhÃ ́ng táo¡o buy plan náo¿u entry_high quÃ¡ sÃ¡t khÃ¡ng cá»±.
if take_profit_1 is None or (take_profit_1 - entry_high) < (entry_high - stop_loss):
    reject_buy_plan("Risk/reward khÃ ́ng Ä'á»§ tá»'t")
```

VÃ­ dá»¥: support = 2330, ATR_H4 = 15.

```text
watch_low  = 2330 - 15 * 0.10 = 2328.5
watch_high = 2330 + 15 * 0.50 = 2337.5
entry_low  = 2330 - 15 * 0.20 = 2327.0
entry_high = 2330 + 15 * 0.20 = 2333.0
```

### 9.3 CÃ¡ch táo¡o entry/SL/TP cho SELL

Vá»›i ká»‹ch báo£n sell:

- Entry zone Æ°u tiÃan gáo§n resistance zone, pivot, swing high (Ä'á»‰nh dao Ä'á»TMng) hoáo·c ATR zone.
- Stop loss Ä'áo·t trÃan resistance/swing high má»TMt khoáo£ng buffer.
- Take profit Ä'áo·t táo¡i support zone gáo§n nháo¥t hoáo·c vÃ1ng há»- trá»£ káo¿ tiáo¿p.
- KhÃ ́ng sell náo¿u giÃ¡ Ä'ang sÃ¡t há»- trá»£ mÃ  khÃ ́ng cÃ3 breakdown (phÃ¡ xuá»'ng) rÃμ rÃ ng.

CÃ ́ng thá»©c tham chiáo¿u cho SELL:

```python
atr_entry = atr_h4

# Chá»n resistance há»£p lá»‡:
# 1. Æ ̄u tiÃan strength cao hÆ¡n: strong > moderate > weak
# 2. Náo¿u cÃ1ng strength, chá»n vÃ1ng gáo§n current_price nháo¥t
# 3. Chá»‰ chá»n resistance náo±m trÃan hoáo·c gáo§n current_price, khÃ ́ng chá»n vÃ1ng quÃ¡ xa
resistance_level = select_best_resistance(
    resistance_zones=resistance_zones,
    current_price=current_price,
    max_distance=atr_entry * 1.5
)

watch_low  = resistance_level - atr_entry * 0.50
watch_high = resistance_level + atr_entry * 0.10

entry_low  = resistance_level - atr_entry * 0.20
entry_high = resistance_level + atr_entry * 0.20

stop_loss = resistance_level + max(atr_entry * 0.30, min_stop_distance)

take_profit_1 = nearest_support_below(entry_low, support_zones)
take_profit_2 = next_support_below(take_profit_1, support_zones)

# KhÃ ́ng táo¡o sell plan náo¿u entry_low quÃ¡ sÃ¡t há»- trá»£.
if take_profit_1 is None or (entry_low - take_profit_1) < (stop_loss - entry_low):
    reject_sell_plan("Risk/reward khÃ ́ng Ä'á»§ tá»'t")
```

VÃ­ dá»¥: resistance = 2365, ATR_H4 = 15.

```text
watch_low  = 2365 - 15 * 0.50 = 2357.5
watch_high = 2365 + 15 * 0.10 = 2366.5
entry_low  = 2365 - 15 * 0.20 = 2362.0
entry_high = 2365 + 15 * 0.20 = 2368.0
```

### 9.4 Äiá»u kiá»‡n xÃ¡c nháo­n

Má»-i ká»‹ch báo£n pháo£i cÃ3 condition (Ä'iá»u kiá»‡n kÃ­ch hoáo¡t), vÃ­ dá»¥:

- CÃ3 náo¿n H1 Ä'Ã3ng xÃ¡c nháo­n tÄƒng táo¡i há»- trá»£.
- GiÃ¡ giá» ̄ trÃan vÃ1ng há»- trá»£ sau khi retest (kiá»ƒm tra láo¡i vÃ1ng giÃ¡).
- MACD histogram yáo¿u dáo§n theo hÆ°á»›ng phÃ1 há»£p.
- KhÃ ́ng vÃ o lá»‡nh trong 15 phÃot trÆ°á»›c/sau tin Ä'á».

Äiá»u kiá»‡n xÃ¡c nháo­n pháo£i Ä'Æ°á»£c tÃ­nh báo±ng code. Vá»›i BUY, xÃ¡c nháo­n há»£p lá»‡ gá»"m má»TMt hoáo·c nhiá»u tÃ­n hiá»‡u: giÃ¡ náo±m trong entry zone, náo¿n H1 rejection/engulfing/break tÄƒng, H1 BOS/CHOCH bullish, quÃ©t thanh khoáo£n Ä'Ã¡y rá»"i Ä'Ã3ng láo¡i trÃan vÃ1ng, vÃ1ng á»Ÿ discount hoáo·c equilibrium phÃ1 há»£p. Vá»›i SELL, Ä'iá»u kiá»‡n Ä'á»'i xá»©ng: giÃ¡ náo±m trong entry zone, náo¿n H1 rejection/engulfing/break giáo£m, H1 BOS/CHOCH bearish, quÃ©t thanh khoáo£n Ä'á»‰nh rá»"i Ä'Ã3ng láo¡i dÆ°á»›i vÃ1ng, vÃ1ng á»Ÿ premium hoáo·c equilibrium phÃ1 há»£p.

Náo¿u giÃ¡ chÆ°a vÃ o vÃ1ng hoáo·c chÆ°a cÃ3 xÃ¡c nháo­n H1, scenario chá»‰ lÃ  vÃ1ng theo dÃμi. KhÃ ́ng tÃ­nh `position_sizing` nhÆ° lá»‡nh ready cho scenario chÆ°a xÃ¡c nháo­n.

### 9.5 Entry checklist

Má»-i káo¿t quáo£ phÃ¢n tÃ­ch pháo£i tráo£ vá» `entry_checklist` Ä'á»ƒ ngÆ°á»i dÃ1ng biáo¿t vÃ¬ sao Ä'Æ°á»£c vÃ o lá»‡nh hoáo·c vÃ¬ sao pháo£i chá»:

```json
[
  {"label": "Xu hÆ°á»›ng", "status": "pass", "value": "trend_up", "note": "Cáo§n Æ°u tiÃan khi D1/H4 cÃ3 hÆ°á»›ng rÃμ."},
  {"label": "VÃ1ng POI", "status": "pass", "value": [1.095, 1.1], "note": "Cáo§n cÃ3 vÃ1ng entry/POI há»£p lá»‡ vÃ  chÆ°a bá»‹ vÃ ́ hiá»‡u."},
  {"label": "XÃ¡c nháo­n H1", "status": "wait", "value": "none", "note": "Cáo§n náo¿n H1 xÃ¡c nháo­n táo¡i vÃ1ng."},
  {"label": "Tin tá»©c", "status": "pass", "value": "KhÃ ́ng cÃ3 tin tÃ¡c Ä'á»TMng cao gáo§n", "note": "TrÃ¡nh vÃ o lá»‡nh gáo§n tin tÃ¡c Ä'á»TMng cao."},
  {"label": "Spread", "status": "pass", "value": "normal", "note": "Spread pháo£i bÃ¬nh thÆ°á»ng."},
  {"label": "R:R", "status": "pass", "value": "1:2.1", "note": "R:R tá»'i thiá»ƒu nÃan tá»« 1:1.5 trá»Ÿ lÃan."},
  {"label": "Lot", "status": "wait", "value": "--", "note": "Lot chá»‰ tÃ­nh khi entry Ä'Ã£ xÃ¡c nháo­n."}
]
```

Checklist nÃ y do Rule Engine táo¡o. AI chá»‰ Ä'Æ°á»£c diá»...n giáo£i láo¡i, khÃ ́ng tá»± sá»­a tráo¡ng thÃ¡i.

### 9.6 Backtest/replay setup

Má»-i trade plan há»£p lá»‡ pháo£i cÃ3 pháo§n `backtest` dáo¡ng replay trÃan náo¿n H1 Ä'á»ƒ kiá»ƒm chá»©ng vÃ1ng entry hiá»‡n táo¡i tá»«ng hoáo¡t Ä'á»TMng ra sao trong lá»‹ch sá»­ gáo§n nháo¥t. Replay khÃ ́ng Ä'Æ°á»£c dÃ1ng dá» ̄ liá»‡u tÆ°Æ¡ng lai trong quyáo¿t Ä'á»‹nh realtime; nÃ3 chá»‰ lÃ  lá»›p Ä'o lÆ°á»ng cháo¥t lÆ°á»£ng setup.

CÃ¡c chá»‰ sá»' báo ̄t buá»TMc:

- `win_rate`: tá»· lá»‡ lá»‡nh tháo ̄ng.
- `expectancy_r`: ká»3 vá»ng trung bÃ¬nh theo Ä'Æ¡n vá»‹ R.
- `average_r`: R trung bÃ¬nh.
- `average_mfe_r`: MFE trung bÃ¬nh theo R.
- `average_mae_r`: MAE trung bÃ¬nh theo R.
- `max_drawdown_r`: drawdown lá»›n nháo¥t theo R.
- `by_symbol`: hiá»‡u quáo£ theo tá»«ng mÃ£.
- `by_session`: hiá»‡u quáo£ theo phiÃan Asia, London, New York, Late US.

Output máo«u:

```json
{
  "backtest": {
    "mode": "plan_replay",
    "symbol": "EUR/USD",
    "timeframe": "H1",
    "summary": {
      "trade_count": 12,
      "win_rate": 58.33,
      "expectancy_r": 0.42,
      "average_r": 0.42,
      "average_mfe_r": 1.35,
      "average_mae_r": -0.62,
      "max_drawdown_r": 2.1
    },
    "by_symbol": {
      "EUR/USD": {"trade_count": 12, "win_rate": 58.33}
    },
    "by_session": {
      "London": {"trade_count": 5, "win_rate": 60.0, "expectancy_r": 0.48},
      "New York": {"trade_count": 4, "win_rate": 50.0, "expectancy_r": 0.22}
    }
  }
}
```

Náo¿u chÆ°a cÃ3 trade plan há»£p lá»‡ hoáo·c khÃ ́ng Ä'á»§ náo¿n, `backtest.summary.trade_count = 0` vÃ  pháo£i cÃ3 `reason`.

### 9.7 Äiá»u kiá»‡n vÃ ́ hiá»‡u

Má»-i ká»‹ch báo£n pháo£i cÃ3 invalidation (Ä'iá»u kiá»‡n vÃ ́ hiá»‡u), vÃ­ dá»¥:

- H1 Ä'Ã3ng dÆ°á»›i vÃ1ng há»- trá»£ chÃ­nh vá»›i ká»‹ch báo£n buy.
- H1 Ä'Ã3ng trÃan vÃ1ng khÃ¡ng cá»± chÃ­nh vá»›i ká»‹ch báo£n sell.
- Spread giÃ£n báo¥t thÆ°á»ng.
- Tin tá»©c lÃ m biáo¿n Ä'á»TMng máo¡nh ngÆ°á»£c ká»‹ch báo£n.

### 9.8 Logic táo¡o hoáo·c khÃ ́ng táo¡o ká»‹ch báo£n

| Äiá»u kiá»‡n | HÃ nh Ä'á»TMng |
|---|---|
| Buy score < 50 | KhÃ ́ng táo¡o trade plan buy, hoáo·c chá»‰ ghi lÃ1⁄2 do Ä'á»©ng ngoÃ i buy |
| Sell score < 50 | KhÃ ́ng táo¡o trade plan sell, hoáo·c chá»‰ ghi lÃ1⁄2 do Ä'á»©ng ngoÃ i sell |
| Cáo£ buy vÃ  sell Ä'á»u < 50 | `direction_bias = stand_aside` |
| CÃ3 tin Ä'á» trong 3 giá» tá»›i | `trade_permission = caution` hoáo·c `blocked` tÃ1y má»©c Ä'á»TM gáo§n |
| CÃ3 tin Ä'á» trong 30 phÃot tá»›i | `trade_permission = blocked` |
| Dá» ̄ liá»‡u lá»-i hoáo·c thiáo¿u nhiá»u náo¿n | KhÃ ́ng táo¡o trade plan |

### 9.9 Scanner Mode â€" logic quÃ©t nhiá»u mÃ£

Scanner Mode dÃ1ng láo¡i cÃ¡c engine chÃ­nh, nhÆ°ng output á»Ÿ má»©c tÃ3m táo ̄t thay vÃ¬ táo¡o bÃ¡o cÃ¡o dÃ i cho táo¥t cáo£ mÃ£.

#### Input cá»§a Scanner Mode

```json
{
  "mode": "scanner",
  "symbols": [
    "EUR/USD", "GBP/USD", "AUD/USD", "NZD/USD", "USD/JPY", "USD/CHF", "USD/CAD",
    "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/AUD", "EUR/NZD", "EUR/CAD",
    "GBP/JPY", "GBP/CHF", "GBP/AUD", "GBP/NZD", "GBP/CAD",
    "CHF/JPY", "AUD/JPY", "NZD/JPY", "CAD/JPY",
    "AUD/CHF", "NZD/CHF", "CAD/CHF", "AUD/NZD", "AUD/CAD", "NZD/CAD",
    "XAU/USD"
  ],
  "timeframes": ["D1", "H4", "H1"],
  "account_balance": 10000,
  "risk_pct": 1,
  "timezone": "Asia/Ho_Chi_Minh",
  "max_ai_details": 3
}
```

#### CÃ¡c bÆ°á»›c cháo¡y scanner

```python
def scan_market(symbols):
    rows = []

    for symbol in symbols:
        data = load_price_data(symbol)
        indicators = calc_indicators(data)
        zones = calc_zones(data)
        regime = detect_market_regime(data, indicators, zones)
        bias = detect_direction_bias(regime, indicators, zones)
        risk = calc_risk_condition(...)

        buy_score = score_buy_scenario(...)
        sell_score = score_sell_scenario(...)

        best_side = "buy" if buy_score >= sell_score else "sell"
        best_score = max(buy_score, sell_score)
        permission = calc_trade_permission(...)

        scanner_action = classify_scanner_action(
            best_score=best_score,
            permission=permission,
            price_in_entry_zone=check_price_in_entry_zone(...),
            confirmation=check_h1_confirmation(...)
        )

        rows.append({
            "symbol": symbol,
            "bias": bias,
            "permission": permission,
            "buy_score": buy_score,
            "sell_score": sell_score,
            "best_side": best_side,
            "best_score": best_score,
            "scanner_action": scanner_action
        })

    rows = sort_by_priority(rows)
    return rows
```

#### PhÃ¢n loáo¡i scanner_action

| Action | NghÄ©a tiáo¿ng Viá»‡t | Äiá»u kiá»‡n gá»£i Ã1⁄2 |
|---|---|---|
| `ready` | CÃ3 thá»ƒ xem xÃ©t vÃ o lá»‡nh | `best_score >= 80`, `trade_permission = allowed`, giÃ¡ náo±m trong entry zone, cÃ3 xÃ¡c nháo­n H1 |
| `watch` | ÄÃ¡ng theo dÃμi | `best_score >= 75`, permission khÃ ́ng bá»‹ blocked, nhÆ°ng cÃ2n thiáo¿u entry hoáo·c xÃ¡c nháo­n |
| `wait` | Chá» thÃam | `best_score` tá»« 60â€"74 hoáo·c setup chÆ°a rÃμ |
| `skip` | Bá» qua | `best_score < 60`, dá» ̄ liá»‡u lá»-i, permission bá»‹ blocked, hoáo·c R:R kÃ©m |

#### Quy táo ̄c xáo¿p háo¡ng scanner

Æ ̄u tiÃan sáo ̄p xáo¿p theo thá»© tá»±:

1. `scanner_action`: ready > watch > wait > skip.
2. `trade_permission`: allowed > caution > blocked.
3. `best_score`: cao Ä'áo¿n tháo¥p.
4. `risk_reward`: cao Ä'áo¿n tháo¥p náo¿u Ä'Ã£ táo¡o Ä'Æ°á»£c trade plan sÆ¡ bá»TM.

#### Khi nÃ o gá»i AI trong Scanner Mode

Scanner Mode khÃ ́ng gá»i AI cho táo¥t cáo£ mÃ£. Quy táo ̄c MVP:

```python
qualified = [
    row for row in scanner_rows
    if row["best_score"] >= 75 and row["permission"] != "blocked"
]

ai_targets = qualified[:max_ai_details]  # máo·c Ä'á»‹nh tá»'i Ä'a 3 mÃ£
```

AI chá»‰ viáo¿t nháo­n Ä'á»‹nh ngáo ̄n cho `ai_targets`. CÃ¡c mÃ£ cÃ2n láo¡i chá»‰ hiá»ƒn thá»‹ dá» ̄ liá»‡u rule-based.

#### Khi ngÆ°á»i dÃ1ng báo¥m View Detail

Náo¿u ngÆ°á»i dÃ1ng báo¥m `View Detail` á»Ÿ má»TMt dÃ2ng scanner:

- Há»‡ thá»'ng cháo¡y Single Analysis Mode cho mÃ£ Ä'Ã3.
- Táo¡o output JSON Ä'áo§y Ä'á»§.
- Táo¡o trade plan chi tiáo¿t náo¿u Ä'á»§ Ä'iá»u kiá»‡n.
- Gá»i AI Writer Ä'á»ƒ viáo¿t nháo­n Ä'á»‹nh Ä'áo§y Ä'á»§.

---

## 10. Position Sizing (tÃ­nh khá»'i lÆ°á»£ng vÃ o lá»‡nh)

### 10.1 NguyÃan táo ̄c

Position sizing pháo£i dá»±a trÃan sá»' tiá»n cháo¥p nháo­n rá»§i ro, khoáo£ng cÃ¡ch tá»« entry Ä'áo¿n stop loss, contract size (quy mÃ ́ há»£p Ä'á»"ng), pip size (kÃ­ch thÆ°á»›c pip) vÃ  account currency (Ä'á»"ng tiá»n tÃ i khoáo£n).

KhÃ ́ng nÃan chá»‰ dÃ1ng cÃ ́ng thá»©c pip value Ä'Æ¡n giáo£n cho má»i sáo£n pháo©m, vÃ¬ USD/JPY, USD/CAD, USD/CHF vÃ  XAU/USD cÃ3 cÃ¡ch quy Ä'á»•i khÃ¡c nhau.

### 10.2 CÃ ́ng thá»©c tá»•ng quÃ¡t

```python
risk_amount = account_balance * risk_pct / 100
price_distance = abs(entry_price - stop_loss)
loss_per_lot = price_distance * contract_size
suggested_lot = risk_amount / loss_per_lot
```

Vá»›i sáo£n pháo©m cáo§n quy Ä'á»•i tiá»n tá»‡, `loss_per_lot` pháo£i Ä'Æ°á»£c quy Ä'á»•i vá» account currency.

### 10.3 VÃ­ dá»¥ vá»›i XAU/USD

Giáo£ sá»­:

- Account balance (sá»' dÆ° tÃ i khoáo£n): 10,000 USD.
- Risk percent (pháo§n trÄƒm rá»§i ro): 1%.
- Risk amount (sá»' tiá»n rá»§i ro): 100 USD.
- Entry: 2340.
- Stop loss: 2324.
- Distance (khoáo£ng cÃ¡ch giÃ¡): 16 USD.
- Contract size: 100 oz cho 1 standard lot.

CÃ¡ch tÃ­nh:

```text
loss_per_1_lot = 16 * 100 = 1,600 USD
suggested_lot = 100 / 1,600 = 0.0625 lot
lÃ m trÃ2n = 0.06 lot
```

### 10.4 Cáo¥u hÃ¬nh pip/contract cho tá»«ng mÃ£

```python
SYMBOL_CONFIG = {
    "EUR/USD": {
        "pip_size": 0.0001,
        "contract_size": 100000,
        "quote_currency": "USD",
        "account_currency": "USD"
    },
    "GBP/USD": {
        "pip_size": 0.0001,
        "contract_size": 100000,
        "quote_currency": "USD",
        "account_currency": "USD"
    },
    "AUD/USD": {
        "pip_size": 0.0001,
        "contract_size": 100000,
        "quote_currency": "USD",
        "account_currency": "USD"
    },
    "NZD/USD": {
        "pip_size": 0.0001,
        "contract_size": 100000,
        "quote_currency": "USD",
        "account_currency": "USD"
    },
    "USD/JPY": {
        "pip_size": 0.01,
        "contract_size": 100000,
        "quote_currency": "JPY",
        "account_currency": "USD",
        "pip_value_requires_conversion": True
    },
    "USD/CAD": {
        "pip_size": 0.0001,
        "contract_size": 100000,
        "quote_currency": "CAD",
        "account_currency": "USD",
        "pip_value_requires_conversion": True
    },
    "USD/CHF": {
        "pip_size": 0.0001,
        "contract_size": 100000,
        "quote_currency": "CHF",
        "account_currency": "USD",
        "pip_value_requires_conversion": True
    },
    "XAU/USD": {
        "contract_size": 100,
        "price_unit": "USD per oz",
        "quote_currency": "USD",
        "account_currency": "USD",
        "position_sizing_method": "price_distance_x_contract_size",
        "note": "KhÃ ́ng dÃ1ng pip_size Ä'á»ƒ tÃ­nh position sizing cho XAU/USD. DÃ1ng price_distance * contract_size; váo«n pháo£i kiá»ƒm tra contract_size vá»›i broker cá»¥ thá»ƒ."
    }
}
```

### 10.5 LÆ°u Ã1⁄2 riÃang XAU/USD

XAU/USD phá»¥ thuá»TMc quy Æ°á»›c tá»«ng broker. Äá»ƒ trÃ¡nh nháo§m láo«n, pháo§n position sizing (tÃ­nh khá»'i lÆ°á»£ng vÃ o lá»‡nh) cho XAU/USD **khÃ ́ng dÃ1ng pip_size** mÃ  dÃ1ng trá»±c tiáo¿p cÃ ́ng thá»©c:

```python
price_distance = abs(entry_price - stop_loss)
loss_per_1_lot = price_distance * contract_size
suggested_lot = risk_amount / loss_per_1_lot
```

Trong Ä'Ã3 contract_size (quy mÃ ́ há»£p Ä'á»"ng) thÆ°á»ng lÃ  100 oz cho 1 standard lot, nhÆ°ng váo«n pháo£i kiá»ƒm tra láo¡i vá»›i broker cá»¥ thá»ƒ. Náo¿u muá»'n hiá»ƒn thá»‹ sá»' pip cho ngÆ°á»i dÃ1ng, cÃ3 thá»ƒ cáo¥u hÃ¬nh pip_size riÃang chá»‰ Ä'á»ƒ hiá»ƒn thá»‹, khÃ ́ng dÃ1ng pip_size Ä'á»ƒ tÃ­nh lot vÃ ng.

Do Ä'Ã3, há»‡ thá»'ng pháo£i cho phÃ©p override (ghi Ä'Ã ̈ cáo¥u hÃ¬nh) theo broker.

---

## 11. Output JSON cáo¥u trÃoc

### 11.1 Máo«u JSON Ä'áo§y Ä'á»§

```json
{
  "symbol": "XAU/USD",
  "timestamp": "2026-05-29T10:00:00+07:00",
  "data_quality": {
    "price_source": "MT5",
    "terminal_connected": true,
    "broker_logged_in": true,
    "display_symbol": "XAU/USD",
    "broker_symbol": "XAUUSDm",
    "last_candle_time_utc": "2026-05-29T02:00:00Z",
    "last_candle_time_vn": "2026-05-29T09:00:00+07:00",
    "is_delayed": false,
    "missing_candles": 0,
    "spread_points": 22,
    "spread_status": "normal",
    "contract_size": 100,
    "warning": null
  },
  "market_regime": {
    "primary": "trend_up",
    "secondary": ["news_sensitive"],
    "structure": "HH/HL trÃan H4",
    "explanation": "D1 tÄƒng, giÃ¡ trÃan EMA50 vÃ  EMA200, H4 váo«n giá» ̄ cáo¥u trÃoc Ä'Ã¡y cao hÆ¡n."
  },
  "direction_bias": "buy",
  "trade_permission": {
    "status": "caution",
    "reason": "CÃ3 CPI trong 3 giá» tá»›i, khÃ ́ng nÃan vÃ o lá»‡nh vá»TMi.",
    "resume_after": "2026-05-29T20:00:00+07:00"
  },
  "decision_summary": {
    "main_view": "Æ ̄u tiÃan buy pullback nhÆ°ng cáo§n chá» xÃ¡c nháo­n vÃ¬ cÃ3 tin CPI.",
    "action": "wait_for_confirmation",
    "best_scenario": "buy",
    "best_score": 76
  },
  "technical": {
    "price": 2342.5,
    "ema50_d1": 2320.1,
    "ema200_d1": 2280.4,
    "rsi_h4": 48.5,
    "rsi_h4_previous": 42.1,
    "macd_histogram_h4": {
      "value": -0.0023,
      "previous_value": -0.0041,
      "direction": "increasing",
      "label": "bearish_weakening"
    },
    "atr_d1": 15.2,
    "atr_avg_14d": 14.1,
    "support_zones": [
      {"level": 2330, "type": "pivot_weekly", "strength": "strong"},
      {"level": 2310, "type": "swing_low_h4", "strength": "moderate"}
    ],
    "resistance_zones": [
      {"level": 2365, "type": "pivot_monthly", "strength": "strong"},
      {"level": 2382, "type": "swing_high_d1", "strength": "strong"}
    ]
  },
  "scenario_scores": {
    "buy": {
      "trend_alignment": 23,
      "momentum_alignment": 14,
      "location_quality": 19,
      "smc_quality": 12,
      "risk_condition": 8,
      "macro_alignment": 12,
      "total": 76,
      "rating": "cÃ¢n nháo ̄c Ä'Æ°á»£c"
    },
    "sell": {
      "trend_alignment": 5,
      "momentum_alignment": 5,
      "location_quality": 3,
      "risk_condition": 8,
      "smc_quality": 2,
      "macro_alignment": 6,
      "total": 27,
      "rating": "Ä'á»©ng ngoÃ i"
    }
  },
  "macro": {
    "dxy": 104.2,
    "us10y": 4.25,
    "us2y": 4.15,
    "fed_rate": "5.25-5.50",
    "vix": 16.8,
    "ai_summary": "DXY vÃ  lá»£i suáo¥t yáo¿u nháo1 Ä'ang há»- trá»£ vÃ ng, nhÆ°ng CPI sáo ̄p cÃ ́ng bá»' lÃ m rá»§i ro biáo¿n Ä'á»TMng tÄƒng."
  },
  "economic_events": [
    {"event": "CPI", "time_vn": "19:30", "impact": "high", "hours_until": 3}
  ],
  "scenarios": [
    {
      "type": "buy",
      "priority": "primary",
      "score": 76,
      "entry_zone": [2335, 2342],
      "stop_loss": 2324,
      "take_profit": [2365, 2382],
      "risk_reward": "1:2.3",
      "condition": "Chá»‰ cÃ¢n nháo ̄c náo¿u cÃ3 náo¿n H1 xÃ¡c nháo­n tÄƒng vÃ  giÃ¡ giá» ̄ trÃan 2330.",
      "invalidation": "H1 Ä'Ã3ng dÆ°á»›i 2324 hoáo·c spread giÃ£n máo¡nh trÆ°á»›c tin CPI.",
      "position_sizing": {
        "account_balance": 10000,
        "risk_pct": 1,
        "risk_amount_usd": 100,
        "entry_price": 2340,
        "stop_loss": 2324,
        "price_distance": 16,
        "contract_size": 100,
        "suggested_lot": 0.06
      }
    },
    {
      "type": "stand_aside",
      "priority": "secondary",
      "reason": "CPI trong 3 giá» tá»›i cÃ3 thá»ƒ lÃ m biáo¿n Ä'á»TMng máo¡nh. Náo¿u khÃ ́ng cÃ3 xÃ¡c nháo­n rÃμ, nÃan Ä'á»©ng ngoÃ i."
    }
  ],
  "why_not_opposite": {
    "sell": "Sell score tháo¥p vÃ¬ D1 váo«n trend up, giÃ¡ chÆ°a á»Ÿ khÃ¡ng cá»± rÃμ vÃ  vÄ© mÃ ́ chÆ°a á»§ng há»TM USD máo¡nh."
  },
  "confidence_reason": [
    "D1 Ä'ang giá» ̄ xu hÆ°á»›ng tÄƒng.",
    "H4 pullback vá» gáo§n há»- trá»£.",
    "Sell khÃ ́ng thuáo­n vÃ¬ chÆ°a cÃ3 khÃ¡ng cá»± rÃμ.",
    "CPI sáo ̄p cÃ ́ng bá»' nÃan khÃ ́ng nÃan vÃ o lá»‡nh vá»TMi."
  ],
  "risk_management": {
    "max_risk_pct": 1,
    "max_correlated_positions": 2,
    "warnings": [
      "KhÃ ́ng vÃ o lá»‡nh 15 phÃot trÆ°á»›c/sau tin Ä'á».",
      "LuÃ ́n kiá»ƒm tra spread vÃ  giÃ¡ broker trÃan MT5 trÆ°á»›c khi vÃ o lá»‡nh.",
      "Náo¿u MT5 máo¥t káo¿t ná»'i hoáo·c spread giÃ£n báo¥t thÆ°á»ng, khÃ ́ng vÃ o lá»‡nh."
    ]
  }
}
```

### 11.2 Máo«u JSON cho Scanner Mode

Scanner Mode tráo£ vá» báo£ng tÃ3m táo ̄t Ä'á»ƒ ngÆ°á»i dÃ1ng lá»c nhanh mÃ£ Ä'Ã¡ng chÃo Ã1⁄2. Output nÃ y khÃ ́ng thay tháo¿ JSON phÃ¢n tÃ­ch Ä'áo§y Ä'á»§ cá»§a Single Analysis Mode.

```json
{
  "mode": "scanner",
  "timestamp": "2026-05-29T14:30:00+07:00",
  "symbols_scanned": 8,
  "ai_details_limit": 3,
  "summary": {
    "ready_count": 1,
    "watch_count": 2,
    "wait_count": 3,
    "skip_count": 1
  },
  "rows": [
    {
      "symbol": "XAU/USD",
      "market_regime": "trend_up",
      "direction_bias": "buy",
      "trade_permission": "allowed",
      "buy_score": 94,
      "sell_score": 18,
      "best_side": "buy",
      "best_score": 94,
      "scanner_action": "ready",
      "entry_status": "confirmed_entry",
      "risk_reward": "1:3.8",
      "short_reason": "Buy pullback táo¡i support máo¡nh, H1 Ä'Ã£ xÃ¡c nháo­n, macro thuáo­n vÃ ng.",
      "ai_summary_available": true,
      "detail_action": "View Detail"
    },
    {
      "symbol": "GBP/USD",
      "market_regime": "trend_down",
      "direction_bias": "sell",
      "trade_permission": "allowed",
      "buy_score": 28,
      "sell_score": 78,
      "best_side": "sell",
      "best_score": 78,
      "scanner_action": "watch",
      "entry_status": "watch_zone",
      "risk_reward": null,
      "short_reason": "Sell thuáo­n trend nhÆ°ng giÃ¡ chÆ°a há»"i vá» khÃ¡ng cá»±.",
      "ai_summary_available": true,
      "detail_action": "View Detail"
    },
    {
      "symbol": "EUR/USD",
      "market_regime": "range",
      "direction_bias": "neutral",
      "trade_permission": "caution",
      "buy_score": 61,
      "sell_score": 58,
      "best_side": "buy",
      "best_score": 61,
      "scanner_action": "wait",
      "entry_status": "waiting_confirmation",
      "risk_reward": null,
      "short_reason": "GiÃ¡ Ä'ang á»Ÿ giá» ̄a range, R:R chÆ°a tá»'t.",
      "ai_summary_available": false,
      "detail_action": "View Detail"
    }
  ]
}
```

CÃ¡c trÆ°á»ng quan trá»ng:

| TrÆ°á»ng | Ã nghÄ©a |
|---|---|
| `scanner_action` | Káo¿t luáo­n nhanh: ready/watch/wait/skip |
| `best_side` | HÆ°á»›ng cÃ3 Ä'iá»ƒm cao hÆ¡n: buy hoáo·c sell |
| `best_score` | Äiá»ƒm cao nháo¥t giá» ̄a buy vÃ  sell |
| `entry_status` | Tráo¡ng thÃ¡i entry do `entry_engine.py` tÃ­nh: `confirmed_entry`, `waiting_confirmation`, `watch_zone`, `invalidated`, `no_setup` |
| `ai_summary_available` | MÃ£ nÃ y cÃ3 Ä'Æ°á»£c AI viáo¿t nháo­n Ä'á»‹nh ngáo ̄n trong láo§n scan khÃ ́ng |
| `detail_action` | HÃ nh Ä'á»TMng UI Ä'á»ƒ má»Ÿ phÃ¢n tÃ­ch chi tiáo¿t |


### 11.3 TrÆ°á»ng `ai_settings` trong output

Má»-i output JSON nÃan ghi láo¡i AI provider/model Ä'Ã£ dÃ1ng Ä'á»ƒ dá»... debug vÃ  xem láo¡i journal, nhÆ°ng tuyá»‡t Ä'á»'i khÃ ́ng ghi API Key.

VÃ­ dá»¥:

```json
{
  "ai_settings_used": {
    "provider_name": "AI Box",
    "provider_type": "custom_openai_compatible",
    "model_macro": "deepseek-v4-pro",
    "model_writer": "deepseek-v4-pro",
    "api_format": "openai_compatible",
    "ai_enabled": true,
    "fallback_used": false
  }
}
```

Náo¿u AI chÆ°a cáo¥u hÃ¬nh hoáo·c bá»‹ táo ̄t:

```json
{
  "ai_settings_used": {
    "provider_name": null,
    "ai_enabled": false,
    "fallback_used": true,
    "fallback_reason": "AI chÆ°a Ä'Æ°á»£c cáo¥u hÃ¬nh, macro score táo¡m Ä'áo·t trung tÃ­nh."
  }
}
```

---

## 12. Kiáo¿n trÃoc ká»1 thuáo­t

### 12.1 Kiáo¿n trÃoc tá»•ng thá»ƒ

```
User Input
  â†"
Data Provider â†' láo¥y OHLCV D1/H4/H1
  â†"
Indicator Engine â†' tÃ­nh EMA, RSI, MACD, ATR
  â†"
Structure Engine â†' tÃ­nh pivot, swing high/low, support/resistance zones
  â†"
Regime Engine â†' xÃ¡c Ä'á»‹nh market regime
  â†"
Scoring Engine â†' cháo¥m buy/sell scenario riÃang
  â†"
Trade Plan Engine â†' táo¡o entry/SL/TP/R:R/position size
  â†"
AI Writer â†' diá»...n giáo£i vÄ© mÃ ́, tin tá»©c, nháo­n Ä'á»‹nh tiáo¿ng Viá»‡t
  â†"
PyQt6 UI â†' hiá»ƒn thá»‹ káo¿t quáo£
  â†"
SQLite Journal â†' lÆ°u lá»‹ch sá»­ phÃ¢n tÃ­ch/giao dá»‹ch
```

### 12.2 Cáo¥u trÃoc thÆ° má»¥c Ä'á» xuáo¥t

KhÃ ́ng nÃan nhÃ©t toÃ n bá»TM logic vÃ o má»TMt file `main.py` hoáo·c má»TMt file UI lá»›n. NÃan chia module Ä'á»ƒ dá»... sá»­a vÃ  nÃ¢ng cáo¥p.

```text
ai_market_analyst/
  main.py                 # Entry point khá»Ÿi táo¡o QApplication vÃ  MainWindow
  config.py               # Cáo¥u hÃ¬nh chung, danh sÃ¡ch mÃ£, symbol config
  settings.py             # Äá»c/ghi Settings, AI provider, model, timezone
  ai_providers.py         # Adapter cho OpenAI/Claude/Gemini/DeepSeek/custom provider
  ui/                     # Giao diá»‡n PyQt6: window, screens, components, QSS
  workers/                # QThread/QRunnable cho tÃ¡c vá»¥ ná»n
  terminology.py          # Tá»« Ä'iá»ƒn thuáo­t ngá» ̄ Anh - Viá»‡t cho UI
  mt5_provider.py         # Káo¿t ná»'i MetaTrader5, láo¥y OHLCV, spread, symbol info
  indicators.py           # TÃ­nh EMA, RSI, MACD, ATR
  structure.py            # Pivot, swing high/low, support/resistance
  regime.py               # Market regime
  scoring.py              # Buy/sell scenario score
  trade_plan.py           # Entry, SL, TP, risk/reward
  scanner.py              # Scanner Mode, quÃ©t nhiá»u mÃ£ vÃ  xáo¿p háo¡ng setup
  position_sizing.py      # TÃ­nh lot
  macro.py                # Lá»‹ch kinh táo¿, vÄ© mÃ ́
  ai_writer.py            # Gá»i AI Ä'á»ƒ viáo¿t nháo­n Ä'á»‹nh
  journal.py              # SQLite journal
  utils.py                # HÃ m phá»¥ trá»£: clamp, timezone, format sá»'
  samples/
    sample_xauusd.json
    sample_eurusd.json
```

### 12.3 CÃ ́ng nghá»‡ sá»­ dá»¥ng

| ThÃ nh pháo§n | CÃ ́ng nghá»‡ | LÃ1⁄2 do |
|---|---|---|
| Desktop App Shell (khung á»©ng dá»¥ng desktop) | PyQt6 | á» ̈ng dá»¥ng desktop local, kiá»ƒm soÃ¡t layout, worker, settings vÃ  tráo£i nghiá»‡m ngÆ°á»i dÃ1ng |
| Chart View (biá»ƒu Ä'á»" nhÃong) | `QWebEngineView` + HTML/JavaScript chart | NhÃong chart web tÆ°Æ¡ng tÃ¡c trong app desktop, dá»... zoom/pan/cáo­p nháo­t dá» ̄ liá»‡u |
| Core Processing (xá»­ lÃ1⁄2 lÃμi) | Python thuáo§n trong `core/` vÃ  `services/` | Xá»­ lÃ1⁄2 MT5, AI, indicator, scoring, trade plan vÃ  position sizing Ä'á»TMc láo­p vá»›i UI |
| Data (dá» ̄ liá»‡u) | MetaTrader5 Python API | Láo¥y dá» ̄ liá»‡u trá»±c tiáo¿p tá»« terminal MT5 Ä'ang Ä'Äƒng nháo­p broker |
| Indicators (chá»‰ bÃ¡o) | pandas, numpy | Chá»§ Ä'á»TMng, Ã­t phá»¥ thuá»TMc thÆ° viá»‡n ngoÃ i |
| AI | OpenAI API, Claude API, Gemini API, DeepSeek API hoáo·c Custom OpenAI-compatible Provider (nhÃ  cung cáo¥p tÃ1y chá»‰nh tÆ°Æ¡ng thÃ­ch OpenAI) | Viáo¿t nháo­n Ä'á»‹nh, tÃ3m táo ̄t vÄ© mÃ ́, cháo¥m Macro Alignment |
| Database (cÆ¡ sá»Ÿ dá» ̄ liá»‡u) | SQLite | CÃ3 sáoμn trong Python, Ä'á»§ cho 1 ngÆ°á»i dÃ1ng |
| Deploy (cháo¡y á»©ng dá»¥ng) | Local báo±ng `python main.py` hoáo·c file `.exe` Ä'Ã3ng gÃ3i sau nÃ y | ÄÆ¡n giáo£n, khÃ ́ng cáo§n VPS |

### 12.4 NguyÃan táo ̄c code

- Scoring Engine pháo£i lÃ  Python thuáo§n, khÃ ́ng phá»¥ thuá»TMc PyQt6.
- PyQt6 UI chá»‰ gá»i controller/service/worker Ä'á»ƒ cháo¡y phÃ¢n tÃ­ch vÃ  render káo¿t quáo£.
- `QWebEngineView` chá»‰ dÃ1ng Ä'á»ƒ hiá»ƒn thá»‹ chart web nhÃong. JavaScript chart khÃ ́ng Ä'Æ°á»£c tá»± tÃ­nh indicator, scoring, entry, SL, TP hoáo·c lot.
- Core Python chá»‹u trÃ¡ch nhiá»‡m xá»­ lÃ1⁄2 MT5, AI, indicator, scoring, trade plan vÃ  position sizing; UI/chart chá»‰ nháo­n dá» ̄ liá»‡u Ä'Ã£ chuáo©n hÃ3a Ä'á»ƒ hiá»ƒn thá»‹.
- CÃ3 mock data (dá» ̄ liá»‡u máo«u) chá»‰ Ä'á»ƒ test scoring ná»TMi bá»TM khi phÃ¡t triá»ƒn, khÃ ́ng dÃ1ng cho phÃ¢n tÃ­ch thá»±c chiáo¿n.
- CÃ3 log lá»-i khi thiáo¿u dá» ̄ liá»‡u hoáo·c API lá»-i.
- CÃ3 cáo¥u hÃ¬nh timezone (mÃoi giá»), máo·c Ä'á»‹nh lÃ  Asia/Bangkok hoáo·c Asia/Ho_Chi_Minh tÃ1y ngÆ°á»i dÃ1ng.
- CÃ3 cáo¥u hÃ¬nh AI Provider (nhÃ  cung cáo¥p AI) vÃ  Model (mÃ ́ hÃ¬nh AI) trong Settings, khÃ ́ng hardcode provider/model trong code.
- CÃ3 dictionary (tá»« Ä'iá»ƒn) thuáo­t ngá» ̄ Anh - Viá»‡t Ä'á»ƒ UI luÃ ́n hiá»ƒn thá»‹ giáo£i thÃ­ch tiáo¿ng Viá»‡t cáo¡nh thuáo­t ngá» ̄ tiáo¿ng Anh.
- Táo¥t cáo£ sá»' giÃ¡ do code tÃ­nh pháo£i Ä'Æ°á»£c lÆ°u trong JSON Ä'á»ƒ AI khÃ ́ng tá»± bá»‹a.

### 12.5 Timezone Handling (xá»­ lÃ1⁄2 mÃoi giá»)

MÃoi giá» lÃ  pháo§n dá»... gÃ¢y lá»-i trong dá» ̄ liá»‡u náo¿n, lá»‹ch kinh táo¿ vÃ  thá»i Ä'iá»ƒm Ä'Æ°á»£c phÃ©p giao dá»‹ch láo¡i. Quy táo ̄c báo ̄t buá»TMc:

- MÃoi giá» hiá»ƒn thá»‹ máo·c Ä'á»‹nh: `Asia/Ho_Chi_Minh`. CÃ3 thá»ƒ cáo¥u hÃ¬nh sang `Asia/Bangkok`; hai mÃoi giá» nÃ y Ä'á»u UTC+7.
- Táo¥t cáo£ timestamp (dáo¥u thá»i gian) lÆ°u trong SQLite nÃan lÆ°u theo UTC Ä'á»ƒ trÃ¡nh lá»‡ch khi Ä'á»•i mÃ¡y hoáo·c Ä'á»•i mÃ ́i trÆ°á»ng.
- Táo¥t cáo£ timestamp hiá»ƒn thá»‹ trÃan PyQt6 UI pháo£i convert (chuyá»ƒn Ä'á»•i) sang giá» Viá»‡t Nam.
- `last_candle_time` trong `data_quality` pháo£i cÃ3 cáo£ `last_candle_time_utc` vÃ  `last_candle_time_vn`.
- Lá»‹ch kinh táo¿ tá»« TradingEconomics hoáo·c Forex Factory pháo£i chuáo©n hÃ3a vá» UTC trÆ°á»›c, sau Ä'Ã3 convert sang giá» Viá»‡t Nam.
- `resume_after` trong Trade Permission pháo£i hiá»ƒn thá»‹ theo giá» Viá»‡t Nam.
- `resume_after = event_time_vn + event_buffer_minutes`, máo·c Ä'á»‹nh `event_buffer_minutes = 30`.
- Input ngÃ y/giá» tá»« PyQt6 UI pháo£i Ä'Æ°á»£c chuyá»ƒn thÃ nh timezone-aware datetime (datetime cÃ3 mÃoi giá»), khÃ ́ng dÃ1ng naive datetime (datetime khÃ ́ng cÃ3 mÃoi giá»).

Code máo«u:

```python
from zoneinfo import ZoneInfo
from datetime import timezone, timedelta

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def to_vn_time(dt):
    if dt.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware")
    return dt.astimezone(VN_TZ)


def calc_resume_after(event_time_utc, buffer_minutes=30):
    event_time_vn = to_vn_time(event_time_utc)
    return event_time_vn + timedelta(minutes=buffer_minutes)
```

### 12.6 PyQt6 UI (giao diá»‡n desktop PyQt6)

Giao diá»‡n MVP nÃan Ä'Æ¡n giáo£n nhÆ°ng rÃμ rÃ ng, Æ°u tiÃan Ä'á»c nhanh quyáo¿t Ä'á»‹nh.

#### Sidebar (thanh bÃan)

- Chá»n mode (cháo¿ Ä'á»TM): Single Analysis (phÃ¢n tÃ­ch má»TMt mÃ£) / Scanner (quÃ©t thá»‹ trÆ°á»ng).
- Náo¿u Single Analysis: chá»n 1 symbol trong danh sÃ¡ch 28 cáo·p Forex + XAU/USD.
- Náo¿u Scanner: chá»n All Supported Symbols (toÃ n bá»TM 28 cáo·p Forex + XAU/USD) hoáo·c chá»n thá»§ cÃ ́ng nhiá»u mÃ£.
- MT5 status (tráo¡ng thÃ¡i MT5): Connected / Not connected. Náo¿u chÆ°a káo¿t ná»'i thÃ¬ hiá»ƒn thá»‹ cáo£nh bÃ¡o vÃ  nÃot Retry (thá»­ láo¡i).
- Nháo­p account balance (sá»' dÆ° tÃ i khoáo£n).
- Nháo­p risk percent (pháo§n trÄƒm rá»§i ro má»-i lá»‡nh), máo·c Ä'á»‹nh 1%.
- Chá»n timezone (mÃoi giá») hiá»ƒn thá»‹, máo·c Ä'á»‹nh giá» Viá»‡t Nam.
- NÃot `Analyze` (phÃ¢n tÃ­ch) cho Single Analysis hoáo·c `Scan Market` (quÃ©t thá»‹ trÆ°á»ng) cho Scanner Mode.
- NÃot hoáo·c tab `Settings` (cÃ i Ä'áo·t) Ä'á»ƒ cáo¥u hÃ¬nh nhÃ  cung cáo¥p AI, model, API key, dá» ̄ liá»‡u MT5 vÃ  ngÃ ́n ngá» ̄ hiá»ƒn thá»‹. Base URL vÃ  cáo¥u hÃ¬nh ká»1 thuáo­t AI cháo¡y ngáo§m theo provider.

#### Settings panel (báo£ng cÃ i Ä'áo·t)

Settings panel pháo£i cÃ3 cÃ¡c tab (tháo») sau:

1. **AI Provider (nhÃ  cung cáo¥p AI)**
   - NhÃ  cung cáo¥p: DeepSeek / OpenAI / Anthropic / Claude.
   - Model: dropdown theo nhÃ  cung cáo¥p.
   - API Key: Ã ́ nháo­p dáo¡ng password/masked.
   - Test API Key (kiá»ƒm tra khÃ3a API).
   - CÃ¡c cáo¥u hÃ¬nh Base URL, API format, timeout, retry, max tokens cháo¡y ngáo§m.

2. **MT5 Data Settings (cÃ i Ä'áo·t dá» ̄ liá»‡u MT5)**
   - MT5 status (tráo¡ng thÃ¡i MT5): Connected / Not connected.
   - Broker login status (tráo¡ng thÃ¡i Ä'Äƒng nháo­p broker): Logged in / Not logged in.
   - Symbol Mapping (Ã¡nh xáo¡ mÃ£): vÃ­ dá»¥ XAU/USD â†' XAUUSDm, USD/CAD â†' USDCADm hoáo·c USDCADc, NZD/USD â†' NZDUSDm hoáo·c NZDUSDc.
   - Auto-select symbol in Market Watch (tá»± thÃam mÃ£ vÃ o Market Watch): báo­t/táo ̄t.
   - Spread threshold (ngÆ°á»¡ng spread báo¥t thÆ°á»ng) theo tá»«ng mÃ£.
   - Retry Connection (thá»­ káo¿t ná»'i láo¡i MT5).
   - KhÃ ́ng cÃ3 lá»±a chá»n MT5/MT5 trong sáo£n pháo©m.

3. **Trading Settings (cÃ i Ä'áo·t giao dá»‹ch)**
   - Account balance (sá»' dÆ° tÃ i khoáo£n).
   - Risk percent (pháo§n trÄƒm rá»§i ro má»-i lá»‡nh).
   - Lot step (bÆ°á»›c lot).
   - Contract size override (ghi Ä'Ã ̈ quy mÃ ́ há»£p Ä'á»"ng) theo tá»«ng mÃ£ náo¿u broker khÃ¡c máo·c Ä'á»‹nh.

4. **Display Settings (cÃ i Ä'áo·t hiá»ƒn thá»‹)**
   - Timezone (mÃoi giá»).
   - Term explanation mode (cháo¿ Ä'á»TM giáo£i thÃ­ch thuáo­t ngá» ̄): `always_show` (luÃ ́n hiá»ƒn thá»‹), `first_time_only` (chá»‰ láo§n Ä'áo§u), `tooltip` (hiá»ƒn thá»‹ trong tooltip).
   - Language (ngÃ ́n ngá» ̄): MVP máo·c Ä'á»‹nh tiáo¿ng Viá»‡t.

NÃot báo ̄t buá»TMc:

- `Save Settings` (lÆ°u cÃ i Ä'áo·t).
- `Test AI Connection` (kiá»ƒm tra káo¿t ná»'i AI).
- `Reset to Default` (khÃ ́i phá»¥c máo·c Ä'á»‹nh).

Náo¿u Test AI Connection tháo¥t báo¡i, UI pháo£i hiá»ƒn thá»‹ lá»-i dá»... hiá»ƒu, vÃ­ dá»¥:

```text
KhÃ ́ng káo¿t ná»'i Ä'Æ°á»£c AI Provider (nhÃ  cung cáo¥p AI). Kiá»ƒm tra láo¡i API Key (khÃ3a API), Model (mÃ ́ hÃ¬nh AI) hoáo·c káo¿t ná»'i máo¡ng.
```

#### Main area (khu vá»±c chÃ­nh)

Vá»›i Single Analysis Mode, hiá»ƒn thá»‹ theo thá»© tá»±:

1. Decision Summary (tÃ3m táo ̄t quyáo¿t Ä'á»‹nh).
2. Trade Permission (quyá»n cho phÃ©p giao dá»‹ch): allowed / caution / blocked.
3. Scenario Scores (Ä'iá»ƒm buy/sell).
4. Technical Analysis (phÃ¢n tÃ­ch ká»1 thuáo­t).
5. Macro Summary (tÃ3m táo ̄t vÄ© mÃ ́).
6. Trade Plan (káo¿ hoáo¡ch giao dá»‹ch).
7. Position Sizing (tÃ­nh lot/khá»'i lÆ°á»£ng).
8. Data Quality (cháo¥t lÆ°á»£ng dá» ̄ liá»‡u).
9. Journal (nháo­t kÃ1⁄2).

Vá»›i Scanner Mode, hiá»ƒn thá»‹ báo£ng tá»•ng há»£p:

| Cá»TMt | Ã nghÄ©a |
|---|---|
| Symbol | MÃ£ giao dá»‹ch |
| Bias | ThiÃan hÆ°á»›ng giao dá»‹ch |
| Permission | allowed/caution/blocked |
| Buy Score | Äiá»ƒm ká»‹ch báo£n mua |
| Sell Score | Äiá»ƒm ká»‹ch báo£n bÃ¡n |
| Best Setup | HÆ°á»›ng cÃ3 Ä'iá»ƒm tá»'t nháo¥t |
| Action | ready/watch/wait/skip |
| Reason | LÃ1⁄2 do ngáo ̄n |
| View Detail | Má»Ÿ phÃ¢n tÃ­ch Ä'áo§y Ä'á»§ cá»§a mÃ£ Ä'Ã3 |

#### MÃ u sáo ̄c gá»£i Ã1⁄2

- Buy (mua): xanh.
- Sell (bÃ¡n): Ä'á».
- Caution (tháo­n trá»ng): vÃ ng.
- Stand aside / blocked (Ä'á»©ng ngoÃ i / bá»‹ cháo·n): xÃ¡m.

#### Tráo¡ng thÃ¡i xá»­ lÃ1⁄2

Khi ngÆ°á»i dÃ1ng báo¥m Analyze hoáo·c Scan Market, hiá»ƒn thá»‹ spinner/progress theo cÃ¡c bÆ°á»›c:

1. Loading price data (Ä'ang táo£i dá» ̄ liá»‡u giÃ¡).
2. Calculating indicators (Ä'ang tÃ­nh chá»‰ bÃ¡o).
3. Checking economic events (Ä'ang kiá»ƒm tra lá»‹ch kinh táo¿).
4. Scoring scenarios hoáo·c scanning symbols (Ä'ang cháo¥m Ä'iá»ƒm / quÃ©t cÃ¡c mÃ£).
5. Calling AI macro writer náo¿u cáo§n (Ä'ang gá»i AI viáo¿t nháo­n Ä'á»‹nh náo¿u mÃ£ Ä'á»§ Ä'iá»u kiá»‡n).
6. Rendering result (Ä'ang hiá»ƒn thá»‹ káo¿t quáo£).

### 12.7 MT5 Connection Fallback (xá»­ lÃ1⁄2 khi MT5 khÃ ́ng káo¿t ná»'i)

Pháo§n má»m khÃ ́ng Ä'Æ°á»£c tá»± Ä'á»TMng chuyá»ƒn sang nguá»"n giÃ¡ khÃ¡c khi MT5 lá»-i. Náo¿u MT5 khÃ ́ng káo¿t ná»'i Ä'Æ°á»£c, há»‡ thá»'ng pháo£i cháo·n phÃ¢n tÃ­ch thá»±c chiáo¿n vÃ  hiá»ƒn thá»‹ cáo£nh bÃ¡o rÃμ rÃ ng.

Quy táo ̄c báo ̄t buá»TMc:

- Náo¿u terminal MT5 chÆ°a má»Ÿ: `trade_permission = blocked`.
- Náo¿u MT5 chÆ°a Ä'Äƒng nháo­p broker: `trade_permission = blocked`.
- Náo¿u khÃ ́ng tÃ¬m tháo¥y broker symbol: `trade_permission = blocked`.
- Náo¿u khÃ ́ng láo¥y Ä'Æ°á»£c OHLCV D1/H4/H1: khÃ ́ng táo¡o Trade Plan.
- Náo¿u spread báo¥t thÆ°á»ng: cÃ3 thá»ƒ phÃ¢n tÃ­ch nhÆ°ng khÃ ́ng cho `ready_to_enter`.
- KhÃ ́ng cÃ3 Yahoo Finance/yfinance fallback trong sáo£n pháo©m.

UI pháo£i hiá»ƒn thá»‹:

```text
ðŸ" ́ MT5 chÆ°a sáoμn sÃ ng

HÃ£y má»Ÿ MetaTrader 5, Ä'Äƒng nháo­p broker vÃ  kiá»ƒm tra Symbol Mapping.
Sau Ä'Ã3 báo¥m Retry.
```

### 12.8 AI Fallback (phÆ°Æ¡ng Ã¡n dá»± phÃ2ng khi AI lá»-i)

Pháo§n má»m khÃ ́ng Ä'Æ°á»£c dá»«ng toÃ n bá»TM chá»‰ vÃ¬ AI API lá»-i, AI Provider (nhÃ  cung cáo¥p AI) cáo¥u hÃ¬nh sai, model khÃ ́ng tá»"n táo¡i, háo¿t credit hoáo·c ngÆ°á»i dÃ1ng táo ̄t AI trong Settings (cÃ i Ä'áo·t). Scoring ká»1 thuáo­t, trade plan vÃ  position sizing váo«n pháo£i hoáo¡t Ä'á»TMng náo¿u dá» ̄ liá»‡u giÃ¡ há»£p lá»‡.

#### TrÆ°á»ng há»£p AI Macro Scoring lá»-i

Náo¿u AI cháo¥m Macro Alignment bá»‹ lá»-i do timeout, rate limit (giá»›i háo¡n tá»'c Ä'á»TM), háo¿t credit, JSON sai format hoáo·c lá»-i máo¡ng:

- `macro_alignment = 7`.
- `macro_reason = "KhÃ ́ng láo¥y Ä'Æ°á»£c Ä'Ã¡nh giÃ¡ vÄ© mÃ ́ tá»« AI, táo¡m cháo¥m trung tÃ­nh."`
- ThÃam warning: `"AI macro unavailable, macro score fallback to neutral"`.
- KhÃ ́ng dá»«ng app.

#### TrÆ°á»ng há»£p AI Writer lá»-i

Náo¿u AI khÃ ́ng viáo¿t Ä'Æ°á»£c nháo­n Ä'á»‹nh tiáo¿ng Viá»‡t:

- KhÃ ́ng dá»«ng app.
- DÃ1ng template cá»' Ä'á»‹nh.
- Váo«n hiá»ƒn thá»‹ technical score, scenario score, entry, SL, TP, risk/reward vÃ  position sizing.

Template fallback:

```text
KhÃ ́ng thá»ƒ táo¡o nháo­n Ä'á»‹nh AI táo¡i thá»i Ä'iá»ƒm nÃ y. Há»‡ thá»'ng váo«n hiá»ƒn thá»‹ phÃ¢n tÃ­ch ká»1 thuáo­t, Ä'iá»ƒm ká»‹ch báo£n vÃ  quáo£n trá»‹ rá»§i ro dá»±a trÃan dá» ̄ liá»‡u Ä'Ã£ tÃ­nh toÃ¡n. Pháo§n vÄ© mÃ ́ Ä'Æ°á»£c táo¡m coi lÃ  trung tÃ­nh.
```

#### Retry (thá»­ láo¡i)

- Náo¿u AI timeout: retry tá»'i Ä'a 1 láo§n.
- Náo¿u AI tráo£ JSON sai format: thá»­ parse/sá»­a JSON 1 láo§n.
- Náo¿u váo«n lá»-i: fallback ngay, khÃ ́ng gá»i láo·p vÃ ́ háo¡n.

Code máo«u:

```python
def safe_macro_score(ai_client, macro_payload):
    try:
        result = ai_client.score_macro(macro_payload)
        return validate_macro_result(result)
    except Exception as exc:
        log_error("macro_ai_failed", exc)
        return {
            "macro_score": 7,
            "reason": "KhÃ ́ng láo¥y Ä'Æ°á»£c Ä'Ã¡nh giÃ¡ vÄ© mÃ ́ tá»« AI, táo¡m cháo¥m trung tÃ­nh.",
            "fallback": True,
        }
```


### 12.8 Terminology Dictionary (tá»« Ä'iá»ƒn thuáo­t ngá» ̄ Anh - Viá»‡t)

Pháo§n má»m nÃan cÃ3 file `terminology.py` hoáo·c `terminology.json` Ä'á»ƒ quáo£n lÃ1⁄2 thá»'ng nháo¥t cÃ¡ch hiá»ƒn thá»‹ thuáo­t ngá» ̄.

VÃ­ dá»¥:

```python
TERMS = {
    "Market Regime": "tráo¡ng thÃ¡i thá»‹ trÆ°á»ng",
    "Direction Bias": "thiÃan hÆ°á»›ng giao dá»‹ch",
    "Setup Quality Score": "Ä'iá»ƒm cháo¥t lÆ°á»£ng ká»‹ch báo£n",
    "Trade Permission": "quyá»n cho phÃ©p giao dá»‹ch",
    "Entry Zone": "vÃ1ng vÃ o lá»‡nh",
    "Stop Loss": "cáo ̄t lá»-",
    "Take Profit": "chá»'t lá»i",
    "Risk/Reward": "tá»· lá»‡ rá»§i ro/lá»£i nhuáo­n",
    "Position Sizing": "tÃ­nh khá»'i lÆ°á»£ng vÃ o lá»‡nh",
    "AI Provider": "nhÃ  cung cáo¥p AI",
    "Model": "mÃ ́ hÃ¬nh AI",
    "API Key": "khÃ3a truy cáo­p API",
}


def term(label):
    vi = TERMS.get(label)
    return f"{label} ({vi})" if vi else label
```

UI pháo£i gá»i hÃ m nÃ y khi render label quan trá»ng. VÃ­ dá»¥:

```python
market_regime_title.setText(term("Market Regime"))
buy_score_card.setTitle(term("Buy Score"))
api_key_input.setPlaceholderText(term("API Key"))
```

Má»¥c tiÃau: ngÆ°á»i dÃ1ng khÃ ́ng cáo§n hiá»ƒu háo¿t thuáo­t ngá» ̄ tiáo¿ng Anh váo«n Ä'á»c Ä'Æ°á»£c mÃ n hÃ¬nh.

---

## 13. Journal (nháo­t kÃ1⁄2 giao dá»‹ch)

### 13.1 Má»¥c Ä'Ã­ch

Journal giÃop ngÆ°á»i dÃ1ng xem láo¡i:

- Há»‡ thá»'ng Ä'Ã£ phÃ¢n tÃ­ch gÃ¬.
- Ká»‹ch báo£n nÃ o Ä'Æ°á»£c Æ°u tiÃan.
- NgÆ°á»i dÃ1ng cÃ3 vÃ o lá»‡nh khÃ ́ng.
- Káo¿t quáo£ lá»‡nh ra sao.
- LÃ1⁄2 do Ä'Ãong/sai sau khi thá»‹ trÆ°á»ng cháo¡y.

### 13.2 Dá» ̄ liá»‡u lÆ°u trong journal

| TrÆ°á»ng | Ã nghÄ©a |
|---|---|
| timestamp | Thá»i Ä'iá»ƒm phÃ¢n tÃ­ch |
| symbol | MÃ£ giao dá»‹ch |
| data_source | Nguá»"n dá» ̄ liá»‡u, máo·c Ä'á»‹nh `MT5` |
| market_regime | Tráo¡ng thÃ¡i thá»‹ trÆ°á»ng |
| direction_bias | ThiÃan hÆ°á»›ng giao dá»‹ch |
| buy_score | Äiá»ƒm ká»‹ch báo£n mua |
| sell_score | Äiá»ƒm ká»‹ch báo£n bÃ¡n |
| selected_scenario | Ká»‹ch báo£n Ä'Æ°á»£c chá»n |
| entry_zone | VÃ1ng vÃ o lá»‡nh |
| stop_loss | Cáo ̄t lá»- |
| take_profit | Chá»'t lá»i |
| suggested_lot | Lot Ä'á» xuáo¥t |
| user_action | NgÆ°á»i dÃ1ng cÃ3 vÃ o lá»‡nh hay khÃ ́ng |
| result | Káo¿t quáo£ sau nÃ y: win/loss/breakeven/skipped |
| analysis_json | ToÃ n bá»TM JSON output cá»§a láo§n phÃ¢n tÃ­ch Ä'Ã3, dÃ1ng Ä'á»ƒ xem láo¡i full context |
| note | Ghi chÃo cÃ¡ nhÃ¢n |

### 13.3 LÆ°u káo¿t quáo£ Scanner Mode

Scanner Mode nÃan cho phÃ©p lÆ°u snapshot (áo£nh chá»¥p tráo¡ng thÃ¡i phÃ¢n tÃ­ch) Ä'á»ƒ xem láo¡i thá»‹ trÆ°á»ng táo¡i má»TMt thá»i Ä'iá»ƒm.

CÃ¡c field nÃan lÆ°u thÃam:

| Field | Ã nghÄ©a |
|---|---|
| `scan_id` | ID cá»§a láo§n quÃ©t |
| `scan_timestamp_utc` | Thá»i Ä'iá»ƒm quÃ©t theo UTC |
| `symbols_scanned` | Danh sÃ¡ch mÃ£ Ä'Ã£ quÃ©t |
| `scanner_rows_json` | ToÃ n bá»TM JSON báo£ng scanner |
| `top_symbol` | MÃ£ cÃ3 Ä'iá»ƒm tá»'t nháo¥t |
| `top_action` | ready/watch/wait/skip cá»§a mÃ£ tá»'t nháo¥t |
| `notes` | Ghi chÃo cá»§a ngÆ°á»i dÃ1ng náo¿u cÃ3 |

Náo¿u ngÆ°á»i dÃ1ng báo¥m `View Detail` vÃ  lÆ°u phÃ¢n tÃ­ch chi tiáo¿t, báo£n ghi chi tiáo¿t Ä'Ã3 nÃan liÃan káo¿t vá»›i `scan_id` Ä'á»ƒ biáo¿t nÃ3 Ä'áo¿n tá»« láo§n quÃ©t nÃ o.

---

## 14. Äáo·c tÃ­nh riÃang tá»«ng mÃ£ giao dá»‹ch

| MÃ£ | Pip size (kÃ­ch thÆ°á»›c pip) | Contract size (quy mÃ ́ há»£p Ä'á»"ng) | Äáo·c tÃ­nh | Yáo¿u tá»' áo£nh hÆ°á»Ÿng chÃ­nh |
|---|---:|---:|---|---|
| EUR/USD | 0.0001 | 100,000 EUR | Thanh khoáo£n cao, spread tháo¥p, Ä'i tÆ°Æ¡ng Ä'á»'i mÆ°á»£t | Fed, ECB, DXY |
| GBP/USD | 0.0001 | 100,000 GBP | Biáo¿n Ä'á»TMng máo¡nh, dá»... quÃ©t SL | BOE, CPI Anh, dá» ̄ liá»‡u lÆ°Æ¡ng UK |
| AUD/USD | 0.0001 | 100,000 AUD | Nháo¡y hÃ ng hÃ3a vÃ  Trung Quá»'c | RBA, quáo·ng sáo ̄t, than, PMI Trung Quá»'c |
| NZD/USD | 0.0001 | 100,000 NZD | Nháo¡y hÃ ng hÃ3a, sá» ̄a vÃ  Trung Quá»'c | RBNZ, Global Dairy Trade, PMI Trung Quá»'c |
| USD/JPY | 0.01 | 100,000 USD | Nháo¡y vá»›i chÃanh lá»‡ch lÃ£i suáo¥t | US10Y, BOJ, can thiá»‡p tiá»n tá»‡ Nháo­t |
| USD/CHF | 0.0001 | 100,000 USD | Mang tÃ­nh trÃo áo©n an toÃ n | SNB, risk sentiment (tÃ¢m lÃ1⁄2 rá»§i ro) |
| USD/CAD | 0.0001 | 100,000 USD | Nháo¡y vá»›i dáo§u | WTI Oil, BOC, dá» ̄ liá»‡u Canada |
| EUR/GBP | 0.0001 | 100,000 EUR | Cross chÃ¢u Ã'u, thÆ°á»ng cháo­m hÆ¡n GBP pairs khÃ¡c | ECB, BOE, dá» ̄ liá»‡u Eurozone/UK |
| EUR/JPY | 0.01 | 100,000 EUR | Cross risk-on/risk-off, nháo¡y JPY | ECB, BOJ, yield toÃ n cáo§u |
| EUR/CHF | 0.0001 | 100,000 EUR | Cross phÃ2ng thá»§, biáo¿n Ä'á»TMng thÆ°á»ng tháo¥p hÆ¡n | ECB, SNB, risk sentiment |
| EUR/AUD | 0.0001 | 100,000 EUR | Cross nháo¡y chÃanh lá»‡ch Eurozone/Ãšc | ECB, RBA, Trung Quá»'c, hÃ ng hÃ3a |
| EUR/NZD | 0.0001 | 100,000 EUR | Cross biáo¿n Ä'á»TMng khÃ¡ máo¡nh | ECB, RBNZ, hÃ ng hÃ3a má»m |
| EUR/CAD | 0.0001 | 100,000 EUR | Cross nháo¡y dáo§u vÃ  Eurozone | ECB, BOC, WTI Oil |
| GBP/JPY | 0.01 | 100,000 GBP | Biáo¿n Ä'á»TMng ráo¥t máo¡nh, dá»... quÃ©t SL | BOE, BOJ, risk sentiment |
| GBP/CHF | 0.0001 | 100,000 GBP | Cross nháo¡y GBP vÃ  trÃo áo©n CHF | BOE, SNB, risk sentiment |
| GBP/AUD | 0.0001 | 100,000 GBP | Cross biáo¿n Ä'á»TMng máo¡nh | BOE, RBA, Trung Quá»'c |
| GBP/NZD | 0.0001 | 100,000 GBP | Má»TMt trong cÃ¡c cross biáo¿n Ä'á»TMng máo¡nh | BOE, RBNZ, risk sentiment |
| GBP/CAD | 0.0001 | 100,000 GBP | Nháo¡y GBP vÃ  dáo§u Canada | BOE, BOC, WTI Oil |
| CHF/JPY | 0.01 | 100,000 CHF | Cross trÃo áo©n, nháo¡y yield | SNB, BOJ, risk sentiment |
| AUD/JPY | 0.01 | 100,000 AUD | Risk proxy phá»• biáo¿n | RBA, BOJ, Trung Quá»'c, risk sentiment |
| NZD/JPY | 0.01 | 100,000 NZD | Risk proxy, biáo¿n Ä'á»TMng vá»«a-cao | RBNZ, BOJ, risk sentiment |
| CAD/JPY | 0.01 | 100,000 CAD | Nháo¡y dáo§u vÃ  JPY | BOC, BOJ, WTI Oil |
| AUD/CHF | 0.0001 | 100,000 AUD | Risk-on/risk-off giá» ̄a AUD vÃ  CHF | RBA, SNB, Trung Quá»'c |
| NZD/CHF | 0.0001 | 100,000 NZD | Cross hÃ ng hÃ3a vÃ  trÃo áo©n | RBNZ, SNB, risk sentiment |
| CAD/CHF | 0.0001 | 100,000 CAD | Cross dáo§u vÃ  trÃo áo©n | BOC, SNB, WTI Oil |
| AUD/NZD | 0.0001 | 100,000 AUD | Cross tÆ°Æ¡ng quan cao, nháo¡y RBA/RBNZ | RBA, RBNZ, dá» ̄ liá»‡u Ãšc/New Zealand |
| AUD/CAD | 0.0001 | 100,000 AUD | Cross hÃ ng hÃ3a: Ãšc vs Canada | RBA, BOC, quáo·ng sáo ̄t, dáo§u |
| NZD/CAD | 0.0001 | 100,000 NZD | Cross hÃ ng hÃ3a má»m vs dáo§u | RBNZ, BOC, sá» ̄a, WTI Oil |
| XAU/USD | KhÃ ́ng dÃ1ng Ä'á»ƒ tÃ­nh lot | 100 oz máo·c Ä'á»‹nh | Biáo¿n Ä'á»TMng máo¡nh, Ä'a yáo¿u tá»' | Real yield, DXY, Ä'á»‹a chÃ­nh trá»‹, láo¡m phÃ¡t |

LÆ°u Ã1⁄2:

- Pip value (giÃ¡ trá»‹ pip) cá»§a USD/JPY, USD/CAD, USD/CHF thay Ä'á»•i theo tá»· giÃ¡ hiá»‡n táo¡i.
- XAU/USD dÃ1ng `price_distance * contract_size` Ä'á»ƒ tÃ­nh position sizing; pip_size náo¿u cÃ3 chá»‰ dÃ1ng Ä'á»ƒ hiá»ƒn thá»‹ sá»' pip.
- XAU/USD phá»¥ thuá»TMc quy Æ°á»›c broker, pháo£i cho phÃ©p cáo¥u hÃ¬nh láo¡i contract size, lot step vÃ  min lot.
- KhÃ ́ng dÃ1ng báo£ng nÃ y thay cho thÃ ́ng sá»' há»£p Ä'á»"ng tháo­t cá»§a broker.

---

## 15. Lá»TM trÃ¬nh phÃ¡t triá»ƒn

### 15.1 MVP

Má»¥c tiÃau: táo¡o Ä'Æ°á»£c báo£n cháo¡y local phá»¥c vá»¥ má»TMt ngÆ°á»i dÃ1ng.

Ná»TMi dung:

- PyQt6 desktop UI.
- 28 cáo·p Forex phá»• biáo¿n + XAU/USD.
- D1/H4/H1.
- Tá»± tÃ­nh EMA, RSI, MACD, ATR.
- TÃ­nh pivot, swing high/low, support/resistance.
- Market Regime.
- Direction Bias.
- Buy/Sell scoring riÃang.
- Trade Plan.
- Position sizing.
- Cáo£nh bÃ¡o dá» ̄ liá»‡u.
- Journal SQLite.
- AI viáo¿t nháo­n Ä'á»‹nh tiáo¿ng Viá»‡t.

### 15.2 Báo£n nÃ¢ng cáo¥p 1

- TÃ­ch há»£p MT5 hoáo·c broker API.
- Dá» ̄ liá»‡u spread tháo­t.
- Cáo¥u hÃ¬nh broker-specific cho XAU/USD.
- Cáo£i thiá»‡n lá»‹ch kinh táo¿ báo±ng API á»•n Ä'á»‹nh hÆ¡n.
- ThÃam bÃ¡o cÃ¡o cuá»'i ngÃ y.

### 15.3 Báo£n nÃ¢ng cáo¥p 2

- Market Scanner (quÃ©t nhiá»u mÃ£).
- Backtest.
- Paper Trading.
- Alert.
- ThÃam cá»• phiáo¿u Má»1.

### 15.4 Báo£n nÃ¢ng cáo¥p xa hÆ¡n

- AI Chart Reader (AI Ä'á»c biá»ƒu Ä'á»" tá»« áo£nh).
- Portfolio Risk (rá»§i ro toÃ n danh má»¥c).
- Multi-timeframe dashboard (báo£ng Ä'iá»u khiá»ƒn Ä'a khung thá»i gian).
- TÃ­ch há»£p broker sÃ¢u hÆ¡n náo¿u tháo­t sá»± cáo§n.

---

## 16. CÃ¡c lÆ°u Ã1⁄2 quan trá»ng khi triá»ƒn khai

### 16.1 KhÃ ́ng Ä'á»ƒ AI tá»± quyáo¿t Ä'á»‹nh sá»' liá»‡u giao dá»‹ch

AI chá»‰ Ä'Æ°á»£c viáo¿t nháo­n Ä'á»‹nh dá»±a trÃan dá» ̄ liá»‡u Ä'Ã£ cÃ3. Entry, SL, TP, lot, risk/reward pháo£i do code tÃ­nh.

### 16.2 KhÃ ́ng giao dá»‹ch khi dá» ̄ liá»‡u khÃ ́ng Ä'Ã¡ng tin

Náo¿u dá» ̄ liá»‡u thiáo¿u, náo¿n cuá»'i quÃ¡ cÅ©, API lá»-i hoáo·c timezone sai, há»‡ thá»'ng pháo£i cáo£nh bÃ¡o vÃ  khÃ ́ng nÃan táo¡o trade plan.

### 16.3 KhÃ ́ng dÃ1ng má»TMt Ä'iá»ƒm sá»' tá»•ng duy nháo¥t

Pháo£i cÃ3 Ä'iá»ƒm riÃang cho buy vÃ  sell. Má»TMt thá»‹ trÆ°á»ng cÃ3 thá»ƒ khÃ ́ng phÃ1 há»£p Ä'á»ƒ buy nhÆ°ng ráo¥t phÃ1 há»£p Ä'á»ƒ sell, hoáo·c ngÆ°á»£c láo¡i.

### 16.4 KhÃ ́ng bá» qua vá»‹ trÃ­ giÃ¡

Trend tá»'t nhÆ°ng vÃ o sai vÃ1ng váo«n lÃ  setup xáo¥u. Location Quality pháo£i cÃ3 trá»ng sá»' Ä'á»§ lá»›n.

### 16.5 KhÃ ́ng xem tin tá»©c nhÆ° pháo§n phá»¥

Tin Ä'á» sÃ¡t giá» cÃ3 thá»ƒ lÃ m vÃ ́ hiá»‡u toÃ n bá»TM phÃ¢n tÃ­ch ká»1 thuáo­t. VÃ¬ váo­y cáo§n `trade_permission` Ä'á»ƒ cháo·n giao dá»‹ch khi rá»§i ro quÃ¡ cao.

### 16.6 KhÃ ́ng dÃ1ng máo·c Ä'á»‹nh pip value cho má»i broker

Äáo·c biá»‡t vá»›i XAU/USD, pháo£i kiá»ƒm tra contract size, pip size vÃ  lot step cá»§a broker.

### 16.7 KhÃ ́ng lÃ m quÃ¡ rá»TMng trong MVP

MVP chá»‰ nÃan lÃ m tá»'t má»TMt viá»‡c: phÃ¢n tÃ­ch 28 cáo·p Forex + XAU/USD theo quy trÃ¬nh rÃμ rÃ ng. KhÃ ́ng thÃam cá»• phiáo¿u, crypto hoáo·c indices trÆ°á»›c khi lÃμi phÃ¢n tÃ­ch á»•n Ä'á»‹nh.

---

## 17. TiÃau chÃ­ hoÃ n thiá»‡n, báo£o trÃ¬ vÃ  Ä'Ã3ng gÃ3i

### 17.1 TiÃau chÃ­ hoÃ n thiá»‡n tÃ­nh nÄƒng

TrÆ°á»›c khi coi MVP lÃ  dÃ1ng Ä'Æ°á»£c, pháo§n má»m pháo£i cÃ3:

- Dashboard hiá»ƒn thá»‹ tráo¡ng thÃ¡i MT5, AI, database vÃ  cáo¥u hÃ¬nh hiá»‡n táo¡i.
- Single Analysis cháo¡y Ä'Æ°á»£c má»TMt mÃ£, cÃ3 progress, lá»-i rÃμ rÃ ng vÃ  káo¿t quáo£ Ä'áo§y Ä'á»§.
- Scanner quÃ©t danh sÃ¡ch MVP mÃ  khÃ ́ng lÃ m Ä'Æ¡ giao diá»‡n.
- Journal lÆ°u, lá»c, má»Ÿ chi tiáo¿t vÃ  export JSON.
- Settings lÆ°u Ä'Æ°á»£c AI provider, MT5 mapping, trading config, display config.
- Fallback khi AI lá»-i hoáo·c chÆ°a cáo¥u hÃ¬nh.
- Fallback UI khi MT5 chÆ°a sáoμn sÃ ng.
- Log ká»1 thuáo­t Ä'á»ƒ debug.
- Test cho core logic quan trá»ng.

### 17.2 TiÃau chÃ­ hoÃ n thiá»‡n giao diá»‡n

UI PyQt6 pháo£i Ä'áo¡t:

- CÃ3 app icon, title, window size tá»'i thiá»ƒu vÃ  layout co giÃ£n.
- CÃ3 theme/QSS thá»'ng nháo¥t, khÃ ́ng style ráo£i rÃ¡c.
- CÃ3 component dÃ1ng chung cho button, card, badge, table, loading, error vÃ  empty state.
- CÃ3 tráo¡ng thÃ¡i loading/progress khi cháo¡y tÃ¡c vá»¥ dÃ i.
- KhÃ ́ng trÃ n ngang á»Ÿ 1366x768.
- Hiá»ƒn thá»‹ tá»'t á»Ÿ Windows scaling 100%, 125% vÃ  150%.
- KhÃ ́ng Ä'á»ƒ mÃ n hÃ¬nh tráo ̄ng hoáo·c traceback thÃ ́ khi lá»-i.

### 17.3 TiÃau chÃ­ dá»... nÃ¢ng cáo¥p

Code pháo£i Ä'áo£m báo£o:

- Core khÃ ́ng import PyQt6.
- UI khÃ ́ng tÃ­nh toÃ¡n indicator, scoring hoáo·c lot.
- Controller Ä'iá»u phá»'i UI vá»›i worker/service.
- Service phá»¥ trÃ¡ch MT5, AI, database, settings vÃ  logging.
- Database thay Ä'á»•i báo±ng migration.
- Settings, symbol mapping vÃ  provider config khÃ ́ng hard-code.
- CÃ3 test hoáo·c mock cho MT5, AI vÃ  database.

### 17.4 TiÃau chÃ­ Ä'Ã3ng gÃ3i vÃ  cÃ i Ä'áo·t

Báo£n release pháo£i cÃ3:

- Script build Windows báo±ng PyInstaller hoáo·c cÃ ́ng cá»¥ tÆ°Æ¡ng Ä'Æ°Æ¡ng.
- File `.exe` cháo¡y Ä'Æ°á»£c báo±ng double click.
- Asset, QSS, font, icon vÃ  migration Ä'Æ°á»£c include Ä'áo§y Ä'á»§.
- User data náo±m trong `%APPDATA%/AI Market Analyst/`.
- KhÃ ́ng cáo§n user tá»± sá»­a Ä'Æ°á»ng dáo«n sau khi cÃ i.
- Test trÃan mÃ¡y sáo¡ch hoáo·c Windows user profile má»›i.
- TÃ i liá»‡u ngáo ̄n cho ngÆ°á»i dÃ1ng cuá»'i: cÃ¡ch má»Ÿ app, cáo¥u hÃ¬nh MT5, cáo¥u hÃ¬nh AI, backup journal.

---

## 18. Káo¿t luáo­n

AI Market Analyst lÃ  cÃ ́ng cá»¥ há»- trá»£ phÃ¢n tÃ­ch, khÃ ́ng pháo£i mÃ¡y in tiá»n vÃ  khÃ ́ng pháo£i há»‡ thá»'ng tá»± Ä'á»TMng giao dá»‹ch. GiÃ¡ trá»‹ chÃ­nh cá»§a sáo£n pháo©m náo±m á»Ÿ viá»‡c biáo¿n quÃ¡ trÃ¬nh phÃ¢n tÃ­ch thá»‹ trÆ°á»ng tá»« cáo£m tÃ­nh thÃ nh quy trÃ¬nh cÃ3 cáo¥u trÃoc:

1. Dá» ̄ liá»‡u tháo­t.
2. Chá»‰ bÃ¡o tá»± tÃ­nh.
3. Nháo­n diá»‡n tráo¡ng thÃ¡i thá»‹ trÆ°á»ng.
4. Cháo¥m Ä'iá»ƒm tá»«ng ká»‹ch báo£n riÃang.
5. Táo¡o káo¿ hoáo¡ch giao dá»‹ch cÃ3 Ä'iá»u kiá»‡n rÃμ rÃ ng.
6. Quáo£n trá»‹ rá»§i ro báo±ng position sizing.
7. DÃ1ng AI Ä'á»ƒ diá»...n giáo£i, khÃ ́ng dÃ1ng AI Ä'á»ƒ bá»‹a sá»'.

Náo¿u triá»ƒn khai Ä'Ãong nguyÃan táo ̄c trÃan, MVP cÃ3 thá»ƒ trá»Ÿ thÃ nh má»TMt cÃ ́ng cá»¥ cÃ¡ nhÃ¢n thá»±c táo¿, dá»... má»Ÿ rá»TMng vÃ  Ã­t rá»§i ro hÆ¡n nhiá»u so vá»›i viá»‡c há»i AI trá»±c tiáo¿p â€œnÃan mua hay bÃ¡nâ€.

## Logic Updates

- RSI momentum scoring must use `rsi_h4_previous`. BUY only gives the highest 30-50 RSI pullback score when current RSI is rising. SELL only gives the highest 50-70 RSI pullback score when current RSI is falling.
- Trade plan generation must return both `watch_zone` and `entry_zone`. `watch_zone` is the wider monitoring range. `entry_zone` is the narrow confirmation range around the selected level (`level +/- 0.20 ATR`) and is the only zone passed to `core/entry_engine.py` for `price_in_entry_zone` and `ready_to_trade`.
- Backtest replay must apply `cooldown_bars` after each trade exit before allowing a new touch of the same `entry_zone` to create another trade. Default cooldown is 5 H1 bars.
- AI commentary prompt must include `entry_context` with `entry_zone`, `watch_zone`, `stop_loss`, `take_profit`, `entry_status`, `confirmation_score`, and `price_vs_zone` (`in_zone`, `near_zone`, `far`, or `unknown`).
- Scanner rows must include `price_vs_zone` so the table can show whether current price is in, near, or far from the narrow `entry_zone` without opening Detail.
- Entry checklist trend logic must be side-aware: trend_up passes for buy, trend_down passes for sell, opposite trend waits/fails, and range can pass only when a valid POI/edge setup has enough location quality.
- `confidence_reason` must include score component breakdowns (`trend_alignment`, `momentum_alignment`, `location_quality`, `risk_condition`, `macro_alignment`), low `macro_confidence` context, and nearby caution event context when available.
