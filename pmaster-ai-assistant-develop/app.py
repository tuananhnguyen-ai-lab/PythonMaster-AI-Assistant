import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types
import pymysql

app = Flask(__name__)
CORS(app, origins=["http://localhost:8000"])

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'gemini_chat_db',
    'cursorclass': pymysql.cursors.DictCursor
}

client = genai.Client(api_key="AQ.Ab8RN6JYrjERLxk2dgg-VEbpGJsAJ7ZXeNF5SR7EvF1MdM8Fvw")


# ============================================================
# STOP-WORD FILTERING & KEYWORD MATCHING
# ============================================================
# MySQL FULLTEXT (NATURAL LANGUAGE MODE) tự động bỏ qua từ ngắn
# (< ft_min_word_len, mặc định 3-4 với InnoDB) và không có khái
# niệm "stop-word tiếng Việt". Vì vậy câu "Cho tôi thông tin 2
# bảng A và B" sau khi MySQL xử lý gần như chỉ còn lại đúng từ
# "thông", "tin" -> match nhầm vào FAQ không liên quan.
#
# Giải pháp: tự trích xuất "từ khóa có nghĩa" (loại bỏ stop-word
# tiếng Việt, KHÔNG loại theo độ dài để giữ lại 'A', 'B', '2'...),
# rồi tự tính điểm khớp (matched keywords / total keywords) trong
# Python. Chỉ chấp nhận FAQ nếu tỷ lệ khớp đủ cao VÀ số từ khóa
# khớp tuyệt đối đủ lớn. Nếu không, luôn fallback 100% sang Gemini.
# ============================================================

VN_STOPWORDS = {
    "là", "của", "và", "các", "những", "một", "này", "đó", "sao", "như",
    "thế", "nào", "gì", "cho", "tôi", "với", "theo", "trong", "trên",
    "dưới", "được", "có", "không", "sẽ", "đã", "đang", "về", "cụ", "thể",
    "thông", "tin", "bạn", "mình", "ạ", "nhé", "vậy", "hãy", "làm", "ơn",
    "giúp", "xin", "nếu", "thì", "mà", "ra", "vào", "lên", "xuống", "rồi",
    "chưa", "hay", "hoặc", "khi", "đâu", "ai", "bao", "nhiêu", "mấy",
    "kia", "ấy", "để", "còn", "lại", "cũng", "rất", "quá", "hơn", "tại",
    "sao", "vì", "nên", "phải", "cần", "muốn", "biết", "xem", "giờ",
    "đây", "kìa", "chỗ", "nơi", "nhất", "luôn", "chỉ", "mọi", "tất", "cả",
}

# Ngưỡng chấp nhận FAQ: tỷ lệ từ khóa của câu hỏi khớp với FAQ
FAQ_MIN_MATCH_RATIO = 0.6
# Số từ khóa khớp tối thiểu (tuyệt đối) để chống trường hợp câu hỏi
# rất ngắn (1 từ khóa) vô tình khớp 100% với một FAQ không liên quan
FAQ_MIN_MATCHED_KEYWORDS = 2


