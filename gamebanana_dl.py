import requests
import os
import time
import re
from tqdm import tqdm  

# ================= 配置区域 =================
BASE_DOWNLOAD_PATH = "GameBanana_Downloads"
GAME_ID = 8552  # 原神 ID

# ================= API 配置 =================
BASE_URL = "https://gamebanana.com/apiv11"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# ================= 辅助函数 =================

def sanitize_filename(name):
    """清理文件名"""
    if not name: return "unknown"
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def remove_html_tags(text):
    """移除 HTML 标签"""
    if not text: return "无描述"
    return re.sub(re.compile('<.*?>'), '', text)

# --- 历史记录管理 ---
def load_history(character_folder):
    """读取已完成的 Mod ID 列表"""
    history_path = os.path.join(character_folder, "history.txt")
    if not os.path.exists(history_path):
        return set()
    with open(history_path, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def append_history(character_folder, mod_id):
    """将完成的 Mod ID 写入记录"""
    history_path = os.path.join(character_folder, "history.txt")
    try:
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(f"{mod_id}\n")
    except Exception as e:
        print(f"    [警告] 无法写入历史记录: {e}")


def download_resource(url, save_path):
    """下载文件并显示进度条"""
    if os.path.exists(save_path):
        print(f"    [跳过] 文件已存在: {os.path.basename(save_path)}")
        return

    try:
        with requests.get(url, headers=HEADERS, stream=True) as r:
            r.raise_for_status()
            
            total_size = int(r.headers.get('content-length', 0))
            filename = os.path.basename(save_path)
            
            # leave=True: 下载完成后保留进度条在屏幕上
            # ncols=100: 设置进度条宽度，防止太窄
            with tqdm(total=total_size, unit='B', unit_scale=True, 
                      desc=f"    下载: {filename[:20]}", 
                      ncols=100, leave=True) as bar:
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        bar.update(len(chunk))
                        
    except Exception as e:
        print(f"    [失败] 下载出错: {e}")

def save_mod_info(folder_path, data):
    """保存信息到 txt"""
    info_path = os.path.join(folder_path, "info.txt")
    if os.path.exists(info_path): return 

    content = (
        f"标题: {data.get('_sName', '未知')}\n"
        f"上传者: {data.get('_aSubmitter', {}).get('_sName', '未知')}\n"
        f"发布日期: {time.strftime('%Y-%m-%d', time.localtime(data.get('_tsDateAdded', 0)))}\n"
        f"点赞数: {data.get('_nLikeCount', 0)}\n"
        f"链接: {data.get('_sProfileUrl', '无')}\n\n"
        f"=== 描述 ===\n{remove_html_tags(data.get('_sText', ''))}\n"
    )
    try:
        with open(info_path, "w", encoding="utf-8") as f:
            f.write(content)
    except:
        pass

def process_submission(item_id, item_title, character_folder):
    """处理单个 Mod"""
    
    # 1. 准备文件夹
    safe_title = sanitize_filename(item_title)
    mod_dir = os.path.join(character_folder, safe_title)
    
    if not os.path.exists(mod_dir):
        os.makedirs(mod_dir)
        print(f"\n>>> 发现新 Mod: {safe_title}")
    else:
        # 如果文件夹存在但没有历史记录，可能是以前下了一半，显示检查更新
        print(f"\n>>> 检查内容: {safe_title}")

    # 2. 获取详情
    detail_url = f"{BASE_URL}/Mod/{item_id}"
    params = {"_csvProperties": "_aFiles,_aPreviewMedia,_sText,_sName,_nLikeCount,_tsDateAdded,_aSubmitter,_sProfileUrl"}

    try:
        resp = requests.get(detail_url, params=params, headers=HEADERS)
        if resp.status_code != 200: return False
        
        data = resp.json()
        
        # 保存 info.txt
        save_mod_info(mod_dir, data)

        # 下载预览图
        media = data.get("_aPreviewMedia", {})
        if media and "_aImages" in media:
            for idx, img in enumerate(media["_aImages"]):
                base = img.get("_sBaseUrl")
                fname = img.get("_sFile")
                if base and fname:
                    ext = os.path.splitext(fname)[1] or ".jpg"
                    download_resource(f"{base}/{fname}", os.path.join(mod_dir, f"preview_{idx}{ext}"))

        # 下载 Mod 本体
        files = data.get("_aFiles", [])
        if files:
            for f_info in files:
                if f_info.get("_sDownloadUrl"):
                    safe_fname = sanitize_filename(f_info.get("_sFile"))
                    download_resource(f_info["_sDownloadUrl"], os.path.join(mod_dir, safe_fname))
        
        return True # 标记为成功

    except Exception as e:
        print(f"    [异常] {e}")
        return False

# ================= 主程序 =================

def main():
    print(f"=== GameBanana Mod 下载器 喵喵喵 ===")
    user_input = input("请输入角色名字 (例如 Aino): ").strip()
    if not user_input: return

    safe_char_name = sanitize_filename(user_input)
    char_dir = os.path.join(BASE_DOWNLOAD_PATH, safe_char_name)
    if not os.path.exists(char_dir):
        os.makedirs(char_dir)

    # 加载历史记录
    history_ids = load_history(char_dir)
    print(f"已加载历史记录，将自动跳过 {len(history_ids)} 个已完成任务。")

    page = 1
    search_params = {
        "_nPage": 1,
        "_sSort": "new",
        "_sName": user_input,
        "_csvModelInclusions": "Mod"
    }

    try:
        while True:
            print(f"------------------------------------------------")
            print(f"正在扫描第 {page} 页...")
            search_params["_nPage"] = page
            
            resp = requests.get(f"{BASE_URL}/Game/{GAME_ID}/Subfeed", params=search_params, headers=HEADERS)
            if resp.status_code != 200:
                print("API 请求结束。")
                break
            
            data = resp.json()
            records = data.get("_aRecords", [])
            
            if not records:
                print("没有更多数据。")
                break
            
            skipped_count = 0
            
            for record in records:
                r_id = str(record.get("_idRow"))
                r_name = record.get("_sName")
                
                # 检查历史记录
                if r_id in history_ids:
                    skipped_count += 1
                    continue
                
                if r_id:
                    success = process_submission(r_id, r_name, char_dir)
                    if success:
                        append_history(char_dir, r_id)
                        history_ids.add(r_id)
                    
                    time.sleep(1) 

            if skipped_count > 0:
                print(f"  (本页有 {skipped_count} 个 Mod 因已在历史记录中而跳过)")

            if data.get("_aMetadata", {}).get("_bIsComplete"):
                print("\n所有页面已扫描完毕！")
                break
                
            page += 1
            
    except KeyboardInterrupt:
        print("\n\n[!] 用户强制停止。历史记录已保存。")
    except Exception as e:
        print(f"\n[!] 发生错误: {e}")

if __name__ == "__main__":
    main()