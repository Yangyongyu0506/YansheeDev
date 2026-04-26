"""
fetch_robust.py - 机器人识别并靠近目标颜色方块后执行 grab2

用法: python fetch_robust.py <color>
  color: red / yellow / green

流程:
  1. 拍照并检测目标颜色方块
  2. 先用水平偏移做左右对准
  3. 用目标面积判断前后距离并调整
  4. 在面积容差内执行 grab2
"""

import os
import sys
import time

import cv2

import YanAPI
import take_pic
from color_detect import (
    CONTOUR_THICKNESS,
    DOT_RADIUS,
    DRAW_COLORS,
    SUPPORTED_COLORS,
    detect_color_blocks,
    get_latest_photo,
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
MAX_ITERATIONS = 100
SEARCH_WALK_REPEAT = 2

# 目标面积（像素面积）和可接受容差
# 该值用于估计抓取距离，建议在实机上按场地和相机高度微调。
TARGET_AREA_BY_COLOR = {
    "red": 9000,
    "yellow": 9000,
    "green": 70000,
}
AREA_TOLERANCE_RATIO = 0.15  # ±15%
AREA_TOLERANCE_MIN = 1200


def do_take_photo():
    """调用 take_pic.main() 拍照存入 photos，再返回最新图片路径。"""
    take_pic.main()
    return get_latest_photo(PHOTOS_DIR)


def get_area_bounds(target_color):
    """返回目标面积上下界。"""
    target_area = TARGET_AREA_BY_COLOR[target_color]
    tol = max(int(target_area * AREA_TOLERANCE_RATIO), AREA_TOLERANCE_MIN)
    return target_area, tol, target_area - tol, target_area + tol


def save_debug_image(
    image_path, result, target_color, target_area, lower_bound, upper_bound
):
    """保存带检测信息的调试图片。"""
    os.makedirs(TEST_PHOTOS_DIR, exist_ok=True)

    img = cv2.imread(image_path)
    if img is None:
        return

    bgr = DRAW_COLORS.get(target_color, (255, 255, 255))
    for block in result["blocks"]:
        cx, cy = block["center_x"], block["center_y"]
        area = int(block["area"])
        cv2.drawContours(img, [block["contour"]], -1, bgr, CONTOUR_THICKNESS)
        cv2.circle(img, (cx, cy), DOT_RADIUS + 2, (255, 255, 255), 2)
        cv2.circle(img, (cx, cy), DOT_RADIUS, bgr, -1)
        label = "{} ({},{}) area={}".format(target_color, cx, cy, area)
        cv2.putText(
            img,
            label,
            (cx + DOT_RADIUS + 5, cy + 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 255),
            1,
        )

    cv2.line(img, (CENTER_X, 0), (CENTER_X, IMAGE_HEIGHT), (255, 255, 255), 1)
    cv2.putText(
        img,
        "target_area={} range=[{},{}]".format(target_area, lower_bound, upper_bound),
        (8, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1,
    )

    save_path = os.path.join(TEST_PHOTOS_DIR, os.path.basename(image_path))
    cv2.imwrite(save_path, img)
    print("[INFO] 调试图片已保存: {}".format(save_path))


def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_robust.py <color>")
        print("支持颜色: {}".format(", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    target_color = sys.argv[1].strip().lower()
    if target_color not in SUPPORTED_COLORS:
        print(
            "[ERROR] 不支持的颜色 '{}', 支持: {}".format(
                target_color, ", ".join(SUPPORTED_COLORS)
            )
        )
        sys.exit(1)

    target_area, area_tol, lower_bound, upper_bound = get_area_bounds(target_color)

    print("=" * 60)
    print("  目标颜色: {}".format(target_color))
    print("  中心容差: ±{} px".format(CENTER_TOLERANCE))
    print("  目标面积: {}".format(target_area))
    print(
        "  面积容差: ±{} (有效区间: {} ~ {})".format(area_tol, lower_bound, upper_bound)
    )
    print("  最大迭代: {}".format(MAX_ITERATIONS))
    print("=" * 60)

    os.makedirs(PHOTOS_DIR, exist_ok=True)
    YanAPI.yan_api_init(YanAPI.ip)

    print("[INFO] 复位姿态...")
    YanAPI.sync_play_motion("reset")

    ever_found = False

    for iteration in range(1, MAX_ITERATIONS + 1):
        print("\n--- 第 {} 次迭代 ---".format(iteration))

        photo_path = do_take_photo()
        if photo_path is None:
            print("[WARN] 拍照失败，1 秒后重试...")
            continue

        result = detect_color_blocks(photo_path, target_color)
        save_debug_image(
            photo_path, result, target_color, target_area, lower_bound, upper_bound
        )

        if not result["found"]:
            print("[INFO] 未检测到 {} 色方块，继续向左搜索...".format(target_color))
            YanAPI.sync_play_motion(
                name="walk",
                direction="left",
                speed="fast",
                repeat=SEARCH_WALK_REPEAT,
            )
            continue

        ever_found = True
        block = max(result["blocks"], key=lambda b: b["area"])
        cx = block["center_x"]
        cy = block["center_y"]
        area = int(block["area"])
        offset = cx - CENTER_X

        print(
            "[INFO] 检测到目标: center=({}, {}) area={} offset={:+d}px".format(
                cx, cy, area, offset
            )
        )

        if abs(offset) > CENTER_TOLERANCE:
            if offset < 0:
                print("[INFO] 已发现目标但偏左，向左移动 1 步对准...")
                YanAPI.sync_play_motion(
                    name="walk", direction="left", speed="fast", repeat=1
                )
            else:
                print("[INFO] 已发现目标但偏右，向右移动 1 步对准...")
                YanAPI.sync_play_motion(
                    name="walk", direction="right", speed="fast", repeat=1
                )
            continue

        if lower_bound <= area <= upper_bound:
            print("[INFO] 面积已进入目标容差，执行 grab2...")
            YanAPI.sync_play_motion(name="grab2")
            print("[INFO] 抓取完成。")
            return

        print(
            "[INFO] 目标已对准但面积 {} 未进入 [{} , {}]，向前靠近 1 步...".format(
                area, lower_bound, upper_bound
            )
        )
        YanAPI.sync_play_motion(
            name="walk", direction="forward", speed="fast", repeat=1
        )
        YanAPI.sync_play_motion("reset")
        continue

    print("\n" + "=" * 60)
    if not ever_found:
        print("[ERROR] 达到最大迭代次数，始终未找到 {} 色方块。".format(target_color))
    else:
        print("[ERROR] 达到最大迭代次数，未能调整到可抓取面积区间。")
    print("=" * 60)


if __name__ == "__main__":
    main()
