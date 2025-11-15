# -*- coding: utf-8 -*-
"""
Sentinel-1 IW2 VV InSAR DEM Pipeline (Snappy)
Flow (matching your table):
1 Read  -> 2 Apply-Orbit  -> 3 TOPSAR-Split -> 4 Re-Apply-Orbit ->
5 Back-Geocoding(Stack) -> 6 ESD(optional) -> 7 Interferogram ->
8 Goldstein Filtering -> 9 SNAPHU Unwrapping -> 10 Deburst ->
11 Terrain Correction -> GeoTIFF
"""

import  os, glob, subprocess, datetime, sys
import esa_snappy as snappy
from esa_snappy import ProductIO, GPF, jpy
import shutil
import subprocess
import re, tqdm


# 保证使用 GUI 的 SNAP_HOME 配置
#os.environ["SNAP_HOME"] = os.path.expanduser("~/.snap")
#os.environ["ESASNAP_HOME"] = os.environ["SNAP_HOME"]
#os.environ["SNAP_AUXDATA_DIR"] = os.path.join(os.environ["SNAP_HOME"], "auxdata")

# 注册所有 SNAP 算子（包括 DEM）
GPF.getDefaultInstance().getOperatorSpiRegistry().loadOperatorSpis()

HashMap = jpy.get_type('java.util.HashMap')
Integer = jpy.get_type('java.lang.Integer')


# ---------------------- simple logger ----------------------
def logmsg(log, level, msg):
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    log.write(line + "\n")
    log.flush()

def read_product(logmsg,log,master_zip,slave_zip):
    logmsg(log, "INFO", f"Reading master={os.path.basename(master_zip)}, slave={os.path.basename(slave_zip)}")
    master = ProductIO.readProduct(master_zip)
    slave  = ProductIO.readProduct(slave_zip)
    if master is None or slave is None:
        logmsg(log, "ERROR", "Failed to read input products.")
        raise RuntimeError("ReadProduct returned None")
    return master,slave, log

def apply_orbit(logmsg,log,master,slave):
    p = HashMap()
    p.put("Orbit State Vectors", "Sentinel Precise (Auto Download)")
    master = GPF.createProduct("Apply-Orbit-File", p, master)
    slave = GPF.createProduct("Apply-Orbit-File", p, slave)
    return master,slave, log

def back_geocoding(logmsg,log,dem,master_split_orb,slave_split_orb):
    p = HashMap()
    p.put("demName", dem)
    p.put("resamplingType", "BILINEAR_INTERPOLATION")
    bg = GPF.createProduct("Back-Geocoding", p, [master_split_orb, slave_split_orb])
    return bg, log

def topsar_split(logmsg,log,iw,polarization,master,slave):
    p = HashMap()
    p.put("subswath", "IW2")
    p.put("firstBurstIndex", "4")
    p.put("lastBurstIndex", "7")
    p.put("selectedPolarisations", "VV")
    master_split = GPF.createProduct("TOPSAR-Split", p, master)
    slave_split  = GPF.createProduct("TOPSAR-Split", p, slave)
    return master_split,slave_split, log
    
def enhanced_spectral_diversity(logmsg,log,bg):
    esd_params = HashMap()
    esd_params.put('fineWinWidthStr', '128')
    esd_params.put('fineWinHeightStr', '128')
    esd_params.put('fineWinAccStr', '8')
    esd_params.put('fineWinOversamplingStr', '2')
    esd_params.put('xCorrThresholdStr', '0.05')
    esd = GPF.createProduct("Enhanced-Spectral-Diversity", esd_params, bg)
    # ProductIO.writeProduct(esd, os.path.join(output_dir, "stack_esd"), "BEAM-DIMAP")
    return esd, log

def interferogram(logmsg,log,esd):
    p = HashMap()
    p.put("subtractFlatEarthPhase", True)
    p.put("includeCoherence", True)
    p.put("coherenceRangeWinSize", 10)
    p.put("coherenceAzimuthWinSize", 3)
    p.put("subtractTopographicPhase", False)
    logmsg(log, "INFO", "Step 7: Interferogram Formation...")
    ifg = GPF.createProduct("Interferogram", p, [esd])
    # ProductIO.writeProduct(ifg, os.path.join(output_dir, "ifg"), "BEAM-DIMAP")
    return ifg, log

def goldstein_phase_filtering(logmsg,log,ifg):
    p = HashMap()
    p.put("alpha", 0.7)
    p.put("FFTSizeString", "32")
    p.put("WindowSize", 3)
    logmsg(log, "INFO", "Step 8: Goldstein phase filtering...")
    flt = GPF.createProduct("GoldsteinPhaseFiltering", p, ifg)
    ProductIO.writeProduct(flt, os.path.join(output_dir, "ifg_flt"), "BEAM-DIMAP")
    return flt, log
    
