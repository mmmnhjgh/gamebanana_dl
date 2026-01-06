import requests
import os
import time
import re
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================= 配置区域 =================
BASE_DOWNLOAD_PATH = "GameBanana_Downloads"
GENSHIN_GAME_ID = 20357  # 原神 ID

# 最大同时下载线程数
MAX_WORKERS = 4 

# ================= API 配置 =================
BASE_URL = "https://gamebanana.com/apiv11"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# ================= 辅助函数 =================

def sanitize_filename(name):
    """清理文件名"""
    if not name: return "unknown"
    name = re.sub(r'[\x00-\x1f]', ' ', name) 
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def remove_html_tags(text):
    if not text: return "无描述"
    return re.sub(re.compile('<.*?>'), '', text)

def load_history(character_folder):
    history_path = os.path.join(character_folder, "history.txt")
    if not os.path.exists(history_path):
        return set()
    with open(history_path, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def append_history(character_folder, mod_id):
    history_path = os.path.join(character_folder, "history.txt")
    try:
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(f"{mod_id}\n")
    except Exception as e:
        print(f"    [警告] 无法写入历史记录: {e}")

def download_resource(url, save_path):
    if os.path.exists(save_path):
        return
    try:
        with requests.get(url, headers=HEADERS, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            filename = os.path.basename(save_path)
            with tqdm(total=total_size, unit='B', unit_scale=True, 
                      desc=f"下载: {filename[:15]}", ncols=90, leave=True) as bar:
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        bar.update(len(chunk))
    except Exception as e:
        print(f"    [失败] 下载出错: {e}")

def save_mod_info(folder_path, data):
    info_path = os.path.join(folder_path, "info.txt")
    if os.path.exists(info_path): return 
    content = (
        f"标题: {data.get('_sName', '未知')}\n"
        f"上传者: {data.get('_aSubmitter', {}).get('_sName', '未知')}\n"
        f"链接: {data.get('_sProfileUrl', '无')}\n\n"
        f"=== 描述 ===\n{remove_html_tags(data.get('_sText', ''))}\n"
    )
    try:
        with open(info_path, "w", encoding="utf-8") as f:
            f.write(content)
    except:
        pass

# ================= 核心逻辑 =================

def get_category_name(cat_id):
    """
    尝试根据 ID 获取官方名字
    """
    print(f"正在获取 ID {cat_id} 的官方名称...")
    url = f"{BASE_URL}/ModCategory/{cat_id}"
    params = {"_csvProperties": "_sName"} 
    
    try:
        resp = requests.get(url, params=params, headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            name = data.get("_sName")
            if name:
                print(f"API 识别成功: {name}")
                return name
    except Exception:
        pass
    
    return None

def process_submission(item_id, item_title, character_folder):
    """处理单个 Mod"""
    safe_title = sanitize_filename(item_title)
    mod_dir = os.path.join(character_folder, safe_title)
    
    if not os.path.exists(mod_dir):
        os.makedirs(mod_dir)
    
    detail_url = f"{BASE_URL}/Mod/{item_id}"
    params = {"_csvProperties": "_aFiles,_aPreviewMedia,_sText,_sName,_nLikeCount,_tsDateAdded,_aSubmitter,_sProfileUrl"}

    try:
        resp = requests.get(detail_url, params=params, headers=HEADERS)
        if resp.status_code != 200: return False
        data = resp.json()
        
        save_mod_info(mod_dir, data)

        media = data.get("_aPreviewMedia", {})
        if media and "_aImages" in media:
            for idx, img in enumerate(media["_aImages"]):
                base = img.get("_sBaseUrl")
                fname = img.get("_sFile")
                if base and fname:
                    ext = os.path.splitext(fname)[1] or ".jpg"
                    download_resource(f"{base}/{fname}", os.path.join(mod_dir, f"preview_{idx}{ext}"))

        files = data.get("_aFiles", [])
        if files:
            for f_info in files:
                if f_info.get("_sDownloadUrl"):
                    safe_fname = sanitize_filename(f_info.get("_sFile"))
                    download_resource(f_info["_sDownloadUrl"], os.path.join(mod_dir, safe_fname))
        return True

    except Exception as e:
        print(f"    [异常] Mod {item_title} 出错: {e}")
        return False

# ================= 主程序 =================

def main():
    print(f"=== GameBanana 原神下载器 (ID版+自动命名) ===")
    
    # 1. 输入 ID
    input_str = input("请输入 Mod 分类 ID (例如 18959): ").strip()
    
    if not input_str.isdigit():
        print("错误：ID 必须是纯数字。")
        return
        
    char_id = int(input_str)

    # 2. 获取名字 (如果 API 失败，强制让用户输入名字，绝不使用 ID 命名)
    folder_name = get_category_name(char_id)
    
    if not folder_name:
        # 这里是关键修改：如果自动获取失败，让用户手动输入，而不是用数字
        print(f"无法自动获取 ID {char_id} 的名字。")
        folder_name = input("请手动输入该角色的名字 (将作为文件夹名): ").strip()
        if not folder_name:
            folder_name = str(char_id) # 如果用户实在懒得输，才被迫用 ID
    
    safe_folder_name = sanitize_filename(folder_name)
    
    # 3. 创建目录
    char_dir = os.path.join(BASE_DOWNLOAD_PATH, safe_folder_name)
    if not os.path.exists(char_dir):
        os.makedirs(char_dir)
    
    print(f"目标文件夹: {char_dir}")

    # 加载历史记录
    history_ids = load_history(char_dir)
    print(f"已加载历史记录，将跳过 {len(history_ids)} 个任务。")

    # 4. 循环爬取
    page = 1
    list_url = f"{BASE_URL}/Mod/Index" 
    
    search_params = {
        "_idGameRow": GENSHIN_GAME_ID,
        "_aFilters[Generic_Category]": char_id, 
        "_nPage": 1,
        "_nPerpage": 50 
    }

    try:
        while True:
            print(f"\n------------------------------------------------")
            print(f"正在获取第 {page} 页列表 (ID: {char_id})...")
            search_params["_nPage"] = page
            
            resp = requests.get(list_url, params=search_params, headers=HEADERS)
            if resp.status_code != 200:
                print(f"列表请求失败 Code: {resp.status_code}")
                break
            
            data = resp.json()
            records = data.get("_aRecords", [])
            
            if not records:
                print("本页无数据，停止扫描。")
                break
            
            tasks_to_run = []
            skipped_count = 0
            
            for record in records:
                r_id = str(record.get("_idRow"))
                r_name = record.get("_sName", "Unknown Mod")
                
                if r_id in history_ids:
                    skipped_count += 1
                else:
                    tasks_to_run.append((r_id, r_name))
            
            if skipped_count > 0:
                print(f"  (跳过 {skipped_count} 个已下载项目)")
            
            if tasks_to_run:
                print(f"  >>> 启动 {len(tasks_to_run)} 个下载任务...")
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    future_to_mod = {
                        executor.submit(process_submission, mid, mname, char_dir): mid 
                        for (mid, mname) in tasks_to_run
                    }
                    for future in as_completed(future_to_mod):
                        mod_id = future_to_mod[future]
                        if future.result():
                            append_history(char_dir, mod_id)
                            history_ids.add(mod_id)
            else:
                print("  >>> 本页所有 Mod 均已下载。")

            current_records = len(records)
            if current_records < search_params["_nPerpage"]:
                print("\n所有页面处理完毕！")
                break
                
            page += 1
            time.sleep(1) 
            
    except KeyboardInterrupt:
        print("\n\n[!] 用户停止。")
    except Exception as e:
        print(f"\n[!] 发生错误: {e}")

if __name__ == "__main__":
    main()