"""
test.py — 用 fetch_put_vision.py 的 put 视觉检测算法测试 photos 中的图片
检测结果带轮廓+中心点，保存到 test_photos
"""

import os
import cv2
import numpy as np

# ======================== 路径配置 ========================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
PHOTOS_DIR = os.path.join(PROJECT_DIR, "photos")
TEST_PHOTOS_DIR = os.path.join(PROJECT_DIR, "test_photos")

# ======================== 与 fetch_put_vision.py 的 put 检测完全一致的参数 ========================
PUT_COLOR_RANGES = {
    "red": [
        (np.array([0, 60, 80]),     np.array([12, 255, 255])),
        (np.array([165, 60, 80]),   np.array([180, 255, 255])),
    ],
    "yellow": [
        (np.array([25, 80, 150]),   np.array([45, 255, 255])),
    ],
    "green": [
        (np.array([35, 100, 100]),  np.array([85, 255, 255])),
    ],
}

PUT_MIN_CONTOUR_AREA = 2000
PUT_MORPH_KERNEL = (3, 3)
PUT_ERODE_ITERATIONS = 1
PUT_DILATE_ITERATIONS = 2
PUT_BLUR_KERNEL = (5, 5)

IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
CENTER_X = IMAGE_WIDTH // 2

DRAW_COLORS = {
    "red":    (0, 0, 255),
    "yellow": (0, 255, 255),
    "green":  (0, 200, 0),
}
DOT_RADIUS = 6
CONTOUR_THICKNESS = 2

SUPPORTED_COLORS = ["red", "yellow", "green"]


def detect_color_blocks_put(image_path, target_color):
    """
    与 fetch_put_vision.py 的 detect_color_blocks_put 完全一致。
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


def run_test():
    if not os.path.exists(TEST_PHOTOS_DIR):
        os.makedirs(TEST_PHOTOS_DIR)

    # 获取 photos 中的所有图片，按文件名排序
    image_files = sorted([
        f for f in os.listdir(PHOTOS_DIR)
        if f.lower().endswith((".jpg", ".png", ".jpeg", ".bmp"))
    ])

    if not image_files:
        print("[ERROR] photos 目录中没有图片")
        return

    print("=" * 60)
    print("  Put 视觉检测测试 — 共 {} 张图片".format(len(image_files)))
    print("  检测颜色: {}".format(", ".join(SUPPORTED_COLORS)))
    print("  无 Y 坐标过滤")
    print("=" * 60)

    for fname in image_files:
        fpath = os.path.join(PHOTOS_DIR, fname)
        print("\n--- {} ---".format(fname))

        img = cv2.imread(fpath)
        if img is None:
            print("[ERROR] 无法读取: {}".format(fname))
            continue

        all_detections = []

        for color in SUPPORTED_COLORS:
            result = detect_color_blocks_put(fpath, color)
            bgr = DRAW_COLORS[color]

            for block in result["blocks"]:
                cx, cy = block["center_x"], block["center_y"]
                # 轮廓
                cv2.drawContours(img, [block["contour"]], -1, bgr, CONTOUR_THICKNESS)
                # 中心点：白色外圈 + 颜色实心圆
                cv2.circle(img, (cx, cy), DOT_RADIUS + 2, (255, 255, 255), 2)
                cv2.circle(img, (cx, cy), DOT_RADIUS, bgr, -1)
                # 坐标标签
                label = "{} ({},{})".format(color, cx, cy)
                cv2.putText(img, label, (cx + DOT_RADIUS + 5, cy + 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                all_detections.append((color, cx, cy, block["area"]))

            status = "found {} block(s)".format(result["count"]) if result["found"] else "not found"
            print("  {}: {}".format(color, status))
            for i, block in enumerate(result["blocks"]):
                print("    #{}: center({}, {}) area={:.0f}".format(
                    i + 1, block["center_x"], block["center_y"], block["area"]))

        # 画中心参考线
        cv2.line(img, (CENTER_X, 0), (CENTER_X, IMAGE_HEIGHT), (255, 255, 255), 1)

        # 保存
        save_path = os.path.join(TEST_PHOTOS_DIR, fname)
        cv2.imwrite(save_path, img)
        summary = ", ".join("{}({},{})".format(c, x, y) for c, x, y, _ in all_detections)
        print("  => 保存到: {} | 检测结果: {}".format(
            save_path, summary if summary else "(none)"))

    print("\n" + "=" * 60)
    print("  测试完成，结果保存在: {}".format(TEST_PHOTOS_DIR))
    print("=" * 60)


if __name__ == "__main__":
    run_test()
