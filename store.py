import json
import re
import httpx
from typing import List, Any
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from model import PostMetadata, LineKind, Post


def read_metadata(filename: str) -> List[PostMetadata]:
    """
    Read post metadata from a JSON Lines file.

    Args:
        filename: Path to the JSON Lines file.

    Returns:
        List[PostMetadata]: Parsed post metadata objects.
    """

    results = []
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            # Convert string timestamp back to datetime if needed
            # The model expects a datetime object.
            # Assuming the JSON has "published_at" as a string.
            if "published_at" in data and isinstance(data["published_at"], str):
                data["published_at"] = datetime.fromisoformat(data["published_at"])
            results.append(PostMetadata(**data))
    return results


def write_jsonl(objects: List[Any], filename: str, buffer_size: int = 100) -> None:
    """
    將物件列表序列化為 JSON Lines 格式並寫入檔案。

    使用緩衝機制以提高寫入效率，避免逐行寫入的性能問題。

    Args:
        objects: 要寫入的物件列表
        filename: 目標檔案路徑
        buffer_size: 緩衝區大小（預設 100 行）
    """
    with open(filename, "w", encoding="utf-8") as f:
        buffer = []

        for obj in objects:
            # 將物件序列化為 JSON 字串並加上換行符
            obj_dict = asdict(obj) if is_dataclass(obj) else obj.__dict__
            json_line = json.dumps(obj_dict, ensure_ascii=False, default=str) + "\n"
            buffer.append(json_line)

            # 當緩衝區達到指定大小時，批次寫入
            if len(buffer) >= buffer_size:
                f.writelines(buffer)
                buffer.clear()

        # 寫入剩餘的資料
        if buffer:
            f.writelines(buffer)


def download_post(post_many: list["Post"], target_dir: str, download_images: bool = False) -> None:
    """
    Download posts as markdown files in the target directory.

    Args:
        post_many: List of Post objects to download.
        target_dir: Directory where the posts will be saved.
        download_images: Whether to download images locally. Defaults to False.
    """
    target_path = Path(target_dir)
    if not target_path.exists():
        target_path.mkdir(parents=True, exist_ok=True)

    for post in post_many:
        try:
            # Sanitize title for directory structure
            # Replace / with _ and remove other potentially unsafe characters
            safe_title = re.sub(r'[\\/*?:"<>|]', "", post.metadata.title).strip()
            date_str = post.metadata.published_at.strftime("%Y_%m%d")
            year_str = post.metadata.published_at.strftime("%Y")
            folder_name = f"{date_str}_{safe_title}"

            post_dir = target_path / year_str / folder_name
            post_dir.mkdir(parents=True, exist_ok=True)

            md_file = post_dir / "post.md"

            with open(md_file, "w", encoding="utf-8") as f:
                lines_content = []
                links_refs = []
                images_refs = []

                # Add Title as H1
                lines_content.append(f"# {post.metadata.title}\n\n")

                # Add Original Site Link
                lines_content.append(f"[origin_site]({post.metadata.url})\n\n")

                link_count = 0
                image_count = 0

                for line in post.content_many:
                    if line.kind == LineKind.TEXT:
                        lines_content.append(line.body + "\n\n")
                    elif line.kind == LineKind.LINK:
                        link_count += 1
                        ref_id = f"link-{link_count}"
                        text = line.body
                        # Markdown link syntax [text][id]
                        lines_content.append(f"[{text}][{ref_id}]\n\n")
                        links_refs.append(f"[{ref_id}]: {line.url}\n")
                    elif line.kind == LineKind.IMAGE:
                        image_count += 1
                        ref_id = f"image-{image_count}"
                        alt_text = line.body

                        # Download image
                        if line.url:
                            # Sanitize filename
                            safe_filename = re.sub(r'[\\/*?:"<>|\s]', "", line.body).strip()
                            if not safe_filename:
                                safe_filename = f"image_{image_count}.jpg"  # Fallback if body is empty or unsafe

                            image_path = post_dir / safe_filename

                            if download_images:
                                try:
                                    # Use sync logic here since download_post is sync
                                    # For better performance in async context, this should ideally be async or run in thread
                                    # But following current sync signature
                                    with httpx.Client(follow_redirects=True) as client:
                                        resp = client.get(line.url)
                                        if resp.status_code == 200:
                                            with open(image_path, "wb") as img_f:
                                                img_f.write(resp.content)
                                            # Use local filename for markdown ref
                                            images_refs.append(f"[{ref_id}]: {safe_filename}\n")
                                        else:
                                            # Fallback to URL if download fails
                                            images_refs.append(f"[{ref_id}]: {line.url}\n")
                                except Exception as e:
                                    print(f"Failed to download image {line.url}: {e}")
                                    images_refs.append(f"[{ref_id}]: {line.url}\n")
                            else:
                                # When download_images is False, use remote URL
                                images_refs.append(f"[{ref_id}]: {line.url}\n")
                        else:
                            images_refs.append(f"[{ref_id}]: #\n")

                        # Markdown image syntax ![alt][id]
                        lines_content.append(f"![{alt_text}][{ref_id}]\n\n")

                # Write content
                f.writelines(lines_content)

                # Write references if any
                if links_refs or images_refs:
                    f.write("\n")
                    if links_refs:
                        f.writelines(links_refs)
                    if images_refs:
                        f.writelines(images_refs)
        except Exception as e:
            print(f"Error downloading post {post.metadata.url}: {e}")
            continue
