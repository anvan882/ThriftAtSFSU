from flask import Flask, render_template, request, url_for
from dotenv import load_dotenv
import mysql.connector
import os

load_dotenv()

app = Flask(__name__)

# === Database Connection Dev ===
db = mysql.connector.connect(
    user=os.getenv("DB_USER"),
    host=os.getenv("DB_HOST"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    port=os.getenv("DB_PORT"),
)

# === Routes ===

# Home Page: also serves as search form
@app.route("/")
def home():
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT name FROM Categories")
    categories = [row['name'] for row in cursor.fetchall()]
    return render_template('index.html', categories=categories, keyword='', category='')

# Search Results Page
@app.route("/search", methods=["GET"])
def search():
    category = request.args.get('category', '')
    keyword = request.args.get('keyword', '')

    cursor = db.cursor(dictionary=True)
    
    query = """
        SELECT p.title, p.price, p.description, p.product_image AS image_url, c.name AS category_name
        FROM Products p
        JOIN Categories c ON p.category_id = c.category_id
        WHERE (%s = '' OR c.name = %s)
        AND (p.title LIKE %s OR p.description LIKE %s)
    """
    keyword_like = f"%{keyword}%"
    cursor.execute(query, (category, category, keyword_like, keyword_like))
    results = cursor.fetchall()

    return render_template('results.html', items=results, count=len(results),
                           keyword=keyword, category=category)


# About Me Pages
@app.route("/joe")
def joe():
    return render_template('joe.html', name="Joseph Shur") 

@app.route("/hilary")
def hilary():
    return render_template('hilary.html', name="Hilary Lui")

@app.route("/joseph")
def joseph():
    return render_template('about_JosephA.html', name="Joseph Alhambra")

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