import json
import logging
import queue
import shutil
import sys, os, uuid
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib_helper import load_json_with_comments, func_name

# 这个库只负责把音频转换为json格式的字幕，存放在指定路径下。

DONE = "#DONE"

class STTServer:
    def __init__(self, initial_prompt: str|None=None): 
        self.settings = load_json_with_comments('settings.json')
        self.input_dir = os.path.normpath(self.settings.get('input_dir', './input'))
        self.exts = self.settings.get('input_exts', ['.mp3', '.wav', '.m4a', '.flac', '.mp4', '.mkv', '.avi'])
        self.settings = self.settings['stts']
        self.output_dir = os.path.normpath(self.settings.get('output_dir', './STT/temp'))
        os.makedirs(self.output_dir, exist_ok=True)
        self.settings = self.settings['engine_settings']
        self.initial_prompt = initial_prompt if initial_prompt and self.settings["use_initial_prompt"] else None
        
        self.stable_whisper_init()

    def stt(self, processing_queue: queue.Queue=None) -> None:
        """把输入目录下的所有可处理的文件打成字幕，字幕文件的路径压入堆"""
        all_items = os.listdir(self.input_dir)
        files_only = sorted([os.path.join(self.input_dir, item) for item in all_items if os.path.isfile(os.path.join(self.input_dir, item))])

        for filename in files_only: 
            for ext in self.exts:
                if filename.endswith(ext): 
                    self.stable_whisper_stt(filename, processing_queue)
                    break
        self.model = None # 释放

        if processing_queue != None: processing_queue.put(DONE) # 运行完毕信号

    def stable_whisper_init(self) -> None:
        import stable_whisper
        self.model = stable_whisper.load_model(self.settings.get('model', 'medium'))
            
    def stable_whisper_stt(self, audio_path: str, processing_queue: queue.Queue=None) -> bool: # 待完成
        if not os.path.exists(audio_path): 
            logging.warning(f"{func_name()}: 文件 \"{audio_path}\" 不存在")
            return False
        id = str(uuid.uuid4())
        file_extension = os.path.splitext(audio_path)[1]
        temp_audio_path = os.path.join(self.output_dir, f"{id}{file_extension}")

        try: # whisper没法支持奇怪字符的文件名，你说这扯不扯
            shutil.copy2(os.path.normpath(audio_path), temp_audio_path)
            no_speech_threshold = self.settings.get('no_speech_threshold', 0.6)
            result = self.model.transcribe(
                os.path.normpath(audio_path), 
                no_speech_threshold=no_speech_threshold,
                initial_prompt=self.initial_prompt
            ).to_dict()
            newsegments = []
            i = 0
            for segment in result["segments"]:
                segment["id"] = i
                newsegments.append(segment)
                i += 1
            result["segments"] = newsegments

            result_path = os.path.join(self.output_dir, os.path.basename(os.path.normpath(audio_path))+".json")
            with open(result_path, "w+", encoding="utf-8") as f: json.dump(result, f, ensure_ascii=False, indent=3)

            try: 
                if os.path.exists(temp_audio_path): os.remove(temp_audio_path)
                logging.info(f"{func_name()}: 临时文件删除成功")
            except: logging.info(f"{func_name()}: 临时文件删除失败")
            logging.info(f"{func_name()}: STT完毕：{audio_path}")
            if processing_queue != None: processing_queue.put(result_path)
            return True
        
        except Exception as e:
            logging.warning(f"{func_name()}: 发送错误：{e}")
            if os.path.exists(temp_audio_path): os.remove(temp_audio_path)
            return False

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    stt = STTServer()
    stt.stt()