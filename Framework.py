import json
import logging
import os
import queue
import threading, LLMAPI, Formats
from lib_helper import func_name, load_json_with_comments
import STT.STTServer, Tools.Database, Tools.VectorDatabase, Tools.Crawler

class Framework:
    def __init__(self):
        self.settings = load_json_with_comments("settings.json")

        self.output_dir = os.path.normpath(self.settings["output_dir"])
        os.makedirs(self.output_dir, exist_ok=True)

        self.llms = LLMAPI.LLM()
        description_path = os.path.normpath(self.settings["description_input_path"])
        if os.path.exists(description_path):
            with open(description_path, "r", encoding="utf-8") as f: self.description = f.read()
            self.description = self.description.strip()
            if self.description:
                try:
                    result = self.llms.req([
                        {"role": "system", "content": LLMAPI.INITIAL_PROMPT_GENERATION},
                        {"role": "user", "content": self.description}
                    ], self.settings["llms"]["SmallModel"])["content"]
                    result = result.strip() if result.strip() != "UNKNOWN" else ""
                except Exception as e:
                    logging.warning(f"{func_name()}: STT初始Prompt生成失败：{e}")
                    result = ""
            else: result = ""
        else: result = ""
        self.stt = STT.STTServer.STTServer(result)

        self.db = Tools.Database.DB()
        embedder = Tools.VectorDatabase.Embedder(self.settings["embedding_model_name"])
        self.vdb = Tools.VectorDatabase.VDB(embedder)
        self.crawler = Tools.Crawler.Crawler(self.settings["Crawler"]["website"])
        self.processing_queue = queue.Queue()

    def run(self): # 待测试
        """总启动"""
        th = threading.Thread(
            target=self.stt.stt, 
            kwargs={"processing_queue": self.processing_queue}, 
            daemon=True
        )
        th.start()
        if not self.settings["enable_parallel"]: th.join()

        if self.settings["global_memory"]:
            PostTaskList = []

            while True:
                path = os.path.normpath(self.processing_queue.get())
                if path == STT.STTServer.DONE: 
                    logging.info(f"{func_name()}: 翻译完毕")
                    break

                with open(path, "r", encoding="utf-8") as f: OriginalJsonData = json.load(f)
                if self.settings.get("delay_segment_ends", 0.0) > 0.0: OriginalJsonData = Formats.delay_segment_ends(OriginalJsonData, self.settings["delay_segment_ends"])
                chunks = Formats.normal_chunks(OriginalJsonData, self.settings["chunk_size"])

                processed_chunks = []
                prev = None
                for chunk in chunks:
                    processed_chunk = self.Task(chunk, prev)
                    processed_chunks.append(processed_chunk)
                    # 这里是主要处理，记得Task要传入prev参数，prev是mem格式
                chunks = processed_chunks
                logging.debug(f"{func_name()}: 处理后chunks: {chunks}")

                TranslatedJsonData = Formats.chunks2json(chunks, OriginalJsonData)
                logging.debug(f"{func_name()}: 生成的TranslatedJsonData: {TranslatedJsonData}")
                PostTaskList.append({ "filename": os.path.basename(path), "jsondata": TranslatedJsonData })
                if os.path.exists(path) and self.settings["delete_stt"]: os.remove(path)
                # endbug

            # 这个时候，数据库中便存储好了全文的记忆，而PostTaskList中存储了翻译后的json数据及其原本的文件名

            enable_refine = self.settings["enable_refine"]
            for episode in PostTaskList:
                filename = episode["filename"]
                if filename.endswith(".json"): filename = filename[:-5]
                TranslatedJsonData = episode["jsondata"]
                if not enable_refine: 
                    Formats.json2subtitle(TranslatedJsonData, self.output_dir, filename, self.settings["replacing"])
                    continue

                # 这里才是润色的主流程
                chunks = Formats.shifted_chunks(TranslatedJsonData, self.settings["chunk_size"]) 

                chunks = [self.PostTask(chunk) for chunk in chunks]

                RefinedJsonData = Formats.chunks2json(chunks, TranslatedJsonData)
                Formats.json2subtitle(RefinedJsonData, self.output_dir, filename, self.settings["replacing"])
            if enable_refine: logging.info(f"{func_name()}: 润色完毕")

        else:
            enable_refine = self.settings["enable_refine"]
            while True:
                path = os.path.normpath(self.processing_queue.get())
                if path == STT.STTServer.DONE: 
                    logging.info(f"{func_name()}: 处理完毕")
                    break

                with open(path, "r", encoding="utf-8") as f: OriginalJsonData = json.load(f)
                chunks = Formats.normal_chunks(OriginalJsonData, self.settings["chunk_size"])

                processed_chunks = []
                prev = None
                for chunk in chunks:
                    processed_chunk = self.Task(chunk, prev)
                    processed_chunks.append(processed_chunk)
                    # 这里是主要处理，记得Task要传入prev参数，prev是mem格式
                chunks = processed_chunks
                logging.debug(f"{func_name()}: 处理后chunks: {chunks}")

                TranslatedJsonData = Formats.chunks2json(chunks, OriginalJsonData)
                logging.debug(f"{func_name()}: 生成的TranslatedJsonData: {TranslatedJsonData}")
                if os.path.exists(path) and self.settings["delete_stt"]: os.remove(path)
                
                filename = os.path.basename(path)
                if filename.endswith(".json"): filename = filename[:-5]
                if not enable_refine:
                    Formats.json2subtitle(TranslatedJsonData, self.output_dir, filename, self.settings["replacing"])
                    logging.info(f"{func_name()}: {filename}处理完毕")
                    continue

                # 这里才是润色的主流程
                chunks = Formats.shifted_chunks(TranslatedJsonData, self.settings["chunk_size"]) 

                chunks = [self.PostTask(chunk) for chunk in chunks]

                RefinedJsonData = Formats.chunks2json(chunks, TranslatedJsonData)
                Formats.json2subtitle(RefinedJsonData, self.output_dir, filename, self.settings["replacing"])

                self.db.clear()
                self.vdb.clear()
                logging.info(f"{func_name()}: {filename}带有润色的处理完毕")
        
        logging.info(f"{func_name()}: 程序运行完毕")
        self.quit()

    def Task(self, chunk, prev: None|list[dict]=None) -> list[dict]: 
        """翻译
        \n第一步：判断是否有转录错误。有就标记。
        \n第二步：判断是否需要查询历史信息，如果是则判断使用哪个数据库，并给出查询关键词或句子，不需要调用则跳到第七步
        \n第三步：查询
        \n第四步：判断查询结果是否有用，有用则跳到第七步，没用则返回第二步，如果足够多次不行就标记，随后如果启用网络查询就上网查，没有启用则跳至第七步。
        \n第五步：上网查
        \n第六步：判断查询结果是否有用，没用则返回第四步，足够多次不行就标记
        \n第七步：根据查询结果和标记信息进行翻译，如果不知道的地方要标记为不知道（幻觉控制）
        \n第八步：输出
        """
        # text = "\n".join([f"{k}: {v}" for k, v in chunk.items()])
        context = ""
        if prev: context = "\n".join([f"{item.get('id', '')}: {item.get('TranslatedText', '')}" for item in prev[:]])
        
        # 1
        check_msg = [{"role": "user", "content": LLMAPI.CHECK_TRANSCRIPTION_PROMPT.format(
            text=str(chunk),
            description=self.description if self.description else "未提供"
        )}]
        check_result = self.llms.req(check_msg, self.settings["llms"]["SmallModel"])
        has_error = False
        if check_result:
            try:
                check_data = json.loads(check_result["content"])
                has_error = check_data.get("has_error", False)
            except: pass
        
        reference_info = ""
        retry_count = 0
        max_retry = self.settings.get("max_retry", 2)
        
        while self.settings.get("search_local", True) and retry_count < max_retry:
            # 2
            need_msg = [{"role": "user", "content": LLMAPI.NEED_SEARCH_PROMPT.format(
                text=str(chunk), 
                context=context,
                description=self.description if self.description else "未提供"
            )}]
            need_result = self.llms.req(need_msg, self.settings["llms"]["SmallModel"])
            
            need_search = False
            search_type = "vector"
            query = {}
            sentences = []
            keywords = []
            
            if need_result:
                try:
                    need_data = Formats.Replacing(need_result["content"], {"": ["\'", "\\'"]})
                    logging.info(need_data)
                    need_data = json.loads(need_data)
                    need_search = need_data.get("need_search", False)
                    search_type = need_data.get("search_type", "vector")
                    query = need_data.get("query", {})
                    sentences = query.get("sentences", [])
                    keywords = query.get("keywords", [])
                except Exception as e: 
                    logging.warning(f"记忆查询命令提取出错：{e}")
                    pass
            
            if not need_search: break
            
            # 3
            search_results = []
            if search_type == "vector" and sentences:
                for sentence in sentences:
                    search_results += self.vdb.search({"OriginalText": sentence}, k=3)
            elif search_type == "fulltext" and keywords:
                search_results = self.db.search(keywords, k=3)
            
            # 4
            if search_results:
                results_text = "\n".join([f"原文: {r.get('OriginalText', '')} -> 译文: {r.get('TranslatedText', '')}" for r in search_results])
                eval_msg = [{"role": "user", "content": LLMAPI.EVALUATE_SEARCH_PROMPT.format(
                    text=str(chunk), 
                    results=results_text,
                    description=self.description if self.description else "未提供"
                )}]
                eval_result = self.llms.req(eval_msg, self.settings["llms"]["SmallModel"])
                
                useful = False
                if eval_result:
                    try:
                        eval_data = json.loads(eval_result["content"])
                        useful = eval_data.get("useful", False)
                    except: pass
                
                if useful:
                    reference_info = f"参考翻译:\n{results_text}"
                    break
            
            retry_count += 1
        
        # 5&6
        if not reference_info and self.settings.get("Crawler", {}).get("enable_crawler", False):
            web_msg = [{"role": "user", "content": LLMAPI.NEED_WEB_SEARCH_PROMPT.format(
                text=str(chunk), 
                retry_count=retry_count,
                description=self.description if self.description else "未提供"
            )}]
            web_result = self.llms.req(web_msg, self.settings["llms"]["SmallModel"])
            
            if web_result:
                try:
                    web_data = json.loads(web_result["content"])
                    if web_data.get("need_web", False):
                        query = web_data.get("query", "")
                        if query:
                            web_results = self.crawler.search(query, max_results=2)
                            if web_results:
                                web_text = "\n".join([f"{r['title']}: {r['snippet']}" for r in web_results])
                                reference_info = f"网络搜索结果:\n{web_text}"
                except: pass
        
        # 7
        chunklength = len(chunk)
        if chunklength < 4: StrongFormat = str({ "translated": {k: f"对先前id{k}翻译内容" for k in chunk.keys()} })
        else:
            keys = list(chunk.keys())
            format_parts = []
            format_parts.append(f'"{keys[0]}": "翻译{keys[0]}"')
            if chunklength >= 2: format_parts.append(f'"{keys[1]}": "翻译{keys[1]}"')
            if chunklength > 3: format_parts.append('...')
            if chunklength >= 3: format_parts.append(f'"{keys[-1]}": "翻译{keys[-1]}"')
            StrongFormat = f'{{ "translated": {{ {", ".join(format_parts)} }} }}'
            
        translate_msg = [{"role": "user", "content": LLMAPI.TRANSLATE_PROMPT.format(
            reference_info=reference_info if reference_info else "None",
            text=str(chunk),
            context=context if context else "None",
            StrongFormat=StrongFormat,
            description=self.description if self.description else "未提供"
        )}]
        while True:
            translate_result = self.llms.req(translate_msg, self.settings["llms"]["LargeModelJson"])
            
            # 8
            result_chunk = chunk.copy()
            if translate_result:
                try:
                    translate_data = json.loads(translate_result["content"])
                    translated = translate_data.get("translated", {})
                    for k, v in translated.items():
                        try:
                            result_chunk[int(k)] = v
                        except:
                            if k in result_chunk:
                                result_chunk[k] = v
                    break
                except Exception as e:
                    logging.warning(f"{func_name()}: 解析翻译结果失败: {e}")
        
        mem_data = [{"OriginalText": chunk[k], "TranslatedText": result_chunk[k]} for k in chunk.keys()]
        self.vdb.save(mem_data)
        self.db.save(mem_data)
        
        return result_chunk

    def PostTask(self, chunk) -> list[dict]: 
        """润色，待所有字幕文件翻译完毕后调用
        \n第一步：检查标记内容、通顺性、谬误，如果没有问题则跳到第六步
        \n第二步：判断调用哪个数据库，并给出查询关键词或句子，不需要调用则跳到第四步
        \n第三步：查询
        \n第四步：判断查询结果是否有用，没用则返回第一步，足够多次不行就标记
        \n第五步：根据查询结果润色，未解决的标记要保留
        \n第六步：输出
        """
        
        # 1
        check_msg = [{"role": "user", "content": LLMAPI.CHECK_REFINE_PROMPT.format(text=str(chunk))}]
        check_result = self.llms.req(check_msg, self.settings["llms"]["SmallModel"])
        
        has_issue = False
        if check_result:
            try:
                check_data = json.loads(check_result["content"])
                has_issue = check_data.get("has_issue", False)
            except: pass
        
        reference_info = ""
        
        # 2
        if has_issue:
            retry_count = 0
            max_retry = self.settings.get("max_retry", 2)
            
            while self.settings.get("search_local", True) and retry_count < max_retry:
                need_msg = [{"role": "user", "content": LLMAPI.NEED_SEARCH_PROMPT.format(
                    text=str(chunk), 
                    context="",
                    description=self.description if self.description else "未提供"
                )}]
                need_result = self.llms.req(need_msg, self.settings["llms"]["SmallModel"])
                
                need_search = False
                search_type = "vector"
                keywords = []
                
                if need_result:
                    try:
                        need_data = json.loads(need_result["content"])
                        need_search = need_data.get("need_search", False)
                        search_type = need_data.get("search_type", "vector")
                        keywords = need_data.get("keywords", [])
                    except: pass
                
                if not need_search: break
                
                # 3
                search_results = []
                if search_type == "vector" and keywords:
                    query_text = " ".join(keywords)
                    search_results = self.vdb.search({"TranslatedText": query_text}, k=3)
                elif search_type == "fulltext" and keywords:
                    search_results = self.db.search(keywords, k=3)
                
                # 4
                if search_results:
                    results_text = "\n".join([f"原文: {r.get('OriginalText', '')} -> 译文: {r.get('TranslatedText', '')}" for r in search_results])
                    eval_msg = [{"role": "user", "content": LLMAPI.EVALUATE_SEARCH_PROMPT.format(
                        text=str(chunk), 
                        results=results_text,
                        description=self.description if self.description else "未提供"
                    )}]
                    eval_result = self.llms.req(eval_msg, self.settings["llms"]["SmallModel"])
                    
                    useful = False
                    if eval_result:
                        try:
                            eval_data = json.loads(eval_result["content"])
                            useful = eval_data.get("useful", False)
                        except: pass
                    
                    if useful:
                        reference_info = f"参考翻译:\n{results_text}"
                        break
                
                retry_count += 1
        
        # 5
        chunklength = len(chunk)
        if chunklength < 4: StrongFormat = str({ "refined": {k: f"润色{k}" for k in chunk.keys()} })
        else:
            keys = list(chunk.keys())
            format_parts = []
            format_parts.append(f'"{keys[0]}": "润色{keys[0]}"')
            if chunklength >= 2: format_parts.append(f'"{keys[1]}": "润色{keys[1]}"')
            if chunklength > 3: format_parts.append('...')
            if chunklength >= 3: format_parts.append(f'"{keys[-1]}": "润色{keys[-1]}"')
            StrongFormat = f'{{ "refined": {{ {", ".join(format_parts)} }} }}'
            
        refine_msg = [{"role": "user", "content": LLMAPI.REFINE_PROMPT.format(
            reference_info=reference_info if reference_info else "无参考信息",
            text=str(chunk),
            StrongFormat=StrongFormat,
            description=self.description if self.description else "未提供"
        )}]

        while True:
            refine_result = self.llms.req(refine_msg, self.settings["llms"]["LargeModelJson"])
            
            # 6
            result_chunk = chunk.copy()
            if refine_result:
                try:
                    refine_data = json.loads(refine_result["content"])
                    refined = refine_data.get("refined", {})
                    for k, v in refined.items():
                        try:
                            result_chunk[int(k)] = v
                        except:
                            if k in result_chunk:
                                result_chunk[k] = v
                    break
                except Exception as e:
                    logging.warning(f"解析润色结果失败：{e}")
        
        return result_chunk

    def quit(self):
        """把资源清一清"""
        self.db.clear()
        self.vdb.__del__()