def run_snaphu(snaphu_dir, logmsg, log):
    snaphu_conf = os.path.join(snaphu_dir, "snaphu.conf")

    # 1. 查找 snaphu 可执行路径
    snaphu_bin = shutil.which("snaphu") or "/gs/bs/tga-guc-lab/users/vickey/snaphu/snaphu-v2.0.7/bin/snaphu"
    if not os.path.exists(snaphu_bin):
        raise FileNotFoundError(f"[FATAL] SNAPHU not found at {snaphu_bin}")

    # 2. 从 snaphu.conf 中提取命令
    input_file = None
    width = None
    with open(snaphu_conf, "r") as f:
        for line in f:
            line = line.strip()
            # 允许带 "#" 的命令行
            if "snaphu" in line and "-f" in line:
                # 去掉开头的 "#"
                line = line.lstrip("#").strip()
                parts = line.split()
                if len(parts) >= 4:
                    input_file = parts[-2]
                    width = parts[-1]
                    break

    if not input_file or not width:
        raise ValueError("[FATAL] Cannot find SNAPHU command line in snaphu.conf")

    # 3️⃣ 输出日志
    logmsg(log, "INFO", f"Step 9.3: Running SNAPHU at {snaphu_bin} ...")
    logmsg(log, "INFO", f"Working dir: {snaphu_dir}")
    logmsg(log, "INFO", f"Config file: {snaphu_conf}")
    logmsg(log, "INFO", f"Command from conf: snaphu -f snaphu.conf {input_file} {width}")

    try:
        result = subprocess.run(
            [snaphu_bin, "-f", "snaphu.conf", input_file, width],
            cwd=snaphu_dir,
            capture_output=True,
            text=True,
            check=True
        )
        logmsg(log, "INFO", "SNAPHU unwrap completed successfully.")
        if result.stdout:
            logmsg(log, "DEBUG", result.stdout)
    except subprocess.CalledProcessError as e:
        logmsg(log, "ERROR", f"SNAPHU failed with code {e.returncode}")
        if e.stdout:
            logmsg(log, "ERROR", e.stdout)
        if e.stderr:
            logmsg(log, "ERROR", e.stderr)
        raise RuntimeError("SNAPHU unwrap failed.")

