# nlp-service/transformer_handler.py
from flask import Flask, request, jsonify
from transformers import pipeline
import numpy as np
from pymongo import MongoClient
import logging

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class NLPEngine:
    def __init__(self):
        try:
            self.classifier = pipeline(
                "text-classification", 
                model="bert-base-multilingual-uncased"
            )
            self.vectorizer = pipeline(
                "feature-extraction", 
                model="paraphrase-multilingual-MiniLM-L12-v2"
            )
            self.db = MongoClient("mongodb://localhost:27017", 
                               serverSelectionTimeoutMS=5000).chatbot_db
            logger.info("✅ NLP Engine khởi tạo thành công")
        except Exception as e:
            logger.error(f"❌ Lỗi khởi tạo NLP Engine: {str(e)}")
            raise

    def process_message(self, text):
        try:
            # Phân loại intent
            result = self.classifier(text[:512])[0]  # Giới hạn độ dài input
            logger.info(f"Phân loại intent: {result}")

            if result['score'] < 0.6:
                self._save_unknown_question(text)
                return {"intent": "unknown", "text": text}
            
            return result
        except Exception as e:
            logger.error(f"Lỗi xử lý tin nhắn: {str(e)}")
            return {"error": str(e)}

    def _save_unknown_question(self, text):
        try:
            embedding = np.mean(self.vectorizer(text[:512])[0], axis=0).tolist()
            self.db.unknown_questions.insert_one({
                "text": text,
                "embedding": embedding,
                "status": "pending",
                "timestamp": datetime.now()
            })
            logger.info(f"Đã lưu câu hỏi mới: {text[:50]}...")
        except Exception as e:
            logger.error(f"Lỗi lưu câu hỏi: {str(e)}")

# Khởi tạo engine
try:
    nlp_engine = NLPEngine()
except Exception as e:
    logger.error(f"Không thể khởi động NLP Engine: {str(e)}")
    exit(1)

@app.route('/process', methods=['POST'])
def process():
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({"error": "Thiếu trường 'text'"}), 400

        result = nlp_engine.process_message(data['text'])
        return jsonify(result)
    except Exception as e:
        logger.error(f"Lỗi endpoint /process: {str(e)}")
        return jsonify({"error": "Lỗi server"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)