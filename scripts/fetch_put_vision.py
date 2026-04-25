"""
fetch_put_vision.py — 识别拾取指定颜色方块，视觉引导放置

用法: python fetch_put_vision.py <color>
  color: red / yellow / green

流程:
  Phase 1 (fetch): 向左搜索目标颜色方块，对准后拾取
  Phase 2 (put):   视觉引导向左搜索目标放置区域，对准后放置
"""

import sys
import os
import time
import cv2
import numpy as np

import YanAPI
import take_pic
from color_detect import (
    get_latest_photo,
    detect_color_blocks,
    SUPPORTED_COLORS,
    DRAW_COLORS,
    DOT_RADIUS,
    CONTOUR_THICKNESS,
)


# ======================== 路径配置 ========================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
PHOTOS_DIR = os.path.join(PROJECT_DIR, "photos")
TEST_PHOTOS_DIR = os.path.join(PROJECT_DIR, "test_photos")


# ======================== 参数配置 ========================
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
CENTER_X = IMAGE_WIDTH // 2
CENTER_TOLERANCE = 40
SEARCH_WALK_REPEAT = 2
MAX_ITERATIONS = 40

INITIAL_BACKWARD_STEPS = 3
PUT_CENTER_TOLERANCE = 40
PUT_SEARCH_WALK_REPEAT = 2
PUT_MAX_ITERATIONS = 40


# ======================== Put 阶段本地颜色检测（无 Y 过滤） ========================
PUT_COLOR_RANGES = {
    "red": [
        (np.array([0, 60, 80]),     np.array([12, 255, 255])),
        (np.array([165, 60, 80]),   np.array([180, 255, 255])),
    ],
    "yellow": [
        (np.array([20, 140, 190]),  np.array([34, 255, 255])),
        (np.array([20, 200, 170]),  np.array([34, 255, 255])),
    ],
    "green": [
        (np.array([35, 100, 100]),  np.array([85, 255, 255])),
    ],
}

PUT_MIN_CONTOUR_AREA = 1000
PUT_MORPH_KERNEL = (3, 3)
PUT_ERODE_ITERATIONS = 1
PUT_DILATE_ITERATIONS = 2
PUT_BLUR_KERNEL = (5, 5)


def detect_color_blocks_put(image_path, target_color):
    """
    Put 阶段专用的颜色检测。
    与 color_detect.py 的 detect_color_blocks 使用相同的 HSV 参数，
    但不做 Y 坐标过滤（放置区域目标可能在画面中部）。
    """
    result = {
        "found": False,
        "count": 0,
        "blocks": [],
        "image_path": image_path,
    }

    img = cv2.imread(image_path)
    if img is None:
        print("[ERROR] Cannot read: {}".format(image_path))
        return result

    h_img, w_img = img.shape[:2]

    blurred = cv2.GaussianBlur(img, PUT_BLUR_KERNEL, 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

    target_color = target_color.lower()
    if target_color not in PUT_COLOR_RANGES:
        print("[ERROR] Unsupported color: {}".format(target_color))
        return result

    mask = np.zeros((h_img, w_img), dtype=np.uint8)
    for lower, upper in PUT_COLOR_RANGES[target_color]:
        mask |= cv2.inRange(hsv, lower, upper)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, PUT_MORPH_KERNEL)
    mask = cv2.erode(mask, kernel, iterations=PUT_ERODE_ITERATIONS)
    mask = cv2.dilate(mask, kernel, iterations=PUT_DILATE_ITERATIONS)

    contours_result = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours_result[-2]  # 兼容不同 OpenCV 版本

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < PUT_MIN_CONTOUR_AREA:
            continue

        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue

        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
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


# ======================== 拍照 ========================
def do_take_photo():
    take_pic.main()
    return get_latest_photo(PHOTOS_DIR)


