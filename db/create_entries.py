import mysql.connector
from mysql.connector import errorcode, Binary
import os
import re
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

def get_image_filename(title, ext='jpg'):
    """
    Convert the product title to a lowercase, conjoined string with the specified extension.
    Example: "iPhone 12" becomes "iphone12.jpg" (if ext='jpg')
    """
    return re.sub(r'\W+', '', title.lower()) + f".{ext}"

image_folder = os.path.join(os.path.dirname(__file__), "images")

db_name = input("Enter the name of the database to connect to: ").strip()

db = mysql.connector.connect(
    user=os.getenv("DB_USER"),
    host=os.getenv("DB_HOST"),
    password=os.getenv("DB_PASSWORD"),
    database=db_name,
    port=os.getenv("DB_PORT"),
)

sample_users = [
    ('Alice', 'Smith', 'alice@example.com', 'hashed_password1', '1234567890', 'SFSU student selling items I no longer need. Looking for good homes for my stuff!'),
    ('Bob', 'Johnson', 'bob@example.com', 'hashed_password2', '0987654321', 'Grad student at SFSU. I buy and sell tech and books. Quick responses and fair prices.')
]

sample_categories = [
    ('Electronics', 'Devices and gadgets'),
    ('Books', 'All kinds of books'),
    ('Clothing', 'Men and women apparel'),
    ('Textbooks', 'Course materials and academic books'),
    ('Furniture', 'Dorm and apartment furniture'),
    ('School Supplies', 'Notebooks, stationery, and study materials'),
    ('Computer Accessories', 'Keyboards, mice, cables, and peripherals'),
    ('Sports & Fitness', 'Exercise equipment and sports gear'),
    ('Home Decor', 'Decorative items and small furnishings'),
    ('Kitchen & Dining', 'Cookware, utensils, and small appliances'),
    ('Musical Instruments', 'Instruments, equipment, and accessories'),
    ('Video Games', 'Games, consoles, and gaming accessories'),
    ('Art & Craft Supplies', 'Materials for creative projects'),
    ('Bicycles & Transportation', 'Bikes, skateboards, and scooters'),
    ('Collectibles', 'Trading cards, figures, and memorabilia'),
    ('Dorm Essentials', 'Storage, organizers, and dorm necessities'),
    ('Beauty & Personal Care', 'Unused cosmetics and personal items'),
    ('Tickets & Events', 'Campus and local event tickets'),
    ('Handmade Crafts', 'Student-made items and crafts')
]

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

try:
    cnx = db
    cursor = cnx.cursor(prepared=True)

    try:
        cursor.execute("ALTER TABLE Users ADD COLUMN bio TEXT")
        print("Added bio column to Users table")
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_DUP_FIELDNAME:
            pass
        else:
            print(f"Error adding bio column: {err}")
    
    try:
        cursor.execute("ALTER TABLE Products ADD COLUMN `condition` VARCHAR(50)")
        print("Added condition column to Products table")
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_DUP_FIELDNAME:
            pass
        else:
            print(f"Error adding condition column: {err}")
    
    cursor.executemany("""
        INSERT INTO Users (first_name, last_name, email, password, phone_number, bio)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, sample_users)

    cursor.executemany("""
        INSERT INTO Categories (name, description)
        VALUES (%s, %s)
    """, sample_categories)

    cnx.commit()

    cursor.execute("SELECT user_id, email FROM Users")
    user_map = {email: user_id for user_id, email in cursor.fetchall()}

    cursor.execute("SELECT category_id, name FROM Categories")
    category_map = {name: category_id for category_id, name in cursor.fetchall()}

    insert_product_query = """
        INSERT INTO Products (title, description, price, category_id, seller_id, `condition`)
        VALUES (%s, %s, %s, %s, %s, %s)
    """

    insert_image_query = """
        INSERT INTO ProductImages (product_id, image_data, image_order)
        VALUES (%s, %s, %s)
    """

    for product in sample_products:
        title, description, price, category_name, seller_email, condition = product

        seller_id = user_map.get(seller_email)
        category_id = category_map.get(category_name)

        print(f"Processing product: {title}, Seller ID: {seller_id}, Category ID: {category_id}")

        price_decimal = Decimal(str(price))
        product_data = (title, description, price_decimal, category_id, seller_id, condition)
        cursor.execute(insert_product_query, product_data)
        product_id = cursor.lastrowid
        print(f"Inserted product {title} with ID: {product_id}")

        image_filename = get_image_filename(title)
        image_path = os.path.join(image_folder, image_filename)
        print(f"Image path: {image_path}")

        try:
            with open(image_path, "rb") as img_file:
                print(f"Reading image file: {image_path}")
                image_blob = Binary(img_file.read())
                image_data = (product_id, image_blob, 0)
                cursor.execute(insert_image_query, image_data)
                print(f"Inserted image for product ID: {product_id}")
        except FileNotFoundError:
            print(f"Warning: Image file not found for product '{title}' at {image_path}. No image inserted.")

    cnx.commit()
    print("Sample data and product images inserted successfully.")

except mysql.connector.Error as err:
    print("Error:", err)
finally:
    if 'cursor' in locals():
        cursor.close()
    if 'cnx' in locals() and cnx.is_connected():
        cnx.close()