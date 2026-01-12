import gradio as gr
import threading
import json
import os
import re
import subprocess
import sys
from lib_helper import load_json_with_comments
import Framework
from STT.STTServer import DONE as STT_DONE

# Globals to keep running Framework instance
_framework = None
_framework_thread = None
_framework_lock = threading.Lock()
_prev_framework_running = False
_finish_notified = False

SETTINGS_PATH = os.path.normpath("settings.json")


def _parse_json_with_comments(text: str) -> dict:
    """Parse JSON text that may contain // comments or /* */ comments."""
    placeholder1 = "#占位符1#"
    placeholder2 = "#占位符2#"
    t = text.replace("https://", placeholder1).replace("http://", placeholder2)
    t = re.sub(r'//.*$', '', t, flags=re.MULTILINE)
    t = re.sub(r'/\*.*?\*/', '', t, flags=re.DOTALL)
    t = t.replace(placeholder1, "https://").replace(placeholder2, "http://")
    return json.loads(t)

def load_settings_raw():
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as f: raw = f.read()
    except Exception as e: return f'Error reading {SETTINGS_PATH}: {e}', {}
    try: parsed = _parse_json_with_comments(raw)
    except Exception as e:
        # try to use helper that strips comments from file
        try: parsed = load_json_with_comments(SETTINGS_PATH)
        except Exception as e2: return raw, {}
        return raw, parsed
    return raw, parsed

def save_settings_dict(settings: dict) -> tuple[str, dict]:
    try:
        with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
        pretty = json.dumps(settings, ensure_ascii=False, indent=4)
        return pretty, settings
    except Exception as e:
        return f'Error saving settings: {e}', settings

