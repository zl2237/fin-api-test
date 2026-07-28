import json
import yaml

def yaml_to_json_file(yaml_file: str, json_file: str):
    with open(yaml_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 这里直接写文件名
    yaml_to_json_file("input.yaml", "output.json")
    print("转换完成：input.yaml → output.json")