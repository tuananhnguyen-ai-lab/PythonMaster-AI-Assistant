CREATE DATABASE IF NOT EXISTS gemini_chat_db;
USE gemini_chat_db;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(255) DEFAULT 'Đoạn chat mới',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_id INT NOT NULL,
    sender_type ENUM('user', 'model') NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

-- Thêm cột phân quyền vào bảng users hiện tại
ALTER TABLE users ADD COLUMN role ENUM('user', 'dev') DEFAULT 'user';

-- Nâng cấp user có id=1 thành 'dev' để bạn test quyền truy cập
UPDATE users SET role = 'dev' WHERE id = 1;

-- Tạo bảng FAQs bám sát cấu trúc file Excel/Sheets
CREATE TABLE IF NOT EXISTS faqs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    stt INT NULL,
    nhom_nghiep_vu VARCHAR(100) NULL,
    intent VARCHAR(150) NULL,
    tinh_huong TEXT NULL,
    cau_hoi_mau TEXT NULL,
    xu_ly_tinh_huong TEXT NULL,
    tra_loi_chuan TEXT NOT NULL,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    -- Đánh index Fulltext cho cột câu hỏi mẫu để tìm kiếm LIKE/MATCH mượt hơn
    FULLTEXT KEY ft_faq_search (cau_hoi_mau)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Thêm sẵn 1 user mặc định để test hệ thống
INSERT INTO users (id, username) VALUES (1, 'default_user') 
ON DUPLICATE KEY UPDATE id=id;

SELECT * FROM users;
SELECT * FROM conversations;
SELECT * FROM messages;
