import json
from typing import List, Any
from dataclasses import asdict, is_dataclass


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
