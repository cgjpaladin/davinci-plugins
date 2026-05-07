#!/usr/bin/env python3
"""批量分析短剧截图的字幕像素区域 - v2 改进版。

改进策略：
1. 先检测暗色半透明背景条（短剧字幕几乎都有）
2. 在底条区域内检测亮色文字
3. 返回底条 + 文字的并集范围
"""

import sys
import os
import json
import statistics
from PIL import Image


def get_row_brightness(gray_pixels, w, y, step=4):
    """获取某一行的平均亮度（隔step列采样提速）。"""
    vals = [gray_pixels[x, y] for x in range(0, w, step)]
    return sum(vals) / len(vals) if vals else 0


def get_row_brightness_detail(gray_pixels, w, y, step=2):
    """获取某一行的亮度列表（用于计算方差）。"""
    return [gray_pixels[x, y] for x in range(0, w, step)]


def find_dark_bar(gray_pixels, h, w):
    """
    在底部区域寻找暗色背景条。
    
    短剧字幕特征：画面底部有一个暗色半透明横条，通常 60-200px 高。
    寻找方法：底部 40% 区域内，亮度明显低于周围的行组成连续区域。
    """
    bottom_40_start = int(h * 0.60)
    
    # 计算底部 40% 每行的平均亮度
    row_brightness = []
    for y in range(bottom_40_start, h):
        b = get_row_brightness(gray_pixels, w, y)
        row_brightness.append((y, b))
    
    if not row_brightness:
        return None
    
    # 找亮度最低的连续区域（暗色底条）
    brightness_values = [b for _, b in row_brightness]
    global_mean = statistics.mean(brightness_values)
    
    # 亮度低于均值至少 15 的行视为 "暗行"
    dark_threshold = global_mean - 15
    dark_rows = [y for y, b in row_brightness if b < dark_threshold]
    
    if not dark_rows:
        # 放宽阈值，用低于均值的行
        dark_rows = [y for y, b in row_brightness if b < global_mean]
    
    if not dark_rows:
        return None
    
    # 找连续的暗行区域（至少 30px 高，间隔不超过 10px 视为连续）
    regions = []
    region_start = dark_rows[0]
    prev_y = dark_rows[0]
    
    for y in dark_rows[1:]:
        if y - prev_y > 10:
            if prev_y - region_start >= 30:
                regions.append((region_start, prev_y))
            region_start = y
        prev_y = y
    
    if prev_y - region_start >= 30:
        regions.append((region_start, prev_y))
    
    if not regions:
        return None
    
    # 返回最底部最大的暗色区域（通常就是字幕底条）
    # 按高度和位置排序：优先底部 + 足够大的
    regions.sort(key=lambda r: (r[1] * 0.7 + (r[1] - r[0]) * 0.3), reverse=True)
    
    best = regions[0]
    return best


def analyze_subtitle_in_bar(gray_pixels, w, bar_top, bar_bottom):
    """在暗色底条内分析文字位置。"""
    # 扫描底条内每行，找亮度高的像素（文字）
    text_row_indicators = []
    for y in range(bar_top, bar_bottom + 1):
        row_vals = get_row_brightness_detail(gray_pixels, w, y, step=4)
        if len(row_vals) < 2:
            continue
        row_mean = sum(row_vals) / len(row_vals)
        
        # 计算亮点比例（文字通常较亮）
        bright_count = sum(1 for v in row_vals if v > 160)
        bright_ratio = bright_count / len(row_vals)
        
        # 方差高说明有文字边缘
        variance = sum((v - row_mean) ** 2 for v in row_vals) / len(row_vals)
        
        text_row_indicators.append({
            'y': y,
            'bright_ratio': bright_ratio,
            'variance': variance
        })
    
    if not text_row_indicators:
        return bar_top, bar_bottom
    
    # 找出方差最高的行（文字区域）
    var_mean = statistics.mean([t['variance'] for t in text_row_indicators])
    var_std = statistics.stdev([t['variance'] for t in text_row_indicators]) if len(text_row_indicators) > 1 else 0
    var_threshold = var_mean + var_std * 0.5  # 宽松阈值
    
    text_rows = [t['y'] for t in text_row_indicators if t['variance'] > var_threshold]
    
    if len(text_rows) >= 15:
        # 有足够的文字行，返回文字的实际范围
        return min(text_rows), max(text_rows)
    else:
        # 文字行太少，可能检测不准，返回底条范围（安全做法）
        return bar_top, bar_bottom


