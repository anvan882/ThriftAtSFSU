from flask import Flask, render_template, request, Response
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import pooling
import os

load_dotenv()

app = Flask(__name__)

# === Database Connection Pool ===
dbconfig = {
    "user": os.getenv("DB_USER"),
    "host": os.getenv("DB_HOST"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": os.getenv("DB_PORT"),
}
cnxpool = pooling.MySQLConnectionPool(pool_name="mypool", pool_size=10, **dbconfig)

@app.route("/", methods=["GET"])
def home():
    """Combined Home Page + Search Page"""

    # Retrieve possible filter values from the query parameters
    category = request.args.get('category', '')
    keyword = request.args.get('keyword', '')

    # Fetch all categories to populate the dropdown
    connection = cnxpool.get_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT name FROM Categories")
    categories = [row['name'] for row in cursor.fetchall()]

    # If no category/keyword specified, it shows all products
    # If category or keyword is specified, it filters accordingly
    query = """
        SELECT p.product_id, p.title, p.price, p.description, c.name AS category_name,
               IF(p.product_image IS NOT NULL, 1, 0) AS has_image
        FROM Products p
        JOIN Categories c ON p.category_id = c.category_id
        WHERE (%s = '' OR c.name = %s)
          AND (p.title LIKE %s OR p.description LIKE %s)
    """
    keyword_like = f"%{keyword}%"
    cursor.execute(query, (category, category, keyword_like, keyword_like))
    results = cursor.fetchall()

    cursor.close()
    connection.close()

    # Pass categories, the filtered results, and the current search parameters
    return render_template('index.html',
                           categories=categories,
                           items=results,
                           keyword=keyword,
                           category=category,
                           count=len(results))

@app.route('/image/<int:product_id>')
def serve_image(product_id):
    connection = cnxpool.get_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT product_image FROM Products WHERE product_id = %s", (product_id,))
    result = cursor.fetchone()
    cursor.close()
    connection.close()
    
    if result and result.get('product_image'):
        image_blob = result['product_image']
        if image_blob.startswith(b'\x89PNG'):
            mime = 'image/png'
        elif image_blob.startswith(b'\xff\xd8'):
            mime = 'image/jpeg'
        else:
            mime = 'application/octet-stream'
        return Response(image_blob, mimetype=mime)
    return Response(status=404)

# About Me Pages
@app.route("/joe")
def joe():
    return render_template('about_team/joe.html', name="Joseph Shur") 

@app.route("/hilary")
def hilary():
    return render_template('about_team/hilary.html', name="Hilary Lui")

@app.route("/joseph")
def joseph():
    return render_template('about_team/joseph.html', name="Joseph Alhambra")

@app.route("/annison")
def annison():
    return render_template('about_team/annison.html', name="Annison Van")

@app.route("/sid")
def sid():
    return render_template('about_team/sid.html', name="Sid Padmanabhuni")

@app.route('/login')
def login():
    return render_template('auth/login.html')

@app.route('/signup')
def signup():
    return render_template('auth/signup.html')

# Messaging page
@app.route("/messaging_page")
def messaging():
    users = [
        {'name': 'John Doe'},
        {'name': 'Jane Doe'}
    ]
    return render_template('messaging_page.html', users=users)


if __name__ == '__main__':
    if os.getenv("FLASK_ENV") == "production":
        app.debug = False
    else:
        app.debug = True
    app.run()