# ---------------------- pipeline ----------------------
def fixed_pipeline(
    master_zip,
    slave_zip,
    output_dir,
    iw="IW2",
    polarization="VV",
    dem="SRTM 1Sec HGT"
):
    start_time = datetime.datetime.now()  # Start time
    os.makedirs(output_dir, exist_ok=True)
    log_path = os.path.join(output_dir, "log.txt")
    log = open(log_path, "w")

    # 1️⃣ Read master/slave
    master,slave, log = read_product(logmsg,log,master_zip,slave_zip)
    logmsg(log, "INFO", "Step 1 done: read master/slave.")

    # 2️⃣ Apply precise orbitSRTM 1Sec HGT (Auto Download)
    master,slave, log = apply_orbit(logmsg,log,master,slave)
    # ProductIO.writeProd uct(master, os.path.join(output_dir, "master_orb"), "BEAM-DIMAP")
    # ProductIO.writeProduct(slave, os.path.join(output_dir, "slave_orb"), "BEAM-DIMAP")
    logmsg(log, "INFO", "Step 2 done: precise orbit applied.")

    # 3️⃣ TOPSAR-Split (IW2, VV)
    master_split,slave_split, log = topsar_split(logmsg,log,iw,polarization,master,slave)
    # ProductIO.writeProduct(master_split, os.path.join(output_dir, "master_split"), "BEAM-DIMAP")
    # ProductIO.writeProduct(slave_split,  os.path.join(output_dir, "slave_split"),  "BEAM-DIMAP")
    logmsg(log, "INFO", f"Step 3 done: split {iw} {polarization.upper()}.")

    # 4️⃣ Re-apply orbit after split
    master_split_orb,slave_split_orb, log = apply_orbit(logmsg,log,master_split,slave_split)
    # ProductIO.writeProduct(master_split_orb, os.path.join(output_dir, "master_split_orb"), "BEAM-DIMAP")
    # ProductIO.writeProduct(slave_split_orb, os.path.join(output_dir, "slave_split_orb"), "BEAM-DIMAP")
    logmsg(log, "INFO", "Step 4 done: orbit reapplied on split scenes.")

    # 5️⃣ Back-Geocoding (stack)
    bg, log = back_geocoding(logmsg,log,dem,master_split_orb,slave_split_orb)
    # ProductIO.writeProduct(bg, os.path.join(output_dir, "stack_bg"), "BEAM-DIMAP")
    logmsg(log, "INFO", f"Step 5 done. Bands: {list(bg.getBandNames())}")

    # 6️⃣ Enhanced Spectral Diversity (optional, auto-fallback)
    try:
        logmsg(log, "INFO", "Step 6: Running Enhanced-Spectral-Diversity...")
        esd, log = enhanced_spectral_diversity(logmsg,log,bg)
        logmsg(log, "INFO", f"Step 6 done. ESD bands: {list(esd.getBandNames())}")
    except Exception as e:
        logmsg(log, "WARN", f"ESD failed: {e}. Using Back-Geocoding result.")
        esd = bg

    # 7️⃣ Interferogram Formation
    ifg, log = interferogram(logmsg,log,esd)
    ifg_bands = list(ifg.getBandNames())
    logmsg(log, "INFO", f"Step 7 done. IFG bands: {ifg_bands}")
    if len(ifg_bands) == 0:
        logmsg(log, "ERROR", "Interferogram has no bands. Check overlap/bursts/metadata.")
        raise RuntimeError("IFG empty")

    # 8️⃣ Goldstein Phase Filtering
    flt, log = goldstein_phase_filtering(logmsg,log,ifg)
    logmsg(log, "INFO", "Step 8 done.")

    # 9️⃣ Phase Unwrapping (SNAPHU)
    snaphu_dir = os.path.join(output_dir, "snaphu")
    os.makedirs(snaphu_dir, exist_ok=True)

    # 直接读取已生成的滤波后干涉图文件
    flt_path = os.path.join(output_dir, "ifg_flt.dim")
    # flt = ProductIO.readProduct(flt_path)

    # === 9.1 Snaphu Export ===
    p = HashMap()
    p.put("targetFolder", snaphu_dir)
    p.put("statCostMode", "TOPO")
    p.put("initMethod", "MCF")
    p.put("outputFormat", "FLOAT")
    p.put("saveWrappedPhase", True)
    p.put("saveCoherence", True)
    p.put("saveUnwPhase", True)
    p.put("unwrapAlgorithm", "SNAPHU")

    
    # ✅ 关键参数 — 这些控制写入 snaphu.conf 的内容
    p.put("exportPhase", True)
    p.put("exportCoherence", True)
    p.put("exportUnwPhase", True)
    p.put("exportSnaphuConf", True)     # 部分版本支持显式导出配置
    p.put("tileExtension", True)
    p.put("tileRows", Integer(16))     # Tile 行数
    p.put("tileCols", Integer(16))     # Tile 列数
    p.put("rowOverlap", Integer(400))
    p.put("colOverlap", Integer(400))
    p.put("tileCostThreshold", Integer(500))  # 部分版本支持，会写入 conf 中
    p.put("numberOfProcessors", Integer(8))

    snaphu_exp = GPF.createProduct("SnaphuExport", p, flt)
    ProductIO.writeProduct(snaphu_exp, snaphu_dir, "Snaphu")
    
    logmsg(log, "INFO", "Step 9.1: Snaphu export complete. Checking configuration...")


    # === 9.2 Unwrap files generated ===
    run_snaphu(snaphu_dir, logmsg, log)

    # === 9.3 Import result ===
    unw_hdrs = glob.glob(os.path.join(snaphu_dir, "UnwPhase*.hdr"))
    if not unw_hdrs:
        logmsg(log, "ERROR", "SNAPHU output not found (UnwPhase*.hdr).")
        raise RuntimeError("SNAPHU output missing")
    unw_hdr = unw_hdrs[0]

    p = HashMap()
    p.put("snaphuImportFile", unw_hdr)
    p.put("unwrapBandName", "VV")
    unw = GPF.createProduct("SnaphuImport", p, [ProductIO.readProduct(unw_hdr),flt])
    # ProductIO.writeProduct(unw, os.path.join(output_dir, "ifg_unw"), "BEAM-DIMAP")
    logmsg(log, "INFO", "Step 9 done: unwrap imported.")

    # 🔟 Deburst（拼接 burst）
    # 将每个子波束中的 burst 片段拼接为连续条带，用于后续干涉处理
    p = HashMap()  # Deburst 无需额外参数
    logmsg(log, "INFO", "Step 10: TOPSAR Deburst...")
    deburst = GPF.createProduct("TOPSAR-Deburst", p, unw)
    # ProductIO.writeProduct(deburst, os.path.join(output_dir, "ifg_deburst"), "BEAM-DIMAP")
    logmsg(log, "INFO", "Step 10 done: deburst complete.")
    print(deburst.getBandNames())
    print(deburst.getMetadataRoot().toString())

    # 11️⃣ Terrain Correction（投影到地理坐标并输出 DEM）
    p = HashMap()
    p.put('demName', "SRTM 1Sec HGT")
    p.put('externalDEMNoDataValue', 0.0)                        # <externalDEMNoDataValue>
    p.put('externalDEMApplyEGM', True)                           # <externalDEMApplyEGM>
    p.put('demResamplingMethod', 'BILINEAR_INTERPOLATION')       # <demResamplingMethod>
    p.put('imgResamplingMethod', 'BILINEAR_INTERPOLATION')       # <imgResamplingMethod>
    p.put('pixelSpacingInMeter', 10.0)                           # <pixelSpacingInMeter>
    p.put('pixelSpacingInDegree', 8.983152841195215E-5)          # <pixelSpacingInDegree>
    p.put('mapProjection', (
        'GEOGCS["WGS84(DD)", '
        'DATUM["WGS84", SPHEROID["WGS84",6378137.0,298.257223563]], '
        'PRIMEM["Greenwich",0.0], UNIT["degree",0.017453292519943295], '
        'AXIS["Geodetic longitude",EAST], AXIS["Geodetic latitude",NORTH], '
        'AUTHORITY["EPSG","4326"]]'
    ))
    p.put('alignToStandardGrid', False)                          # <alignToStandardGrid>
    p.put('standardGridOriginX', 0.0)                            # <standardGridOriginX>
    p.put('standardGridOriginY', 0.0)                            # <standardGridOriginY>
    p.put('nodataValueAtSea', True)                              # <nodataValueAtSea>

    # === 输出控制，与 XML 布尔字段完全对应 ===
    p.put('saveDEM', True)
    p.put('saveLatLon', False)
    p.put('saveIncidenceAngleFromEllipsoid', False)
    p.put('saveLocalIncidenceAngle', False)
    p.put('saveProjectedLocalIncidenceAngle', False)
    p.put('saveSelectedSourceBand', True)
    p.put('saveLayoverShadowMask', False)
    p.put('outputComplex', False)
    p.put('applyRadiometricNormalization', False)
    p.put('saveSigmaNought', False)
    p.put('saveGammaNought', False)
    p.put('saveBetaNought', False)

    p.put('incidenceAngleForSigma0', 'Use projected local incidence angle from DEM')
    p.put('incidenceAngleForGamma0', 'Use projected local incidence angle from DEM')
    p.put('auxFile', 'Latest Auxiliary File')

    logmsg(log, "INFO", "Step 11: Terrain-Correction & export GeoTIFF...")
    tc = GPF.createProduct("Terrain-Correction", p, deburst)
    ProductIO.writeProduct(tc, os.path.join(output_dir, "ifg_deb_TC"), "BEAM-DIMAP");
    ProductIO.writeProduct(tc, os.path.join(output_dir, "DEM_output"), "GeoTIFF-BigTIFF")
    logmsg(log, "INFO", "Step 11 done: terrain correction complete. DEM exported.")

    logmsg(log, "INFO", "All steps finished successfully.")

    
    end_time = datetime.datetime.now()  # End time
    duration = end_time - start_time
    logmsg(log, "INFO", f"Total execution time: {duration}")
    log.close()


