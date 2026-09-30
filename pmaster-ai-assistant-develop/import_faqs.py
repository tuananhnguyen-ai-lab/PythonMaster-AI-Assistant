"""
Import dữ liệu FAQ từ file Excel (danh_sach_faq.xlsx) vào cơ sở dữ liệu MySQL.
Tự động xử lý GỘP Ô (Merged cells) cho TẤT CẢ các cột (Intent, Tình huống, Xử lý,...).
"""

import pandas as pd
from sqlalchemy import create_engine, text

# ======================= CẤU HÌNH =======================
EXCEL_PATH = "danh_sach_faq.xlsx"   # Đường dẫn tới file Excel
SHEET_NAME = "Trang tính1"          # Tên sheet trong file
TABLE_NAME = "faqs"                 # Tên bảng trong MySQL

# Cấu hình chuỗi kết nối MySQL
DB_URL = "mysql+pymysql://root:123456@localhost:3306/gemini_chat_db"
# ==========================================================

def read_faq_excel(path: str, sheet_name: str) -> pd.DataFrame:
    """Đọc file Excel FAQ và tự động điền dữ liệu cho toàn bộ các ô bị gộp (merged cells)."""
    df = pd.read_excel(path, sheet_name=sheet_name, header=0)

    # 1. Đặt lại tên cột khớp với MySQL
    df.columns = [
        "stt",
        "nhom_nghiep_vu",
        "intent",
        "tinh_huong",
        "cau_hoi_mau",
        "xu_ly_tinh_huong",
        "tra_loi_chuan",
    ][: len(df.columns)]

    # 2. Xử lý Merged Cells: Tự động copy dữ liệu ô phía trên xuống các ô bị gộp bên dưới
    # Áp dụng cho TẤT CẢ các cột có khả năng bị gộp ô
    merged_cols = ["stt", "nhom_nghiep_vu", "intent", "tinh_huong", "xu_ly_tinh_huong", "tra_loi_chuan"]
    for col in merged_cols:
        if col in df.columns:
            df[col] = df[col].ffill()

    # 3. Lọc bỏ các dòng hoàn toàn trống câu hỏi hoặc câu trả lời (sau khi đã fill)
    df = df.dropna(subset=["cau_hoi_mau", "tra_loi_chuan"])

    # 4. Thêm cột trạng thái is_active
    df["is_active"] = 1

    # 5. Chuẩn hoá kiểu dữ liệu và xóa khoảng trắng thừa ở hai đầu
    df["stt"] = df["stt"].fillna(0).astype(int)
    for col in ["nhom_nghiep_vu", "intent", "tinh_huong", 
                "cau_hoi_mau", "xu_ly_tinh_huong", "tra_loi_chuan"]:
        df[col] = df[col].astype(str).str.strip()

    return df.reset_index(drop=True)

def import_to_db(df: pd.DataFrame, db_url: str, table_name: str):
    """Đẩy dữ liệu đã được làm sạch vào MySQL."""
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # Xóa dữ liệu cũ để nạp bản mới chuẩn nhất
        conn.execute(text(f"TRUNCATE TABLE {table_name}"))
        conn.commit()
        print(f"🧹 Đã dọn dẹp dữ liệu cũ trong bảng '{table_name}'.")

    # Nạp dữ liệu vào MySQL
    df.to_sql(table_name, engine, if_exists="append", index=False)

    with engine.connect() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
    print(f"✅ Import thành công! Bảng '{table_name}' hiện có {count} dòng đầy đủ thông tin.")

def main():
    print(f"Đang đọc dữ liệu từ '{EXCEL_PATH}' ...")
    try:
        df = read_faq_excel(EXCEL_PATH, SHEET_NAME)
        print(f"Đã xử lý xong các ô gộp cho {len(df)} dòng FAQ.")
        
        print(f"\nĐang kết nối & import vào MySQL...")
        import_to_db(df, DB_URL, TABLE_NAME)
    except Exception as e:
        print(f"❌ Xảy ra lỗi: {e}")

if __name__ == "__main__":
    main()