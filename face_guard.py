# -*- coding: utf-8 -*-
"""
================================================================================
 FaceGuard 酱 · 鲸鱼娘 —— 二次元风护眼距离提醒小工具（单文件版 v2.2）
================================================================================
 【功能一句话】
   读取本机摄像头 → 本地人脸检测（OpenCV Haar 级联）→ 实时跟踪"人脸占画面比例"。
   当人脸持续变大（= 头不断向屏幕凑近）超过设定阈值、且连续多帧确认后，触发提醒：
   鲸鱼娘二次元弹窗 + 可选屏幕右上角悬浮字幕 + 可选提示音。冷却时间内不会重复报警。

 【v2.0 蓝鲸版新增】
   * 主题换肤：整个软件背景改成深海蓝渐变（海面蓝 → 深海黑蓝），所有控件
     （面板 / 滑块 / 按钮 / 进度条 / 滚轮 / 弹窗）统一蓝调，彻底告别原来的粉色；
   * 悬浮球：主窗口最小化后自动出现在桌面右下角，球体颜色随"距离水平"由蓝渐变到红
     （蓝 = 离得远，红 = 贴脸），并支持拖动、悬停看数值、双击回主窗口、右键菜单。

 【v2.1 立绘版新增】
   * 鲸鱼娘立绘：改用抠好图的蓝发鲸鱼娘 PNG（assets/whale_girl.png 半身 +
     assets/whale_girl_head.png 头部特写），替换原来纯 Canvas 画的鲸鱼娘；
     抠图脚本用 OpenCV 洪水填充去背景 + 去白边羽化，见 README「立绘素材」一节；
   * 悬浮球改成"圆形头像 + 距离色光环"：头像由立绘裁圆，光环颜色仍按
     蓝→红表示远近，并叠一层同色薄雾，颜色信号一眼可辨；
   * 立绘缺失/损坏时，界面自动退回原来的 Canvas 矢量鲸鱼娘，不会开天窗。

 【隐私承诺（硬性要求）】
   * 全程离线：代码中没有任何网络请求，运行时绝不联网下载模型/上传数据；
   * 人脸模型 haarcascade_frontalface_default.xml 随程序打包内置（见 build.bat）；
   * 摄像头画面只在本机内存中实时处理，不写文件、不上传任何服务器，关闭即消失。

 【技术选型（为什么这样选）】
   * GUI      : Tkinter —— Python 标准库，零额外依赖，PyInstaller 打包体积最小；
   * 人脸检测 : OpenCV 自带 Haar 级联 —— 比 MTCNN 轻量几个数量级（模型 <1MB），
                CPU 单线程即可 30FPS 实时，且 XML 直接内置在 opencv 包里可随包打包；
   * 显示辅助 : Pillow —— 把 OpenCV 帧高效刷到 Tkinter 画布，并负责立绘缩放、
                圆形头像蒙版与颜色薄雾；
   * 美术素材 : 鲸鱼娘立绘是从截图抠出来的透明 PNG（打包进 EXE）；
                未提供立绘时退回 Canvas 图元现画，零素材也能跑。

 【运行】   python face_guard.py
 【打包】   双击 build.bat（或 python -m PyInstaller --noconfirm --clean FaceGuard.spec）
================================================================================
"""

import os
import sys
import time
import colorsys
import queue
import random
import platform
import threading
import traceback

# ---------------- 第三方依赖（pip install opencv-python-headless pillow） ----------------
import cv2
import numpy as np                 # OpenCV 依赖，显式引入便于阅读
from PIL import Image, ImageTk, ImageChops, ImageDraw   # 界面显示 / 立绘缩放与圆形蒙版

IS_WINDOWS = (platform.system() == "Windows")

# Windows 下开启 DPI 感知，高分屏上界面文字不模糊（失败也不影响运行）
if IS_WINDOWS:
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try:
        import winsound            # Windows 自带，用于提示音，非 Windows 自动跳过
    except ImportError:
        winsound = None

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox

# ================================ 常量与文案 ================================

APP_NAME = "FaceGuard 酱 · 鲸鱼娘"
APP_VERSION = "v2.2"

# 内置人脸检测模型文件名（打包时用 --add-data 塞进 EXE，见 build.bat）
CASCADE_FILENAME = "haarcascade_frontalface_default.xml"

# ---------------- 鲸鱼娘立绘素材（从截图抠图得到，打包时 --add-data "assets;assets"） ----------------
ASSET_DIRNAME = "assets"
MASCOT_FULL   = "whale_girl.png"        # 半身立绘：待机画面等大尺寸场合
MASCOT_HEAD   = "whale_girl_head.png"   # 头部方形特写：图标/悬浮字幕/悬浮球等小尺寸场合

# ---------------- 蓝鲸主题配色（整个软件的背景/控件都从这里取色） ----------------
BG_DEEP    = "#04121f"   # 窗口最底色 / 渐变末端（深海）
GRAD_TOP   = "#0b3d6b"   # 背景渐变顶部（海面蓝）
GRAD_BOT   = "#04121f"   # 背景渐变底部（深海）
PANEL      = "#0a2647"   # 卡片 / 面板底色
PANEL_2    = "#0d3157"   # 次级面板 / 输入框底色
LINE       = "#1b4f7f"   # 描边
TXT        = "#dceeff"   # 主文字
TXT_DIM    = "#7fa8cc"   # 次要文字
ACCENT     = "#2b8fe0"   # 主强调色（鲸蓝）
ACCENT_DK  = "#1c7fd6"   # 强调色按下态
ACCENT_LT  = "#8fdcff"   # 强调色亮部（标题/数值）
OK_C       = "#4fd6a0"   # 距离正常
WARN_C     = "#ffc93c"   # 偏近 / 冷却
ALERT_C    = "#ff5a5a"   # 报警

WHALE_BLUE = "#2f8fff"   # 鲸鱼娘身体主色
WHALE_DEEP = "#1d6fd0"   # 兜帽深色
SKIN       = "#ffe3cc"   # 脸
BLUSH      = "#ff9db1"   # 腮红

KEY_COLOR  = "#0b0c0d"   # 透明色键：让圆角悬浮窗/悬浮球四角透出桌面（仅 Windows 有效）

# 弹窗文案：(大字颜文字, 正文)。每次报警随机抽一条，避免视觉疲劳
POPUP_TEXTS = [
    ("(っ˘ω˘ς) 脸都要贴到我尾巴上啦！",
     "鲸鱼娘提醒：你和屏幕的距离已经太近啦～\n"
     "建议保持 50~70cm，退后一点点，眼睛会谢谢你的！"),
    ("(๑•̀ㅂ•́)و✧ 喷水警告！",
     "检测到有人正在向屏幕俯冲……\n"
     "鲸鱼娘已经喷水阻止了！\n抬头、挺胸、远离屏幕～"),
    ("(；・∀・) 太近了太近了！",
     "近距离 + 长时间盯屏 = 眼睛加班。\n"
     "去接杯水，闭眼休息 20 秒再回来吧～"),
    ("(๑˃ᴗ˂)ﻭ 护眼海域提醒",
     "你已进入『贴脸码字』海域！\n"
     "请退到 50~70cm 的安全距离，鲸鱼娘就放心了～"),
]

# 屏幕角落悬浮字幕（短句）
FLOAT_TEXTS = [
    "太近啦！(っ˘ω˘ς)",
    "鲸鱼娘：退后一点嘛～",
    "喷水警告！离屏幕远一点！",
    "贴脸啦，眼睛要抗议了 (；・∀・)",
    "护眼海域：请保持距离～",
]

# 状态栏文案：(文字, 颜色)
STATE_TEXT = {
    "noface":   ("咦，鲸鱼娘没看到你的脸……(っ˘ω˘ς)", TXT_DIM),
    "far":      ("离得有点远呢，靠近一点点让我看看你～", TXT_DIM),
    "normal":   ("距离刚刚好，鲸鱼娘很满意！(๑˃ᴗ˂)ﻭ", OK_C),
    "near":     ("有点近了哦……鲸鱼娘开始紧张了 (；・∀・)", WARN_C),
    "cooldown": ("冷却中……刚提醒过啦，快退后呀 (っ˘ω˘ς)", WARN_C),
    "alert":    ("太近啦！！鲸鱼娘喷水警告！(๑•̀ㅂ•́)و✧", ALERT_C),
}

# 字体（Windows 用微软雅黑，其它系统自动回退到默认字体）
_FONT = "Microsoft YaHei UI" if IS_WINDOWS else "Helvetica"
FONT_UI    = (_FONT, 10)
FONT_SMALL = (_FONT, 9)
FONT_BTN   = (_FONT, 11, "bold")
FONT_TITLE = (_FONT, 16, "bold")
FONT_POP   = (_FONT, 15, "bold")
FONT_TINY  = (_FONT, 9, "bold")


# ================================ 工具函数 ================================