# ======================== 保存调试可视化 ========================
def save_debug_image(image_path, result, target_color):
    if not os.path.exists(TEST_PHOTOS_DIR):
        os.makedirs(TEST_PHOTOS_DIR)

    img = cv2.imread(image_path)
    if img is None:
        return

    bgr = DRAW_COLORS.get(target_color, (255, 255, 255))
    for block in result["blocks"]:
        cx, cy = block["center_x"], block["center_y"]
        cv2.drawContours(img, [block["contour"]], -1, bgr, CONTOUR_THICKNESS)
        cv2.circle(img, (cx, cy), DOT_RADIUS + 2, (255, 255, 255), 2)
        cv2.circle(img, (cx, cy), DOT_RADIUS, bgr, -1)
        label = "{} ({},{})".format(target_color, cx, cy)
        cv2.putText(img, label, (cx + DOT_RADIUS + 5, cy + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    cv2.line(img, (CENTER_X, 0), (CENTER_X, IMAGE_HEIGHT), (255, 255, 255), 1)

    fname = os.path.basename(image_path)
    save_path = os.path.join(TEST_PHOTOS_DIR, fname)
    cv2.imwrite(save_path, img)
    print("[INFO] 调试图片已保存: {}".format(save_path))


def _get_encounter_index(encountered_colors, target_color):
    if target_color in encountered_colors:
        return encountered_colors.index(target_color) + 1
    return -1


# ======================== Phase 1: Fetch ========================
def do_fetch(target_color):
    """搜索并拾取目标颜色方块，返回物块编号。"""
    print("=" * 55)
    print("  [Phase 1] Fetch — 目标颜色: {}".format(target_color))
    print("  中心容差: ±{} 像素".format(CENTER_TOLERANCE))
    print("  最大迭代: {} 次".format(MAX_ITERATIONS))
    print("=" * 55)

    os.makedirs(PHOTOS_DIR, exist_ok=True)
    YanAPI.yan_api_init(YanAPI.ip)

    print("[INFO] 复位姿态...")
    YanAPI.sync_play_motion("reset")
    time.sleep(0.5)

    encountered_colors = []
    ever_found = False
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1
        print("\n--- [Fetch] 第 {} 次迭代 ---".format(iteration))

        photo_path = do_take_photo()
        if photo_path is None:
            print("[WARN] 拍照失败，1 秒后重试...")
            time.sleep(1)
            continue

        result = detect_color_blocks(photo_path, target_color)
        save_debug_image(photo_path, result, target_color)

        for color in SUPPORTED_COLORS:
            if color not in encountered_colors:
                res_c = detect_color_blocks(photo_path, color)
                if res_c["found"]:
                    encountered_colors.append(color)
                    print("[INFO] 新发现 {} 色方块 (累计第 {} 个: {})".format(
                        color, len(encountered_colors),
                        ", ".join(encountered_colors)))

        if not result["found"]:
            print("[INFO] 未检测到 {} 色方块，继续向左搜索...".format(target_color))
            YanAPI.sync_play_motion(
                name="walk", direction="left", speed="slow",
                repeat=SEARCH_WALK_REPEAT,
            )
            time.sleep(0.3)
            continue

        ever_found = True
        block = max(result["blocks"], key=lambda b: b["area"])
        cx = block["center_x"]
        cy = block["center_y"]
        area = block["area"]
        offset = cx - CENTER_X

        print("[INFO] 检测到 {} 色方块 中心=({}, {}) 面积={:.0f} 偏移={:+d}px".format(
            target_color, cx, cy, area, offset))

        if abs(offset) <= CENTER_TOLERANCE:
            block_index = _get_encounter_index(encountered_colors, target_color)
            print("[INFO] 方块已对准中心！")
            print("[INFO] 累计识别顺序: {}".format(" -> ".join(encountered_colors)))
            print("[RESULT] 物块编号: {}".format(block_index))
            print("[INFO] 开始执行 grasp 拾取...")
            YanAPI.sync_play_motion(name="grab2")
            print("[INFO] 拾取完成！")
            return block_index

        if offset < 0:
            print("[INFO] 方块偏左，向左调整 1 步...")
            YanAPI.sync_play_motion(
                name="walk", direction="left", speed="slow", repeat=1,
            )
        else:
            print("[INFO] 方块偏右，向右调整 1 步...")
            YanAPI.sync_play_motion(
                name="walk", direction="right", speed="slow", repeat=1,
            )

        time.sleep(0.3)

    block_index = _get_encounter_index(encountered_colors, target_color)
    print("\n" + "=" * 55)
    if not ever_found:
        print("[ERROR] 已达最大迭代次数 ({})，始终未找到 {} 色方块。".format(
            MAX_ITERATIONS, target_color))
    else:
        print("[ERROR] 已达最大迭代次数 ({})，无法将方块对准中心。".format(
            MAX_ITERATIONS))
    print("[INFO] 累计识别顺序: {}".format(" -> ".join(encountered_colors)))
    print("[RESULT] 物块编号: {}".format(block_index))
    print("=" * 55)
    return block_index


# ======================== Phase 2: Put (Vision) ========================
def do_put_vision(target_color):
    """视觉引导放置：向左搜索目标放置区域，对准后放置方块。"""
    print("\n" + "=" * 55)
    print("  [Phase 2] Put (Vision) — 目标颜色: {}".format(target_color))
    print("  预期识别顺序: 绿色 → 黄色 → 红色")
    print("  中心容差: ±{} 像素".format(PUT_CENTER_TOLERANCE))
    print("  最大迭代: {} 次".format(PUT_MAX_ITERATIONS))
    print("=" * 55)

    # 后退 3 步
    print("[INFO] 后退 {} 步...".format(INITIAL_BACKWARD_STEPS))
    for i in range(INITIAL_BACKWARD_STEPS):
        YanAPI.sync_play_motion(name="walk", direction="backward", speed="slow", repeat=1)
        print("[INFO] 后退第 {}/{} 步完成".format(i + 1, INITIAL_BACKWARD_STEPS))
    print("[INFO] 后退完成")

    encountered_colors = []
    expected_order = ["green", "yellow", "red"]
    red_navigated = False
    ever_found = False
    iteration = 0

    while iteration < PUT_MAX_ITERATIONS:
        iteration += 1
        print("\n--- [Put] 第 {} 次迭代 ---".format(iteration))

        # 1) 拍照
        photo_path = do_take_photo()
        if photo_path is None:
            print("[WARN] 拍照失败，1 秒后重试...")
            time.sleep(1)
            continue

        # 2) 检测所有颜色，更新 encounter 记录并校验顺序
        for color in expected_order:
            if color not in encountered_colors:
                res_c = detect_color_blocks_put(photo_path, color)
                if res_c["found"]:
                    encountered_colors.append(color)
                    expected_idx = expected_order.index(color)
                    actual_idx = len(encountered_colors) - 1
                    if expected_idx != actual_idx:
                        print("[ERROR] 颜色顺序异常！期望第 {} 个是 {}，实际第 {} 个是 {}".format(
                            actual_idx + 1, expected_order[actual_idx],
                            len(encountered_colors), color))
                    print("[INFO] [Put] 新发现 {} 色区域 (累计: {})".format(
                        color, " -> ".join(encountered_colors)))

        # 3) 红色特殊处理：依次识别到绿色和黄色后，先导航到黄色中心再左转 3 次
        if target_color == "red" and not red_navigated:
            if "green" in encountered_colors and "yellow" in encountered_colors:
                print("[INFO] 红色目标：已依次检测到绿色和黄色，导航至黄色中心...")
                result_yellow = detect_color_blocks_put(photo_path, "yellow")
                save_debug_image(photo_path, result_yellow, "yellow")

                if result_yellow["found"]:
                    block_y = max(result_yellow["blocks"], key=lambda b: b["area"])
                    offset_y = block_y["center_x"] - CENTER_X
                    print("[INFO] 检测到黄色 中心=({},{}) 偏移={:+d}px".format(
                        block_y["center_x"], block_y["center_y"], offset_y))

                    if abs(offset_y) <= PUT_CENTER_TOLERANCE:
                        print("[INFO] 已对准黄色中心，连续左转 3 次...")
                        YanAPI.sync_play_motion(name="turn around", direction="left", repeat=1)
                        print("[INFO] 左转 1/3 完成")
                        YanAPI.sync_play_motion(name="turn around", direction="left", repeat=1)
                        print("[INFO] 左转 2/3 完成")
                        YanAPI.sync_play_motion(name="turn around", direction="left", repeat=1)
                        print("[INFO] 左转 3/3 完成")
                        red_navigated = True
                        print("[INFO] 红色导航完成，接下来搜索红色区域...")
                        time.sleep(0.3)
                        continue
                    else:
                        if offset_y < 0:
                            print("[INFO] 黄色偏左，向左调整 1 步...")
                            YanAPI.sync_play_motion(
                                name="walk", direction="left", speed="slow", repeat=1)
                        else:
                            print("[INFO] 黄色偏右，向右调整 1 步...")
                            YanAPI.sync_play_motion(
                                name="walk", direction="right", speed="slow", repeat=1)
                        time.sleep(0.3)
                        continue
                else:
                    print("[INFO] 未检测到黄色，继续向左搜索...")
                    YanAPI.sync_play_motion(
                        name="walk", direction="left", speed="slow",
                        repeat=PUT_SEARCH_WALK_REPEAT)
                    print("[INFO] 向左搜索 {} 步完成".format(PUT_SEARCH_WALK_REPEAT))
                    time.sleep(0.3)
                    continue

        # 4) 检测目标颜色
        result = detect_color_blocks_put(photo_path, target_color)
        save_debug_image(photo_path, result, target_color)

        if not result["found"]:
            print("[INFO] 未检测到 {} 色区域，继续向左搜索...".format(target_color))
            YanAPI.sync_play_motion(
                name="walk", direction="left", speed="slow",
                repeat=PUT_SEARCH_WALK_REPEAT)
            print("[INFO] 向左搜索 {} 步完成".format(PUT_SEARCH_WALK_REPEAT))
            time.sleep(0.3)
            continue

        ever_found = True
        block = max(result["blocks"], key=lambda b: b["area"])
        cx = block["center_x"]
        cy = block["center_y"]
        area = block["area"]
        offset = cx - CENTER_X

        print("[INFO] 检测到 {} 色区域 中心=({}, {}) 面积={:.0f} 偏移={:+d}px".format(
            target_color, cx, cy, area, offset))

        # 5) 判断是否对准中心
        if abs(offset) <= PUT_CENTER_TOLERANCE:
            print("[INFO] 已对准 {} 色区域中心！".format(target_color))
            print("[INFO] 执行 place2 放置方块...")
            YanAPI.sync_play_motion(name="place2")
            print("[INFO] 放置完成！")
            return True

        # 6) 未对准 → 微调
        if offset < 0:
            print("[INFO] 目标偏左，向左调整 1 步...")
            YanAPI.sync_play_motion(
                name="walk", direction="left", speed="slow", repeat=1)
        else:
            print("[INFO] 目标偏右，向右调整 1 步...")
            YanAPI.sync_play_motion(
                name="walk", direction="right", speed="slow", repeat=1)

        time.sleep(0.3)

    # 超时
    print("\n" + "=" * 55)
    if not ever_found:
        print("[ERROR] 已达最大迭代次数 ({})，始终未找到 {} 色区域。".format(
            PUT_MAX_ITERATIONS, target_color))
    else:
        print("[ERROR] 已达最大迭代次数 ({})，无法将 {} 色区域对准中心。".format(
            PUT_MAX_ITERATIONS, target_color))
    print("=" * 55)
    return False


# ======================== 主流程 ========================
def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_put_vision.py <color>")
        print("支持颜色: {}".format(", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    target_color = sys.argv[1].strip().lower()
    if target_color not in SUPPORTED_COLORS:
        print("[ERROR] 不支持的颜色 '{}', 支持: {}".format(
            target_color, ", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    # Phase 1: 拾取
    block_index = do_fetch(target_color)

    if block_index == -1:
        print("[ERROR] Fetch 失败，终止放置。")
        return

    # Phase 2: 视觉引导放置
    do_put_vision(target_color)


if __name__ == "__main__":
    main()
