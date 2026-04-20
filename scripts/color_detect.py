import cv2
import numpy as np
import os
import glob
import re


# ============================================================
# 坐标系说明:
#   原点 (0,0) 在图片左上角，X 向右递增，Y 向下递增
#
#   (0,0) ──────────── X ──────────── (640,0)
#     │                                     │
#     │              图片区域                 │
#     │                                     │
#   (0,480) ──────────────────────── (640,480)
# ============================================================

# --------------------- 颜色 HSV 范围 ---------------------
COLOR_RANGES = {
    "red": [
        (np.array([0, 100, 100]),   np.array([12, 255, 255])),    # 略拓宽 H 上限以覆盖偏橙红色
        (np.array([165, 100, 100]), np.array([180, 255, 255])),
    ],
    "yellow": [
        (np.array([20, 100, 100]),  np.array([34, 255, 255])),    # 收紧 H 上限避免误入绿色区间
    ],
    "green": [
        (np.array([35, 100, 100]),  np.array([85, 255, 255])),
    ],
}

SUPPORTED_COLORS = ["red", "yellow", "green"]

# --------------------- 检测参数 ---------------------
# 策略：优先不漏检，宁可多一些误检
MIN_CONTOUR_AREA = 500     # 最小轮廓面积
MIN_Y_RATIO = 0.35         # 方块中心 Y 至少在图片 35% 高度以下

# 形态学参数（3x3 小核，减少色彩融合导致的横向扩展）
MORPH_KERNEL = (3, 3)
ERODE_ITERATIONS = 1
DILATE_ITERATIONS = 2

# 高斯模糊（平滑颜色边界，减轻色彩渗出）
BLUR_KERNEL = (5, 5)


def get_latest_photo(photos_dir):
    """
    从 photos_dir 中找到文件名数值最大的图片。
    """
    patterns = [os.path.join(photos_dir, ext) for ext in ("*.jpg", "*.png", "*.jpeg", "*.bmp")]
    files = []
    for p in patterns:
        files.extend(glob.glob(p))

    if not files:
        return None

    def extract_number(filepath):
        numbers = re.findall(r'\d+', os.path.basename(filepath))
        return int(numbers[0]) if numbers else 0

    return max(files, key=extract_number)


def detect_color_blocks(image_path, target_color, min_area=MIN_CONTOUR_AREA):
    """
    读取图片，检测指定颜色的方块。

    处理流程:
      1. 高斯模糊去噪 → 2. BGR→HSV → 3. HSV 阈值分割
      4. 形态学处理 → 5. 查找轮廓 → 6. 面积 + Y坐标过滤 → 7. 计算中心

    返回 dict:
      found, count, blocks[{center_x, center_y, area, bbox, contour}],
      image_path, image_size
    """
    result = {
        "found": False,
        "count": 0,
        "blocks": [],
        "image_path": image_path,
        "image_size": (0, 0),
    }

    img = cv2.imread(image_path)
    if img is None:
        print("[ERROR] Cannot read: {}".format(image_path))
        return result

    h_img, w_img = img.shape[:2]
    result["image_size"] = (w_img, h_img)

    # 1. 高斯模糊
    blurred = cv2.GaussianBlur(img, BLUR_KERNEL, 0)

    # 2. 转 HSV
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

    # 3. 颜色掩膜
    target_color = target_color.lower()
    if target_color not in COLOR_RANGES:
        print("[ERROR] Unsupported color: {}".format(target_color))
        return result

    mask = np.zeros((h_img, w_img), dtype=np.uint8)
    for lower, upper in COLOR_RANGES[target_color]:
        mask |= cv2.inRange(hsv, lower, upper)

    # 4. 形态学处理（小核 3x3，减轻色彩融合）
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, MORPH_KERNEL)
    mask = cv2.erode(mask, kernel, iterations=ERODE_ITERATIONS)
    mask = cv2.dilate(mask, kernel, iterations=DILATE_ITERATIONS)

    # 5. 查找轮廓
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 6. 过滤 + 计算中心坐标
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue

        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        # Y 坐标过滤：方块集中在图片下半部分
        if cy < h_img * MIN_Y_RATIO:
            continue

        x, y, w, h = cv2.boundingRect(cnt)

        result["blocks"].append({
            "center_x": cx,
            "center_y": cy,
            "area": area,
            "bbox": (x, y, w, h),
            "contour": cnt,
        })

    result["count"] = len(result["blocks"])
    result["found"] = result["count"] > 0
    return result


