# 激活height环境
# 运行前请确保已激活height环境，例如：
# conda activate height

import asf_search as asf
from asf_search import ASFSession
import os
import time
import json
from datetime import datetime

# -----------------------------
# 配置区：用户可调整的过滤参数
# -----------------------------
START_DATE = "2017-04-01"
END_DATE   = "2025-10-06"
PLATFORM   = "Sentinel-1"
BEAMMODE   = "IW"       # 附加 filter：Beam Mode = IW
PRODUCT_TYPE = "L1 Single Look Complex (SLC)"     # L1 SLC
POLARIZATION = ""      # 只要 VV 极化
DIRECTION = None         # "ASCENDING" 或 "DESCENDING" 或 None 不限制
BURST_IDS = None         # 如 [3,4,5] 或 None（不限制）
ROI = "139.6874,35.6105,139.8258,35.7151"  # 东京经纬度矩形（minLon,minLat,maxLon,maxLat）

# 输出路径（基础目录）
BASE_DIR = "/gucnas2/vickey/s1/SLC/download"

# ASF 认证信息（下载时需要）
# 优先从环境变量读取，未提供则在认证时回退到 ~/.netrc
ASF_USERNAME = os.getenv("ASF_USERNAME", "").strip()
ASF_PASSWORD = os.getenv("ASF_PASSWORD", "").strip()

# 全局变量：当前会话的时间文件夹路径（在搜索时创建）
CURRENT_SESSION_DIR = None
ASC_DIR = None
DES_DIR = None
SEARCH_RESULT_FILE = None

# -----------------------------
# 工具函数
# -----------------------------
def test_asf_authentication():
    """测试ASF认证是否正常工作"""
    print("\n🧪 测试ASF认证...")
    
    try:
        if ASF_USERNAME and ASF_PASSWORD:
            print(f"   使用环境变量: {ASF_USERNAME}")
            session = ASFSession().auth_with_creds(ASF_USERNAME, ASF_PASSWORD)
        else:
            print("   使用 ~/.netrc 文件")
            # 当没有环境变量时，创建ASFSession但不调用auth_with_creds
            # ASFSession会自动使用~/.netrc进行认证
            session = ASFSession()
        
        # 尝试一个简单的搜索来验证认证
        test_search = asf.search(
            platform=PLATFORM,
            start=START_DATE,
            end=END_DATE,
            maxResults=1
        )
        print("✅ 认证测试成功")
        return True
        
    except Exception as e:
        print(f"❌ 认证测试失败: {e}")
        return False
def create_session_directory():
    """创建以当前时间命名的会话文件夹"""
    global CURRENT_SESSION_DIR, ASC_DIR, DES_DIR, SEARCH_RESULT_FILE
    
    # 创建基础目录
    os.makedirs(BASE_DIR, exist_ok=True)
    
    # 生成时间戳文件夹名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    CURRENT_SESSION_DIR = os.path.join(BASE_DIR, timestamp)
    
    # 创建会话文件夹和子文件夹
    ASC_DIR = os.path.join(CURRENT_SESSION_DIR, "Ascending")
    DES_DIR = os.path.join(CURRENT_SESSION_DIR, "Descending")
    SEARCH_RESULT_FILE = os.path.join(CURRENT_SESSION_DIR, "search_results.json")
    
    os.makedirs(CURRENT_SESSION_DIR, exist_ok=True)
    os.makedirs(ASC_DIR, exist_ok=True)
    os.makedirs(DES_DIR, exist_ok=True)
    
    print(f"📁 创建会话文件夹: {CURRENT_SESSION_DIR}")
    
    return CURRENT_SESSION_DIR

