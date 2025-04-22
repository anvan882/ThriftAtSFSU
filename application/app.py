from flask import Flask, render_template, request, Response, abort, url_for, redirect, flash, session, send_file
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import pooling, Error
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") # Needed for flash messages
if not app.secret_key:
    print("Warning: FLASK_SECRET_KEY is not set. Flashing will not work.")
    raise ValueError("No FLASK_SECRET_KEY set for Flask application")

# === Decorators ===
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def public_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' in session:
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# === Database Connection Pool ===
dbconfig = {
    "user": os.getenv("DB_USER"),
    "host": os.getenv("DB_HOST"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": os.getenv("DB_PORT"),
}
cnxpool = pooling.MySQLConnectionPool(pool_name="mypool", pool_size=10, **dbconfig)

# === Context Processors ===
@app.context_processor
def inject_user_status():
    user_is_logged_in = ('user_id' in session)
    profile_pic_url = None
    if user_is_logged_in:
        # In a real app, you might query the DB here to check if the user *actually* has a pic
        # For simplicity, we'll just generate the URL. The route handles fallback.
        profile_pic_url = url_for('serve_profile_picture')
    else:
        # Optionally provide a default/guest avatar URL even for logged-out users
        # profile_pic_url = url_for('static', filename='avatars/guest.png') 
        pass

    return dict(
        user_is_logged_in=user_is_logged_in,
        profile_pic_url=profile_pic_url
    )

@app.context_processor
def inject_categories():
    # Don't inject categories for auth pages
    if request.endpoint in ['login', 'signup']:
        return {}
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT name FROM Categories")
        categories = [r['name'] for r in cursor.fetchall()]
        cursor.close()
        connection.close()
        return dict(categories=categories)
    except Exception as e:
        # Log the error or handle it appropriately
        print(f"Error fetching categories: {e}")
        return dict(categories=[]) # Return empty list on error

# Define TEAM_INFO globally
TEAM_INFO = {
    'joe': {
        'name': 'Joseph Shur',
        'linkedin_url': 'https://linkedin.com/in/joeshur',
        'github_url': 'https://github.com/joseph-shur'
    },
    'sid': {
        'name': 'Sid Padmanabhuni',
        'linkedin_url': 'https://linkedin.com/in/SidPad03',
        'github_url': 'https://github.com/SidPad03'
    },
    'hilary':  {
        'name': 'Hilary Lui',
        'linkedin_url': 'https://linkedin.com/in/hilarylui17',
        'github_url': 'https://github.com/Hluii'
    },
    'annison': {
        'name': 'Annison Van',
        'linkedin_url': 'https://linkedin.com/in/annisonvan',
        'github_url': 'https://github.com/anvan882'
    },
    'joseph':  {
        'name': 'Joseph Alhambra',
        'linkedin_url': 'https://linkedin.com/in/joseph-alhambra-iii-5a439b353',
        'github_url': 'https://github.com/JosephCVA'
    },
}

@app.context_processor
def inject_team_members():
    """Injects team member information for the 'About Us' dropdown."""
    # Pass only the keys (usernames) and names for the dropdown links
    team_members_for_nav = {
        username: data['name'] for username, data in TEAM_INFO.items()
    }
    return dict(team_members=team_members_for_nav)

@app.route("/", methods=["GET"])
def home():
    """Combined Home Page + Search Page"""
    category = request.args.get('category', '')
    keyword  = request.args.get('keyword', '')

    connection = cnxpool.get_connection()
    cursor = connection.cursor(dictionary=True)

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

@app.route('/profile_picture')
@login_required # User must be logged in to view their picture
def serve_profile_picture():
    user_id = session.get('user_id')
    if not user_id:
        # Should not happen due to @login_required, but belt-and-suspenders
        abort(401) 

    connection = None
    cursor = None
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT profile_picture FROM Users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        if user and user.get('profile_picture'):
            img = user['profile_picture']
            # Basic MIME type detection (same as serve_image)
            if img.startswith(b'\x89PNG'):
                mime = 'image/png'
            elif img.startswith(b'\xff\xd8'):
                mime = 'image/jpeg'
            else:
                mime = 'application/octet-stream'
            return Response(img, mimetype=mime)
        else:
            # Serve default avatar if no picture found or DB error
            # Make sure you have a default avatar image at static/avatars/default.png
            default_avatar_path = os.path.join(app.static_folder, 'avatars', 'default.png')
            try:
                return send_file(default_avatar_path, mimetype='image/png')
            except FileNotFoundError:
                 # Fallback if default avatar is missing
                print("Error: Default avatar not found at static/avatars/default.png")
                abort(404)

    except Error as db_err:
        print(f"Database error serving profile picture: {db_err}")
        abort(500)
    except Exception as e:
        print(f"Error serving profile picture: {e}")
        abort(500)
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

# === About Pages ===
@app.route('/about/<username>')
def about(username):
    # TEAM_INFO moved to global scope
    info = TEAM_INFO.get(username)
    if not info:
        abort(404)

    # this will load templates/about_<username>.html
    template_name = f'about_team/{username}.html'
    return render_template(template_name, **info)

# === Other Routes ===
@app.route("/profile")
@login_required
def profile():
    return render_template('pages/profile.html')

@app.route('/login', methods=['GET', 'POST'])
@public_only
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('pages/auth/login.html')

        connection = None
        cursor = None
        try:
            connection = cnxpool.get_connection()
            # Fetch user with password hash
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT user_id, password FROM Users WHERE email = %s", (email,))
            user = cursor.fetchone()

            if user and check_password_hash(user['password'], password):
                # Password matches
                # TODO: Implement session management (e.g., flask-login)
                session['user_id'] = user['user_id'] # Set user_id in session
                session.permanent = True # Optional: Make session persistent 
                flash('Login successful! Welcome back.', 'success')
                return redirect(url_for('home'))
            else:
                # Invalid credentials
                flash("Couldn't login. Please check your email and password.", 'error') # Updated message
                return render_template('pages/auth/login.html')

        except Error as db_err:
            print(f"Database error during login: {db_err}")
            flash('An error occurred during login. Please try again later.', 'error')
            return render_template('pages/auth/login.html')
        except Exception as e:
            print(f"An unexpected error occurred during login: {e}")
            flash('An unexpected login error occurred.', 'error')
            return render_template('pages/auth/login.html')
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    # For GET requests
    return render_template('pages/auth/login.html')

@app.route('/signup', methods=['GET', 'POST'])
@public_only
def signup():
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone_number = request.form.get('phone_number')
        profile_picture = request.files.get('profile_picture')

        # --- Validation --- 
        if not all([first_name, last_name, email, password, phone_number]):
            flash('All text fields are required.', 'error')
            return render_template('pages/auth/signup.html', form_data=request.form) # Pass form data
        
        # SFSU Email Validation
        if not email.lower().endswith('@sfsu.edu'):
            flash('Please use a valid SFSU email address (ending in @sfsu.edu).', 'error')
            return render_template('pages/auth/signup.html', form_data=request.form) # Pass form data

        # Phone Number Validation (10 digits)
        digits_only = ''.join(filter(str.isdigit, phone_number))
        if not digits_only.isdigit() or len(digits_only) != 10:
             flash('Please enter a valid 10-digit phone number.', 'error')
             return render_template('pages/auth/signup.html', form_data=request.form)

        if not profile_picture or profile_picture.filename == '':
            flash('Profile picture is required.', 'error')
            return render_template('pages/auth/signup.html', form_data=request.form) # Pass form data

        # Check file type (simple check based on extension)
        allowed_extensions = {'png', 'jpg', 'jpeg'}
        if '.' not in profile_picture.filename or \
           profile_picture.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
            flash('Invalid file type for profile picture. Please use PNG, JPG, or JPEG.', 'error')
            return render_template('pages/auth/signup.html', form_data=request.form) # Pass form data
        # --- End Validation ---

        hashed_password = generate_password_hash(password)
        picture_blob = profile_picture.read()

        connection = None
        cursor = None
        try:
            connection = cnxpool.get_connection()
            cursor = connection.cursor()

            # Check if email already exists
            cursor.execute("SELECT user_id FROM Users WHERE email = %s", (email,))
            if cursor.fetchone():
                flash('Email address already registered.', 'error')
                return render_template('pages/auth/signup.html', form_data=request.form) # Pass form data

            # Insert new user
            insert_query = """
            INSERT INTO Users (first_name, last_name, email, password, phone_number, profile_picture)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            user_data = (first_name, last_name, email, hashed_password, phone_number, picture_blob)
            cursor.execute(insert_query, user_data)
            connection.commit()

            flash('Account created successfully! Please log in.', 'success') # Updated message
            return redirect(url_for('login')) # Redirect to login on success

        except Error as db_err:
            print(f"Database error: {db_err}")
            flash('Signup unsuccessful. A database error occurred.', 'error') # Updated message
            # Optional: Rollback transaction if something went wrong
            if connection and connection.is_connected():
                connection.rollback()
            return render_template('pages/auth/signup.html', form_data=request.form) # Pass form data
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            flash('Signup unsuccessful. An unexpected error occurred.', 'error') # Updated message
            return render_template('pages/auth/signup.html', form_data=request.form) # Pass form data
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    # For GET requests
    return render_template('pages/auth/signup.html', form_data={}) # Pass empty dict for GET

@app.route('/listingIndie')
@login_required
def listingIndie():
    return render_template('pages/listings/listing_indie.html')

@app.route('/newListing')
@login_required
def newListing():
    return render_template('pages/listings/new_listing.html')

# Messages
@app.route('/messages')
@login_required
def messages():
    # Active conversation (highlighted in the sidebar)
    active_user = {
        "id": 1,
        "name": "John Doe",
        "avatar_url": "/static/avatars/john.png",
        "online": True,
        "last_message": "Hey, are you coming?"
    }

    # All of the "other" conversations, now with a direction flag
    all_users = [
        {
            "id": 2,
            "name": "Alice Smith",
            "avatar_url": "/static/avatars/alice.png",
            "online": False,
            "last_message": "Thanks for the update!",
            "direction": "incoming"
        },
        {
            "id": 3,
            "name": "Bob Johnson",
            "avatar_url": "/static/avatars/bob.png",
            "online": True,
            "last_message": "Let's catch up soon.",
            "direction": "outgoing"
        },
        {
            "id": 4,
            "name": "Carol Lee",
            "avatar_url": "/static/avatars/carol.png",
            "online": True,
            "last_message": "Got it, thanks!",
            "direction": "incoming"
        }
    ]

    # Split into two lists
    incoming_users = [u for u in all_users if u["direction"] == "incoming"]
    outgoing_users = [u for u in all_users if u["direction"] == "outgoing"]

    # The user whose chat is open on the right
    chat_user = {
        "name": active_user["name"],
        "avatar_url": active_user["avatar_url"],
        "online": active_user["online"],
        "status_text": "Active now"
    }

    # Chat history messages
    messages = [
        {"text": "Hi there!",           "timestamp": "10:01 AM", "is_sent": False},
        {"text": "Hello!",              "timestamp": "10:02 AM", "is_sent": True},
        {"text": "How are you?",        "timestamp": "10:03 AM", "is_sent": False},
        {"text": "I'm good—thanks!",    "timestamp": "10:04 AM", "is_sent": True},
        {"text": "Want to grab lunch?", "timestamp": "10:05 AM", "is_sent": False}
    ]

    return render_template(
        'pages/messaging.html',
        active_user=active_user,
        incoming_users=incoming_users,
        outgoing_users=outgoing_users,
        chat_user=chat_user,
        messages=messages
    )

# Wishlist Page
@app.route('/wishlist')
@login_required
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
    return render_template('pages/wishlist.html', items=items)

@app.route('/logout')
@login_required # Must be logged in to log out
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.debug = os.getenv("FLASK_ENV") != "production"
    app.run()
