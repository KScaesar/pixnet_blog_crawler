# 任務交接文件 - Post Markdown 重寫專案

## 📋 原始任務

**目標**: 尋找 `backup/${YYYY}` 目錄下所有子目錄遞迴的 `post.md`，改寫為 `post_v2.md`

**處理方式**: 使用 IDE agent 手動逐個處理（不使用 shell 腳本）

**原因**: 其他帳號沒有 API 額度，無法使用 `llm_rewrite_post.sh` 腳本

## 🎯 處理 PROMPT

```
## ROLE
You are a Markdown Architect and Copy Editor.
Your task is to transform raw text into a **highly structured, visually organized Markdown document**.

## CRITICAL OBJECTIVE
You must balance two conflicting goals:
1.  **MAXIMIZE Structure**: Aggressively use Markdown elements (Headings, Lists, Bold) to organize the text.
2.  **MINIMIZE Text Changes**: Do NOT rewrite sentences or change vocabulary. Fix errors, but keep the original wording.

## MANDATORY OPERATIONS

### 1. Structure Discovery (Force Markdown Usage)
* **Headings**: You MUST identify topic shifts. Convert short, standalone introductory lines into headings.
* **Lists**: You MUST identify enumerations or parallel concepts. Convert them into Bullet Points or Numbered Lists.
* **Emphasis**: Use bolding **extremely sparingly**. Only bold the single most critical concept in a section. **Do not** bold frequent nouns or entire sentences.
* **Consolidate**: You MUST merge loose, consecutive lines that discuss the same immediate subject into a single cohesive paragraph block.
* **Split**: Start a new paragraph block only when the specific focus or sub-topic changes.

### 2. Correction & Flow
* **Punctuation**: You MUST insert missing punctuation (commas, periods) to fix run-on sentences and ensure proper reading flow.
* **Typos**: Fix obvious spelling errors.
* **Paragraphs**: Merge broken lines caused by copy-pasting into coherent paragraphs.
* **Emoji Hygiene**: Reduce a lot of emojis.
* **URL Integrity**: Strictly preserve URLs. **NEVER** insert spaces inside a URL path. Specifically, ensure that 'domain.com/@username' remains a single continuous string.

### 3. Constraints (The No Rewriting Rule)
* **Do NOT** rewrite sentences to "improve" the style. (Target: < 50 chars added/removed per paragraph).
* **Do NOT** summarize.
* **Do NOT** add intro/outro fluff.
* **Do NOT** change the order of information.

## OUTPUT
Output ONLY the formatted Markdown content.
```

## ✅ 已確認的問答（不要再問）

### Q1: 使用什麼方式處理？
**A**: 直接用 IDE 的 agent，**不要用 shell 腳本**
- 原因：其他帳號沒有 API 額度
- 不要建議使用 `llm_rewrite_post.sh`

### Q2: 處理方式？
**A**: **手動逐個處理**（不使用腳本）
- 即使很慢也要手動處理
- 不要再問是否使用腳本

### Q3: 批次大小？
**A**: **每次處理 10-15 個文件，分多次完成**
- 不要一次處理全部
- 分批處理以保持質量

## 🎯 下一步行動

1. **⚠️ 確認年份**: **務必主動詢問用戶**要處理哪個年份 (例如 2024)，並將指令中的 `${YYYY}` 替換為該年份。
2. **繼續處理**: 鎖定該年份，處理下一批 10-15 個文件。
3. **無需重複詢問方式**: 確認年份後，直接開始手動處理，無需再問是否用腳本。

### 處理要點

- 修正斷行問題
- 增加 Markdown 結構（標題、列表）
- 減少 emoji
- 保持原文內容不變
- 保持 URL 完整性

## 📁 文件位置

- **源文件**: `${PROJECT_ROOT}/backup/${YYYY}/*/post.md`
- **目標文件**: `${PROJECT_ROOT}/backup/${YYYY}/*/post_v2.md`
- **腳本參考**: `${PROJECT_ROOT}/llm_rewrite_post.sh` (僅供參考，不使用)

## 維護與檢查指令

```bash
# 查看總文件數
find backup/${YYYY} -name "post.md" | wc -l

# 查看已完成數量
find backup/${YYYY} -name "post_v2.md" | wc -l

# 🧹 空檔案檢查與清理
# 1. 找出並列出大小為 0 的空檔案 (若 script 中斷可能產生)
find backup/${YYYY} -name "post_v2.md" -size 0 | sort -r

# 2. 刪除所有空檔案 (刪除後可重新跑 script)
find backup/${YYYY} -name "post_v2.md" -size 0 -delete

# 查看待處理文件列表 (前 15 筆)
comm -23 \
  <(find backup/${YYYY} -maxdepth 2 -name "post.md" -type f | sed 's/post\.md$//' | sort) \
  <(find backup/${YYYY} -maxdepth 2 -name "post_v2.md" -type f | sed 's/post_v2\.md$//' | sort) \
  | sort -r | head -15
```
