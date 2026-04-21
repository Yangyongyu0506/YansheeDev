"""
fetch-copy.py — 机器人识别并拾取指定颜色方块（带物块编号追踪）

用法: python fetch-copy.py <color>
  color: red / yellow / green

流程:
  1. 机器人持续向左走，边走边拍照检测目标颜色方块
  2. 找到目标后，根据方块在画面中的水平位置调整左右移动
  3. 方块对准画面正中后，执行 fetch 动作拾取

额外功能:
  - 追踪持续识别到的物块是第几个（从左到右 1/2/3），最终输出编号
  - 返回值: main() 返回 (block_index, target_color)
    block_index: 1/2/3 表示第几个物块，-1 表示出错
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

# 物块编号追踪：连续确认次数阈值，达到后才认为稳定
TRACK_CONFIRM_THRESHOLD = 3


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


def determine_block_index(photo_path, target_color):
    """
    检测所有三种颜色的方块，根据水平位置从左到右排序，
    返回目标颜色方块是第几个（1, 2, 3），-1 表示判断失败。
    """
    positions = []  # [(color, center_x), ...]
    for color in SUPPORTED_COLORS:
        res = detect_color_blocks(photo_path, color)
        if res["found"]:
            # 取面积最大的块
            best = max(res["blocks"], key=lambda b: b["area"])
            positions.append((color, best["center_x"]))

    if not positions:
        return -1

    # 按 center_x 从小到大排序（左到右）
    positions.sort(key=lambda x: x[1])

    print("[INFO] 检测到方块从左到右: {}".format(
        " < ".join("{}({})".format(c, x) for c, x in positions)))

    for idx, (color, _) in enumerate(positions):
        if color == target_color:
            return idx + 1  # 1-indexed

    return -1


# ======================== 主流程 ========================
def main():
    # ---------- 参数校验 ----------
    if len(sys.argv) < 2:
        print("用法: python fetch-copy.py <color>")
        print("支持颜色: {}".format(", ".join(SUPPORTED_COLORS)))
        return -1, ""

    target_color = sys.argv[1].strip().lower()
    if target_color not in SUPPORTED_COLORS:
        print("[ERROR] 不支持的颜色 '{}', 支持: {}".format(
            target_color, ", ".join(SUPPORTED_COLORS)))
        return -1, target_color

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

    # ---------- 物块编号追踪 ----------
    # 记录每次检测到的编号，用于投票确认
    index_history = []
    confirmed_index = -1

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

        # 3) 尝试判断物块编号（无论是否找到目标颜色都检测全部颜色）
        idx = determine_block_index(photo_path, target_color)
        if idx > 0:
            index_history.append(idx)
            print("[INFO] 本次判断物块编号: {}".format(idx))
        else:
            print("[INFO] 本次无法判断物块编号")

        # 4) 未找到目标 → 继续向左搜索
        if not result["found"]:
            print("[INFO] 未检测到 {} 色方块，继续向左搜索...".format(target_color))
            YanAPI.sync_play_motion(
                name="walk", direction="left", speed="slow",
                repeat=SEARCH_WALK_REPEAT,
            )
            time.sleep(0.3)
            continue

        # 5) 找到目标，取面积最大的块
        ever_found = True
        block = max(result["blocks"], key=lambda b: b["area"])
        cx = block["center_x"]
        cy = block["center_y"]
        area = block["area"]
        offset = cx - CENTER_X

        print("[INFO] 检测到 {} 色方块 中心=({}, {}) 面积={:.0f} 偏移={:+d}px".format(
            target_color, cx, cy, area, offset))

        # 6) 判断是否已对准中心
        if abs(offset) <= CENTER_TOLERANCE:
            # 投票确定最终物块编号
            confirmed_index = _vote_index(index_history)
            print("[INFO] 方块已对准中心！")
            print("[RESULT] 物块编号: {}".format(confirmed_index))
            print("[INFO] 开始执行 fetch 拾取...")
            YanAPI.sync_play_motion(name="grasp")
            print("[INFO] 拾取完成！")
            return confirmed_index, target_color

        # 7) 未对准 → 根据偏移方向调整
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

    # ---------- 超时退出 ----------
    confirmed_index = _vote_index(index_history) if index_history else -1
    print("\n" + "=" * 55)
    if not ever_found:
        print("[ERROR] 已达最大迭代次数 ({})，始终未找到 {} 色方块。".format(
            MAX_ITERATIONS, target_color))
    else:
        print("[ERROR] 已达最大迭代次数 ({})，无法将方块对准中心。".format(
            MAX_ITERATIONS))
    print("[RESULT] 物块编号: {}".format(confirmed_index))
    print("=" * 55)
    return confirmed_index, target_color


def _vote_index(index_history):
    """
    对历史编号记录进行投票，返回出现次数最多的编号。
    多数相同时取最近一次。
    """
    if not index_history:
        return -1

    from collections import Counter
    counter = Counter(index_history)
    max_count = max(counter.values())
    # 在出现 max_count 的编号中，取最近一次出现的
    for idx in reversed(index_history):
        if counter[idx] == max_count:
            return idx
    return -1


if __name__ == "__main__":
    block_index, color = main()
    print("\n========== 返回值 ==========")
    print("block_index = {}".format(block_index))
    print("target_color = {}".format(color))
