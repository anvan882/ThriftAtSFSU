from flask import Flask, render_template, request, url_for, Response
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

# Home Page: also serves as search form
@app.route("/")
def home():
    connection = cnxpool.get_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT name FROM Categories")
    categories = [row['name'] for row in cursor.fetchall()]
    cursor.close()
    connection.close()
    return render_template('index.html', categories=categories, keyword='', category='')

# Search Results Page (avoiding loading image blobs)
@app.route("/search", methods=["GET"])
def search():
    category = request.args.get('category', '')
    keyword = request.args.get('keyword', '')

    connection = cnxpool.get_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Get categories for the search bar on the results page
    cursor.execute("SELECT name FROM Categories")
    categories = [row['name'] for row in cursor.fetchall()]
    
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

    return render_template('results.html', items=results, count=len(results),
                           keyword=keyword, category=category, categories=categories)

# Serve Image Route with dynamic MIME type detection
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
        # Detect image type by inspecting the first bytes of the blob
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
    return render_template('joe.html', name="Joseph Shur") 

@app.route("/hilary")
def hilary():
    return render_template('hilary.html', name="Hilary Lui")

@app.route("/joseph")
def joseph():
    return render_template('joseph.html', name="Joseph Alhambra")

@app.route("/annison")
def annison():
    return render_template('annison.html', name="Annison Van")

@app.route("/sid")
def sid():
    return render_template('sid.html', name="Sid Padmanabhuni")

if __name__ == '__main__':
    if os.getenv("FLASK_ENV") == "production":
        app.debug = False
    else:
        app.debug = True
    app.run()