def extract_keywords(text: str):
    """Tách văn bản thành danh sách từ khóa có nghĩa (đã bỏ stop-word).
    Không lọc theo độ dài để giữ lại các token ngắn nhưng quan trọng
    (mã bảng 'A', 'B', số '2', v.v.)."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\sÀ-ỹ]", " ", text, flags=re.UNICODE)
    tokens = [t for t in text.split() if t]
    return [t for t in tokens if t not in VN_STOPWORDS]


def keyword_match_ratio(user_keywords, faq_question: str) -> float:
    """Tỷ lệ từ khóa của câu hỏi người dùng xuất hiện trong câu FAQ mẫu."""
    if not user_keywords:
        return 0.0
    faq_keywords = set(extract_keywords(faq_question))
    matched = sum(1 for kw in user_keywords if kw in faq_keywords)
    return matched / len(user_keywords)


def find_best_faq_match(cursor, user_message: str):
    """Trả về (faq_row hoặc None). Chỉ trả FAQ khi đủ tin cậy,
    ngược lại trả None để chat_endpoint fallback sang Gemini."""
    user_keywords = extract_keywords(user_message)

    # Câu hỏi chỉ gồm từ nhiễu/từ chung (không còn từ khóa có nghĩa nào)
    # -> không thể có FAQ match đáng tin cậy, fallback ngay sang Gemini.
    if not user_keywords:
        return None

    # Bước 1: lấy tập ứng viên rộng bằng FULLTEXT BOOLEAN MODE (nhanh,
    # dùng index). Boolean mode ở đây dùng OR (không có dấu '+') để
    # không bỏ lỡ ứng viên chỉ vì thiếu 1-2 từ khóa.
    boolean_query = " ".join(f"{kw}*" for kw in user_keywords)
    candidates = []
    try:
        cursor.execute("""
            SELECT intent, xu_ly_tinh_huong, tra_loi_chuan, cau_hoi_mau
            FROM faqs
            WHERE is_active = 1
              AND MATCH(cau_hoi_mau) AGAINST(%s IN BOOLEAN MODE)
        """, (boolean_query,))
        candidates = cursor.fetchall()
    except Exception as e:
        print(f"Lỗi truy vấn Full-Text Search: {e}")

    # Bước 2 (dự phòng): nếu FULLTEXT không trả kết quả nào — thường
    # xảy ra khi TẤT CẢ từ khóa của câu hỏi đều ngắn hơn ft_min_word_len
    # (ví dụ 'A', 'B') và bị MySQL âm thầm bỏ qua — thì quét toàn bộ
    # FAQ đang active để không bỏ sót ứng viên hợp lệ. Với bảng FAQ
    # (thường vài chục-vài trăm dòng) chi phí này không đáng kể.
    if not candidates:
        cursor.execute("""
            SELECT intent, xu_ly_tinh_huong, tra_loi_chuan, cau_hoi_mau
            FROM faqs
            WHERE is_active = 1
        """)
        candidates = cursor.fetchall()

    # Bước 3: chấm điểm chính xác bằng khớp từ khóa (không phụ thuộc
    # MySQL relevance score, vốn dễ bị từ chung/từ nhiễu làm sai lệch).
    best_row = None
    best_ratio = 0.0
    for row in candidates:
        ratio = keyword_match_ratio(user_keywords, row["cau_hoi_mau"])
        matched_count = round(ratio * len(user_keywords))
        required_matches = min(FAQ_MIN_MATCHED_KEYWORDS, len(user_keywords))

        if (
            ratio > best_ratio
            and ratio >= FAQ_MIN_MATCH_RATIO
            and matched_count >= required_matches
        ):
            best_ratio = ratio
            best_row = row

    return best_row


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    data = request.json or {}
    user_message = data.get("message")
    conversation_id = data.get("conversation_id")
    user_id = data.get("user_id", 1)

    if not user_message:
        return jsonify({"error": "Vui lòng nhập tin nhắn"}), 400

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            if not conversation_id:
                cursor.execute(
                    "INSERT INTO conversations (user_id, title) VALUES (%s, %s)",
                    (user_id, user_message[:30])
                )
                connection.commit()
                conversation_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO messages (conversation_id, sender_type, content) VALUES (%s, %s, %s)",
                (conversation_id, 'user', user_message)
            )
            connection.commit()

            # ---- FAQ matching (chính xác, có fallback 100% sang Gemini) ----
            faq_row = find_best_faq_match(cursor, user_message)

            if faq_row:
                model_reply = faq_row['tra_loi_chuan']
            else:
                cursor.execute(
                    "SELECT sender_type, content FROM messages WHERE conversation_id = %s ORDER BY created_at ASC",
                    (conversation_id,)
                )
                db_messages = cursor.fetchall()

                history = []
                for msg in db_messages[:-1]:
                    role = "user" if msg['sender_type'] == 'user' else "model"
                    history.append({
                        "role": role,
                        "parts": [{"text": msg['content']}]
                    })

                chat = client.chats.create(
                    model="gemini-3.6-flash",
                    history=history,
                    config=types.GenerateContentConfig(
                        system_instruction="Bạn là trợ lý ảo thông minh chuyên trách Hệ thống Quản lý Học tập (LMS). Hãy luôn trả lời ngắn gọn, rõ ràng, hỗ trợ học viên tra cứu tài liệu, lịch học và giải đáp thắc mắc chuyên môn.",
                    )
                )

                response = chat.send_message(user_message)
                model_reply = response.text

            cursor.execute(
                "INSERT INTO messages (conversation_id, sender_type, content) VALUES (%s, %s, %s)",
                (conversation_id, 'model', model_reply)
            )
            connection.commit()

        return jsonify({
            "status": "success",
            "conversation_id": conversation_id,
            "reply": model_reply,
            "used_faq": bool(faq_row)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        connection.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)