def find_latest_session_directory():
    """查找最新的会话文件夹"""
    global CURRENT_SESSION_DIR, ASC_DIR, DES_DIR, SEARCH_RESULT_FILE
    
    if not os.path.exists(BASE_DIR):
        return None
    
    # 获取所有时间戳文件夹
    session_dirs = [d for d in os.listdir(BASE_DIR) 
                    if os.path.isdir(os.path.join(BASE_DIR, d)) and 
                    d.replace('_', '').replace('-', '').isdigit()]
    
    if not session_dirs:
        return None
    
    # 按时间排序，获取最新的
    session_dirs.sort(reverse=True)
    CURRENT_SESSION_DIR = os.path.join(BASE_DIR, session_dirs[0])
    ASC_DIR = os.path.join(CURRENT_SESSION_DIR, "Ascending")
    DES_DIR = os.path.join(CURRENT_SESSION_DIR, "Descending")
    SEARCH_RESULT_FILE = os.path.join(CURRENT_SESSION_DIR, "search_results.json")
    
    return CURRENT_SESSION_DIR

def normalize_processing_level(value: str) -> str:
    """标准化处理级别名称"""
    v = (value or "").strip().upper()
    if v in {"SLC", "LEVEL1 SLC", "L1 SLC", "LEVEL-1 SLC"}:
        return "SLC"
    if v in {"GRD", "GROUND RANGE DETECTED", "LEVEL1 GRD", "L1 GRD", "LEVEL-1 GRD"}:
        return "GRD"
    if v in {"OCN"}:
        return "OCN"
    # 常见人类可读写法
    if "SINGLE LOOK COMPLEX" in v:
        return "SLC"
    if "GROUND RANGE" in v or "GRD" in v:
        return "GRD"
    return value  # 默认返回原值

def load_search_results(filepath):
    """从JSON文件加载搜索结果"""
    if not os.path.exists(filepath):
        return None
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

# -----------------------------
# 步骤1：搜索数据函数（包含附加 filters）
# -----------------------------
def search_with_direction(direction_value):
    """根据指定的轨道方向搜索数据"""
    opts = {}

    # 基础字段：仅在非空时加入
    if PLATFORM:
        opts["platform"] = PLATFORM
    if BEAMMODE:
        opts["beamMode"] = BEAMMODE
    if PRODUCT_TYPE:
        opts["processingLevel"] = normalize_processing_level(PRODUCT_TYPE)
    if START_DATE:
        opts["start"] = START_DATE
    if END_DATE:
        opts["end"] = END_DATE

    # ROI：仅在非空时解析并加入 WKT
    if ROI and ROI.strip():
        # 将逗号分隔的 bbox 转换为合法的 WKT POLYGON，满足 asf_search 对 intersectsWith 的要求
        min_lon, min_lat, max_lon, max_lat = [float(x) for x in ROI.split(",")]
        wkt_polygon = (
            f"POLYGON(("
            f"{min_lon} {min_lat},"
            f"{max_lon} {min_lat},"
            f"{max_lon} {max_lat},"
            f"{min_lon} {max_lat},"
            f"{min_lon} {min_lat}"
            f"))"
        )
        opts["intersectsWith"] = wkt_polygon

    # Polarization 作为附加 filter：仅在非空时加入
    if POLARIZATION:
        opts["polarization"] = POLARIZATION

    # 设置轨道方向
    opts["flightDirection"] = direction_value

    # 调试：打印有效查询参数
    print(f"\n📋 搜索 {direction_value} 轨道数据，使用参数:")
    for key, value in opts.items():
        print(f"   - {key}: {value}")
    
    print(f"🔍 正在搜索...")
    results = asf.geo_search(**opts)
    
    filtered = []
    for r in results:
        props = r.properties
        # 进一步过滤 burst id
        if BURST_IDS is not None:
            # 检查 props 中是否有 burst id 信息
            burst = props.get("burst", None)
            if burst is None or burst not in BURST_IDS:
                continue
        filtered.append(r)
    
    print(f"✅ 找到 {len(filtered)} 景数据")
    return filtered

