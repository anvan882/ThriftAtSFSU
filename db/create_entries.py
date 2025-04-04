import mysql.connector
from mysql.connector import errorcode, Binary
import os
import re
from decimal import Decimal


def get_image_filename(title):
    """
    Convert the product title to a lowercase, conjoined string.
    Example: "iPhone 12" becomes "iphone12.jpg"
    """
    return re.sub(r'\W+', '', title.lower()) + ".jpg"

db_name = input("Enter the name of the database to connect to: ").strip()

# Database connection config
db = mysql.connector.connect(
    user=os.getenv("DB_USER"),
    host=os.getenv("DB_HOST"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    port=os.getenv("DB_PORT"),
)

# Sample Users and Categories
sample_users = [
    ('Alice', 'Smith', 'alice@example.com', 'hashed_password1', '1234567890'),
    ('Bob', 'Johnson', 'bob@example.com', 'hashed_password2', '0987654321')
]

sample_categories = [
    ('Electronics', 'Devices and gadgets'),
    ('Books', 'All kinds of books'),
    ('Clothing', 'Men and women apparel')
]

# Product sample data using email and category name as placeholders
sample_products = [
    ('iPhone 12', 'A used iPhone 12 in good condition.', 599.99, 'Electronics', 'alice@example.com'),
    ('Harry Potter Book Set', 'All 7 books, hardcover.', 75.00, 'Books', 'bob@example.com'),
    ('Leather Jacket', 'Black leather jacket, barely used.', 120.00, 'Clothing', 'alice@example.com'),
    ('Samsung Galaxy S21', 'Slightly used, works perfectly.', 499.99, 'Electronics', 'bob@example.com'),
    ('MacBook Pro 2020', '16-inch, excellent condition.', 1399.00, 'Electronics', 'alice@example.com'),
    ('AirPods Pro', 'With wireless charging case.', 159.00, 'Electronics', 'bob@example.com'),
    ('Kindle Paperwhite', '8GB version, almost new.', 89.99, 'Books', 'alice@example.com'),
    ('The Great Gatsby', 'Vintage edition with notes.', 10.00, 'Books', 'bob@example.com'),
    ('Python Programming', 'Beginner to Advanced, 3rd edition.', 25.00, 'Books', 'alice@example.com'),
    ('White Shirt', 'White cotton t-shirt, size M.', 15.00, 'Clothing', 'alice@example.com'),
    ('Jeans', "Blue Levi's jeans, size 32.", 40.00, 'Clothing', 'bob@example.com'),
    ('Winter Coat', 'Heavy-duty coat, size L.', 85.00, 'Clothing', 'alice@example.com'),
    ('JBL Speaker', 'Portable and waterproof.', 45.99, 'Electronics', 'bob@example.com'),
    ('Monitor 27"', '4K UHD monitor with HDMI input.', 279.99, 'Electronics', 'alice@example.com'),
    ('Office Mouse', 'Wireless ergonomic mouse.', 29.99, 'Electronics', 'bob@example.com'),
    ('Notebook Set', 'Set of 5 college-ruled notebooks.', 12.50, 'Books', 'bob@example.com'),
    ('Hoodie', 'Gray hoodie, fleece-lined.', 35.00, 'Clothing', 'alice@example.com'),
    ('Sneakers', 'Nike running shoes, size 10.', 60.00, 'Clothing', 'bob@example.com')
]

# Path to your images folder
image_folder = "/home/sid/Code/db/images"  # Update if needed

try:
    cnx = mysql.connector.connect(**config)
    cursor = cnx.cursor(prepared=True)

    # Insert Users
    cursor.executemany("""
        INSERT INTO Users (first_name, last_name, email, password, phone_number)
        VALUES (%s, %s, %s, %s, %s)
    """, sample_users)

    # Insert Categories
    cursor.executemany("""
        INSERT INTO Categories (name, description)
        VALUES (%s, %s)
    """, sample_categories)

    # Commit before selecting IDs
    cnx.commit()

    # Map emails to user_ids
    cursor.execute("SELECT user_id, email FROM Users")
    user_map = {email: user_id for user_id, email in cursor.fetchall()}

    # Map category names to category_ids
    cursor.execute("SELECT category_id, name FROM Categories")
    category_map = {name: category_id for category_id, name in cursor.fetchall()}

    # Prepare product insert
    insert_product_query = """
        INSERT INTO Products (title, description, price, category_id, seller_id, product_image)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    
    for product in sample_products:
        title, description, price, category_name, seller_email = product

        seller_id = user_map.get(seller_email)
        category_id = category_map.get(category_name)

        print (f"Processing product: {title}, Seller ID: {seller_id}, Category ID: {category_id}")
        image_filename = get_image_filename(title)
        image_path = os.path.join(image_folder, image_filename)

        print(f"Image path: {image_path}")

        try:
            with open(image_path, "rb") as img_file:
                print(f"Reading image file: {image_path}")
                image_blob = Binary(img_file.read())  # Wrap binary data explicitly
        except FileNotFoundError:
            print(f"Warning: Image file not found for product '{title}' at {image_path}. Inserting NULL.")
            image_blob = None

        # Convert explicitly to Decimal
        price_decimal = Decimal(str(price))

        product_data = (title, description, price_decimal, category_id, seller_id, image_blob)
        cursor.execute(insert_product_query, product_data)

    cnx.commit()
    print("Sample data and product images inserted successfully.")

except mysql.connector.Error as err:
    print("Error:", err)
finally:
    if 'cursor' in locals():
        cursor.close()
    if 'cnx' in locals() and cnx.is_connected():
        cnx.close()