def load_settings_to_controls():
    raw, settings = load_settings_raw()
    if not settings: return raw, False, 50, False, "https://cn.bing.com/search?q={query}", True, 3, "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", True, True, 0.5, True, "medium", 0.7, "", "", "", "", "", "", "", "", "", "", "无法解析settings.json"

    # read only the allowed, leaving other settings untouched
    enable_refine = settings.get('enable_refine', False)
    chunk_size = settings.get('chunk_size', 50)
    crawler_enable = settings.get('Crawler', {}).get('enable_crawler', False)
    crawler_website = settings.get('Crawler', {}).get('website', '')
    search_local = settings.get('search_local', False)
    enable_parallel = settings.get('enable_parallel', True)
    max_retry = settings.get('max_retry', 3)
    embedding_model_name = settings.get('embedding_model_name', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    delete_stt = settings.get('delete_stt', True)
    global_memory = settings.get('global_memory', True)
    delay_segment_ends = settings.get('delay_segment_ends', 0.5)
    do_log = settings.get('do_log', True)

    stt_model = settings.get('stts', {}).get('engine_settings', {}).get('model', 'medium')
    no_speech_threshold = settings.get('stts', {}).get('engine_settings', {}).get('no_speech_threshold', 0.7)

    small = settings.get('llms', {}).get('SmallModel', {})
    small_api_key = small.get('api_key', '')
    small_api_base = small.get('api_base', '')
    small_model = small.get('model', '')
    small_temperature = small.get('temperature', 1.0)

    large = settings.get('llms', {}).get('LargeModelJson', {})
    large_api_key = large.get('api_key', '')
    large_api_base = large.get('api_base', '')
    large_model = large.get('model', '')
    large_temperature = large.get('temperature', 1.0)

    # do not load or save description from file; description is runtime-only
    desc_text = ''

    return enable_refine, chunk_size, crawler_enable, crawler_website, search_local, enable_parallel, max_retry, embedding_model_name, delete_stt, global_memory, delay_segment_ends, do_log, stt_model, no_speech_threshold, small_api_key, small_api_base, small_model, small_temperature, large_api_key, large_api_base, large_model, large_temperature, desc_text, "已加载settings.json"

def save_settings_from_controls(enable_refine, chunk_size, crawler_enable, crawler_website, search_local, enable_parallel, max_retry, embedding_model_name, delete_stt, global_memory, delay_segment_ends, do_log, stt_model, no_speech_threshold, small_api_key, small_api_base, small_model, small_temperature, large_api_key, large_api_base, large_model, large_temperature, desc_text):
    # load current settings file
    try: settings = load_json_with_comments(SETTINGS_PATH)
    except Exception as e: return f"无法读取 {SETTINGS_PATH}: {e}"

    # update only allowed fields
    settings['enable_refine'] = bool(enable_refine)
    settings['chunk_size'] = int(chunk_size)
    settings.setdefault('Crawler', {})['enable_crawler'] = bool(crawler_enable)
    settings['Crawler']['website'] = crawler_website
    settings['search_local'] = bool(search_local)
    settings['enable_parallel'] = bool(enable_parallel)
    settings['max_retry'] = int(max_retry)
    settings['embedding_model_name'] = embedding_model_name
    settings['delete_stt'] = bool(delete_stt)
    settings['global_memory'] = bool(global_memory)
    settings['delay_segment_ends'] = float(delay_segment_ends)
    settings['do_log'] = bool(do_log)

    settings.setdefault('stts', {}).setdefault('engine_settings', {})['model'] = stt_model
    settings.setdefault('stts', {}).setdefault('engine_settings', {})['no_speech_threshold'] = float(no_speech_threshold)

    settings.setdefault('llms', {}).setdefault('SmallModel', {})['api_key'] = small_api_key
    settings.setdefault('llms', {}).setdefault('SmallModel', {})['api_base'] = small_api_base
    settings.setdefault('llms', {}).setdefault('SmallModel', {})['model'] = small_model
    settings.setdefault('llms', {}).setdefault('SmallModel', {})['temperature'] = float(small_temperature)

    settings.setdefault('llms', {}).setdefault('LargeModelJson', {})['api_key'] = large_api_key
    settings.setdefault('llms', {}).setdefault('LargeModelJson', {})['api_base'] = large_api_base
    settings.setdefault('llms', {}).setdefault('LargeModelJson', {})['model'] = large_model
    settings.setdefault('llms', {}).setdefault('LargeModelJson', {})['temperature'] = float(large_temperature)

    # description is runtime-only; we do NOT save it to disk here

    pretty, saved = save_settings_dict(settings)
    if pretty.startswith('Error'): return pretty
    return "已保存settings.json"

def _start_framework(description_text: str=""):
    global _framework, _framework_thread, _prev_framework_running, _finish_notified
    with _framework_lock:
        if _framework_thread and _framework_thread.is_alive():
            return "Framework 已在运行"
        try:
            _ = load_json_with_comments(SETTINGS_PATH)
        except Exception:
            return "无法读取settings，无法启动"
        try:
            _framework = Framework.Framework(description_override=description_text.strip() if description_text else None)
        except Exception as e:
            return f"新建 Framework 失败: {e}"
        def target():
            try:
                _framework.run()
            except Exception as e:
                print(f"Framework 运行失败: {e}")
            finally:
                # try to clear the runtime description in the UI
                try:
                    description_widget = globals().get('description_text')
                    if description_widget is not None:
                        description_widget.value = ""
                except Exception:
                    pass
        _framework_thread = threading.Thread(target=target, daemon=True)
        _framework_thread.start()
        # live update helpers
        _prev_framework_running = True
        _finish_notified = False
        return "Framework 已启动"

def _stop_framework():
    global _framework, _framework_thread
    with _framework_lock:
        if not _framework or not _framework_thread or not _framework_thread.is_alive(): return "Framework 未在运行"
        try:
            if hasattr(_framework, 'processing_queue') and _framework.processing_queue: _framework.processing_queue.put(STT_DONE)
            return "停止信号已发送"
        except Exception as e: return f"停止失败: {e}"


def _open_dir(path: str) -> str:
    try:
        if not os.path.exists(path): return f"目录不存在: {path}"
        if os.name == 'nt': os.startfile(path)
        else:
            if sys.platform == 'darwin': subprocess.Popen(['open', path])
            else: subprocess.Popen(['xdg-open', path])
        return f"已打开目录: {path}"
    except Exception as e:
        return f"打开目录失败: {e}"

def _open_input_dir(): return _open_dir(os.path.normpath("input"))

def _open_output_dir(): return _open_dir(os.path.normpath("output"))

def get_status():
    global _framework_thread
    if _framework_thread and _framework_thread.is_alive(): return "运行中..."
    return "未运行"

def update_live_view():
    global _prev_framework_running, _finish_notified, _framework_thread

    running = bool(_framework_thread and _framework_thread.is_alive())
    status_text = "运行中..." if running else "未运行"

    need_status = False
    need_desc = False
    desc_update = None

    if _prev_framework_running and not running and not _finish_notified:
        status_text = "运行完毕"
        _finish_notified = True
        desc_update = ""
        need_status = True
        need_desc = True
    else:
        if _prev_framework_running != running: need_status = True

    _prev_framework_running = running

    status_out = gr.update(value=status_text) if need_status else gr.update()
    desc_out = gr.update(value=desc_update) if need_desc else gr.update()

    return status_out, desc_out



# Build Gradio UI
with gr.Blocks(title="烤肉机") as demo:

    gr.Markdown("## 烤肉机控制面板")
    with gr.Tab("主程序"):
        with gr.Row():
            with gr.Column(scale=1):
                start_btn = gr.Button("运行")
                stop_btn = gr.Button("发送停止信号")
                status = gr.Textbox(label="运行状态", interactive=False)
                with gr.Row():
                    open_input_btn = gr.Button("打开输入目录")
                    open_output_btn = gr.Button("打开输出目录")
            with gr.Column(scale=2):
                description_text = gr.TextArea(label="在此插入对翻译内容的简短描述", lines=8)

    with gr.Tab("设置"):
        save_btn = gr.Button("保存设置")
        load_btn = gr.Button("还原至上次保存的设置")
        status_box = gr.Textbox(label="信息", interactive=False)

        with gr.Row():

            with gr.Column():
                gr.Markdown("### 用于翻译的较大模型设置")
                large_api_key = gr.Textbox(label="密钥", type="password", info="例如：sk-114514")
                large_api_base = gr.Textbox(label="API端点链接", info="例如：https://api.openai.com/v1")
                large_model = gr.Textbox(label="模型名称")
                large_temperature = gr.Number(label="Temperature", value=1.0)
                gr.Markdown("### 用于调用工具的较小模型设置")
                small_api_key = gr.Textbox(label="密钥", type="password", info="例如：sk-114514")
                small_api_base = gr.Textbox(label="API端点链接", info="例如：https://api.openai.com/v1")
                small_model = gr.Textbox(label="模型名称")
                small_temperature = gr.Number(label="Temperature", value=1.0)

            with gr.Column():
                gr.Markdown("### 主要设置")
                search_local = gr.Checkbox(label="启用本地搜索功能", info="通过对历史翻译进行检索以优化翻译")
                global_memory = gr.Checkbox(label="不同音视频文件间是否共享记忆", info="如果选择，那么翻译时查询信息时会查询其他剧集中保存的历史翻译。")
                enable_refine = gr.Checkbox(label="启用润色功能", info="会消耗更多token")
                
                gr.Markdown("### 转录设置")
                stt_model = gr.Dropdown(choices=["tiny","base","small","medium","large"], label="转录模型大小", info="模型越大效果越好，但会消耗更多运算资源和时间")
                no_speech_threshold = gr.Number(label="无语音判断阈值", value=0.7, info="该值越大，模型越倾向于判断音频中无语音内容，从而跳过该部分内容的转录。一般无需调整该值。")
                
                gr.Markdown("### 爬虫设置")
                crawler_enable = gr.Checkbox(label="是否启用网络搜索以获取更多背景信息")
                crawler_website = gr.Textbox(label="搜索引擎", info="在此输入搜索引擎的网址，使用 {query} 作为查询占位符，例如：https://cn.bing.com/search?q={query}")

                gr.Markdown("### 其他设置")
                chunk_size = gr.Number(label="每次处理几个句子", value=50)
                enable_parallel = gr.Checkbox(label="启用转录与翻译的并行进行")
                delete_stt = gr.Checkbox(label="是否在翻译完毕后删除临时转录文件")
                max_retry = gr.Number(label="搜索功能最大尝试次数", value=3, info="防止无限循环")
                embedding_model_name = gr.Textbox(label="词嵌入模型名称", value="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
                delay_segment_ends = gr.Number(label="字幕结束延迟", value=0.5, info="每个字幕片段结束的时间延长多少秒。防止字幕过早消失。")
                do_log = gr.Checkbox(label="是否记录日志")

    # Bind callbacks
    load_btn.click(fn=load_settings_to_controls, outputs=[enable_refine, chunk_size, crawler_enable, crawler_website, search_local, enable_parallel, max_retry, embedding_model_name, delete_stt, global_memory, delay_segment_ends, do_log, stt_model, no_speech_threshold, small_api_key, small_api_base, small_model, small_temperature, large_api_key, large_api_base, large_model, large_temperature, description_text, status_box])
    save_btn.click(fn=save_settings_from_controls, inputs=[enable_refine, chunk_size, crawler_enable, crawler_website, search_local, enable_parallel, max_retry, embedding_model_name, delete_stt, global_memory, delay_segment_ends, do_log, stt_model, no_speech_threshold, small_api_key, small_api_base, small_model, small_temperature, large_api_key, large_api_base, large_model, large_temperature, description_text], outputs=[status_box])

    start_btn.click(fn=_start_framework, inputs=[description_text], outputs=[status])
    stop_btn.click(fn=_stop_framework, outputs=[status])

    open_input_btn.click(fn=_open_input_dir, outputs=[status])
    open_output_btn.click(fn=_open_output_dir, outputs=[status])

    timer = gr.Timer(value=1.0)
    timer.tick(fn=update_live_view, outputs=[status, description_text])

    # Initial load: populate controls
    vals = load_settings_to_controls()
    try: (enable_refine.value, chunk_size.value, crawler_enable.value, crawler_website.value, search_local.value, enable_parallel.value, max_retry.value, embedding_model_name.value, delete_stt.value, global_memory.value, delay_segment_ends.value, do_log.value, stt_model.value, no_speech_threshold.value, small_api_key.value, small_api_base.value, small_model.value, small_temperature.value, large_api_key.value, large_api_base.value, large_model.value, large_temperature.value, description_text.value, msg) = vals
    except Exception: pass

    # ========== 自定义页脚区域 ==========
    gr.HTML("""<div style="height: 1px; background: #e0e0e0; margin: 40px 0;"></div>""")
    
    with gr.Column():
        gr.HTML("""
        <div style="
            width: 100%;
            text-align: center;
            padding: 25px 0;
            color: #666;
            font-family: 'Segoe UI', Arial, sans-serif;
        ">
            <p style="font-size: 14px; margin-bottom: 10px;">
            </p>
            <div style="margin: 15px 0;">
                <a href="https://github.com/DDRP674/Roaster" 
                    target="_blank" 
                    style="
                        display: inline-block;
                        padding: 8px 20px;
                        background: linear-gradient(45deg, #0366d6, #28a745);
                        color: white;
                        text-decoration: none;
                        border-radius: 20px;
                        font-weight: 500;
                        transition: transform 0.2s;
                    "
                    onmouseover="this.style.transform='translateY(-2px)'"
                    onmouseout="this.style.transform='translateY(0)'">
                    <i class="fab fa-github"></i> &nbsp;欢迎访问Github项目地址
                </a>
            </div>
            <p style="font-size: 12px; margin-top: 15px; opacity: 0.7;">
                版本 1.1
            </p>
        </div>
        """)

        gr.HTML("""
        <div style="text-align: center; padding: 20px; color: #666;">
            <div style="display: flex; justify-content: center; gap: 15px; margin: 15px 0;">
                <a href="https://opensource.org/licenses/MIT" target="_blank">
                    <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License">
                </a>
                <a href="https://github.com/996icu/996.ICU" target="_blank">
                    <img src="https://img.shields.io/badge/License-Anti%20996-red.svg" alt="Anti 996 License">
                </a>
            </div>
        </div>
        """)

if __name__ == "__main__": demo.launch()