def analyze_image(filepath):
    """分析单张截图的字幕区域（v2改进版）。"""
    img = Image.open(filepath)
    w, h = img.size
    gray = img.convert('L')
    gray_pixels = gray.load()
    
    # 步骤1：检测暗色底条
    dark_bar = find_dark_bar(gray_pixels, h, w)
    
    if dark_bar is None:
        # fallback: 尝试传统方法
        return fallback_analyze(gray_pixels, w, h, filepath)
    
    bar_top, bar_bottom = dark_bar
    bar_height = bar_bottom - bar_top
    
    # 步骤2：在底条内检测文字
    text_top, text_bottom = analyze_subtitle_in_bar(gray_pixels, w, bar_top, bar_bottom)
    
    # 步骤3：取底条和文字范围的并集（保证覆盖）
    y_min = min(bar_top, text_top)
    y_max = max(bar_bottom, text_bottom)
    
    return {
        'file': os.path.basename(filepath),
        'dimensions': f"{w}x{h}",
        'subtitle_region': {
            'y_min': y_min,
            'y_max': y_max,
            'height': y_max - y_min,
            'y_ratio': f"{y_min/h:.1%} - {y_max/h:.1%}",
            'dark_bar': f"{bar_top}~{bar_bottom}",
            'text': f"{text_top}~{text_bottom}"
        },
        'confidence': 'high' if bar_height >= 40 else 'medium'
    }


def fallback_analyze(gray_pixels, w, h, filepath):
    """传统方法兜底。"""
    # 简单取底部20%检测
    bottom_start = int(h * 0.80)
    row_vars = []
    for y in range(bottom_start, h):
        vals = get_row_brightness_detail(gray_pixels, w, y, step=4)
        if len(vals) < 2:
            row_vars.append(0)
            continue
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        row_vars.append(var)
    
    if not row_vars or all(v == 0 for v in row_vars):
        return {
            'file': os.path.basename(filepath),
            'dimensions': f"{w}x{h}",
            'subtitle_region': None,
            'confidence': 'low'
        }
    
    var_mean = statistics.mean(row_vars)
    var_std = statistics.stdev(row_vars) if len(row_vars) > 1 else 0
    threshold = var_mean + var_std * 0.5
    
    text_rows = [bottom_start + i for i, v in enumerate(row_vars) if v > threshold]
    
    if len(text_rows) < 5:
        return {
            'file': os.path.basename(filepath),
            'dimensions': f"{w}x{h}",
            'subtitle_region': None,
            'confidence': 'low'
        }
    
    return {
        'file': os.path.basename(filepath),
        'dimensions': f"{w}x{h}",
        'subtitle_region': {
            'y_min': min(text_rows),
            'y_max': max(text_rows),
            'height': max(text_rows) - min(text_rows),
            'y_ratio': f"{min(text_rows)/h:.1%} - {max(text_rows)/h:.1%}",
            'method': 'fallback'
        },
        'confidence': 'low'
    }


