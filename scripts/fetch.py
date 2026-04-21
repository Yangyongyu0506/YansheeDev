"""
fetch.py — 机器人识别并拾取指定颜色方块

用法: python fetch.py <color>
  color: red / yellow / green

流程:
  1. 机器人持续向左走，边走边拍照检测目标颜色方块
  2. 找到目标后，根据方块在画面中的水平位置调整左右移动
  3. 方块对准画面正中后，执行 fetch 动作拾取
"""

import sys
import os
import time
import cv2
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
CENTER_X = IMAGE_WIDTH // 2          # 320
CENTER_TOLERANCE = 40                 # 像素，距离中心多少算对准
SEARCH_WALK_REPEAT = 2                # 搜索阶段每轮向左走的步数
MAX_ITERATIONS = 40                   # 最大循环次数，防止死循环


# ======================== 拍照 ========================
def do_take_photo():
    """调用 take_pic.main() 拍照存入 photos，再用 get_latest_photo 获取路径。"""
    take_pic.main()
    return get_latest_photo(PHOTOS_DIR)


# ======================== 保存调试可视化 ========================
def save_debug_image(image_path, result, target_color):
    """将检测结果（轮廓 + 中心点 + 中心线）标注到图片上，保存到 test_photos。"""
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

    # 画中心参考线
    cv2.line(img, (CENTER_X, 0), (CENTER_X, IMAGE_HEIGHT), (255, 255, 255), 1)

    fname = os.path.basename(image_path)
    save_path = os.path.join(TEST_PHOTOS_DIR, fname)
    cv2.imwrite(save_path, img)
    print("[INFO] 调试图片已保存: {}".format(save_path))


# ======================== 主流程 ========================
def main():
    # ---------- 参数校验 ----------
    if len(sys.argv) < 2:
        print("用法: python fetch.py <color>")
        print("支持颜色: {}".format(", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    target_color = sys.argv[1].strip().lower()
    if target_color not in SUPPORTED_COLORS:
        print("[ERROR] 不支持的颜色 '{}', 支持: {}".format(
            target_color, ", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    print("=" * 55)
    print("  目标颜色: {}".format(target_color))
    print("  中心容差: ±{} 像素".format(CENTER_TOLERANCE))
    print("  最大迭代: {} 次".format(MAX_ITERATIONS))
    print("=" * 55)

    # ---------- 初始化 ----------
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    YanAPI.yan_api_init(YanAPI.ip)
    print("[INFO] 复位姿态...")
    YanAPI.sync_play_motion("reset")
    time.sleep(0.5)

    # ---------- 搜索 + 对准循环 ----------
    ever_found = False
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1
        print("\n--- 第 {} 次迭代 ---".format(iteration))

        # 1) 拍照
        photo_path = do_take_photo()
        if photo_path is None:
            print("[WARN] 拍照失败，1 秒后重试...")
            time.sleep(1)
            continue

        # 2) 颜色检测
        result = detect_color_blocks(photo_path, target_color)
        save_debug_image(photo_path, result, target_color)

        # 3) 未找到 → 继续向左搜索
        if not result["found"]:
            print("[INFO] 未检测到 {} 色方块，继续向左搜索...".format(target_color))
            YanAPI.sync_play_motion(
                name="walk", direction="left", speed="slow",
                repeat=SEARCH_WALK_REPEAT,
            )
            time.sleep(0.3)
            continue

        # 4) 找到目标，取面积最大的块
        ever_found = True
        block = max(result["blocks"], key=lambda b: b["area"])
        cx = block["center_x"]
        cy = block["center_y"]
        area = block["area"]
        offset = cx - CENTER_X

        print("[INFO] 检测到 {} 色方块 中心=({}, {}) 面积={:.0f} 偏移={:+d}px".format(
            target_color, cx, cy, area, offset))

        # 5) 判断是否已对准中心
        if abs(offset) <= CENTER_TOLERANCE:
            print("[INFO] 方块已对准中心！开始执行 fetch 拾取...")
            YanAPI.sync_play_motion(name="grab2")
            print("[INFO] 拾取完成！")
            return

        # 6) 未对准 → 根据偏移方向调整
        if offset < 0:
            # 方块在画面左侧 → 机器人向左走，让方块向画面中心靠拢
            print("[INFO] 方块偏左，向左调整 1 步...")
            YanAPI.sync_play_motion(
                name="walk", direction="left", speed="slow", repeat=1,
            )
        else:
            # 方块在画面右侧 → 机器人向右走
            print("[INFO] 方块偏右，向右调整 1 步...")
            YanAPI.sync_play_motion(
                name="walk", direction="right", speed="slow", repeat=1,
            )

        time.sleep(0.3)

    # ---------- 超时退出 ----------
    print("\n" + "=" * 55)
    if not ever_found:
        print("[ERROR] 已达最大迭代次数 ({})，始终未找到 {} 色方块。".format(
            MAX_ITERATIONS, target_color))
    else:
        print("[ERROR] 已达最大迭代次数 ({})，无法将方块对准中心。".format(
            MAX_ITERATIONS))
    print("=" * 55)


if __name__ == "__main__":
    main()