def app_dir():
    """程序所在目录。
    PyInstaller --onefile 打包后，sys.executable 才是 EXE 真实路径
    （__file__ 会被解压到临时目录），所以日志等文件要写到 EXE 旁边。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def log_error(detail):
    """把异常写入 EXE 同目录的日志文件。--windowed 打包后没有控制台，
    这是排错（尤其"双击没反应"）的唯一线索。"""
    try:
        with open(os.path.join(app_dir(), "face_guard_error.log"), "a", encoding="utf-8") as f:
            f.write("\n[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), detail))
    except Exception:
        pass


def find_cascade_path():
    """定位内置 Haar 人脸模型，按优先级尝试多个位置：
    1. PyInstaller 解包目录 sys._MEIPASS（--onefile 打包后 --add-data 的文件在这里）
    2. opencv 包自带的 cv2.data.haarcascades（开发环境直接跑 python face_guard.py）
    3. 兜底：cv2 包目录下找 data 子目录
    全都找不到返回 None（会弹窗报错，绝不联网去下载）。
    """
    if getattr(sys, "frozen", False):                       # 打包后
        cand = os.path.join(sys._MEIPASS, CASCADE_FILENAME)
        if os.path.exists(cand):
            return cand
    try:                                                    # 开发环境：pip 安装的 opencv
        cand = os.path.join(cv2.data.haarcascades, CASCADE_FILENAME)
        if os.path.exists(cand):
            return cand
    except Exception:
        pass
    cand = os.path.join(os.path.dirname(cv2.__file__), "data", CASCADE_FILENAME)
    if os.path.exists(cand):
        return cand
    return None


# ---------------- 颜色工具（"蓝 → 红"悬浮球渐变 + 全部美术绘制都靠它们） ----------------

def hex_to_rgb(color):
    """'#rrggbb' → (r, g, b)。"""
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def rgb_to_hex(rgb):
    """(r, g, b) → '#rrggbb'，自动夹到 0~255。"""
    r, g, b = (max(0, min(255, int(round(v)))) for v in rgb)
    return "#%02x%02x%02x" % (r, g, b)


def shade(color, factor):
    """把颜色整体调亮（factor>1）或调暗（factor<1），用于画高光与阴影。
    Tkinter 不支持透明度，深浅色是唯一的立体感来源。"""
    r, g, b = hex_to_rgb(color)
    return rgb_to_hex((r * factor, g * factor, b * factor))


def distance_color(ratio):
    """『距离水平』→ 悬浮球颜色：0 = 离得远（蓝）→ 1 = 贴脸（红）。

    用 HSV 色相插值（210°蓝 → 0°红），中途经过青 / 绿 / 黄 / 橙，
    比 RGB 直接做蓝红线性插值干净得多（后者中途会发灰发紫，很难看）。
    """
    r = max(0.0, min(1.0, float(ratio)))
    hue = (210.0 * (1.0 - r)) / 360.0
    rr, gg, bb = colorsys.hsv_to_rgb(hue, 0.82, 1.0)
    return rgb_to_hex((rr * 255, gg * 255, bb * 255))


def try_transparent(win):
    """把 KEY_COLOR 设为全透明（Windows layered window 色键），
    让圆角悬浮窗 / 悬浮球的四个角真正透出桌面。
    非 Windows 或 Tk 不支持时静默返回 False，调用方改用同色背景兜底。"""
    if not IS_WINDOWS:
        return False
    try:
        win.attributes("-transparentcolor", KEY_COLOR)
        return True
    except Exception:
        return False


def paint_gradient(canvas, width, height, top, bottom, tag="grad"):
    """在 Canvas 上画竖向线性渐变。

    Tkinter 没有渐变控件，这里用逐像素细线堆出来 —— 只在窗口尺寸变化时重画一次，
    成本可以忽略（几百次 create_line）。
    """
    canvas.delete(tag)
    width, height = int(width), int(height)
    if width <= 1 or height <= 1:
        return
    r1, g1, b1 = hex_to_rgb(top)
    r2, g2, b2 = hex_to_rgb(bottom)
    for i in range(height):
        t = i / float(max(1, height - 1))
        canvas.create_line(0, i, width, i, tags=tag,
                           fill=rgb_to_hex((r1 + (r2 - r1) * t,
                                            g1 + (g2 - g1) * t,
                                            b1 + (b2 - b1) * t)))
    canvas.tag_lower(tag)


def round_rect(canvas, x1, y1, x2, y2, radius, **kw):
    """圆角矩形（用平滑多边形近似）。Tkinter 没有圆角控件，悬浮字幕靠它。"""
    pts = [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
           x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
           x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


def draw_whale_girl(canvas, cx, cy, size, mood="normal",
                    body=WHALE_BLUE, hood=WHALE_DEEP, skin=SKIN, tag=None):
    """在 Canvas 上矢量绘制『鲸鱼娘』：鲸鱼兜帽 + 尾鳍 + 喷水 + 脸蛋 + 腮红。

    纯图元绘制，不依赖任何图片素材，所以打包体积零增长，而且能被多处复用 ——
    悬浮球只要把 body/hood 换成"随距离变化"的颜色，就得到了会变色的鲸鱼娘。

    cx, cy : 中心点；size : 直径；mood : normal / near / alert（决定表情）。
    返回本次创建的 item id 列表。
    """
    r = size / 2.0
    tags = () if tag is None else (tag,)
    items = []

    def oval(x1, y1, x2, y2, **kw):
        items.append(canvas.create_oval(cx + x1 * r, cy + y1 * r,
                                        cx + x2 * r, cy + y2 * r, tags=tags, **kw))

    def poly(pts, **kw):
        flat = []
        for px, py in pts:
            flat += [cx + px * r, cy + py * r]
        items.append(canvas.create_polygon(flat, smooth=True, tags=tags, **kw))

    def line(pts, **kw):
        flat = []
        for px, py in pts:
            flat += [cx + px * r, cy + py * r]
        items.append(canvas.create_line(flat, tags=tags, **kw))

    # ---- 1) 头顶喷水（鲸鱼的标志）----
    for (dx, dy, rr) in ((-0.30, -1.62, 0.15), (0.0, -1.88, 0.12), (0.30, -1.58, 0.14)):
        oval(dx - rr, dy - rr * 1.4, dx + rr, dy + rr * 1.4, fill="#cdefff", outline="")

    # ---- 2) 两侧尾鳍（先画，垫在头后面）----
    poly([(0.0, -0.50), (-0.92, -1.20), (-0.96, -1.52), (-0.16, -0.84)],
         fill=shade(body, 0.86), outline=shade(body, 1.25))
    poly([(0.0, -0.50), (0.92, -1.20), (0.96, -1.52), (0.16, -0.84)],
         fill=shade(body, 0.86), outline=shade(body, 1.25))

    # ---- 3) 头（鲸鱼兜帽）----
    oval(-1.0, -0.90, 1.0, 0.92, fill=body, outline=shade(body, 1.3), width=2)
    items.append(canvas.create_arc(cx - r, cy - r * 1.02, cx + r, cy + r * 0.86,
                                   start=0, extent=180, style="chord",
                                   fill=hood, outline=shade(hood, 1.35),
                                   width=2, tags=tags))
    items.append(canvas.create_arc(cx - r * 0.98, cy - r * 1.0, cx + r * 0.98, cy + r * 0.84,
                                   start=180, extent=180, style="arc",
                                   outline=ACCENT_LT, width=2, tags=tags))

    # ---- 4) 脸 ----
    oval(-0.64, -0.34, 0.64, 0.70, fill=skin, outline=shade(skin, 0.82))

    # ---- 5) 眼睛（三种情绪）----
    eye = "#16324f"
    if mood == "alert":
        line([(-0.46, -0.02), (-0.20, 0.16), (-0.46, 0.34)], fill=eye, width=3)   # >_<
        line([(0.46, -0.02), (0.20, 0.16), (0.46, 0.34)], fill=eye, width=3)
    elif mood == "near":
        for x1, x2 in ((-0.46, -0.16), (0.16, 0.46)):                             # ∩ ∩ 眯眼
            items.append(canvas.create_arc(cx + x1 * r, cy - r * 0.04,
                                           cx + x2 * r, cy + r * 0.34,
                                           start=0, extent=180, style="arc",
                                           outline=eye, width=3, tags=tags))
    else:
        oval(-0.44, -0.06, -0.18, 0.32, fill=eye, outline="")
        oval(0.18, -0.06, 0.44, 0.32, fill=eye, outline="")
        oval(-0.39, 0.00, -0.28, 0.11, fill="#ffffff", outline="")                # 高光
        oval(0.23, 0.00, 0.34, 0.11, fill="#ffffff", outline="")
        oval(-0.25, 0.20, -0.19, 0.26, fill="#ffffff", outline="")
        oval(0.37, 0.20, 0.43, 0.26, fill="#ffffff", outline="")

    # ---- 6) 腮红 ----
    oval(-0.90, 0.16, -0.56, 0.42, fill=BLUSH, outline="")
    oval(0.56, 0.16, 0.90, 0.42, fill=BLUSH, outline="")

    # ---- 7) 嘴 ----
    if mood == "alert":
        oval(-0.16, 0.30, 0.16, 0.62, fill="#8c3b4a", outline="")
    else:
        items.append(canvas.create_arc(cx - r * 0.24, cy + r * 0.26, cx + r * 0.24, cy + r * 0.60,
                                       start=200, extent=140, style="arc",
                                       outline="#a8543f", width=2, tags=tags))
    return items


# ---------------- 立绘素材加载（打包后用 sys._MEIPASS，缺失时程序自动退回矢量画法） ----------------

def asset_path(name):
    """定位 assets 目录下的素材文件。
    1. PyInstaller --onefile 打包后：--add-data "assets;assets" 把整个目录解包到 sys._MEIPASS
    2. 开发环境：脚本同目录的 assets/
    找不到返回 None（调用方会退回 Canvas 矢量鲸鱼娘，绝不报错崩界面）。
    """
    if getattr(sys, "frozen", False):
        cand = os.path.join(sys._MEIPASS, ASSET_DIRNAME, name)
        if os.path.exists(cand):
            return cand
    cand = os.path.join(app_dir(), ASSET_DIRNAME, name)
    if os.path.exists(cand):
        return cand
    return None


_MASCOT_CACHE = {}


def mascot_image(name, height=None):
    """读取立绘并等比缩放到指定高度（LANCZOS 保住小尺寸下的五官清晰度）。
    按 (路径, 高度) 缓存已解码的 PIL 图：一次报警可能同时用到多个尺寸，
    不缓存就会反复读文件 + 反复重采样。
    """
    path = asset_path(name)
    if path is None:
        return None
    key = (path, height)
    if key in _MASCOT_CACHE:
        return _MASCOT_CACHE[key]
    try:
        im = Image.open(path).convert("RGBA")
    except Exception:
        return None
    if height:
        h = max(1, int(height))
        w = max(1, int(round(im.width * h / float(im.height))))
        im = im.resize((w, h), Image.LANCZOS)
    _MASCOT_CACHE[key] = im
    return im


def circular_avatar(im, size, wash=None, wash_alpha=0.0):
    """把 RGBA 立绘裁成圆形头像（悬浮球用），可选叠一层颜色薄雾。

    圆形蒙版按 4 倍超采样再缩回来，边缘才不会有锯齿；
    wash 是叠上去的颜色（悬浮球传距离色），用来在不遮住脸的前提下加强颜色信号。
    """
    if im is None:
        return None
    size = max(8, int(size))
    scale = max(size / float(im.width), size / float(im.height))
    big = im.resize((max(1, int(round(im.width * scale))),
                     max(1, int(round(im.height * scale)))), Image.LANCZOS)
    left = (big.width - size) // 2
    top = (big.height - size) // 3        # 略微上移：脸比几何中心稍高一点更好看
    big = big.crop((max(0, left), max(0, top), max(0, left) + size, max(0, top) + size))

    s4 = size * 4
    mask = Image.new("L", (s4, s4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, s4 - 1, s4 - 1), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    big.putalpha(ImageChops.multiply(big.getchannel("A"), mask))

    if wash and wash_alpha > 0.01:
        # 薄雾只铺在头像的可见像素上：layer 的 alpha = 雾浓度 × 头像 alpha，
        # 再做 alpha_composite 正常混合（不能直接 multiply，那会把颜色乘暗）
        layer = Image.new("RGBA", (size, size), wash + (255,))
        layer.putalpha(ImageChops.multiply(layer.getchannel("A"), big.getchannel("A")))
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * min(1.0, wash_alpha))))
        big = Image.alpha_composite(big, layer)
    return big


# ================================ 靠近判定引擎 ================================

class ProximityEngine:
    """靠近判定引擎：EMA 平滑 + 自适应基线 + 连续帧确认 + 冷却。

    为什么这样设计（抗晃动 / 抗误报）：
    1. fast EMA(α=0.35) 平滑"人脸宽度占比"：抹平单帧检测框抖动，
       打喷嚏/挥手造成的一帧突变会被曲线稀释，几乎不动；
    2. slow EMA(α=0.02) 维护"正常坐姿基线"：人总会慢慢挪动，基线跟着慢速漂移，
       避免"坐姿渐变"被误判成"靠近"；
    3. 只有当【平滑值 / 基线】≥ 触发阈值，且连续 confirm 帧都满足，才报警
       —— 偶尔一两帧凑近（拿水杯）不会触发；
    4. 触发后进入冷却：冷却时间内即使仍贴近也只算 near，不重复报警；
       冷却结束后若仍然贴近，会再提醒一次（防止被无视）；
    5. 处于"贴近区"时冻结基线更新，防止一直贴脸把基线也抬高、
       导致之后永远不再报警。
    """

    ALPHA_FAST = 0.35   # 快速平滑系数：越大跟随越快、抗抖越弱
    ALPHA_SLOW = 0.02   # 基线漂移系数：越小基线越稳定

    def __init__(self):
        self._smoothed = None    # 平滑后的人脸宽度占比
        self._baseline = None    # "正常坐姿"基线占比
        self._streak = 0         # 连续"过近"帧计数
        self._next_fire = 0.0    # 冷却结束时间戳
        self._closeness = 0.0    # 当前 平滑值/基线，供 UI 展示

    def reset(self):
        self._smoothed = None
        self._baseline = None
        self._streak = 0
        self._next_fire = 0.0
        self._closeness = 0.0

    def miss(self):
        """本帧没检测到（稳定）人脸：连续计数清零（突变断链），基线保留。
        短暂遮挡不重学基线，所以晃出画面再回来不会误触发。"""
        self._streak = 0

    def closeness(self):
        return self._closeness

    def update(self, size_ratio, threshold, confirm_frames, cooldown_sec, allow_fire=True):
        """输入本帧人脸宽度占比（0~1），返回 (状态, 是否冷却中)。
        状态: "normal" 正常 / "near" 接近 / "fire" 触发报警（本帧刚好命中）"""
        now = time.time()
        if self._smoothed is None:
            # 第一帧：直接作为初始基线（开机时你坐的位置 = 你的正常距离）
            self._smoothed = size_ratio
            self._baseline = size_ratio
        else:
            self._smoothed += self.ALPHA_FAST * (size_ratio - self._smoothed)
        self._closeness = self._smoothed / max(self._baseline, 1e-6)

        if self._closeness >= threshold:
            # ---- 进入"贴近区"：基线冻结，只累计连续帧 ----
            self._streak += 1
            if (self._streak >= confirm_frames and allow_fire
                    and now >= self._next_fire):
                self._next_fire = now + cooldown_sec   # 触发即进入冷却
                return "fire", True
            return "near", now < self._next_fire

        # ---- 正常区：基线慢速跟随新坐姿，计数清零 ----
        self._baseline += self.ALPHA_SLOW * (self._smoothed - self._baseline)
        self._streak = 0
        return "normal", False


# ================================ 摄像头后台线程 ================================

class CameraWorker(threading.Thread):
    """后台线程：抓帧 → 人脸检测 → 靠近判定 → 画框 → 写入共享状态。

    为什么单独开线程：cv2.VideoCapture.read() 和 Haar 检测都是阻塞操作，
    放主线程会卡死 Tkinter 界面；分开后即使主窗口最小化，检测也在后台继续跑，
    报警弹窗与悬浮球照常更新（满足"最小化后继续检测"）。
    """

    DETECT_WIDTH   = 320    # 检测前把画面宽度缩到 320px：Haar 耗时近似正比于像素数，
                            # 320 宽下单帧约 5~15ms，CPU 占用极低
    MIN_FACE_RATIO = 0.08   # 人脸宽度 < 画面 8% 视为"太远"：远处小脸检测噪声大，
                            # 不参与靠近判定，也避免把背景路人算进来
    WARMUP_SEC     = 2.0    # 启动后 2 秒内不报警：给基线留出学习"正常坐姿"的时间
    MAX_READ_FAIL  = 30     # 连续读取失败约 1 秒后判定摄像头异常

    def __init__(self, cam_index, shared, events, get_params):
        super().__init__(daemon=True, name="CameraWorker")
        self.cam_index  = cam_index
        self.shared     = shared       # dict: lock / frame / metrics（线程间共享）
        self.events     = events       # queue.Queue：向 UI 线程投递一次性事件
        self.get_params = get_params   # 回调：实时获取滑块参数（UI 侧保证线程安全）
        self._stop      = threading.Event()
        self.detector   = None

    def stop(self):
        self._stop.set()

    # ---------- 子步骤 ----------

    def _fatal(self, msg):
        self.events.put(("fatal", msg))

    def _load_model(self):
        """加载内置 Haar 模型。找不到/加载失败 → 报错退出，绝不联网下载。"""
        path = find_cascade_path()
        if path is None:
            self._fatal(
                "找不到人脸检测模型 %s！\n\n"
                "开发运行：请 pip install opencv-python-headless\n"
                "打包运行：打包命令必须带\n"
                "  --add-data \"<opencv的data目录>\\%s;.\"" % (CASCADE_FILENAME, CASCADE_FILENAME))
            return None
        detector = cv2.CascadeClassifier(path)
        if detector.empty():
            self._fatal("人脸模型加载失败：%s" % path)
            return None
        self.detector = detector
        return path

    def _open_camera(self):
        """打开摄像头。Windows 下优先 CAP_DSHOW：打开速度快（避开 MSMF 的
        数秒超时），兼容性更好；失败再兜底用默认后端。"""
        api_pref = cv2.CAP_DSHOW if IS_WINDOWS else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.cam_index, api_pref)
        if not cap.isOpened() and api_pref != cv2.CAP_ANY:
            cap.release()
            cap = cv2.VideoCapture(self.cam_index, cv2.CAP_ANY)
        if not cap.isOpened():
            self._fatal(
                "无法打开摄像头（设备 %d）！\n\n"
                "请依次检查：\n"
                "  1. 摄像头是否被其他软件占用（腾讯会议/钉钉/OBS 等）\n"
                "  2. Windows 设置 → 隐私和安全性 → 相机 → 允许桌面应用访问相机\n"
                "  3. 笔记本是否有物理摄像头开关 / Fn 快捷键\n"
                "  4. 外接摄像头请试试把界面上的【设备编号】改成 1 或 2" % self.cam_index)
            return None
        # 限制分辨率：检测用不到 1080p，降低 CPU 与 USB 带宽压力
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        except Exception:
            pass
        return cap

    @staticmethod
    def _annotate(frame, x, y, w, h, size_pct, state):
        """在帧上画人脸框（BGR 配色，与界面的蓝→红主题保持一致）。
        注意：cv2.putText 不支持中文，所以画面叠加文字只用 ASCII，
        中文都放在 Tkinter 控件里显示。"""
        color = (90, 90, 255) if state == "alert" else \
                (60, 200, 255) if state in ("near", "cooldown") else (255, 190, 80)
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        cv2.putText(frame, "face %.0f%%" % (size_pct * 100),
                    (x, max(18, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # ---------- 主循环 ----------

    def run(self):
        cap = None
        try:
            if self._load_model() is None:
                return
            cap = self._open_camera()
            if cap is None:
                return

            engine = ProximityEngine()
            start_ts = time.time()
            fail_cnt = 0
            fps, t_last = 0.0, time.time()

            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    # 偶发丢帧先容忍（USB 抖动常见），连续失败才报错退出
                    fail_cnt += 1
                    if fail_cnt > self.MAX_READ_FAIL:
                        self._fatal("摄像头画面读取失败（可能被拔出或被其他程序抢占），已自动停止。")
                        return
                    time.sleep(0.03)
                    continue
                fail_cnt = 0

                # 实时获取滑块参数（阈值 / 灵敏度对应连续帧数 / 冷却秒数）
                p = self.get_params()

                # ---------- 1) 人脸检测：缩到小图提速 ----------
                h, w = frame.shape[:2]
                scale = self.DETECT_WIDTH / float(w)
                small = cv2.resize(frame, (self.DETECT_WIDTH, max(1, int(h * scale))),
                                   interpolation=cv2.INTER_AREA)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                gray = cv2.equalizeHist(gray)          # 直方图均衡，提升暗光检出率
                faces = self.detector.detectMultiScale(
                    gray,
                    scaleFactor=1.1,    # 图像金字塔步长：越小越准越慢
                    minNeighbors=5,     # 越大误检越少但可能漏检，5 是常用均衡值
                    minSize=(40, 40),   # 小图上小于 40px 的人脸直接忽略
                )

                # ---------- 2) 取最大的人脸 → 靠近判定 ----------
                state, size_pct, closeness = "noface", 0.0, 0.0
                if len(faces) > 0:
                    x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])   # 最大脸
                    # 小图坐标映射回原始帧坐标
                    x, y, fw, fh = int(x / scale), int(y / scale), int(fw / scale), int(fh / scale)
                    size_pct = fw / float(w)
                    if size_pct >= self.MIN_FACE_RATIO:
                        warmup_ok = (time.time() - start_ts) >= self.WARMUP_SEC
                        st, in_cd = engine.update(
                            size_pct, p["threshold"], p["confirm_frames"],
                            p["cooldown_sec"], allow_fire=warmup_ok)
                        closeness = engine.closeness()
                        if st == "fire":
                            # 触发报警！投递事件给 UI 线程去弹窗/悬浮/响铃
                            self.events.put(("alert", {
                                "popup": random.choice(POPUP_TEXTS),
                                "float": random.choice(FLOAT_TEXTS),
                            }))
                            state = "alert"
                        else:
                            state = "cooldown" if in_cd else st
                    else:
                        engine.miss()      # 太远：不参与判定
                        state = "far"
                    self._annotate(frame, x, y, fw, fh, size_pct, state)
                else:
                    engine.miss()          # 没人脸：绝不触发提醒，计数清零

                # ---------- 3) 帧率统计（平滑显示） ----------
                now = time.time()
                inst = 1.0 / max(now - t_last, 1e-6)
                t_last = now
                fps = inst if fps == 0 else fps * 0.9 + inst * 0.1

                # ---------- 4) 结果写入共享区（加锁） ----------
                with self.shared["lock"]:
                    self.shared["frame"] = frame        # 已画框的帧
                    self.shared["metrics"] = {
                        "state": state, "size_pct": size_pct, "closeness": closeness,
                        "threshold": p["threshold"], "fps": fps, "w": w, "h": h,
                    }
                time.sleep(0.005)   # 轻微让出 CPU（摄像头 30fps 足够）

        except Exception:
            detail = traceback.format_exc()
            log_error(detail)
            self._fatal("程序内部出现异常，已停止：\n%s\n\n详细日志见 face_guard_error.log"
                        % detail[-600:])
        finally:
            if cap is not None:
                cap.release()
            self.events.put(("stopped", None))   # 无论何种退出都通知 UI 复位按钮


# ================================ 主界面 ================================

class FaceGuardApp:

    CANVAS_W, CANVAS_H = 560, 400   # 摄像头画面显示区域
    TICK_MS = 33                    # UI 刷新周期 ≈ 30FPS
    BALL_SIZE = 92                  # 悬浮球直径

    def __init__(self, root):
        self.root = root
        root.title("%s · 护眼距离提醒 %s ｜ 全程离线 · 画面不上传" % (APP_NAME, APP_VERSION))
        root.configure(bg=BG_DEEP)
        root.minsize(640, 720)

        # ---- 线程间共享数据 ----
        self.shared = {"lock": threading.Lock(), "frame": None, "metrics": {}}
        self.events = queue.Queue()
        self.worker = None
        self._running = False
        self._ui_ready = False
        # worker 线程读取的参数快照（主线程 _tick 里从滑块同步过来）
        self._params = {"threshold": 1.25, "confirm_frames": 7, "cooldown_sec": 30}
        self._param_lock = threading.Lock()

        # ---- 弹窗/悬浮窗句柄 ----
        self._popup = None
        self._popup_after = None
        self._float = None
        self._float_after = None
        self._photo = None
        self._img_item = None

        # ---- 立绘 PhotoImage 缓存（Tk 图必须留引用，否则被 GC 掉会变成白图）----
        self._mascot_photos = {}
        self._ball_avatar = None

        # ---- 悬浮球状态（最小化时显示，颜色随距离由蓝到红）----
        self._ball = None
        self._ball_canvas = None
        self._ball_key = None          # (量化后的贴近度, 状态)：变了才重画
        self._ball_pos = None          # 记忆拖动后的位置
        self._ball_drag = None         # 拖动时的鼠标偏移
        self._ball_tip = None
        self._ball_tip_lbl = None

        # ---- 背景渐变画布 ----
        self._bg_size = (0, 0)

        self._build_ui()
        self._ui_ready = True
        self._sync_params()
        self._fit_to_screen()

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(self.TICK_MS, self._tick)

    # ---------------- 界面搭建 ----------------

    def _build_ui(self):
        R = self.root

        # === 背景：整窗深海蓝渐变 + 泡泡 + 鲸鱼剪影（先创建 = 垫在最底层）===
        self.bg_canvas = tk.Canvas(R, bg=BG_DEEP, highlightthickness=0, bd=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bg_canvas.bind("<Configure>", self._on_bg_resize)

        # === 卡片 1：标题栏（鲸鱼娘头像 + 标题）===
        head = tk.Frame(R, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        head.pack(fill="x", padx=18, pady=(14, 6))
        icon = tk.Canvas(head, width=58, height=58, bg=PANEL, highlightthickness=0, bd=0)
        icon.pack(side="left", padx=(10, 6), pady=5)
        self._put_mascot(icon, MASCOT_HEAD, 29, 29, 50, fallback=42, mood="normal")
        tbox = tk.Frame(head, bg=PANEL)
        tbox.pack(side="left", pady=5)
        tk.Label(tbox, text="FaceGuard 酱 · 鲸鱼娘", font=FONT_TITLE,
                 bg=PANEL, fg=ACCENT_LT).pack(anchor="w")
        tk.Label(tbox, text="二次元护眼距离小卫士 · 离线运行 · 画面绝不离开你的电脑",
                 font=FONT_SMALL, bg=PANEL, fg=TXT_DIM).pack(anchor="w", pady=(3, 0))

        # === 卡片 2：摄像头画面（待机时显示鲸鱼娘）===
        cam_card = tk.Frame(R, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        cam_card.pack(padx=18, pady=2)
        self.canvas = tk.Canvas(cam_card, width=self.CANVAS_W, height=self.CANVAS_H,
                                bg="#062036", highlightthickness=0, bd=0)
        self.canvas.pack(padx=4, pady=4)
        self._layout_placeholder()

        # === 卡片 3：状态 + 进度 + 开关 + 按钮 ===
        ctrl = tk.Frame(R, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        ctrl.pack(fill="x", padx=18, pady=6)

        self.status_var = tk.StringVar()
        self.lbl_status = tk.Label(ctrl, textvariable=self.status_var, font=FONT_UI,
                                   bg=PANEL, fg=TXT, wraplength=580, justify="left")
        self.lbl_status.pack(fill="x", padx=12, pady=(8, 0))

        bar_row = tk.Frame(ctrl, bg=PANEL)
        bar_row.pack(fill="x", padx=12, pady=(4, 6))
        tk.Label(bar_row, text="靠近程度", font=FONT_SMALL, bg=PANEL, fg=TXT_DIM).pack(side="left")
        style = ttk.Style()
        try:
            style.theme_use("clam")     # clam 才允许自定义进度条颜色
        except Exception:
            pass
        style.configure("whale.Horizontal.TProgressbar", troughcolor=PANEL_2,
                        background=ACCENT, bordercolor=LINE,
                        lightcolor=ACCENT_LT, darkcolor=ACCENT_DK, thickness=12)
        self.progress = ttk.Progressbar(bar_row, maximum=100, mode="determinate",
                                        style="whale.Horizontal.TProgressbar")
        self.progress.pack(side="left", fill="x", expand=True, padx=(8, 0))

        opt = tk.Frame(ctrl, bg=PANEL)
        opt.pack(fill="x", padx=12)
        self.var_popup = tk.BooleanVar(value=True)
        self.var_float = tk.BooleanVar(value=True)
        self.var_sound = tk.BooleanVar(value=True)
        self.var_ball = tk.BooleanVar(value=True)
        self.var_camidx = tk.IntVar(value=0)
        for text, var in (("弹窗提醒", self.var_popup),
                          ("角落悬浮字幕", self.var_float),
                          ("提示音", self.var_sound),
                          ("最小化时显示悬浮球", self.var_ball)):
            tk.Checkbutton(opt, text=text, variable=var, font=FONT_UI, bg=PANEL,
                           fg=TXT, activebackground=PANEL, activeforeground=ACCENT_LT,
                           selectcolor=PANEL_2, highlightthickness=0, bd=0).pack(
                               side="left", padx=(0, 10))
        tk.Label(opt, text="设备编号", font=FONT_UI, bg=PANEL, fg=TXT).pack(side="left")
        ttk.Spinbox(opt, from_=0, to=5, increment=1, width=4,
                    textvariable=self.var_camidx, font=FONT_UI).pack(side="left", padx=(6, 0))

        btns = tk.Frame(ctrl, bg=PANEL)
        btns.pack(pady=8)
        self.btn_start = tk.Button(btns, text="▶ 启动摄像头", font=FONT_BTN, bg=ACCENT,
                                   fg="white", activebackground=ACCENT_DK,
                                   activeforeground="white", relief="flat", padx=24,
                                   pady=5, cursor="hand2", command=self.start_cam)
        self.btn_start.pack(side="left", padx=8)
        self.btn_stop = tk.Button(btns, text="■ 停止摄像头", font=FONT_BTN, bg=PANEL_2,
                                  fg=TXT_DIM, activebackground=LINE,
                                  activeforeground=TXT, relief="flat", padx=24,
                                  pady=5, cursor="hand2", state="disabled",
                                  command=self.stop_cam)
        self.btn_stop.pack(side="left", padx=8)

        # === 卡片 4：参数调节 ===
        box = tk.LabelFrame(R, text=" ⚙ 参数调节 ", font=FONT_UI, bg=PANEL,
                            fg=ACCENT_LT, padx=10, pady=6,
                            highlightthickness=1, highlightbackground=LINE)
        box.pack(fill="x", padx=18, pady=(2, 6))

        def add_scale(row, text, from_, to, res, init, fmt):
            tk.Label(box, text=text, font=FONT_UI, bg=PANEL, fg=TXT) \
                .grid(row=row, column=0, sticky="w", pady=2)
            s = tk.Scale(box, from_=from_, to=to, resolution=res, orient="horizontal",
                         length=280, showvalue=False, bg=PANEL, highlightthickness=0,
                         troughcolor=PANEL_2, fg=ACCENT_LT, bd=0,
                         activebackground=ACCENT_LT, sliderrelief="flat")
            s.grid(row=row, column=1, pady=2)
            val = tk.Label(box, text="", font=FONT_UI, bg=PANEL, fg=ACCENT_LT,
                           width=9, anchor="w")
            val.grid(row=row, column=2, sticky="w")

            def _upd(v):
                val.configure(text=fmt(float(v)))
                if self._ui_ready:
                    self._sync_params()

            s.configure(command=_upd)
            s.set(init)     # set 会触发 command，自动刷新右侧数值
            return s

        self.sc_threshold = add_scale(0, "靠近触发阈值", 1.05, 1.60, 0.01, 1.25,
                                      lambda v: "%.2f 倍" % v)
        self.sc_sens = add_scale(1, "触发灵敏度", 1, 10, 1, 5,
                                 lambda v: "%d 级" % int(v))
        self.sc_cooldown = add_scale(2, "报警冷却秒数", 5, 120, 1, 30,
                                     lambda v: "%d 秒" % int(v))
        tk.Label(box, text="阈值 = 人脸相对『正常坐姿基线』放大多少倍就触发；"
                           "灵敏度越高，需要连续确认的帧数越少；冷却 = 两次报警的最小间隔。",
                 font=FONT_SMALL, bg=PANEL, fg=TXT_DIM, wraplength=560,
                 justify="left").grid(row=3, column=0, columnspan=3, sticky="w")

        # === 底部隐私与悬浮球声明（直接压在渐变最深处，颜色刚好吻合）===
        tk.Label(R, text="※ 100% 离线：无网络请求、无遥测，画面仅在内存中处理，关闭即消失。\n"
                         "※ 悬浮球：最小化主窗口后出现在屏幕右下角，颜色越红 = 离屏幕越近"
                         "（蓝=远 · 红=贴脸），拖可移动 · 双击回主窗口。",
                 font=FONT_SMALL, bg=BG_DEEP, fg=TXT_DIM, justify="center",
                 wraplength=600).pack(side="bottom", pady=(2, 8))

        self.status_var.set("状态：待机中～ 点击【▶ 启动摄像头】开始守护 (っ˘ω˘ς)")

    # ---------------- 立绘摆放（素材缺失自动退回矢量画法） ----------------

    def _mascot_photo(self, name, height):
        """按 (素材名, 高度) 缓存 Tk PhotoImage。"""
        key = (name, int(height))
        if key not in self._mascot_photos:
            im = mascot_image(name, height=height)
            self._mascot_photos[key] = ImageTk.PhotoImage(im) if im is not None else None
        return self._mascot_photos[key]

    def _put_mascot(self, canvas, name, cx, cy, height, fallback=None,
                    mood="normal", tag=None):
        """把立绘放到 canvas 的 (cx, cy)（等比缩放到 height 像素高）。

        立绘是抠好图带透明通道的 PNG，直接 create_image 就能贴到画布上。
        素材丢失/损坏时退回 draw_whale_girl 的矢量鲸鱼娘，界面不会开天窗。
        """
        photo = self._mascot_photo(name, height)
        if photo is not None:
            return canvas.create_image(cx, cy, image=photo,
                                       tags=() if tag is None else (tag,))
        if fallback:
            draw_whale_girl(canvas, cx, cy, fallback, mood=mood, tag=tag)
        return None

    def _layout_placeholder(self):
        """画/重画摄像头画布的待机画面：鲸鱼娘立绘 + 提示文字（用 tag 统一显隐）。"""
        cv = self.canvas
        cv.delete("ph")
        cv.delete("phdeco")
        h = self.CANVAS_H
        self._put_mascot(cv, MASCOT_FULL, self.CANVAS_W // 2, h // 2 - 34, 168,
                         fallback=112, mood="near", tag="phdeco")
        cv.create_text(self.CANVAS_W // 2, h // 2 + 74,
                       text="摄像头未启动\n点击下方【▶ 启动摄像头】\n"
                            "鲸鱼娘会在这里陪你守护眼睛 (っ˘ω˘ς)",
                       fill="#9dc4e6", font=FONT_UI, justify="center", tags=("ph",))

    def _fit_to_screen(self):
        """小屏 / 高 DPI 缩放时把摄像头画布收窄一点，保证所有控件都露得出来
        （Tkinter 没有滚动条兜底，宁可画面小一点也不能让按钮跑到屏幕外）。"""
        try:
            self.root.update_idletasks()
            need = self.root.winfo_reqheight()
            avail = self.root.winfo_screenheight() - 90
            if need > avail:
                new_h = max(240, self.CANVAS_H - min(180, need - avail))
                if new_h != self.CANVAS_H:
                    self.CANVAS_H = new_h
                    self.canvas.configure(height=new_h)
                    self._layout_placeholder()
                    self._show_placeholder(self.shared["frame"] is None)
        except Exception:
            pass

    # ---------------- 背景渐变与装饰 ----------------

    def _on_bg_resize(self, event):
        """窗口尺寸变化时重画背景渐变（只在尺寸真的变了才画，避免抖动重绘）。"""
        if (event.width, event.height) == self._bg_size:
            return
        self._bg_size = (event.width, event.height)
        cv = self.bg_canvas
        paint_gradient(cv, event.width, event.height, GRAD_TOP, GRAD_BOT, tag="grad")
        cv.delete("deco")
        # 深海泡泡：位置由固定种子生成，缩放窗口时不会乱跳
        rnd = random.Random(20240707)
        for _ in range(24):
            x = rnd.uniform(0, max(1, event.width))
            y = rnd.uniform(0, max(1, event.height))
            rr = rnd.uniform(2, 9)
            cv.create_oval(x - rr, y - rr, x + rr, y + rr, tags="deco",
                           outline="#1d5f96", fill="")
        # 右下角鲸鱼剪影（暗色，纯装饰）
        try:
            draw_whale_girl(cv, event.width - 70, event.height - 92, 124,
                            mood="normal", body="#0a2b4a", hood="#092340",
                            skin="#0d3459", tag="deco")
        except Exception:
            pass
        cv.tag_raise("deco")

    # ---------------- 参数同步（主线程写，worker 读） ----------------

    def _sync_params(self):
        sens = int(float(self.sc_sens.get()))
        with self._param_lock:
            self._params["threshold"] = float(self.sc_threshold.get())
            # 灵敏度 1~10 → 需要连续确认的帧数 11~2（灵敏度越高确认越少）
            self._params["confirm_frames"] = max(2, 12 - sens)
            self._params["cooldown_sec"] = int(float(self.sc_cooldown.get()))

    def get_params(self):
        """worker 线程调用：拿一份参数快照。"""
        with self._param_lock:
            return dict(self._params)

    # ---------------- 启动 / 停止 ----------------

    def start_cam(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            cam_idx = int(self.var_camidx.get())
        except Exception:
            cam_idx = 0
        with self.shared["lock"]:          # 清掉上一轮残留画面
            self.shared["frame"] = None
            self.shared["metrics"] = {}
        self.worker = CameraWorker(cam_idx, self.shared, self.events, self.get_params)
        self.worker.start()
        self._running = True
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")

    def stop_cam(self):
        if self.worker:
            self.worker.stop()             # 不阻塞 UI，等 'stopped' 事件复位按钮

    def _set_stopped_ui(self):
        self._running = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        with self.shared["lock"]:
            self.shared["frame"] = None
            self.shared["metrics"] = {}
        self._show_placeholder(True)

    # ---------------- UI 心跳 ----------------

    def _tick(self):
        # 1) 同步滑块 → worker 可读快照
        self._sync_params()
        # 2) 处理 worker 投递的事件
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "alert":
                    self._on_alert(payload)
                elif kind == "fatal":
                    self._set_stopped_ui()
                    messagebox.showerror(APP_NAME, payload)
                elif kind == "stopped":
                    self._set_stopped_ui()
        except queue.Empty:
            pass
        # 3) 画面刷新：最小化时跳过绘制省 CPU，但后台检测线程照常运行
        if self.root.state() != "iconic":
            self._draw_frame()
        self._update_status()
        # 4) 悬浮球：主窗口最小化时出现，颜色随距离由蓝到红
        self._sync_ball()
        # 5) 下一拍
        self.root.after(self.TICK_MS, self._tick)

    def _draw_frame(self):
        with self.shared["lock"]:
            frame = self.shared["frame"]
        if frame is None:
            self._show_placeholder(True)
            return
        self._show_placeholder(False)
        h, w = frame.shape[:2]
        scale = min(self.CANVAS_W / float(w), self.CANVAS_H / float(h))
        if scale < 1.0:
            frame = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))),
                               interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._photo = ImageTk.PhotoImage(Image.fromarray(rgb))   # 保留引用防 GC
        if self._img_item is None:
            self._img_item = self.canvas.create_image(
                self.CANVAS_W // 2, self.CANVAS_H // 2, image=self._photo, tags=("cam",))
        else:
            self.canvas.coords(self._img_item, self.CANVAS_W // 2, self.CANVAS_H // 2)
            self.canvas.itemconfig(self._img_item, image=self._photo)

    def _show_placeholder(self, show):
        """待机画面（鲸鱼娘 + 提示文字）与摄像头画面互斥显示。"""
        state = "normal" if show else "hidden"
        self.canvas.itemconfigure("ph", state=state)
        self.canvas.itemconfigure("phdeco", state=state)
        self.canvas.itemconfigure("cam", state="hidden" if show else "normal")

    def _update_status(self):
        with self.shared["lock"]:
            m = dict(self.shared["metrics"])
        if not m:
            if not self._running:
                self.progress["value"] = 0
            return
        state = m.get("state", "noface")
        txt, color = STATE_TEXT.get(state, ("……", TXT))
        if state in ("noface", "far"):
            extra = ""
        else:
            extra = " ｜ 人脸宽度 %.0f%% ｜ 距离水平 %.0f%%（触发线 %.0f%%）" % (
                m["size_pct"] * 100, m["closeness"] * 100, m["threshold"] * 100)
        self.status_var.set("状态：%s%s ｜ %.1f FPS ｜ %dx%d" % (
            txt, extra, m.get("fps", 0.0), m.get("w", 0), m.get("h", 0)))
        self.lbl_status.configure(fg=color)
        closeness = m.get("closeness", 0.0)
        threshold = max(m.get("threshold", 1.25), 1e-6)
        self.progress["value"] = max(0.0, min(100.0, closeness / threshold * 100.0))

    # ---------------- 悬浮球（最小化时显示：蓝 = 远，红 = 近） ----------------

    def _distance_ratio(self):
        """当前状态 → 0~1 的『贴近度』：0 = 离得远（球是蓝的），1 = 贴脸（球是红的）。"""
        with self.shared["lock"]:
            m = dict(self.shared["metrics"])
        if not m:
            return 0.0, "noface"
        state = m.get("state", "noface")
        if state in ("noface", "far"):
            return 0.0, state
        if state == "alert":
            return 1.0, state
        threshold = max(m.get("threshold", 1.25), 1e-6)
        return max(0.0, min(1.0, m.get("closeness", 0.0) / threshold)), state

    def _sync_ball(self):
        """按"主窗口是否最小化"决定悬浮球的显示/隐藏，并刷新它的颜色。"""
        try:
            minimized = (self.root.state() == "iconic")
        except Exception:
            minimized = False
        if minimized and bool(self.var_ball.get()):
            self._show_ball()
            self._update_ball()
        else:
            self._hide_ball()

    def _show_ball(self):
        if self._ball is not None and self._ball.winfo_exists():
            return
        b = tk.Toplevel(self.root)
        b.overrideredirect(True)              # 无边框
        b.attributes("-topmost", True)        # 置顶，写代码/看视频也看得见
        transparent = try_transparent(b)      # 四角透出桌面（仅 Windows 生效）
        bg = KEY_COLOR if transparent else BG_DEEP
        b.configure(bg=bg)

        cv = tk.Canvas(b, width=self.BALL_SIZE, height=self.BALL_SIZE,
                       bg=bg, highlightthickness=0, bd=0)
        cv.pack()
        cv.configure(cursor="hand2")

        # 位置：沿用上次拖动的位置，否则默认屏幕右下角（任务栏上方）
        if self._ball_pos is None:
            sw, sh = b.winfo_screenwidth(), b.winfo_screenheight()
            self._ball_pos = (sw - self.BALL_SIZE - 36, sh - self.BALL_SIZE - 120)
        b.geometry("+%d+%d" % self._ball_pos)

        cv.bind("<Button-1>", self._ball_press)
        cv.bind("<B1-Motion>", self._ball_drag_move)
        cv.bind("<Double-Button-1>", lambda e: self._restore_window())
        cv.bind("<Button-3>", self._ball_menu)
        cv.bind("<Enter>", self._ball_tip_show)
        cv.bind("<Leave>", self._ball_tip_hide)

        self._ball, self._ball_canvas = b, cv
        self._ball_key = None                 # 强制下一拍重画
        self._draw_ball(distance_color(0.0), 0.0, "noface")

    def _hide_ball(self):
        self._ball_tip_hide()
        if self._ball is not None and self._ball.winfo_exists():
            self._ball.destroy()
        self._ball = None
        self._ball_canvas = None
        self._ball_key = None
        self._ball_avatar = None

    def _update_ball(self):
        if self._ball is None or not self._ball.winfo_exists():
            return
        ratio, state = self._distance_ratio()
        # 贴近度量化到 1/120 + 状态一起作为缓存键：数值几乎没变就不重画，省 CPU
        key = (int(ratio * 120), state)
        if key != self._ball_key:
            self._ball_key = key
            self._draw_ball(distance_color(ratio), ratio, state)
        if self._ball_tip is not None and self._ball_tip.winfo_exists():
            self._ball_tip_lbl.configure(text=self._ball_tip_text(ratio, state))

    def _draw_ball(self, color, ratio, state):
        """画悬浮球：抠好的鲸鱼娘立绘裁成圆形头像，外面套一圈"距离色"光环。

        颜色语义与矢量版一致：蓝 = 离得远，红 = 贴脸；越近光环越亮，
        头像上再叠一层同色薄雾（不遮住五官，只是整体泛红），余光一瞥就知道自己又凑上去了。
        立绘素材缺失时自动退回矢量鲸鱼娘（_draw_ball_vector）。
        """
        cv = self._ball_canvas
        if cv is None:
            return
        cv.delete("all")
        s = self.BALL_SIZE
        cx = cy = s / 2.0
        r = s / 2.0 - 8

        avatar = None
        try:
            head = mascot_image(MASCOT_HEAD)
            if head is not None:
                size = int(2 * (r - 4))
                avatar = ImageTk.PhotoImage(circular_avatar(
                    head, size, wash=hex_to_rgb(color), wash_alpha=0.08 + 0.26 * ratio))
        except Exception:
            avatar = None
        if avatar is None:
            self._draw_ball_vector(cv, color, ratio, state)
            return
        self._ball_avatar = avatar          # 留引用：Tk 图被 GC 掉会变白图

        # 外发光 + 距离色光环 + 内侧高光：越近越亮
        cv.create_oval(cx - r - 5, cy - r - 5, cx + r + 5, cy + r + 5,
                       outline=shade(color, 0.50 + 0.60 * ratio), width=3)
        cv.create_oval(cx - r, cy - r, cx + r, cy + r,
                       outline=shade(color, 0.78), width=8)
        cv.create_oval(cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3,
                       outline=shade(color, 1.35), width=2)
        cv.create_image(cx, cy, image=avatar)

        # 底部读数：距离水平百分比（远 = 小，贴脸 = 100%）
        ty = cy + r - 10
        round_rect(cv, cx - 23, ty - 9, cx + 23, ty + 9, 9,
                   fill="#04121f", outline=shade(color, 1.2), width=1)
        cv.create_text(cx, ty, text="%d%%" % round(ratio * 100),
                       fill="#ffffff", font=FONT_TINY)

    def _draw_ball_vector(self, cv, color, ratio, state):
        """矢量版悬浮球（立绘素材不可用时的兜底）：一只随距离变色的鲸鱼娘。

        球体主色 = 距离颜色（蓝 → 红）；越近颜色越红、外圈越亮、水花越大，
        贴脸时表情变成 >_<。
        """
        s = self.BALL_SIZE
        cx = cy = s / 2.0
        r = s / 2.0 - 8

        # 外圈光晕：越近越亮（贴脸时像在发烫）
        cv.create_oval(cx - r - 5, cy - r - 5, cx + r + 5, cy + r + 5,
                       outline=shade(color, 0.55 + 0.55 * ratio), width=3)

        # 头顶喷水：越近水珠越大
        for k, dx in enumerate((-0.34, 0.0, 0.34)):
            rr = 2.0 + 3.2 * ratio
            px = cx + dx * r
            py = cy - r * (1.40 if k == 1 else 1.22)
            cv.create_oval(px - rr, py - rr * 1.5, px + rr, py + rr * 1.5,
                           fill=shade("#cdefff", 0.85 + 0.2 * ratio), outline="")

        # 两侧尾鳍
        for sgn in (-1, 1):
            cv.create_polygon(cx, cy - r * 0.60,
                              cx + sgn * r * 0.98, cy - r * 1.18,
                              cx + sgn * r * 1.02, cy - r * 0.84,
                              cx + sgn * r * 0.20, cy - r * 0.84,
                              fill=shade(color, 0.80), outline=shade(color, 1.3),
                              smooth=True)

        # 球体（= 鲸鱼娘的头，主色随距离变化）
        cv.create_oval(cx - r, cy - r * 0.94, cx + r, cy + r * 0.94,
                       fill=color, outline=shade(color, 1.35), width=2)
        # 左上高光：圆球的立体感
        cv.create_oval(cx - r * 0.66, cy - r * 0.74, cx - r * 0.10, cy - r * 0.22,
                       fill=shade(color, 1.45), outline="")
        # 下半浅色肚皮：一眼看出是鲸鱼而不是普通圆球
        cv.create_arc(cx - r * 0.94, cy - r * 0.28, cx + r * 0.94, cy + r * 1.02,
                      start=180, extent=180, style="chord",
                      fill=shade(color, 1.30), outline="")

        # 脸：眼睛 + 嘴 + 腮红
        eye = "#102a44"
        if state == "alert":
            # >_< ：三点点折线画"用力闭眼"，比圆眼更符合"喷水警告"的表情
            for sgn in (-1, 1):
                cv.create_line(cx + sgn * r * 0.46, cy - r * 0.18,
                               cx + sgn * r * 0.20, cy,
                               cx + sgn * r * 0.46, cy + r * 0.18,
                               fill=eye, width=3, capstyle="round", joinstyle="round")
            cv.create_oval(cx - r * 0.17, cy + r * 0.18, cx + r * 0.17, cy + r * 0.46,
                           fill="#7d2b3a", outline="")
        else:
            for sgn in (-1, 1):
                cv.create_oval(cx + sgn * r * 0.44 - r * 0.15, cy - r * 0.16,
                               cx + sgn * r * 0.44 + r * 0.15, cy + r * 0.16,
                               fill=eye, outline="")
                cv.create_oval(cx + sgn * r * 0.44 - r * 0.09, cy - r * 0.10,
                               cx + sgn * r * 0.44 + r * 0.02, cy + r * 0.02,
                               fill="#ffffff", outline="")
            cv.create_arc(cx - r * 0.22, cy + r * 0.16, cx + r * 0.22, cy + r * 0.46,
                          start=200, extent=140, style="arc",
                          outline="#8c4a3a", width=2)
        for sgn in (-1, 1):
            cv.create_oval(cx + sgn * r * 0.78 - r * 0.20, cy + r * 0.16,
                           cx + sgn * r * 0.78 + r * 0.20, cy + r * 0.38,
                           fill=BLUSH, outline="")

        # 中心读数：距离水平百分比（远 = 小，贴脸 = 100%）
        cv.create_text(cx, cy + r * 0.74, text="%d%%" % round(ratio * 100),
                       fill="#ffffff", font=FONT_TINY)

    def _ball_tip_text(self, ratio, state):
        if state == "alert":
            mood = "喷水警告！快退后 (๑•̀ㅂ•́)و✧"
        elif state in ("near", "cooldown"):
            mood = "有点近了哦，鲸鱼娘在盯着你 (；・∀・)"
        elif state == "noface":
            mood = "还没看到你的脸 (っ˘ω˘ς)"
        elif state == "far":
            mood = "离得挺远，很乖～"
        else:
            mood = "距离很健康，继续保持！(๑˃ᴗ˂)ﻭ"
        return ("鲸鱼娘悬浮球 ｜ 距离水平 %d%%\n%s\n拖动可移动 · 双击回到主窗口 · 右键更多"
                % (round(ratio * 100), mood))

    def _ball_tip_show(self, _event=None):
        if self._ball is None or not self._ball.winfo_exists():
            return
        ratio, state = self._distance_ratio()
        if self._ball_tip is None or not self._ball_tip.winfo_exists():
            t = tk.Toplevel(self._ball)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            bg = KEY_COLOR if try_transparent(t) else PANEL
            t.configure(bg=bg)
            lbl = tk.Label(t, text="", font=FONT_SMALL, bg=bg, fg=TXT,
                           justify="left", padx=14, pady=10)
            lbl.pack()
            self._ball_tip, self._ball_tip_lbl = t, lbl
        self._ball_tip_lbl.configure(text=self._ball_tip_text(ratio, state))
        self._ball_tip.update_idletasks()
        bx, by = self._ball.winfo_x(), self._ball.winfo_y()
        tw, th = self._ball_tip.winfo_reqwidth(), self._ball_tip.winfo_reqheight()
        x = max(0, min(bx + self.BALL_SIZE - tw, self._ball.winfo_screenwidth() - tw - 8))
        y = by - th - 10
        if y < 0:
            y = by + self.BALL_SIZE + 10
        self._ball_tip.geometry("+%d+%d" % (int(x), int(y)))

    def _ball_tip_hide(self, _event=None):
        if self._ball_tip is not None and self._ball_tip.winfo_exists():
            self._ball_tip.destroy()
        self._ball_tip = None
        self._ball_tip_lbl = None

    def _ball_press(self, event):
        if self._ball is None:
            return
        self._ball_drag = (event.x_root - self._ball.winfo_x(),
                           event.y_root - self._ball.winfo_y())

    def _ball_drag_move(self, event):
        if self._ball is None or self._ball_drag is None:
            return
        x = event.x_root - self._ball_drag[0]
        y = event.y_root - self._ball_drag[1]
        self._ball_pos = (x, y)
        self._ball.geometry("+%d+%d" % (x, y))

    def _ball_menu(self, event):
        m = tk.Menu(self.root, tearoff=0, bg=PANEL, fg=TXT,
                    activebackground=ACCENT, activeforeground="white", bd=0)
        m.add_command(label="回到主窗口", command=self._restore_window)
        if self._running:
            m.add_command(label="暂停检测", command=self.stop_cam)
        m.add_separator()
        m.add_command(label="退出 FaceGuard", command=self._on_close)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _restore_window(self):
        """从悬浮球回到主窗口。"""
        self._hide_ball()
        try:
            self.root.deiconify()
            self.root.state("normal")
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    # ---------------- 提醒：弹窗 / 悬浮字幕 / 提示音 ----------------

    def _on_alert(self, payload):
        kaomoji, body = payload["popup"]
        if self.var_popup.get():
            self._show_popup(kaomoji, body)
        if self.var_float.get():
            self._show_float(payload["float"])
        self._play_sound()

    def _show_popup(self, kaomoji, body):
        """鲸鱼娘弹窗（非模态，自动 9 秒关闭；重复报警时复用同一个窗口刷新文案）。
        注意：故意不用 messagebox（模态会卡住主循环），也不用 transient
        （transient 窗口会随主窗口最小化而隐藏，违背"最小化仍要提醒"）。"""
        if self._popup is not None and self._popup.winfo_exists():
            pop = self._popup
        else:
            pop = tk.Toplevel(self.root)
            pop.title("%s · 护眼提醒" % APP_NAME)
            pop.configure(bg=PANEL)
            pop.resizable(False, False)
            pop.attributes("-topmost", True)     # 置顶，玩游戏/写代码也看得见

            # 顶部：蓝鲸渐变头图 + 鲸鱼娘 + 大字颜文字（全画在同一块 Canvas 上）
            head = tk.Canvas(pop, width=470, height=104, bg=PANEL,
                             highlightthickness=0, bd=0)
            head.pack(fill="x")
            paint_gradient(head, 470, 104, GRAD_TOP, PANEL, tag="pop_grad")
            self._put_mascot(head, MASCOT_HEAD, 58, 54, 88, fallback=84, mood="alert")
            title_id = head.create_text(112, 40, text="", anchor="w",
                                        font=FONT_POP, fill=ACCENT_LT)
            head.create_text(112, 72, text="鲸鱼娘 · 护眼提醒", anchor="w",
                             font=FONT_SMALL, fill=TXT_DIM)

            body_lbl = tk.Label(pop, text="", font=FONT_UI, fg=TXT, bg=PANEL,
                                justify="left", padx=20, pady=14, wraplength=430)
            body_lbl.pack(fill="x")
            tk.Button(pop, text="知道啦～(๑•̀ㅂ•́)و✧", font=FONT_BTN, bg=ACCENT,
                      fg="white", activebackground=ACCENT_DK, activeforeground="white",
                      relief="flat", padx=16, pady=5, cursor="hand2",
                      command=pop.destroy).pack(pady=(0, 16))
            self._popup = pop
            self._popup_items = (head, title_id, body_lbl)
        head, title_id, body_lbl = self._popup_items
        head.itemconfigure(title_id, text=kaomoji)
        body_lbl.configure(text=body)
        pop.update_idletasks()
        sw = pop.winfo_screenwidth()
        pop.geometry("+%d+140" % max(0, int((sw - pop.winfo_reqwidth()) / 2)))
        if self._popup_after is not None:
            try:
                self.root.after_cancel(self._popup_after)
            except Exception:
                pass
        self._popup_after = self.root.after(9000, self._close_popup)

    def _close_popup(self):
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.destroy()
        self._popup_after = None

    def _show_float(self, text):
        """屏幕右上角悬浮字幕：圆角胶囊 + 小鲸鱼娘，6 秒后自动消失。

        圆角和四角透明都靠"色键透明"实现（仅 Windows 有效），
        不支持时退化成深蓝方块背景，功能不受影响。
        """
        if self._float is not None and self._float.winfo_exists():
            f = self._float
        else:
            f = tk.Toplevel(self.root)
            f.overrideredirect(True)             # 无边框
            f.attributes("-topmost", True)
            self._float_bg = KEY_COLOR if try_transparent(f) else PANEL
            f.configure(bg=self._float_bg)
            self._float_canvas = tk.Canvas(f, bg=self._float_bg,
                                           highlightthickness=0, bd=0)
            self._float_canvas.pack()
            self._float = f

        cv = self._float_canvas
        font = tkfont.Font(family=_FONT, size=13, weight="bold")
        icon, pad = 40, 16
        w = int(font.measure(text) + icon + pad * 3)
        h = max(58, int(font.metrics("linespace") + pad * 2))
        cv.configure(width=w, height=h)
        cv.delete("all")
        if self._float_bg != KEY_COLOR:          # 不能透明时铺一层深底兜底
            cv.create_rectangle(0, 0, w, h, fill=PANEL, outline="")
        round_rect(cv, 2, 2, w - 2, h - 2, h / 2.0,
                   fill=PANEL_2, outline=ACCENT, width=2)
        self._put_mascot(cv, MASCOT_HEAD, pad + icon / 2.0, h / 2.0, icon,
                         fallback=icon, mood="alert")
        cv.create_text(pad + icon + pad * 0.5, h / 2.0, text=text, anchor="w",
                       fill=TXT, font=font)
        f.update_idletasks()
        x = f.winfo_screenwidth() - f.winfo_reqwidth() - 24
        f.geometry("+%d+90" % max(0, int(x)))
        if self._float_after is not None:
            try:
                self.root.after_cancel(self._float_after)
            except Exception:
                pass
        self._float_after = self.root.after(6000, self._hide_float)

    def _hide_float(self):
        if self._float is not None and self._float.winfo_exists():
            self._float.destroy()
        self._float_after = None

    def _play_sound(self):
        """两声下行提示音。放在子线程：winsound.Beep 是阻塞调用，别卡 UI。"""
        if not self.var_sound.get() or winsound is None:
            return

        def _beep():
            try:
                winsound.Beep(1046, 150)   # 哆～
                time.sleep(0.03)
                winsound.Beep(784, 280)    # 咦～（下行两音 = "注意"）
            except Exception:
                pass

        threading.Thread(target=_beep, daemon=True).start()

    # ---------------- 退出清理 ----------------

    def _on_close(self):
        try:
            self._hide_ball()
            if self.worker and self.worker.is_alive():
                self.worker.stop()
                self.worker.join(timeout=2.0)
        finally:
            self.root.destroy()


# ================================ 入口 ================================

def main():
    # 打包脚本会调用：python face_guard.py --cascade-path
    # → 打印 Haar 模型的绝对路径后退出，build.bat 用它来拼 --add-data 参数
    if "--cascade-path" in sys.argv:
        path = find_cascade_path()
        if path:
            print(path)
            return
        print("CASCADE_NOT_FOUND", file=sys.stderr)
        sys.exit(1)

    try:
        root = tk.Tk()
        FaceGuardApp(root)
        root.mainloop()
    except Exception:
        detail = traceback.format_exc()
        log_error(detail)
        try:
            messagebox.showerror(APP_NAME, "启动失败：\n%s\n\n详细日志见同目录 face_guard_error.log"
                                 % detail[-500:])
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
