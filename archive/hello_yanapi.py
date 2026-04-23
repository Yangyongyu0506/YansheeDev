#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
hello_yanapi.py
- 验证 SFTP 同步：修改 VERSION 字符串并保存，机器人端再次运行应立刻生效
- 控制机器人做一个简单动作：reset(站立) -> walk(前进1步) -> reset
注意：将机器人放在平整地面，周围留出空间，随时准备按急停/断电。
"""

import time
import YanAPI

VERSION = "SYNC_OK v2"  # 修改为 v3/v4 后保存验证同步

def main():
    print("VERSION:", VERSION)
    print("YanAPI loaded from:", YanAPI.__file__)

    # 若在 PC 端远程控制机器人，取消注释并填入机器人 IP
    # YanAPI.yan_api_init("192.168.100.100")

    # 语音提示（可选）
    try:
        YanAPI.start_voice_tts("YanAPI test start", False)
    except Exception as e:
        print("[WARN] start_voice_tts failed:", e)

    # 动作序列：reset -> walk -> reset
    try:
        YanAPI.sync_play_motion(name="reset")
        time.sleep(1.0)
        YanAPI.sync_play_motion(name="walk", direction="forward", speed="slow", repeat=1)
        time.sleep(0.5)
        YanAPI.sync_play_motion(name="reset")
    except Exception as e:
        print("[WARN] sync_play_motion failed:", e)
        # 兼容部分版本：walk 用 start_play_motion，再用 reset 打断
        try:
            YanAPI.start_play_motion(name="walk", direction="forward", speed="slow", repeat=1)
            time.sleep(3.0)
            YanAPI.sync_play_motion(name="reset")
        except Exception as e2:
            print("[ERROR] start_play_motion fallback failed:", e2)

    print("DONE.")

if __name__ == "__main__":
    main()