def main():
    src_dir = sys.argv[1] if len(sys.argv) > 1 else '/Volumes/MYJC/09_Engineering/字幕位置统计'
    
    if not os.path.isdir(src_dir):
        print(f"错误: 目录不存在 {src_dir}")
        sys.exit(1)

    jpgs = sorted([f for f in os.listdir(src_dir) if f.lower().endswith('.jpg')])
    print(f"分析 {len(jpgs)} 张截图（v2 暗色底条检测法）...\n")

    results = []
    y_mins, y_maxs, heights = [], [], []

    for i, jpg in enumerate(jpgs):
        path = os.path.join(src_dir, jpg)
        result = analyze_image(path)
        results.append(result)
        
        if result['subtitle_region']:
            r = result['subtitle_region']
            y_mins.append(r['y_min'])
            y_maxs.append(r['y_max'])
            heights.append(r['height'])

        status = "OK" if result['confidence'] == 'high' else ("LOW" if result['confidence'] == 'low' else "MED")
        region_str = result['subtitle_region']['y_ratio'] if result['subtitle_region'] else "未检测到"
        detail = ""
        if result['subtitle_region'] and 'dark_bar' in result['subtitle_region']:
            detail = f"  底条{result['subtitle_region']['dark_bar']} | 文字{result['subtitle_region']['text']}"
        print(f" [{status}] {result['file']}")
        print(f"       {region_str}{detail}")

    print(f"\n{'='*70}")
    print("最终推荐覆盖范围")
    print(f"{'='*70}")

    if y_mins:
        overall_min = min(y_mins)
        overall_max = max(y_maxs)
        overall_height = overall_max - overall_min
        ref_h = int(results[0]['dimensions'].split('x')[1])

        # 加安全边距
        safe_margin = max(10, int(overall_height * 0.15))
        safe_min = max(0, overall_min - safe_margin)
        safe_max = min(ref_h, overall_max + safe_margin)

        print(f"""
  推荐像素范围:  Y = {overall_min} ~ {overall_max}
  画面占比:      {overall_min/ref_h:.1%} ~ {overall_max/ref_h:.1%}
  字幕总高度:    {overall_height} px
  安全边距版:    Y = {safe_min} ~ {safe_max} (±{safe_margin}px 缓冲)

  检测统计:
    {len(y_mins)}/{len(results)} 张检测到字幕
    Y_min: {min(y_mins)} ~ {max(y_mins)}   (跨度 {max(y_mins)-min(y_mins)}px)
    Y_max: {min(y_maxs)} ~ {max(y_maxs)}   (跨度 {max(y_maxs)-min(y_maxs)}px)
    高度:  {min(heights)} ~ {max(heights)} px (均值 {sum(heights)//len(heights)}px)

  置信度分布:
    HIGH: {sum(1 for r in results if r['confidence']=='high')} 张
    MED:  {sum(1 for r in results if r['confidence']=='medium')} 张
    LOW:  {sum(1 for r in results if r['confidence']=='low')} 张
""")
        
        # 按 Y_min 排序看分布
        sorted_by_ymin = sorted([(r['file'], r['subtitle_region']['y_min'] if r['subtitle_region'] else 0) 
                                  for r in results], key=lambda x: x[1])
        print("  Y_min 分布（从小到大）:")
        for fname, ymin in sorted_by_ymin[:5]:
            print(f"    {fname}: {ymin}")
        if len(sorted_by_ymin) > 10:
            print(f"    ... ({len(sorted_by_ymin)-10} 张省略)")
        for fname, ymin in sorted_by_ymin[-5:]:
            print(f"    {fname}: {ymin}")

        # 输出 JSON
        report = {
            'source_dir': src_dir,
            'total_images': len(results),
            'detected': len(y_mins),
            'undetected': len(results) - len(y_mins),
            'resolution': results[0]['dimensions'],
            'confidence': {
                'high': sum(1 for r in results if r['confidence']=='high'),
                'medium': sum(1 for r in results if r['confidence']=='medium'),
                'low': sum(1 for r in results if r['confidence']=='low'),
            },
            'recommended_region': {
                'y_min': overall_min,
                'y_max': overall_max,
                'height_px': overall_height,
                'safe_region': {
                    'y_min': safe_min,
                    'y_max': safe_max,
                    'margin_px': safe_margin,
                }
            },
            'per_image': results
        }

        json_path = os.path.join(src_dir, 'subtitle_analysis_report.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n  JSON 报告: {json_path}")
    else:
        print("  未检测到任何字幕区域。")

    print(f"\n{'='*70}")


if __name__ == '__main__':
    main()
