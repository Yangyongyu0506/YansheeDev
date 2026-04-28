"""
maze_with_sensor.py - 利用左腿侧面红外传感器自动走迷宫

用法:
  python3 maze_with_sensor.py

策略:
  6个阶段，交替使用两种判断逻辑:
  - 逻辑A(前/后): 每步读传感器，距离突变增大超过 DELTA 后再走 EXTRA_STEPS 步停止
  - 逻辑B(左):   每步读传感器，距离小于 MIN_DISTANCE 停止
"""

import YanAPI

# ==================== 阈值参数 ====================
DELTA = 300            # 距离突变阈值，单位毫米 (30cm)
EXTRA_STEPS = 3        # 检测到突变后再走的步数
MIN_DISTANCE = 100     # 靠近墙壁停止阈值，单位毫米 (10cm)
WALK_SPEED = "fast"    # 行走速度
# ================================================


def read_infrared():
    """读取红外传感器距离值，返回毫米"""
    val = YanAPI.get_sensors_infrared_value()
    if isinstance(val, str):
        print("[ERROR] 传感器读取失败: {}".format(val))
        return None
    return val


def walk_one_step(direction):
    """朝指定方向走一步"""
    YanAPI.sync_play_motion(name="walk", direction=direction, speed=WALK_SPEED, repeat=1)


def phase_detect_delta_then_extra(direction, label):
    """逻辑A: 向指定方向走，每步读传感器，距离突变增大超过DELTA后再走EXTRA_STEPS步停止"""
    print("[INFO] ===== 阶段开始: 向{}走，检测距离突变 =====".format(label))
    prev = read_infrared()
    if prev is None:
        return False
    print("[INFO] 初始传感器距离: {} mm".format(prev))

    total = 0
    delta_triggered = False

    while True:
        walk_one_step(direction)
        total += 1
        curr = read_infrared()
        if curr is None:
            return False
        print("[INFO] 向{}走第 {} 步，传感器距离: {} mm".format(label, total, curr))

        if not delta_triggered and (curr - prev) > DELTA:
            delta_triggered = True
            print("[INFO] 检测到距离突变 ({} -> {}，增量 {} mm > DELTA {} mm)".format(
                prev, curr, curr - prev, DELTA))
            print("[INFO] 再走 {} 步后停止...".format(EXTRA_STEPS))
            for i in range(EXTRA_STEPS):
                walk_one_step(direction)
                total += 1
                v = read_infrared()
                if v is not None:
                    print("[INFO] 向{}走第 {} 步，传感器距离: {} mm".format(label, total, v))
            break

        prev = curr

    print("[INFO] ===== 阶段结束: 向{}走共 {} 步 =====".format(label, total))
    return True


def phase_walk_until_min_distance(direction, label):
    """逻辑B: 向指定方向走，每步读传感器，距离小于MIN_DISTANCE时停止"""
    print("[INFO] ===== 阶段开始: 向{}走，检测距离 < {} mm =====".format(label, MIN_DISTANCE))
    total = 0

    while True:
        walk_one_step(direction)
        total += 1
        curr = read_infrared()
        if curr is None:
            return False
        print("[INFO] 向{}走第 {} 步，传感器距离: {} mm".format(label, total, curr))

        if curr < MIN_DISTANCE:
            print("[INFO] 距离 {} mm < MIN_DISTANCE {} mm，停止".format(curr, MIN_DISTANCE))
            break

    print("[INFO] ===== 阶段结束: 向{}走共 {} 步 =====".format(label, total))
    return True


def main():
    YanAPI.yan_api_init(YanAPI.ip)
    print("[INFO] 迷宫传感器模式启动，速度: {}".format(WALK_SPEED))
    print("[INFO] 参数: DELTA={}mm, EXTRA_STEPS={}, MIN_DISTANCE={}mm".format(
        DELTA, EXTRA_STEPS, MIN_DISTANCE))

    # 阶段1: 向前走，检测距离突变
    if not phase_detect_delta_then_extra("forward", "前"):
        return

    # 阶段2: 向左走，检测靠近墙壁
    if not phase_walk_until_min_distance("left", "左"):
        return

    # 阶段3: 向后走，检测距离突变
    if not phase_detect_delta_then_extra("backward", "后"):
        return

    # 阶段4: 向左走，检测靠近墙壁
    if not phase_walk_until_min_distance("left", "左"):
        return

    # 阶段5: 向前走，检测距离突变
    if not phase_detect_delta_then_extra("forward", "前"):
        return

    # 阶段6: 向左走，检测靠近墙壁
    if not phase_walk_until_min_distance("left", "左"):
        return

    print("[INFO] 迷宫完成！")


if __name__ == "__main__":
    main()
