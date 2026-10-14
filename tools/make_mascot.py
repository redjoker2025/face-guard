# -*- coding: utf-8 -*-
"""从立绘截图里抠出鲸鱼娘素材（一次性工具，重新抠图时手动跑）。

用法：
    python tools/make_mascot.py

输入：artwork/whale_girl_source.png   （原始立绘截图，白底卡片）
输出：assets/whale_girl.png           半身像（透明底）
      assets/whale_girl_head.png      头部方形特写（透明底，小尺寸图标用）
      .scratch/*.png                  验证图：贴到深蓝底/洋红底上看有没有脏边

算法（为什么这么抠）：
  1. 截图是"圆角描边卡片"，边框线会把卡片内外的背景隔断，所以先裁掉上/左/右边框；
  2. 从四边所有浅色低饱和像素出发做【浮动容差】洪水填充 —— 浮动容差是跟"邻居像素"比，
     所以能顺着白→淡紫的渐变蔓延，却会被蕾丝的深灰描边挡住（蕾丝因此不会被吃掉）；
  3. 最外几圈残留的浅灰边框线判成背景；只保留最大连通域；闭运算补掉蕾丝小镂空；
  4. 去白边：半透明边缘像素是按白底混出来的，按 fg=(obs-(1-a)*白)/a 反解，
     否则贴到深蓝界面上会有一圈白边。
"""
import os
import sys
import numpy as np
import cv2
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "artwork", "whale_girl_source.png")
OUT_DIR = os.path.join(ROOT, "assets")
SCRATCH = os.path.join(ROOT, ".scratch")

TOL = 6                  # 洪水填充容差：太小会漏掉细碎背景，太大会啃进蕾丝
CROP = (11, 11, 159, 241)   # 卡片内部：切掉上/左/右边框线（底边不动，角色本来就裁到边）
HEAD_TOP = 12            # 头部方形特写从第几行开始裁


def imread_unicode(path):
    """cv2.imread 在 Windows 上不认中文/非 ASCII 路径，用字节流解码绕过。"""
    with open(path, "rb") as f:
        return cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)


def background_mask(img, tol):
    """从四边做浮动容差洪水填充，返回 True=背景 的布尔图。"""
    h, w = img.shape[:2]
    filled = np.zeros((h + 2, w + 2), np.uint8)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    val, sat = hsv[:, :, 2].astype(int), hsv[:, :, 1].astype(int)
    like_bg = (val > 190) & (sat < 60)          # 只有"像背景"的边界像素才当种子
    flags = 4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8)
    for x in range(0, w, 3):
        for y in (0, 1, h - 2, h - 1):
            if like_bg[y, x]:
                cv2.floodFill(img, filled, (x, y), 0, (tol,) * 3, (tol,) * 3, flags)
    for y in range(0, h, 3):
        for x in (0, 1, w - 2, w - 1):
            if like_bg[y, x]:
                cv2.floodFill(img, filled, (x, y), 0, (tol,) * 3, (tol,) * 3, flags)
    return filled[1:-1, 1:-1] > 0


def dewhite(rgb, alpha):
    """反解白底混合，去掉半透明边缘上的白边。"""
    a = (alpha.astype(np.float32) / 255.0)[..., None]
    out = np.where(a > 0.02, (rgb.astype(np.float32) - (1.0 - a) * 255.0) / np.maximum(a, 0.02), rgb)
    return np.clip(out, 0, 255).astype(np.uint8)


def build():
    src = imread_unicode(SRC)
    if src is None:
        sys.exit("读不到素材原图：%s" % SRC)
    x0, y0, x1, y1 = CROP
    img = src[y0:y1, x0:x1]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    val, sat = hsv[:, :, 2].astype(int), hsv[:, :, 1].astype(int)

    alpha = np.where(background_mask(img, TOL), 0, 255).astype(np.uint8)
    # 边框残渣：裁剪切不到的灰线是"浅色+低饱和"的细线，角色头发是深蓝高饱和，
    # 所以最外 5 圈里凡是浅灰低饱和的像素一律判成背景，不会误伤头发。
    h, w = alpha.shape
    ring = np.zeros((h, w), bool)
    ring[:5, :] = ring[-5:, :] = ring[:, :5] = ring[:, -5:] = True
    alpha[ring & (val > 170) & (sat < 60)] = 0
    # 只保留最大连通域（边框残渣、背景噪点全丢掉）
    n, lab, stats, _ = cv2.connectedComponentsWithStats((alpha > 0).astype(np.uint8), 8)
    if n > 1:
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        alpha = np.where(lab == biggest, 255, 0).astype(np.uint8)
    # 闭运算补小孔洞，再腐蚀半像素 + 高斯羽化，得到柔和的抗锯齿边
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    alpha = cv2.erode(alpha, np.ones((2, 2), np.uint8), iterations=1)
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0.7)

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    im = Image.fromarray(np.dstack([dewhite(rgb, alpha), alpha]), "RGBA")
    return im.crop(im.getbbox())


def previews(full, head):
    """验证图：洋红底看脏边最灵敏，深蓝底是程序实际背景。"""
    os.makedirs(SCRATCH, exist_ok=True)
    for tag, bg in (("magenta", (255, 0, 255)), ("dark", (11, 61, 107))):
        canvas = Image.new("RGB", (full.width + 40, full.height + 40), bg)
        canvas.paste(full, (20, 20), full)
        canvas.resize((canvas.width * 2, canvas.height * 2), Image.LANCZOS).save(
            os.path.join(SCRATCH, "mascot_check_%s.png" % tag))
    hz = Image.new("RGB", (head.width + 20, head.height + 20), (255, 0, 255))
    hz.paste(head, (10, 10), head)
    hz.resize((hz.width * 2, hz.height * 2), Image.LANCZOS).save(
        os.path.join(SCRATCH, "mascot_check_head.png"))
    print("验证图已输出到 %s\\mascot_check_*.png" % SCRATCH)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    full = build()
    full.save(os.path.join(OUT_DIR, "whale_girl.png"))
    side = min(full.width, full.height)
    head = full.crop((0, HEAD_TOP, side, HEAD_TOP + side))
    head.save(os.path.join(OUT_DIR, "whale_girl_head.png"))
    print("半身像 %s  头部特写 %s" % (full.size, head.size))
    previews(full, head)


if __name__ == "__main__":
    main()
