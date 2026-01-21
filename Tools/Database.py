import sqlite3
import logging
import re
import os
import sys
import threading
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Formats import Replacing

SCHAR = {
    " ": ["。", "，", ".", ",", "？", "?", "！", "!", "；", ";", "：", ":", "“", "”", "\"", "‘", "’", "'", "（", "）", "(", ")", "《", "》", "[", "]", "【", "】", "…", "*", "-", "/"]
}

class DB:
    def __init__(self, db_path="Tools/Database.db", clean=True):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '.', exist_ok=True)
        # lock to protect sqlite connection when used across threads
        self._conn_lock = threading.Lock()
        self.setup()
        if clean: 
            self.clear()
            self.reset_id()
    
    def setup(self):
        try:
            # persistent connection to allow access from other threads; protect with lock
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = self.conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS translation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    created_time DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute("DROP TABLE IF EXISTS translation_fts")
            cursor.execute("DROP TRIGGER IF EXISTS translation_fts_ai")
            cursor.execute("DROP TRIGGER IF EXISTS translation_fts_ad")
            cursor.execute("DROP TRIGGER IF EXISTS translation_fts_au")
            cursor.execute('''
                CREATE VIRTUAL TABLE translation_fts 
                USING fts5(
                    original_text, 
                    translated_text, 
                    content='translation_history', 
                    content_rowid='id'
                )
            ''')
            cursor.execute('''
                CREATE TRIGGER translation_fts_ai 
                AFTER INSERT ON translation_history
                BEGIN
                    INSERT INTO translation_fts (rowid, original_text, translated_text)
                    VALUES (new.id, new.original_text, new.translated_text);
                END
            ''')
            cursor.execute('''
                CREATE TRIGGER translation_fts_ad 
                AFTER DELETE ON translation_history
                BEGIN
                    DELETE FROM translation_fts WHERE rowid = old.id;
                END
            ''')
            cursor.execute('''
                CREATE TRIGGER translation_fts_au 
                AFTER UPDATE ON translation_history
                BEGIN
                    UPDATE translation_fts 
                    SET original_text = new.original_text, translated_text = new.translated_text
                    WHERE rowid = new.id;
                END
            ''')
            
            logging.info("Database创建完成")
            self.conn.commit()
            cursor.close()
            
        except Exception as e:
            logging.error(f"Database初始化失败: {e}")
            raise
    
    def search(self, keywords: list[str], k: int) -> list[dict]:
        """检索出k个最匹配的结果，输入为关键词列表，输出格式跟save函数的输入格式差不多"""
        if not keywords:
            logging.warning("关键词列表为空")
            return []
        
        keywords = [Replacing(keyword, SCHAR) for keyword in keywords]
        
        try:
            fts_query = self.build_query(keywords)
            logging.info(f"构建FTS查询: {fts_query}, 关键词: {keywords}, k={k}")

            query = '''
                SELECT 
                    original_text as OriginalText,
                    translated_text as TranslatedText
                FROM translation_fts 
                WHERE translation_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            '''

            with self._conn_lock:
                self.conn.row_factory = sqlite3.Row
                cursor = self.conn.cursor()
                cursor.execute(query, (fts_query, k))
                results = cursor.fetchall()
                cursor.close()

            formatted_results = []
            for row in results:
                formatted_results.append({
                    "OriginalText": row["OriginalText"],
                    "TranslatedText": row["TranslatedText"]
                })
            
            logging.info(f"全文检索找到 {len(formatted_results)} 条匹配记录")

            if len(formatted_results) < k:
                logging.info(f"FTS结果不足 {k} 条，使用备用搜索补充")
                backup_results = self.like_search(keywords, k - len(formatted_results))

                existing_texts = {result["OriginalText"] for result in formatted_results}
                for result in backup_results:
                    if result["OriginalText"] not in existing_texts:
                        formatted_results.append(result)
                        existing_texts.add(result["OriginalText"])
                
                logging.info(f"补充后共有 {len(formatted_results)} 条记录")

            return formatted_results[:k]
            
        except Exception as e:
            logging.error(f"搜索过程中发生错误: {e}")
            return []
    
    def build_query(self, keywords: list[str]) -> str:
        """构建FTS5搜索查询字符串"""
        cleaned_keywords = []
        for keyword in keywords:
            cleaned = re.sub(r'["^*]', '', keyword.strip())
            if cleaned: cleaned_keywords.append(cleaned)
        
        if not cleaned_keywords: return ""
        query_parts = []
        for keyword in cleaned_keywords:
            if len(keyword) > 2: query_parts.append(f'{keyword}*')
            else: query_parts.append(keyword)
        
        return ' OR '.join(query_parts)
    
    def like_search(self, keywords: list[str], limit: int) -> list[dict]:
        """备用搜索：直接用LIKE搜索"""
        try:
            like_conditions = []
            params = []
            for keyword in keywords:
                if keyword.strip():
                    like_conditions.append("(original_text LIKE ? OR translated_text LIKE ?)")
                    pattern = f'%{keyword}%'
                    params.extend([pattern, pattern])
            
            if not like_conditions: 
                return []
            
            where_clause = " OR ".join(like_conditions)
            query = f'''
                SELECT 
                    original_text as OriginalText,
                    translated_text as TranslatedText
                FROM translation_history 
                WHERE {where_clause}
                ORDER BY created_time DESC
                LIMIT ?
            '''
            params.append(limit)

            with self._conn_lock:
                self.conn.row_factory = sqlite3.Row
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                results = cursor.fetchall()
                cursor.close()
            
            formatted_results = []
            for row in results:
                formatted_results.append({
                    "OriginalText": row["OriginalText"],
                    "TranslatedText": row["TranslatedText"]
                })
            
            logging.info(f"备用搜索找到 {len(formatted_results)} 条记录")
            return formatted_results
            
        except Exception as e:
            logging.error(f"备用搜索过程中发生错误: {e}")
            return []
    
    def save(self, translations: list[dict]) -> bool:
        """存入，格式为：[{ "OriginalText": , "TranslatedText": }]"""
        if not translations:
            logging.warning("传入的翻译记录列表为空")
            return True
        try:
            success_count = 0
            with self._conn_lock:
                cursor = self.conn.cursor()
                for translation in translations:
                    try:
                        if "id" in translation and translation["id"] is not None:
                            cursor.execute("SELECT id FROM translation_history WHERE id = ?", (translation["id"],))
                            if cursor.fetchone():
                                cursor.execute('''
                                    UPDATE translation_history 
                                    SET original_text = ?, translated_text = ?
                                    WHERE id = ?
                                ''', (
                                    translation["OriginalText"],
                                    translation["TranslatedText"],
                                    translation["id"]
                                ))
                                logging.info(f"更新记录 ID: {translation['id']}")
                            else:
                                logging.warning(f"记录 ID {translation['id']} 不存在，执行插入操作")
                                cursor.execute('''
                                    INSERT INTO translation_history (original_text, translated_text)
                                    VALUES (?, ?)
                                ''', (
                                    translation["OriginalText"],
                                    translation["TranslatedText"]
                                ))
                        else:
                            cursor.execute('''
                                INSERT INTO translation_history (original_text, translated_text)
                                VALUES (?, ?)
                            ''', (
                                translation["OriginalText"],
                                translation["TranslatedText"]
                            ))
                            logging.debug("插入新记录")
                        success_count += 1
                    except Exception as e:
                        logging.error(f"保存单条记录失败: {translation}, 错误: {e}")
                        continue
                self.conn.commit()
                cursor.close()
            logging.info(f"成功保存 {success_count}/{len(translations)} 条翻译记录")
            return success_count == len(translations)
        except Exception as e:
            logging.error(f"保存翻译记录过程中发生错误: {e}")
            return False
    
    def get_all_records(self) -> list[dict]:
        try:
            with self._conn_lock:
                self.conn.row_factory = sqlite3.Row
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT id, original_text, translated_text, created_time 
                    FROM translation_history 
                    ORDER BY id
                ''')
                rows = cursor.fetchall()
                cursor.close()
            results = []
            for row in rows:
                results.append({
                    "id": row["id"],
                    "OriginalText": row["original_text"],
                    "TranslatedText": row["translated_text"],
                    "created_time": row["created_time"]
                })
            return results
        except Exception as e:
            logging.error(f"获取所有记录失败: {e}")
            return []

    def get_total_count(self) -> int:
        try:
            with self._conn_lock:
                cursor = self.conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM translation_history")
                count = cursor.fetchone()[0]
                cursor.close()
            logging.info(f"数据库中共有 {count} 条翻译记录")
            return count
        except Exception as e:
            logging.error(f"获取记录数量失败: {e}")
            return 0
        
    def reset_id(self):
        try:
            with self._conn_lock:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='translation_history'")
                self.conn.commit()
                cursor.close()
            logging.info("已重置自增ID计数器")
        except Exception as e:
            logging.error(f"重置自增ID失败: {e}")

    def clear(self):
        """清空"""
        try:
            with self._conn_lock:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM translation_history")
                logging.warning("已清空所有翻译记录")
                self.conn.commit()
                cursor.close()
        except Exception as e: logging.error(f"清空数据失败: {e}")

if __name__ == "__main__": pass