import copy
import logging
import os
import pysubs2

# 专门用来处理字幕至便于处理的格式。最基本的用于模块间交互的格式为：
# { "segments": [{"id": , "start" , "end" , "text": }]}
# 这里忽略了大量的无关数据。这个数据被称为"主格式"

def Replacing(text: str, replacing: dict) -> str:
    for key in replacing:
        for item in replacing[key]: text = text.replace(item, key)
    return text

def json2subtitle(JsonData: dict, output_dir: str, filename: str, replacing: dict={}) -> bool:
    """调用pysubs2库将主格式json数据转换为ass、vtt、srt四种格式的字幕，
    \n输出到output_dir，文件名为filename，但后缀要改成相应的"""
    if replacing: 
        ReplacedSegments = []
        for line in JsonData["segments"]:
            line["text"] = Replacing(line["text"], replacing)
            ReplacedSegments.append(line)
        JsonData["segments"] = ReplacedSegments

    try:
        output_dir = os.path.normpath(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        subs = pysubs2.SSAFile()
        segments = JsonData.get("segments", [])
        for segment in segments:
            line = pysubs2.SSAEvent(
                start=int(segment.get("start", 0) * 1000), 
                end=int(segment.get("end", 0) * 1000),    
                text=segment.get("text", "")
            )
            subs.append(line)
        formats = {
            "ass": subs.save,
            "vtt": subs.save, 
            "srt": subs.save
        }
        for fmt in formats:
            output_path = os.path.join(output_dir, f"{filename}.{fmt}")
            try: subs.save(output_path)
            except Exception as e:
                logging.error(f"转换 {fmt} 格式失败: {e}")
                return False
        return True
    except Exception as e:
        logging.error(f"字幕转换过程中出错: {e}")
        return False

def delay_segment_ends(JsonData: dict, delay_seconds: float) -> dict:
    """将每段的 end 延后 delay_seconds 秒，但若与下一段重叠则以下一段的 start 为上限。
    \n不修改原始 JsonData，返回修改后的新主格式数据。"""
    result = copy.deepcopy(JsonData)
    segments = result.get("segments", [])
    for i, seg in enumerate(segments):
        new_end = seg.get("end", 0) + float(delay_seconds)
        if i + 1 < len(segments):
            next_start = segments[i + 1].get("start", 0)
            seg["end"] = min(new_end, next_start)
        else: seg["end"] = new_end
    return result

def normal_chunks(JsonData: dict, chunksize: int) -> list[dict]:
    """把主格式字幕分割为chunksize大小的块，放在一个列表里。
    \n每个列表都是一个块，里面是chunksize个字典，键为id，值为字幕内容
    \n除了最后一个块之外，前面所有块都必须严格是chunksize大小。
    \n输出数据格式： [{id: "text"}, {id: "text"}] 这被称为chunk格式。其中id是整型"""
    segments = JsonData["segments"]
    result = []
    for i in range(0, len(segments), chunksize):
        chunk = {}
        for segment in segments[i:i+chunksize]: chunk[segment["id"]] = segment["text"]
        result.append(chunk)
    return result

def shifted_chunks(JsonData: dict, chunksize: int) -> list[dict]:
    """与chunks函数一样，除了一点：第一个块的大小是chunksize//2。
    \n也就是说，这个函数输出的块和chunks输出的块有半个chunksize的错位"""
    segments = JsonData["segments"]
    result = []
    start_index = 0
    first_chunk_size = chunksize // 2
    while start_index < len(segments):
        chunk = {}
        end_index = start_index + (first_chunk_size if start_index == 0 else chunksize)
        for segment in segments[start_index:end_index]: chunk[segment["id"]] = segment["text"]
        result.append(chunk)
        start_index = end_index
    return result

def chunks2json(chunks: list[dict], OriginalJsonData: dict) -> dict:
    """把上述的chunk格式转换回主格式，这需要一个能够对应上id的主格式的参考（OriginalJsonData）
    \n这也是说，用chunks里的text按照id替换掉OriginalJsonData里的text后输出
    \n它是chunks函数的逆函数"""
    result = OriginalJsonData.copy()
    id_to_text = {}
    for chunk in chunks: id_to_text.update(chunk)
    for segment in result["segments"]:
        if segment["id"] in id_to_text: segment["text"] = id_to_text[segment["id"]]
    return result

def chunks2mem(OriginalChunks: list[dict], TranslatedChunks: list[dict]) -> list[dict]:
    """输入原本的chunk格式数据和翻译后的chunk格式数据，输出一种方便存储进向量数据库的格式"""
    """\n格式：[{"id": , "OriginalText": , "TranslatedText": }] 这被称为Mem格式"""
    result = []
    for orig_chunk, trans_chunk in zip(OriginalChunks, TranslatedChunks):
        for id_key in orig_chunk:
            if id_key in trans_chunk: result.append({
                "id": id_key,
                "OriginalText": orig_chunk[id_key],
                "TranslatedText": trans_chunk[id_key]
            })
    return result

if __name__ == "__main__": pass