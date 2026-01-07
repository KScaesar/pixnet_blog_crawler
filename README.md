# pixnet_blog_crawler

痞客邦 2025 年底改版後,後台匯出／備份功能一度癱瘓,開發一個 PIXNET 部落格爬蟲備份工具,自救資料。

## 架構說明

- **`page_crawler.py`** - 並發爬取分頁,自動重試,排序索引
- **`post_crawler.py`** - 讀取文章列表,爬取每篇文章完整內容 (尚未實作)
- **`model.py`** - 定義 `PostMetadata` 與 `PageCrawlerSelectors`
- **`dom.py`** - 提取文字、日期、URL (支援多格式日期解析)
- **`store.py`** - JSON Lines 緩衝寫入

## 使用方式

### 安裝相依套件與瀏覽器

本專案使用 `uv` 進行套件管理。除了安裝 python 套件外，還需要安裝 Playwright 所需的瀏覽器二進位檔案。

```bash
uv sync                 # 安裝 Python 套件
uv run playwright install  # 安裝瀏覽器 (必須透過 uv run 執行)
```

> **注意**: 直接執行 `playwright install` 可能會失敗，因為 `playwright` 指令位於虛擬環境中，必須加上 `uv run`。

### 步驟 1: 爬取文章列表

```bash
uv run page_crawler.py
```

產生 `posts.json` (包含所有文章的元資料)

### 步驟 2: 爬取文章內容

```bash
uv run post_crawler.py 2> download_error.log
```

讀取 `posts.json`，爬取每篇文章的完整內容，並將錯誤訊息（如內容抓取失敗）記錄到 `download_error.log`。

### 適應不同 HTML 格式

若要爬取其他部落格,修改 [`page_crawler.py`](https://github.com/KScaesar/pixnet_blog_crawler/blob/main/page_crawler.py#L202-L213) 的 `main()` 函式:

```python
async def main():
    crawler = PageCrawler(
        base_url="https://your-blog.pixnet.net/blog",  # 修改目標 URL
        selectors=PageCrawlerSelectors(
            post_container="div.article",          # 文章容器的 CSS 選擇器
            title=".article h2 a",                 # 標題選擇器
            published_at=".article li.publish",    # 發布時間選擇器
            post_url=".article h2 a",              # 文章連結選擇器
        ),
        start_page=1,
        end_page=163,
    )
```

**如何找到正確的 CSS 選擇器:**
1. 在瀏覽器開啟部落格頁面
2. 按 F12 開啟開發者工具
3. 使用元素選取器 (Inspect) 找到對應的 HTML 元素
4. 複製或撰寫對應的 CSS 選擇器
