color_detect.py 总览

  共 4 个函数

  ---
  1. get_latest_photo(photos_dir) — 找最新照片

  - 输入：photos_dir (str) — 图片文件夹路径
  - 返回：str — 文件名数值最大的图片完整路径；无图片则返回 None

  ---
  2. detect_color_blocks(image_path, target_color, min_area=500) — 核心检测函数

  - 输入：
    - image_path (str) — 图片路径
    - target_color (str) — "red" / "yellow" / "green"
    - min_area (int) — 最小轮廓面积，默认 500
  - 返回：dict
  {
      "found": bool,           # 是否找到
      "count": int,            # 方块数量
      "blocks": [              # 每个方块信息
          {
              "center_x": int, # 中心 X
              "center_y": int, # 中心 Y
              "area": float,   # 轮廓面积
              "bbox": (x, y, w, h),  # 外接矩形
              "contour": np.ndarray, # 轮廓点集（用于绘图）
          },
      ],
      "image_path": str,
      "image_size": (宽, 高),
  }

  ---
  3. print_result(result, target_color) — 格式化打印

  - 输入：result (dict，detect_color_blocks 的返回值) + target_color (str)
  - 返回：无（直接 print）

  ---
  4. run_visual_test(photos_dir, output_dir) — 可视化批量测试

  - 输入：photos_dir (str) + output_dir (str)
  - 返回：无（生成标注图片保存到 output_dir）

  ---
  在其他文件中调用

  # 假设你的脚本在 scripts/ 目录下
  from color_detect import get_latest_photo, detect_color_blocks

  # 用法1：找最新照片，检测红色
  photo = get_latest_photo("../photos")
  result = detect_color_blocks(photo, "red")

  if result["found"]:
      for block in result["blocks"]:
          print("红色方块中心: ({}, {})".format(block["center_x"], block["center_y"]))
  else:
      print("没有找到红色方块")

  # 用法2：检测指定图片的绿色
  result = detect_color_blocks("/path/to/photo.jpg", "green")
  print("找到 {} 个绿色方块".format(result["count"]))

  # 用法3：检测黄色并获取坐标
  result = detect_color_blocks(photo, "yellow")
  if result["count"] > 0:
      x = result["blocks"][0]["center_x"]
      y = result["blocks"][0]["center_y"]