def print_result(result, target_color):
    """格式化打印检测结果"""
    print("=" * 50)
    print("Image: {}".format(result["image_path"]))
    print("Size:  {}x{}".format(result["image_size"][0], result["image_size"][1]))
    print("Color: {} | Found: {} | Count: {}".format(
        target_color, result["found"], result["count"]))
    for i, block in enumerate(result["blocks"]):
        print("  #{}: center({}, {}) area={:.0f} bbox={}".format(
            i + 1, block["center_x"], block["center_y"],
            block["area"], block["bbox"]))
    print("=" * 50)


# ======================== 可视化测试 ========================
DRAW_COLORS = {
    "red":    (0, 0, 255),
    "yellow": (0, 255, 255),
    "green":  (0, 200, 0),
}
DOT_RADIUS = 6
CONTOUR_THICKNESS = 2


def run_visual_test(photos_dir, output_dir):
    """
    对所有照片执行颜色检测，标注轮廓 + 中心点 + 坐标标签，保存到 output_dir。
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    files = sorted(glob.glob(os.path.join(photos_dir, "*.jpg")),
                   key=lambda f: int(re.findall(r'\d+', os.path.basename(f))[0])
                                 if re.findall(r'\d+', os.path.basename(f)) else 0)
    if not files:
        print("[ERROR] No images found in: {}".format(photos_dir))
        return

    for fpath in files:
        img = cv2.imread(fpath)
        if img is None:
            continue

        fname = os.path.basename(fpath)
        all_detections = []

        for color in SUPPORTED_COLORS:
            result = detect_color_blocks(fpath, color)
            bgr = DRAW_COLORS[color]
            for block in result["blocks"]:
                cx, cy = block["center_x"], block["center_y"]
                # 轮廓线
                cv2.drawContours(img, [block["contour"]], -1, bgr, CONTOUR_THICKNESS)
                # 中心点：白色外圈 + 颜色实心圆
                cv2.circle(img, (cx, cy), DOT_RADIUS + 2, (255, 255, 255), 2)
                cv2.circle(img, (cx, cy), DOT_RADIUS, bgr, -1)
                # 坐标标签
                label = "{} ({},{})".format(color, cx, cy)
                cv2.putText(img, label, (cx + DOT_RADIUS + 5, cy + 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                all_detections.append((color, cx, cy))

        cv2.imwrite(os.path.join(output_dir, fname), img)
        summary = ", ".join("{}({},{})".format(c, x, y) for c, x, y in all_detections)
        print("{} => {}".format(fname, summary if summary else "(none)"))


# ======================== 主程序入口 ========================
if __name__ == "__main__":
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
    PHOTOS_DIR = os.path.join(PROJECT_DIR, "photos")
    TEST_DIR = os.path.join(PROJECT_DIR, "test_photos")

    # 检测最新照片
    latest_photo = get_latest_photo(PHOTOS_DIR)
    if latest_photo is None:
        print("[ERROR] No images in: {}".format(PHOTOS_DIR))
    else:
        print("Latest: {}\n".format(os.path.basename(latest_photo)))
        for color in SUPPORTED_COLORS:
            result = detect_color_blocks(latest_photo, color)
            print_result(result, color)

    # 可视化测试
    print("\n--- Visual Test ---")
    run_visual_test(PHOTOS_DIR, TEST_DIR)
    print("\nDone. Images saved to: {}".format(TEST_DIR))
