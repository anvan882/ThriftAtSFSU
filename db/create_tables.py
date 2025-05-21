import mysql.connector
from mysql.connector import errorcode
import time
import os
from dotenv import load_dotenv

load_dotenv()

db_name = input("Enter the name of the database to connect to: ").strip()
action = input("Enter action (create, drop, or reset): ").strip().lower()

db = mysql.connector.connect(
    user=os.getenv("DB_USER"),
    host=os.getenv("DB_HOST"),
    password=os.getenv("DB_PASSWORD"),
    database=db_name,
    port=os.getenv("DB_PORT"),
)

TABLES = {}

TABLES['Users'] = (
    """
    CREATE TABLE IF NOT EXISTS Users (
        user_id INT AUTO_INCREMENT PRIMARY KEY,
        first_name VARCHAR(100),
        last_name VARCHAR(100),
        email VARCHAR(255) UNIQUE,
        password VARCHAR(255),
        phone_number VARCHAR(20),
        profile_picture LONGBLOB,
        bio TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_admin BOOLEAN DEFAULT FALSE
    );
    """
)

TABLES['Categories'] = (
    """
    CREATE TABLE IF NOT EXISTS Categories (
        category_id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100),
        description TEXT
    );
    """
)

TABLES['Products'] = (
    """
    CREATE TABLE IF NOT EXISTS Products (
        product_id INT AUTO_INCREMENT PRIMARY KEY,
        seller_id INT,
        title VARCHAR(255),
        description TEXT,
        price DECIMAL(10,2),
        category_id INT,
        `condition` VARCHAR(50),
        status ENUM('available', 'sold', 'pending-approval') DEFAULT 'available',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (seller_id) REFERENCES Users(user_id),
        FOREIGN KEY (category_id) REFERENCES Categories(category_id)
    );
    """
)

TABLES['Messages'] = (
    """
    CREATE TABLE IF NOT EXISTS Messages (
        message_id INT AUTO_INCREMENT PRIMARY KEY,
        sender_id INT,
        receiver_id INT,
        product_id INT,
        content TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sender_id) REFERENCES Users(user_id),
        FOREIGN KEY (receiver_id) REFERENCES Users(user_id),
        FOREIGN KEY (product_id) REFERENCES Products(product_id)
    );
    """
)

TABLES['Reviews'] = (
    """
    CREATE TABLE IF NOT EXISTS Reviews (
        review_id INT AUTO_INCREMENT PRIMARY KEY,
        reviewer_id INT,
        reviewed_user_id INT,
        rating INT CHECK (rating BETWEEN 1 AND 5),
        comment TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (reviewer_id) REFERENCES Users(user_id),
        FOREIGN KEY (reviewed_user_id) REFERENCES Users(user_id)
    );
    """
)

TABLES['ProductImages'] = (
    """
    CREATE TABLE IF NOT EXISTS ProductImages (
        image_id INT AUTO_INCREMENT PRIMARY KEY,
        product_id INT,
        image_data LONGBLOB,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        image_order INT DEFAULT 0,
        FOREIGN KEY (product_id) REFERENCES Products(product_id) ON DELETE CASCADE
    );
    """
)

TABLES['Wishlist'] = (
    """
    CREATE TABLE IF NOT EXISTS Wishlist (
        wishlist_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        product_id INT,
        date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES Users(user_id),
        FOREIGN KEY (product_id) REFERENCES Products(product_id)
    );
    """
)

TABLES['UserAvailability'] = (
    """
    CREATE TABLE IF NOT EXISTS UserAvailability (
        availability_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        day_of_week ENUM('Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday') NOT NULL,
        time_slot VARCHAR(10) NOT NULL,
        is_available BOOLEAN DEFAULT TRUE,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
        UNIQUE KEY unique_time_slot (user_id, day_of_week, time_slot)
    );
    """
)

TABLES['Reports'] = (
    """
    CREATE TABLE IF NOT EXISTS Reports (
        report_id INT AUTO_INCREMENT PRIMARY KEY,
        reporter_id INT NOT NULL,
        reported_user_id INT,
        reported_product_id INT,
        reason TEXT NOT NULL,
        status ENUM('pending', 'resolved', 'dismissed') DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMP NULL,
        FOREIGN KEY (reporter_id) REFERENCES Users(user_id),
        FOREIGN KEY (reported_user_id) REFERENCES Users(user_id),
        FOREIGN KEY (reported_product_id) REFERENCES Products(product_id) ON DELETE CASCADE
    );
    """
)

DROP_ORDER = [
    "Reports",
    "UserAvailability",
    "Wishlist",
    "ProductImages",
    "Reviews",
    "Messages",
    "Products",
    "Categories",
    "Users"
]

try:
    cnx = db
    cursor = cnx.cursor()

    if action in ['drop', 'reset']:
        print("Disabling foreign key checks...")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")

        for table in DROP_ORDER:
            print(f"Dropping table `{table}` if it exists...")
            cursor.execute(f"DROP TABLE IF EXISTS {table};")
            time.sleep(1)

        print("Re-enabling foreign key checks...")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        cnx.commit()
        print("Tables dropped successfully.")

    if action in ['create', 'reset']:
        for table_name, table_sql in TABLES.items():
            print(f"Creating table `{table_name}`...")
            cursor.execute(table_sql)
            time.sleep(1)
        cnx.commit()
        print("Tables created successfully.")

    if action not in ['drop', 'create', 'reset']:
        print("Invalid action. Please enter 'drop', 'create', or 'reset'.")

except mysql.connector.Error as err:
    if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
        print("Access denied: Check username or password.")
    elif err.errno == errorcode.ER_BAD_DB_ERROR:
        print("Database does not exist.")
    else:
        print(err)
finally:
    if 'cursor' in locals():
        cursor.close()
    if 'cnx' in locals() and cnx.is_connected():
        cnx.close()
