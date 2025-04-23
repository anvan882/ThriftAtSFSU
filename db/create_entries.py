import mysql.connector
from mysql.connector import errorcode, Binary
import os
import re
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

def get_image_filename(title, ext='jpg'):
    """
    Convert the product title to a lowercase, conjoined string with the specified extension.
    Example: "iPhone 12" becomes "iphone12.jpg" (if ext='jpg')
    """
    return re.sub(r'\W+', '', title.lower()) + f".{ext}"

db_name = input("Enter the name of the database to connect to: ").strip()

# Database connection config
db = mysql.connector.connect(
    user=os.getenv("DB_USER"),
    host=os.getenv("DB_HOST"),
    password=os.getenv("DB_PASSWORD"),
    database=db_name,
    port=os.getenv("DB_PORT"),
)

# Sample Users and Categories with bio field added
sample_users = [
    ('Alice', 'Smith', 'alice@example.com', 'hashed_password1', '1234567890', 'SFSU student selling items I no longer need. Looking for good homes for my stuff!'),
    ('Bob', 'Johnson', 'bob@example.com', 'hashed_password2', '0987654321', 'Grad student at SFSU. I buy and sell tech and books. Quick responses and fair prices.')
]

sample_categories = [
    ('Electronics', 'Devices and gadgets'),
    ('Books', 'All kinds of books'),
    ('Clothing', 'Men and women apparel')
]

# Product sample data with condition field added
sample_products = [
    ('iPhone 12', 'A used iPhone 12 in good condition.', 599.99, 'Electronics', 'alice@example.com', 'Good Condition'),
    ('Harry Potter Book Set', 'All 7 books, hardcover.', 75.00, 'Books', 'bob@example.com', 'Great Condition'),
    ('Leather Jacket', 'Black leather jacket, barely used.', 120.00, 'Clothing', 'alice@example.com', 'Good Condition'),
    ('Samsung Galaxy S21', 'Slightly used, works perfectly.', 499.99, 'Electronics', 'bob@example.com', 'Good Condition'),
    ('MacBook Pro 2020', '16-inch, excellent condition.', 1399.00, 'Electronics', 'alice@example.com', 'Great Condition'),
    ('AirPods Pro', 'With wireless charging case.', 159.00, 'Electronics', 'bob@example.com', 'Good Condition'),
    ('Kindle Paperwhite', '8GB version, almost new.', 89.99, 'Books', 'alice@example.com', 'Great Condition'),
    ('The Great Gatsby', 'Vintage edition with notes.', 10.00, 'Books', 'bob@example.com', 'Fairly Used'),
    ('Python Programming', 'Beginner to Advanced, 3rd edition.', 25.00, 'Books', 'alice@example.com', 'Good Condition'),
    ('White Shirt', 'White cotton t-shirt, size M.', 15.00, 'Clothing', 'alice@example.com', 'Good Condition'),
    ('Jeans', "Blue Levi's jeans, size 32.", 40.00, 'Clothing', 'bob@example.com', 'Good Condition'),
    ('Winter Coat', 'Heavy-duty coat, size L.', 85.00, 'Clothing', 'alice@example.com', 'Fairly Used'),
    ('JBL Speaker', 'Portable and waterproof.', 45.99, 'Electronics', 'bob@example.com', 'Good Condition'),
    ('Monitor 27"', '4K UHD monitor with HDMI input.', 279.99, 'Electronics', 'alice@example.com', 'Great Condition'),
    ('Office Mouse', 'Wireless ergonomic mouse.', 29.99, 'Electronics', 'bob@example.com', 'Fairly Used'),
    ('Notebook Set', 'Set of 5 college-ruled notebooks.', 12.50, 'Books', 'bob@example.com', 'New'),
    ('Hoodie', 'Gray hoodie, fleece-lined.', 35.00, 'Clothing', 'alice@example.com', 'Good Condition'),
    ('Sneakers', 'Nike running shoes, size 10.', 60.00, 'Clothing', 'bob@example.com', 'Used')
]

# Path to your images folder
image_folder = "/home/sid/Code/csc648-fa25-0104-team15/db/images"  # Update if needed

try:
    cnx = db  # using our already created connection
    cursor = cnx.cursor(prepared=True)

    # First, alter the tables to add the new columns if they don't exist
    try:
        cursor.execute("ALTER TABLE Users ADD COLUMN bio TEXT")
        print("Added bio column to Users table")
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_DUP_FIELDNAME:
            pass # Column already exists, no action needed
        else:
            print(f"Error adding bio column: {err}")
    
    try:
        cursor.execute("ALTER TABLE Products ADD COLUMN `condition` VARCHAR(50)")
        print("Added condition column to Products table")
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_DUP_FIELDNAME:
            pass # Column already exists, no action needed
        else:
            print(f"Error adding condition column: {err}")
    
    # Insert Users with bio
    cursor.executemany("""
        INSERT INTO Users (first_name, last_name, email, password, phone_number, bio)
        VALUES (%s, %s, %s, %s, %s, %s)
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

    # Prepare product insert with condition
    insert_product_query = """
        INSERT INTO Products (title, description, price, category_id, seller_id, `condition`)
        VALUES (%s, %s, %s, %s, %s, %s)
    """

    # Prepare image insert
    insert_image_query = """
        INSERT INTO ProductImages (product_id, image_data, image_order)
        VALUES (%s, %s, %s)
    """

    for product in sample_products:
        title, description, price, category_name, seller_email, condition = product

        seller_id = user_map.get(seller_email)
        category_id = category_map.get(category_name)

        print(f"Processing product: {title}, Seller ID: {seller_id}, Category ID: {category_id}")

        # Insert product with condition
        price_decimal = Decimal(str(price))
        product_data = (title, description, price_decimal, category_id, seller_id, condition)
        cursor.execute(insert_product_query, product_data)
        product_id = cursor.lastrowid # Get the ID of the inserted product
        print(f"Inserted product {title} with ID: {product_id}")

        # Now handle the image
        image_filename = get_image_filename(title)
        image_path = os.path.join(image_folder, image_filename)
        print(f"Image path: {image_path}")

        try:
            with open(image_path, "rb") as img_file:
                print(f"Reading image file: {image_path}")
                image_blob = Binary(img_file.read())  # Wrap binary data explicitly
                # Insert into ProductImages
                image_data = (product_id, image_blob, 0) # Assuming order 0 for the first/only image
                cursor.execute(insert_image_query, image_data)
                print(f"Inserted image for product ID: {product_id}")
        except FileNotFoundError:
            print(f"Warning: Image file not found for product '{title}' at {image_path}. No image inserted.")
            # image_blob = None # No longer needed here

    cnx.commit()
    print("Sample data and product images inserted successfully.")

except mysql.connector.Error as err:
    print("Error:", err)
finally:
    if 'cursor' in locals():
        cursor.close()
    if 'cnx' in locals() and cnx.is_connected():
        cnx.close()