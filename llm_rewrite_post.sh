#!/usr/bin/env bash
set -euo pipefail

# ---------- Configuration ----------
# Directory to process. Usage: TARGET_DIR=./backup/2024 bash ./llm_rewrite_post.sh
TARGET_DIR="${TARGET_DIR:-.}"

# Controls whether to re-process files that have already been rewritten.
#   true  (Default) -> If 'post_v2.md' exists, SKIP LLM processing. (No API call made)
#   false           -> Force re-run LLM on all files, overwriting existing 'post_v2.md'.
SKIP_EXISTING="${SKIP_EXISTING:-true}"
MAX_LINES=1500

RPS=2
SLEEP_INTERVAL=$(echo "scale=3; 1.0 / $RPS" | bc)

# ---------- Prompt Definition ----------
PROMPT_TEXT="""
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
"""

# ---------- Helper Functions ----------

use_gpt() {
  local src_file=$1
  local dest_file=$2
  
  cat <<EOF | codex exec -m gpt-5-codex-mini - > "$dest_file" 2> /dev/null
Raw Content:
$(cat "$src_file")

$PROMPT_TEXT
EOF
}

use_gemini() {
  local src_file=$1
  local dest_file=$2
  
  gemini --yolo \
    -p "$PROMPT_TEXT" \
    < "$src_file" \
    > "$dest_file" \
    2> /dev/null
}

process_file() {
  local idx=$1
  local src_file=$2
  
  local dir_name="$(dirname "$src_file")"
  local base_name="$(basename "$src_file" .md)"
  local dest_file="${dir_name}/${base_name}_v2.md"
  
  echo "[$idx] Processing: $src_file -> $dest_file"
  
  if [[ "$SKIP_EXISTING" == "true" && -f "$dest_file" ]]; then
    echo "[$idx] Skip (exists): $dest_file" >&2
    return 1
  fi
  
  local line_count=$(wc -l <"$src_file")
  if (( line_count > MAX_LINES )); then
    echo "[$idx] Skip (too many lines: $line_count > $MAX_LINES): $src_file" >&2
    return 1
  fi
  
  # Choose LLM provider
  local llm_result=0
  # use_gpt "$src_file" "$dest_file" || llm_result=$?
  use_gemini "$src_file" "$dest_file" || llm_result=$?

  if [ $llm_result -ne 0 ]; then
    echo "[$idx] Failed to process with GPT: $src_file (Exit code: $llm_result)" >&2
    rm -f "$dest_file"
    return 1
  fi
  
  echo "[$idx] Done: $dest_file"
  return 0
}

# ---------- Main Workflow ----------

main() {
  if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: Directory '$TARGET_DIR' not found." >&2
    exit 1
  fi
  echo "Found Directory '$TARGET_DIR'"
  
  local total_files=$(find "$TARGET_DIR" -type f -name "*.md" ! -name "*_v2.md" | wc -l | xargs)
  echo "Found $total_files files to process"
  
  export -f process_file use_gpt use_gemini
  export SKIP_EXISTING MAX_LINES PROMPT_TEXT
  
  local job_idx=0
  
  while IFS= read -r -d '' src_file; do
    job_idx=$((job_idx + 1))
    
    process_file "$job_idx" "$src_file" &
    
    sleep "$SLEEP_INTERVAL"
  done < <(find "$TARGET_DIR" -type f -name "*.md" ! -name "*_v2.md" -print0 | sort -zr)
  
  echo ""
  echo "Waiting for all background jobs to complete..."
  wait
  
  echo ""
  echo "Total files found: $total_files"
  echo "Rewrite processing complete."
}

main