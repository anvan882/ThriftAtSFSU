from flask import Flask, render_template, request, Response, abort, url_for
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
    keyword  = request.args.get('keyword', '')

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
    like_kw = f"%{keyword}%"
    cursor.execute(query, (category, category, like_kw, like_kw))
    results = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'pages/index.html',
        categories=categories,
        items=results,
        keyword=keyword,
        category=category,
        count=len(results),
        show_filters=True
    )

@app.route('/image/<int:product_id>')
def serve_image(product_id):
    connection = cnxpool.get_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT product_image FROM Products WHERE product_id = %s", (product_id,))
    row = cursor.fetchone()
    cursor.close()
    connection.close()

    if row and row.get('product_image'):
        img = row['product_image']
        if img.startswith(b'\x89PNG'):
            mime = 'image/png'
        elif img.startswith(b'\xff\xd8'):
            mime = 'image/jpeg'
        else:
            mime = 'application/octet-stream'
        return Response(img, mimetype=mime)
    return Response(status=404)

# === About Pages ===
@app.route('/about/<username>')
def about(username):
    team_info = {
        'joe': {
            'name': 'Joseph Shur',        
            'linkedin_url': 'https://linkedin.com/in/joeshur',
            'github_url': 'https://github.com/joeshur'
        },
        'sid': {
            'name': 'Sid Padmanabhuni',   
            'linkedin_url': 'https://linkedin.com/in/sidpad',
            'github_url': 'https://github.com/sidpad'
        },
        'hilary':  {
            'name': 'Hilary Lui',         
            'linkedin_url': 'https://linkedin.com/in/hilarylui',
            'github_url': 'https://github.com/hilarylui'
        },
        'annison': {
            'name': 'Annison Van',        
            'linkedin_url': 'https://linkedin.com/in/annisonvan',
            'github_url': 'https://github.com/annisonvan'
        },
        'about_team/joseph':  {
            'name': 'Joseph Alhambra',    
            'linkedin_url': 'https://linkedin.com/in/josephalhambra','github_url': 'https://github.com/josephalhambra'
        },
    }

    info = team_info.get(username)
    if not info:
        abort(404)

    # this will load templates/about_<username>.html
    template_name = f'about_team/{username}.html'
    return render_template(template_name, **info)

# === Other Routes ===
@app.route("/profile")
def profile():
    return render_template('pages/profile.html')

@app.route('/login')
def login():
    return render_template('pages/auth/login.html')

@app.route("/joseph")
def joseph():
    return render_template('joseph.html', name="Joseph Alhambra")

@app.route("/annison")
def annison():
    return render_template('annison.html', name="Annison Van")

@app.route("/sid")
def sid():
    return render_template('sid.html', name="Sid Padmanabhuni")

@app.route('/wishlist')
def wishlist():
    # Dummy data for testing
    items = [
        {
            'product_id': 1,
            'title': 'Vintage Hoodie',
            'price': 20,
            'description': 'Comfy and warm hoodie from the 90s',
            'has_image': True
        },
        {
            'product_id': 2,
            'title': 'Retro Sneakers',
            'price': 45,
            'description': 'Classic 80s style shoes',
            'has_image': False
        }
    ]
    return render_template('wishlist.html', items=items)

if __name__ == '__main__':
    app.debug = os.getenv("FLASK_ENV") != "production"
    app.run()
