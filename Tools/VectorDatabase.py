import logging
import os
import faiss
import sqlite3
import numpy as np
import torch
import threading
from transformers import AutoTokenizer, AutoModel

class Embedder: 
    def __init__(self, model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        """提前加载模型，先检查显存"""
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logging.info(f"使用设备: {self.device}")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModel.from_pretrained(model_name).to(self.device)
            self.model.eval()
            logging.info(f"成功加载模型: {model_name}")
        except Exception as e:
            logging.error(f"模型加载失败: {e}")
            raise

    def embed(self, texts: list[str]) -> np.array:
        """将文本列表转换为嵌入向量"""
        if isinstance(texts, str): texts = [texts]
        
        with torch.no_grad():
            inputs = self.tokenizer(texts, padding=True, truncation=True, 
                                  max_length=512, return_tensors="pt").to(self.device)
            outputs = self.model(**inputs)
            embeddings = self.mean_pooling(outputs, inputs['attention_mask'])
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            return embeddings.cpu().numpy()

    def mean_pooling(self, model_output, attention_mask):
        token_embeddings = model_output.last_hidden_state
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)


class VDB:
    def __init__(self, embedder: Embedder, temp_path="./Tools/VDBTemp.db", clean=True):
        """先检查能不能用显存，能则用，不能则用CPU
        \n embedder输出单位向量"""
        self.embedder = embedder.embed  # nparray
        self.dim = self.embedder(["init"]).shape[1] 
        self.temp_path = os.path.normpath(temp_path)
        self.next_id = 0
        self.id_map = {} 

        # 两个索引，一个原文，一个译文
        if torch.cuda.is_available():
            try:
                self.res = faiss.StandardGpuResources()
                self.original_index = faiss.GpuIndexFlatIP(self.res, self.dim)
                self.translated_index = faiss.GpuIndexFlatIP(self.res, self.dim)
                self.use_gpu = True
                logging.info("使用GPU")
            except Exception as e:
                logging.info(f"GPU不能用：{e}。使用CPU")
                self.original_index = faiss.IndexFlatIP(self.dim)
                self.translated_index = faiss.IndexFlatIP(self.dim)
                self.use_gpu = False
        else:
            self.original_index = faiss.IndexFlatIP(self.dim)
            self.translated_index = faiss.IndexFlatIP(self.dim)
            self.use_gpu = False
            logging.info("使用CPU")
        self.init_sqlite()
        if clean: self.clear()
    
    def init_sqlite(self):
        """初始化SQLite数据库"""
        # allow using the connection from multiple threads; protect access with a lock
        self.conn = sqlite3.connect(self.temp_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._conn_lock = threading.Lock()
        with self._conn_lock:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS texts (
                    id INTEGER PRIMARY KEY,
                    original_text TEXT,
                    translated_text TEXT
                )
            ''')
            self.conn.commit()
            self.cursor.execute("SELECT MAX(id) FROM texts")
            result = self.cursor.fetchone()
            self.next_id = result[0] + 1 if result[0] is not None else 0
    
    def save(self, messagelist: list[dict[str, str]]):
        """存入，格式为：[{ "OriginalText": , "TranslatedText": }]"""
        if not messagelist: return

        original_texts = [msg.get("OriginalText", "") for msg in messagelist]
        translated_texts = [msg.get("TranslatedText", "") for msg in messagelist]

        original_embeddings = self.embedder(original_texts)
        translated_embeddings = self.embedder(translated_texts)

        for embeddings in [original_embeddings, translated_embeddings]:
            if isinstance(embeddings, torch.Tensor):
                embeddings = embeddings.cpu().numpy()
            embeddings = embeddings.astype(np.float32)
            faiss.normalize_L2(embeddings)
        
        start_index = self.original_index.ntotal  
        self.original_index.add(original_embeddings)
        self.translated_index.add(translated_embeddings)
        
# Insert DB records under lock; embeddings and FAISS ops are done outside the lock
        with self._conn_lock:
            for i, msg in enumerate(messagelist):
                db_id = self.next_id + i
                faiss_index = start_index + i
                self.id_map[faiss_index] = db_id

                self.cursor.execute(
                    "INSERT INTO texts (id, original_text, translated_text) VALUES (?, ?, ?)",
                    (db_id, msg.get("OriginalText", ""), msg.get("TranslatedText", ""))
                )
            self.next_id += len(messagelist)
            self.conn.commit()
        logging.info(f"保存了 {len(messagelist)} 条记录")
    
    def search(self, query: dict, k: int, threshold=0.6) -> list[dict]:
        """用IndexFlatIP取k个最相似且相似度大于threshold的记忆，不够就把有的拿出来
        \n输入为{ "OriginalText": , "TranslatedText": }，提供了哪些就用哪个查找，如果都提供了就用OriginalText
        \n输出格式和save的输入格式一样"""
        if self.original_index.ntotal == 0: return []
        
        search_text = ""
        use_original = False
        use_translated = False

        if "OriginalText" in query and query["OriginalText"]: 
            search_text = query["OriginalText"]
            use_original = True
        elif "TranslatedText" in query and query["TranslatedText"]: 
            search_text = query["TranslatedText"]
            use_translated = True
        else: return []

        query_embedding = self.embedder([search_text])
        if isinstance(query_embedding, torch.Tensor):
            query_embedding = query_embedding.cpu().numpy()
        
        query_embedding = query_embedding.astype(np.float32)
        faiss.normalize_L2(query_embedding)

        if use_original: search_index = self.original_index
        else: search_index = self.translated_index
            
        actual_k = min(k, search_index.ntotal)
        similarities, indices = search_index.search(query_embedding, actual_k)
        
        results = []
        for i in range(actual_k):
            similarity = similarities[0][i]

            if similarity >= threshold:
                faiss_index = indices[0][i]
                db_id = self.id_map.get(faiss_index)
                
                if db_id is not None:
                    with self._conn_lock:
                        self.cursor.execute(
                            "SELECT original_text, translated_text FROM texts WHERE id = ?", 
                            (db_id,)
                        )
                        result = self.cursor.fetchone()
                    if result:
                        results.append({
                            "OriginalText": result[0],
                            "TranslatedText": result[1],
                            "Similarity": float(similarity)
                        })
        
        logging.info(f"VectorDatabase查到{results}")
        return results
    
    def clear(self): # 待测试
        """把用于对应向量的数据库清空，id归零。包括内存中的向量索引"""
        # 清SQLite
        if hasattr(self, '_conn_lock'):
            with self._conn_lock:
                if hasattr(self, 'cursor') and self.cursor:
                    self.cursor.execute("DELETE FROM texts")
                    self.conn.commit()
                self.next_id = 0
                self.id_map.clear() 

        if hasattr(self, 'original_index'):
            try:
                if self.use_gpu and hasattr(self.original_index, 'reset'):
                    self.original_index.reset()
                del self.original_index
            except Exception as e:
                logging.warning(f"释放original_index失败: {e}")

        if hasattr(self, 'translated_index'):
            try:
                if self.use_gpu and hasattr(self.translated_index, 'reset'):
                    self.translated_index.reset()
                del self.translated_index
            except Exception as e:
                logging.warning(f"释放translated_index失败: {e}")

        if hasattr(self, 'res') and self.res:
            try:
                del self.res
            except Exception as e:
                logging.warning(f"释放GPU资源失败: {e}")

        import gc
        gc.collect()

        if self.use_gpu:
            try:
                self.res = faiss.StandardGpuResources()
                self.original_index = faiss.GpuIndexFlatIP(self.res, self.dim)
                self.translated_index = faiss.GpuIndexFlatIP(self.res, self.dim)
            except Exception as e:
                logging.warning(f"重新创建GPU索引失败: {e}, 回退到CPU")
                self.original_index = faiss.IndexFlatIP(self.dim)
                self.translated_index = faiss.IndexFlatIP(self.dim)
                self.use_gpu = False
        else: 
            self.original_index = faiss.IndexFlatIP(self.dim)
            self.translated_index = faiss.IndexFlatIP(self.dim)
        
        logging.info("数据库和向量索引已清空")
    
    def get_stats(self) -> dict:
        with self._conn_lock:
            self.cursor.execute("SELECT COUNT(*) FROM texts")
            count = self.cursor.fetchone()[0]
        return {
            "total_records": count,
            "next_id": self.next_id,
            "original_index_size": self.original_index.ntotal,
            "translated_index_size": self.translated_index.ntotal,
            "using_gpu": self.use_gpu,
            "id_map_size": len(self.id_map)
        }
    
    def __del__(self):
        """析构函数，安全地清理资源"""
        try:
            if hasattr(self, '_conn_lock'):
                with self._conn_lock:
                    if hasattr(self, 'conn') and self.conn:
                        self.conn.close()
            else:
                if hasattr(self, 'conn') and self.conn:
                    self.conn.close()
        except Exception as e: pass

if __name__ == "__main__": pass