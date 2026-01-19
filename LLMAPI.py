import openai, os, logging, json
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib_helper import load_json_with_comments, func_name

# 用于调用API的工具库。prompt范式要作为常量写在这个库的最上方,然后用format函数来拼装


INITIAL_PROMPT_GENERATION = """根据以下对待转录音频的描述，生成用于转录模型的初始提示词（initial prompt）。
提示词本身应该采用的语言应和描述中指定的语言一致。如果描述中没有指定语言，则提示词本身使用与描述一致的语言。
提示词应该包含：待转录内容的类型与语言。提示词应尽量简洁，不超过五十个字。如果描述中没有足够的信息，则输出"UNKNOWN"
示例：
输入："这段英文讲座主要关于Python编程..."
输出："This is a lecture about Python Programming in English."
输入："剧中的XXX人物最终实现了YYY。"
输出："这是一部剧。"
输入："1234"
输出："UNKNOWN"
"""


CHECK_TRANSCRIPTION_PROMPT = """
你是一个语音转录质量检查专家。
以下对转录内容的简介：
{description}

现在，请检查以下转录文本是否存在明显错误(如乱码、不合理的重复、不通顺等)。

转录文本:
{text}

如果存在明显错误,请回复JSON格式: {{"has_error": true, "error_type": "错误类型描述"}}
如果没有明显错误,请回复: {{"has_error": false}}

只返回JSON,不要其他内容。"""


NEED_SEARCH_PROMPT = """
你是翻译或润色助手。
以下是对待翻译或润色的内容的简介：
{description}

现在，判断以下文本在翻译或润色时是否需要查询历史翻译记录，例如人名、专业术语等

原文:
{text}

上下文(可能为空):
{context}

如果需要查询,返回JSON: 
{{"need_search": true, "search_type": "vector或fulltext", "query": {{"keywords": ["keyword1", "keyword2", ...], "sentences": ["sentence1", "sentence2", ...]}}}}
其中，如果search_type为vector，则需要提供sentences，不需要提供keywords。如果search_type为fulltext，则需要提供keywords，不需要提供sentences。

如果不需要查询,返回: {{"need_search": false}}

我们鼓励你多进行查询以获取足够的信息。并且，查询索引、关键词或依据等建议使用原本未翻译的语言以保证足够精确。
只返回严格的JSON格式，不要其他内容。"""


EVALUATE_SEARCH_PROMPT = """
以下是对待翻译或润色的内容的简介：
{description}

现在，评估以下搜索结果对翻译或润色是否有帮助。

原文: {text}
搜索结果:
{results}

如果有帮助,返回JSON: {{"useful": true, "reason": "原因"}}
如果没有帮助,返回: {{"useful": false}}

只返回JSON,不要其他内容。"""


NEED_WEB_SEARCH_PROMPT = """
以下是对待翻译或润色的内容的简介：
{description}

现在，判断是否需要进行网络搜索来获取更多信息。

原文: {text}
已尝试的数据库查询次数: {retry_count}

如果需要网络搜索,返回JSON: {{"need_web": true, "query": "搜索关键词"}} 其中查询关键词建议使用原本未翻译的语言以保证足够精确。
如果不需要,返回: {{"need_web": false}}

只返回JSON,不要其他内容。"""


TRANSLATE_PROMPT = """
你是专业的字幕翻译专家。你将要对字幕进行翻译，翻译成简体中文。
要求:
1. 保持原意，语言流畅自然，避免生硬机翻和翻译腔
2. 如果有不确定的专业术语，并且根据上下文以及所提供的辅助信息无法判断，则用（专业术语: "未翻译的原词"）标记，其中未翻译的原词就是没有翻译的那个专业术语的词
3. 如果有明显的转录错误，并且根据上下文以及所提供的辅助信息无法修正，则用（转录错误："错误的原文"）标记，其中错误的原文是转录错误的那个片段的原文的内容
4. 严格保持ID与翻译文本的一一对应（非常重要！），不得添加、删除或修改ID

以下是对待翻译的内容的简介：
{description}

相关信息与历史翻译：
{reference_info}

现在，请将以下字幕翻译成简体中文。

原文字幕:
{text}

上下文(前一段翻译,可能为空):
{context}

重要格式要求: 每个ID必须对应正确的的翻译文本

使用json格式返回翻译结果，格式如下:
{StrongFormat}
"""


REFINE_PROMPT = """
你是字幕润色专家。你将要对翻译后的字幕进行润色，要求：
1. 保持原意，语言流畅自然，避免生硬机翻和翻译腔
2. 术语、人名等使用一致
3. 根据上下文和所提供的信息将转录错误或术语等标记处修正，如果仍然无法确定应该如何修正则保留标记。
4. 严格保持ID与翻译文本的一一对应（非常重要！），不得添加、删除或修改ID
5. 识别被截断的句子（例如，上一块以不完整的短语结尾，下一块以该短语的剩余部分开始，这是影响观感的）。将被截断的语句合并，然后将完整句子同时填入原本的两个被截断的位置。
例如：{{"1": "1234..."}},{{"2": "...567"}} -> {{"1": "1234567"}},{{"2": "1234567"}}
但是，在进行这一操作时，必须保证最后的句子不会太长。如果句子太长，那么就维持截断的状态。

以下是对待翻译或润色的内容的简介：
{description}

相关信息与历史内容：
{reference_info}

现在润色以下字幕：

待润色的翻译:
{text}

重要格式要求: 每个ID必须对应正确的的翻译文本

使用json格式返回润色后的文本，保持原有的ID和格式，润色后的各个句段应该严格对应其原本所在的id，总id个数不能增减缺失修改。返回JSON格式:
{StrongFormat}
"""


CHECK_REFINE_PROMPT = """检查以下翻译是否存在问题(转录错误、不通顺等)。

翻译文本:
{text}

如果存在问题,返回JSON: {{"has_issue": true, "issue_type": "问题类型"}}
如果没有问题,返回: {{"has_issue": false}}

只返回JSON,不要其他内容。"""


class LLM:
    def __init__(self):
        settingsPath = os.path.normpath("settings.json")
        self.settings = load_json_with_comments(settingsPath)["llms"]

    def req(self, messagelist: list[dict], settings: dict) -> dict:
        """调用OpenAI兼容的API,输入为openai格式的messagelist以及settings字典(见settings.json)
        \n返回结果为 { "role": "assistant", "content": "..."} 格式的字典
        \n如果调用失败则返回空字典{}"""
        logging.debug(f"{messagelist}")
        try:
            client = openai.OpenAI(api_key=settings["api_key"], base_url=settings["api_base"])
            if settings.get("response_format", False):
                try:
                    completion = client.chat.completions.create(
                        model=settings["model"],
                        messages=messagelist,
                        temperature=settings.get("temperature", 1.0),
                        response_format=settings["response_format"]
                    )
                except Exception as e:
                    completion = client.chat.completions.create(
                        model=settings["model"],
                        messages=messagelist,
                        temperature=settings.get("temperature", 1.0)
                    )
            else:
                completion = client.chat.completions.create(
                    model=settings["model"],
                    messages=messagelist,
                    temperature=settings.get("temperature", 1.0)
                )
        except Exception as e:
            logging.error(f"{func_name()}: {e}")
            return {}
        content = completion.choices[0].message.content
        if type(content) == str: content = content.strip("`").strip("json").strip()
        if type(content) == bytes: content = content.decode('utf-8')
        if type(content) == dict: content = json.dumps(content, ensure_ascii=False)
        logging.debug(f"{completion.choices[0].message.content}")
        return { "role": "assistant", "content": completion.choices[0].message.content }