def step1_search_scenes():
    """步骤1：搜索符合条件的Sentinel-1数据"""
    print("\n" + "="*60)
    print("步骤 1: 搜索 Sentinel-1 数据")
    print("="*60)
    
    # 创建时间戳文件夹
    create_session_directory()
    
    # 如果 DIRECTION = None，分别搜索升轨和降轨
    if DIRECTION is None:
        print("\n📡 DIRECTION=None，将分别搜索升轨和降轨数据")
        
        # 搜索升轨数据
        print("\n" + "-"*60)
        print("🔼 搜索升轨数据 (ASCENDING)")
        print("-"*60)
        ascending = search_with_direction("ASCENDING")
        
        # 搜索降轨数据
        print("\n" + "-"*60)
        print("🔽 搜索降轨数据 (DESCENDING)")
        print("-"*60)
        descending = search_with_direction("DESCENDING")
        
        # 合并结果
        filtered = ascending + descending
    else:
        # 如果指定了方向，只搜索一次
        print(f"\n📡 搜索指定方向: {DIRECTION}")
        filtered = search_with_direction(DIRECTION)
        
        # 分割 ascending / descending（与 ASF 字段保持一致）
        ascending = [r for r in filtered if r.properties.get("orbitDirection") == "ASCENDING"]
        descending = [r for r in filtered if r.properties.get("orbitDirection") == "DESCENDING"]

    def print_list(title, scenes):
        print(f"\n{title} ({len(scenes)} 景):")
        print("-" * 60)
        for i, r in enumerate(scenes, 1):
            p = r.properties
            print(f"{i:3d}. {p['sceneName']}")
            print(f"     轨道方向={p.get('orbitDirection')}, "
                  f"burst={p.get('burst', 'N/A')}, "
                  f"极化={p.get('polarization')}")

    print("\n" + "="*60)
    print("搜索结果汇总")
    print("="*60)
    print_list("📡 升轨数据 (Ascending)", ascending)
    print_list("📡 降轨数据 (Descending)", descending)
    
    print(f"\n📊 统计:")
    print(f"   - 升轨数据: {len(ascending)} 景")
    print(f"   - 降轨数据: {len(descending)} 景")
    print(f"   - 总计: {len(filtered)} 景")
    
    # 保存搜索结果（包含方向信息）
    results_data = {
        "search_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "search_parameters": {
            "START_DATE": START_DATE,
            "END_DATE": END_DATE,
            "PLATFORM": PLATFORM,
            "BEAMMODE": BEAMMODE,
            "PRODUCT_TYPE": PRODUCT_TYPE,
            "POLARIZATION": POLARIZATION,
            "DIRECTION": DIRECTION,
            "ROI": ROI
        },
        "total_count": len(filtered),
        "ascending_count": len(ascending),
        "descending_count": len(descending),
        "ascending_scenes": [{"sceneName": r.properties.get("sceneName"),
                             "orbitDirection": r.properties.get("orbitDirection"),
                             "burst": r.properties.get("burst", "N/A"),
                             "polarization": r.properties.get("polarization"),
                             "startTime": r.properties.get("startTime"),
                             "fileID": r.properties.get("fileID"),
                             "url": r.properties.get("url")} for r in ascending],
        "descending_scenes": [{"sceneName": r.properties.get("sceneName"),
                              "orbitDirection": r.properties.get("orbitDirection"),
                              "burst": r.properties.get("burst", "N/A"),
                              "polarization": r.properties.get("polarization"),
                              "startTime": r.properties.get("startTime"),
                              "fileID": r.properties.get("fileID"),
                              "url": r.properties.get("url")} for r in descending]
    }
    
    with open(SEARCH_RESULT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 搜索结果已保存至: {SEARCH_RESULT_FILE}")
    
    return filtered, ascending, descending

# -----------------------------
# 步骤2：下载数据函数
# -----------------------------
def step2_download_scenes():
    """步骤2：下载已搜索到的数据"""
    print("\n" + "="*60)
    print("步骤 2: 下载 Sentinel-1 数据")
    print("="*60)
    
    # 查找最新的会话文件夹
    session_dir = find_latest_session_directory()
    
    if session_dir is None:
        print(f"❌ 未找到任何搜索会话文件夹")
        print(f"   请先运行步骤1进行搜索")
        return
    
    print(f"\n📂 使用会话文件夹: {os.path.basename(session_dir)}")
    
    # 检查是否存在搜索结果
    if not os.path.exists(SEARCH_RESULT_FILE):
        print(f"❌ 未找到搜索结果文件: {SEARCH_RESULT_FILE}")
        print(f"   请先运行步骤1进行搜索")
        return
    
    # 加载搜索结果
    saved_results = load_search_results(SEARCH_RESULT_FILE)
    print(f"\n📊 加载搜索结果:")
    print(f"   - 搜索时间: {saved_results.get('search_time', 'N/A')}")
    print(f"   - 升轨数据: {saved_results.get('ascending_count', 0)} 景")
    print(f"   - 降轨数据: {saved_results.get('descending_count', 0)} 景")
    print(f"   - 总计: {saved_results.get('total_count', 0)} 景")
    
    # 确认是否下载
    choice = input("\n❓ 是否开始下载以上数据？(y/n): ")
    if choice.lower() != "y":
        print("❌ 取消下载。")
        return
    
    # 建立认证 session（优先使用环境变量，否则回退 ~/.netrc）
    user_hint = ASF_USERNAME if ASF_USERNAME else "~/.netrc"
    print(f"\n🔐 正在使用凭据来源: {user_hint} 进行认证...")
    
    # 调试信息：显示认证状态
    print(f"   - 环境变量 ASF_USERNAME: {'已设置' if ASF_USERNAME else '未设置'}")
    print(f"   - 环境变量 ASF_PASSWORD: {'已设置' if ASF_PASSWORD else '未设置'}")
    
    try:
        if ASF_USERNAME and ASF_PASSWORD:
            print(f"   - 使用环境变量认证，用户名: {ASF_USERNAME}")
            session = ASFSession().auth_with_creds(ASF_USERNAME, ASF_PASSWORD)
        else:
            print("   - 使用 ~/.netrc 文件认证")
            session = ASFSession()
        print("✅ 认证成功")
    except Exception as e:
        print("❌ 认证失败")
        print("   - 请确认已能登录 https://urs.earthdata.nasa.gov")
        print("   - 重要：ASF API 使用 NASA Earthdata 认证，不是 ASF 直接账户")
        print("   - 请确保您的账户已授权访问 Sentinel-1 数据")
        print("   - 推荐在 ~/.netrc 配置凭据，或设置环境变量 ASF_USERNAME/ASF_PASSWORD")
        print(f"   - 具体错误: {e}")
        print("\n💡 解决方案：")
        print("   1. 确保使用 NASA Earthdata 账户凭据（不是 ASF 账户）")
        print("   2. 在 https://urs.earthdata.nasa.gov 确认账户状态")
        print("   3. 检查账户是否有 Sentinel-1 数据访问权限")
        return
    
    # 重新搜索获取完整的ASFProduct对象（用于下载）
    print("\n🔍 重新获取数据产品信息...")
    
    # 从新的数据结构中提取场景名称
    ascending_names = [s['sceneName'] for s in saved_results.get('ascending_scenes', [])]
    descending_names = [s['sceneName'] for s in saved_results.get('descending_scenes', [])]
    all_scene_names = ascending_names + descending_names
    
    if not all_scene_names:
        print("❌ 没有找到任何场景数据")
        return
    
    # 使用granule_list搜索
    try:
        results = asf.search(granule_list=all_scene_names)
        print(f"✅ 成功获取 {len(results)} 个产品")
    except Exception as e:
        print(f"❌ 获取产品失败: {e}")
        return
    
    # 分类（按照场景名称列表分类，确保下载到正确的文件夹）
    ascending = [r for r in results if r.properties.get("sceneName") in ascending_names]
    descending = [r for r in results if r.properties.get("sceneName") in descending_names]
    
    def download_list(scenes, target_dir, direction_name):
        """下载场景列表"""
        print(f"\n⬇️  开始下载 {direction_name} 数据 ({len(scenes)} 景)...")
        print("-" * 60)
        
        success_count = 0
        skip_count = 0
        fail_count = 0
        
        for i, r in enumerate(scenes, 1):
            name = r.properties["sceneName"] + ".zip"
            dest = os.path.join(target_dir, name)
            
            if os.path.exists(dest):
                print(f"{i:3d}/{len(scenes)} ✔️  已存在: {name}")
                skip_count += 1
                continue
            
            print(f"{i:3d}/{len(scenes)} ⬇️  下载中: {name}")
            try:
                r.download(path=target_dir, session=session)
                success_count += 1
                print(f"       ✅ 下载完成")
                time.sleep(1)  # 避免请求过快
            except Exception as e:
                fail_count += 1
                print(f"       ❌ 下载失败: {e}")
        
        print(f"\n{direction_name} 下载统计:")
        print(f"   - 成功: {success_count} 景")
        print(f"   - 跳过(已存在): {skip_count} 景")
        print(f"   - 失败: {fail_count} 景")
        
        return success_count, skip_count, fail_count

    # 下载升轨数据
    asc_stats = download_list(ascending, ASC_DIR, "升轨(Ascending)")
    
    # 下载降轨数据
    des_stats = download_list(descending, DES_DIR, "降轨(Descending)")
    
    # 总结
    print("\n" + "="*60)
    print("🎉 下载完成！")
    print("="*60)
    total_success = asc_stats[0] + des_stats[0]
    total_skip = asc_stats[1] + des_stats[1]
    total_fail = asc_stats[2] + des_stats[2]
    print(f"总计统计:")
    print(f"   - 成功下载: {total_success} 景")
    print(f"   - 跳过(已存在): {total_skip} 景")
    print(f"   - 下载失败: {total_fail} 景")
    print(f"\n数据保存位置:")
    print(f"   - 升轨数据: {os.path.abspath(ASC_DIR)}")
    print(f"   - 降轨数据: {os.path.abspath(DES_DIR)}")

# -----------------------------
# 主程序
# -----------------------------
def main():
    """主函数：选择执行步骤"""
    print("\n" + "="*60)
    print("Sentinel-1 数据查找与下载工具")
    print("="*60)
    
    # 首先测试认证
    if not test_asf_authentication():
        print("\n❌ 认证失败，无法继续执行。")
        print("请检查您的NASA Earthdata账户凭据。")
        return
    
    print("\n请选择要执行的步骤:")
    print("  1 - 仅搜索数据（步骤1）")
    print("  2 - 仅下载数据（步骤2，需先执行步骤1）")
    print("  3 - 搜索并下载（执行步骤1和步骤2）")
    print("  q - 退出")
    
    choice = input("\n请输入选项 (1/2/3/q): ").strip().lower()
    
    if choice == '1':
        # 仅搜索
        step1_search_scenes()
        print("\n✅ 步骤1完成！可以运行步骤2进行下载。")
        
    elif choice == '2':
        # 仅下载
        step2_download_scenes()
        
    elif choice == '3':
        # 搜索并下载
        scenes, ascending, descending = step1_search_scenes()
        
        # 询问是否继续下载
        choice2 = input("\n❓ 是否继续执行步骤2进行下载？(y/n): ")
        if choice2.lower() == 'y':
            step2_download_scenes()
        else:
            print("✅ 步骤1完成！可稍后运行步骤2进行下载。")
            
    elif choice == 'q':
        print("👋 再见！")
        return
        
    else:
        print("❌ 无效选项，请重新运行程序")

if __name__ == "__main__":
    main()

