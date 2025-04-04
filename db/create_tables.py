import mysql.connector
from mysql.connector import errorcode
import time
import os

db_name = input("Enter the name of the database to connect to: ").strip()

# Database connection config
db = mysql.connector.connect(
    user="ubuntu",
    host="127.0.0.1",
    password="921652677",
    database=db_name,
    port=3306,
)

# Define table creation SQL
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
        status ENUM('available', 'sold') DEFAULT 'available',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        product_image LONGBLOB,
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

TABLES['Transactions'] = (
    """
    CREATE TABLE IF NOT EXISTS Transactions (
        transaction_id INT AUTO_INCREMENT PRIMARY KEY,
        buyer_id INT,
        seller_id INT,
        product_id INT,
        agreed_price DECIMAL(10,2),
        status ENUM('completed', 'canceled') DEFAULT 'completed',
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (buyer_id) REFERENCES Users(user_id),
        FOREIGN KEY (seller_id) REFERENCES Users(user_id),
        FOREIGN KEY (product_id) REFERENCES Products(product_id)
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

# Table drop order (reverse of dependency)
DROP_ORDER = [
    "Wishlist",
    "Transactions",
    "Reviews",
    "Messages",
    "Products",
    "Categories",
    "Users"
]

# Prompt user for action
action = input("Enter action (drop, create, reset): ").strip().lower()

try:
    cnx = db  # using our already created connection
    cursor = cnx.cursor()

    if action in ['drop', 'reset']:
        print("Disabling foreign key checks...")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")

        for table in DROP_ORDER:
            print(f"Dropping table `{table}` if it exists...")
            cursor.execute(f"DROP TABLE IF EXISTS {table};")
            time.sleep(1)  # Pause for 1 second

        print("Re-enabling foreign key checks...")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        cnx.commit()
        print("Tables dropped successfully.")

    if action in ['create', 'reset']:
        for table_name, table_sql in TABLES.items():
            print(f"Creating table `{table_name}`...")
            cursor.execute(table_sql)
            time.sleep(1)  # Pause for 1 second
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