# ---------------------- main ----------------------
if __name__ == "__main__":
    # 按你的实际路径修改
    #master_zip = "./data/S1A_IW_SLC__1SDV_20170910T204309_20170910T204337_018318_01ED12_DA0E.zip"
    #master_zip = "./data/S1B_IW_SLC__1SDV_20201006T084141_20201006T084208_023690_02D038_B36B.zip"
    #slave_zip  = "./data/S1A_IW_SLC__1SDV_20170922T204310_20170922T204338_018493_01F271_2678.zip"
    #slave_zip = "./data/S1A_IW_SLC__1SDV_20201012T084204_20201012T084231_034761_040CDF_4027.zip"
    
    master_zip = "./data/S1B_IW_SLC__1SDV_20201217T084140_20201217T084207_024740_02F148_C219.zip"
    slave_zip  = "./data/S1B_IW_SLC__1SDV_20201205T084141_20201205T084207_024565_02EB9A_B623.zip"
    output_dir = "./output3"

    # 固定 IW2 + VV；DEM 与 GUI 一致
    try:
        fixed_pipeline(
            master_zip=master_zip,
            slave_zip=slave_zip,
            output_dir=output_dir,
            iw="IW2",
            polarization="VV",
            dem="SRTM 1Sec HGT"
        )
    except Exception as e:
        print(f"[FATAL] {e}")
        sys.exit(1)
