from flask import Flask, render_template, request, Response, abort, url_for, redirect, flash, session, send_file, jsonify
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import pooling, Error
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from datetime import datetime, timedelta

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
        profile_pic_url = url_for('serve_profile_picture')
    else:
        profile_pic_url = url_for('static', filename='pfp/silhouette.png')

    return dict(
        user_is_logged_in=user_is_logged_in,
        profile_pic_url=profile_pic_url
    )

@app.context_processor
def inject_categories():
    # Don't inject categories for auth pages
    if request.endpoint in ['login', 'signup']:
        return {}
    
    connection = None
    cursor = None
    categories = []
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT name FROM Categories")
        categories = [r['name'] for r in cursor.fetchall()]
    except Error as db_err: # Catch specific database errors
        print(f"Database error fetching categories: {db_err}")
    except Exception as e:
        # Log the error or handle it appropriately
        print(f"Error fetching categories: {e}")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
            
    return dict(categories=categories) # Return potentially empty list

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
    # Basic filters
    category = request.args.get('category', '')
    keyword = request.args.get('keyword', '')
    
    # Advanced filters from the sidebar
    min_price_str = request.args.get('min_price', '') # Keep as string initially
    max_price_str = request.args.get('max_price', '') # Keep as string initially
    condition = request.args.get('condition', '')
    rating_str = request.args.get('rating', '') # Keep as string initially
    posted_after = request.args.get('posted_after', '')
    
    connection = None
    cursor = None
    results = []
    min_db_price = 0
    max_db_price = 2000
    min_price = 0
    max_price = 2000
    rating = None
    wishlisted_ids = set() # Initialize empty set for wishlist IDs

    user_id = session.get('user_id') # Get user_id if logged in

    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)

        # If user is logged in, fetch their wishlist IDs
        if user_id:
            cursor.execute("SELECT product_id FROM Wishlist WHERE user_id = %s", (user_id,))
            wishlisted_ids = {row['product_id'] for row in cursor.fetchall()}

        # Get global min/max prices for the slider range
        cursor.execute("SELECT MIN(price) as min_price, MAX(price) as max_price FROM Products WHERE status = 'available'")
        price_range = cursor.fetchone()
        min_db_price = price_range.get('min_price', 0) or 0 # Default to 0 if None or 0
        max_db_price = price_range.get('max_price', 2000) or 2000 # Default to 2000 if None or 0

        # --- Determine filter defaults ---
        # Default min_price filter to actual min_db_price
        default_min_filter = min_db_price 
        # Default max_price filter to actual max_db_price
        default_max_filter = max_db_price 

        # --- Convert filter inputs ---
        try:
            min_price = float(min_price_str) if min_price_str else default_min_filter
        except (ValueError, TypeError):
            min_price = default_min_filter
            
        try:
            max_price = float(max_price_str) if max_price_str else default_max_filter
        except (ValueError, TypeError):
            max_price = default_max_filter
            
        try:
            rating = float(rating_str) if rating_str else None
        except (ValueError, TypeError):
            rating = None

        # --- Build Query ---
        query = """
            SELECT 
                p.product_id, p.title, p.price, p.description, 
                c.name AS category_name,
                pi.image_id AS first_image_id
            FROM Products p
            JOIN Categories c ON p.category_id = c.category_id
            LEFT JOIN ProductImages pi ON p.product_id = pi.product_id AND pi.image_order = 0
        """
        
        params = [] # Initialize parameter list
        
        # For seller rating, we need to join with Reviews if that filter is active
        if rating is not None: # Check if rating filter is active
            query += """
            LEFT JOIN (
                SELECT reviewed_user_id, AVG(rating) as avg_rating
                FROM Reviews
                GROUP BY reviewed_user_id
            ) r ON p.seller_id = r.reviewed_user_id
            """
        
        # --- WHERE clauses ---
        where_clauses = [
            "(%s = '' OR c.name = %s)",
            "(p.title LIKE %s OR p.description LIKE %s)",
            "p.status = 'available'",
            "p.price >= %s",
            "p.price <= %s"
        ]
        params.extend([category, category, f"%{keyword}%", f"%{keyword}%", min_price, max_price])

        # Add condition filter if selected
        condition_param = None
        if condition:
            where_clauses.append("p.`condition` = %s")
            condition_map = {
                'very-worn': 'Very Worn',
                'used': 'Used',
                'fairly-used': 'Fairly Used',
                'good-condition': 'Good Condition',
                'great-condition': 'Great Condition'
            }
            condition_param = condition_map.get(condition, condition)
            params.append(condition_param)
        
        # Add rating filter if selected
        if rating is not None: # Check if rating filter is active
            where_clauses.append("r.avg_rating >= %s")
            params.append(rating)
        
        # Add posted after date filter if selected
        if posted_after:
            where_clauses.append("DATE(p.created_at) >= %s")
            params.append(posted_after)
        
        query += " WHERE " + " AND ".join(where_clauses)
        
        # --- Execute Query ---
        cursor.execute(query, params)
        results = cursor.fetchall()

    except Error as db_err:
        print(f"Database error in home route: {db_err}")
        flash('An error occurred while fetching products.', 'error')
        # Keep default values for render_template in case of DB error before fetch
    except Exception as e:
        print(f"Unexpected error in home route: {e}")
        flash('An unexpected error occurred.', 'error')
        # Keep default values for render_template
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    # --- Render Template ---
    # Use the filter values actually applied (or defaults)
    # Use db values for slider range, actual filter values for slider value
    return render_template(
        'pages/index.html',
        items=results,
        keyword=keyword,
        category=category,
        min_db_price=min_db_price,  # For slider range
        max_db_price=max_db_price,  # For slider range
        min_price=min_price,        # For slider current value
        max_price=max_price,        # For slider current value
        condition=condition,        # For filter state
        rating=rating_str,          # Pass original string back for radio state
        posted_after=posted_after,  # For filter state
        count=len(results),
        show_filters=True,
        wishlisted_ids=wishlisted_ids # Pass wishlisted IDs to template
    )

@app.route('/image/<int:image_id>')
def serve_image(image_id):
    connection = None
    cursor = None
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT image_data FROM ProductImages WHERE image_id = %s", (image_id,))
        row = cursor.fetchone()
        
        if row and row.get('image_data'):
            img = row['image_data']
            # MIME type detection remains the same
            if img.startswith(b'\x89PNG'):
                mime = 'image/png'
            elif img.startswith(b'\xff\xd8'):
                mime = 'image/jpeg'
            else:
                mime = 'application/octet-stream'
            
            # Add caching headers
            response = Response(img, mimetype=mime)
            # Cache for 1 day (86400 seconds)
            response.headers['Cache-Control'] = 'public, max-age=86400'
            response.headers['Expires'] = (datetime.now() + timedelta(days=1)).strftime('%a, %d %b %Y %H:%M:%S GMT')
            return response
        else:
             # If image data not found in DB, fall through to serve placeholder
            pass # Explicitly pass to make flow clear

    except Error as db_err:
        print(f"Database error serving image {image_id}: {db_err}")
        # Fall through to serve placeholder on DB error
    except Exception as e:
        print(f"Unexpected error serving image {image_id}: {e}")
        # Fall through to serve placeholder on other errors
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    
    # --- Serve Placeholder Image --- 
    # This code runs if DB query fails or image data is None
    default_image_path = os.path.join(app.static_folder, 'templatephotos', 'placeholder_img.png')
    try:
        response = send_file(default_image_path, mimetype='image/png')
        # Cache for 1 week (604800 seconds)
        response.headers['Cache-Control'] = 'public, max-age=604800'
        response.headers['Expires'] = (datetime.now() + timedelta(days=7)).strftime('%a, %d %b %Y %H:%M:%S GMT')
        return response
    except FileNotFoundError:
        print(f"Error: Placeholder image not found at {default_image_path}")
        abort(404)

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
            
            response = Response(img, mimetype=mime)
            # Cache for 1 day (86400 seconds)
            response.headers['Cache-Control'] = 'public, max-age=86400'
            response.headers['Expires'] = (datetime.now() + timedelta(days=1)).strftime('%a, %d %b %Y %H:%M:%S GMT')
            return response
        else:
            default_avatar_path = os.path.join(app.static_folder, 'pfp', 'silhouette.png')
            try:
                response = send_file(default_avatar_path, mimetype='image/png')
                # Cache for 1 week (604800 seconds)
                response.headers['Cache-Control'] = 'public, max-age=604800'
                response.headers['Expires'] = (datetime.now() + timedelta(days=7)).strftime('%a, %d %b %Y %H:%M:%S GMT')
                return response
            except FileNotFoundError:
                 # Fallback if default avatar is missing
                print("Error: Default avatar not found at static/pfp/silhouette.png")
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

@app.route('/user_picture/<int:user_id>')
def serve_user_picture(user_id):
    connection = None
    cursor = None
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT profile_picture FROM Users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        if user and user.get('profile_picture'):
            img = user['profile_picture']
            # Basic MIME type detection
            if img.startswith(b'\x89PNG'):
                mime = 'image/png'
            elif img.startswith(b'\xff\xd8'):
                mime = 'image/jpeg'
            else:
                mime = 'application/octet-stream'
            
            response = Response(img, mimetype=mime)
            # Cache for 1 day (86400 seconds)
            response.headers['Cache-Control'] = 'public, max-age=86400'
            response.headers['Expires'] = (datetime.now() + timedelta(days=1)).strftime('%a, %d %b %Y %H:%M:%S GMT')
            return response
        else:
            default_avatar_path = os.path.join(app.static_folder, 'pfp', 'silhouette.png')
            try:
                response = send_file(default_avatar_path, mimetype='image/png')
                # Cache for 1 week (604800 seconds)
                response.headers['Cache-Control'] = 'public, max-age=604800'
                response.headers['Expires'] = (datetime.now() + timedelta(days=7)).strftime('%a, %d %b %Y %H:%M:%S GMT')
                return response
            except FileNotFoundError:
                print("Error: Default avatar not found at static/pfp/silhouette.png")
                abort(404)

    except Error as db_err:
        print(f"Database error serving user picture: {db_err}")
        abort(500)
    except Exception as e:
        print(f"Error serving user picture: {e}")
        abort(500)
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

# === About Pages ===
@app.route('/about/<username>')
def about(username):
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

@app.route('/newListing', methods=['GET', 'POST'])
@login_required
def newListing():
    if request.method == 'POST':
        # Get form data
        title = request.form.get('title')
        price = request.form.get('price')
        category = request.form.get('category')
        condition = request.form.get('condition')
        description = request.form.get('description')
        images = request.files.getlist('images')
        
        # Validation
        errors = False
        
        # Required fields validation
        if not all([title, price, category, condition, description]):
            flash('All fields are required.', 'error')
            errors = True
            
        # Price validation
        try:
            price_decimal = float(price)
            if price_decimal <= 0:
                flash('Price must be greater than zero.', 'error')
                errors = True
        except (ValueError, TypeError):
            flash('Price must be a valid decimal value.', 'error')
            errors = True
            
        # Description length validation (assuming 500 chars max)
        max_desc_length = 500
        if len(description) > max_desc_length:
            flash(f'Description must be less than {max_desc_length} characters.', 'error')
            errors = True
            
        # Images validation
        if not images or images[0].filename == '':
            flash('At least one image is required.', 'error')
            errors = True
        else:
            # Check file types
            allowed_extensions = {'png', 'jpg', 'jpeg'}
            for img in images:
                if '.' not in img.filename or \
                   img.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
                    flash('Invalid file type. Please use PNG, JPG, or JPEG.', 'error')
                    errors = True
                    break
        
        # If validation fails, return form with existing data
        if errors:
            form_data = {
                'title': title,
                'price': price,
                'category': category,
                'condition': condition,
                'description': description
            }
            return render_template('pages/listings/new_listing.html', form_data=form_data)
        
        # Process the form data and save to database
        try:
            connection = cnxpool.get_connection()
            cursor = connection.cursor()
            
            # Get category_id from category name
            cursor.execute("SELECT category_id FROM Categories WHERE name = %s", (category,))
            category_result = cursor.fetchone()
            if not category_result:
                flash('Invalid category selected.', 'error')
                form_data = {
                    'title': title,
                    'price': price,
                    'category': category,
                    'condition': condition,
                    'description': description
                }
                return render_template('pages/listings/new_listing.html', form_data=form_data)
            
            category_id = category_result[0]
            
            # Insert product
            insert_product_query = """
            INSERT INTO Products (title, description, price, category_id, seller_id, status, `condition`)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            seller_id = session.get('user_id')
            product_data = (title, description, price_decimal, category_id, seller_id, 'available', condition)
            cursor.execute(insert_product_query, product_data)
            product_id = cursor.lastrowid
            
            # Insert images
            for i, img in enumerate(images):
                img_data = img.read()
                insert_image_query = """
                INSERT INTO ProductImages (product_id, image_data, image_order)
                VALUES (%s, %s, %s)
                """
                cursor.execute(insert_image_query, (product_id, img_data, i))
            
            connection.commit()
            flash('Listing created successfully!', 'success')
            return redirect(url_for('home'))
            
        except Error as db_err:
            print(f"Database error: {db_err}")
            flash('An error occurred while creating your listing. Please try again.', 'error')
            if connection and connection.is_connected():
                connection.rollback()
            form_data = {
                'title': title,
                'price': price,
                'category': category,
                'condition': condition,
                'description': description
            }
            return render_template('pages/listings/new_listing.html', form_data=form_data)
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            flash('An unexpected error occurred. Please try again.', 'error')
            form_data = {
                'title': title,
                'price': price,
                'category': category,
                'condition': condition,
                'description': description
            }
            return render_template('pages/listings/new_listing.html', form_data=form_data)
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()
    
    # For GET requests
    return render_template('pages/listings/new_listing.html', form_data={})

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
    user_id = session['user_id']
    items = []
    connection = None
    cursor = None
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Fetch wishlisted items details for the user
        # Join Wishlist, Products, and optionally ProductImages to get the first image
        query = """
            SELECT 
                p.product_id, p.title, p.price, p.description,
                pi.image_id AS first_image_id
            FROM Wishlist w
            JOIN Products p ON w.product_id = p.product_id
            LEFT JOIN ProductImages pi ON p.product_id = pi.product_id AND pi.image_order = 0
            WHERE w.user_id = %s AND p.status = 'available' 
        """ # Added check for p.status = 'available'
        cursor.execute(query, (user_id,))
        items = cursor.fetchall()

    except Error as db_err:
        print(f"Database error fetching wishlist: {db_err}")
        flash('Could not load your wishlist due to a database error.', 'error')
    except Exception as e:
        print(f"Error fetching wishlist: {e}")
        flash('An unexpected error occurred while loading your wishlist.', 'error')
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return render_template('pages/wishlist.html', items=items)

@app.route('/add_to_wishlist/<int:product_id>', methods=['POST'])
@login_required
def add_to_wishlist(product_id):
    user_id = session['user_id']
    connection = None
    cursor = None
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor()

        # Check if product exists and is available
        cursor.execute("SELECT product_id FROM Products WHERE product_id = %s AND status = 'available'", (product_id,))
        if not cursor.fetchone():
             return jsonify({'success': False, 'message': 'Product not found or unavailable.'}), 404

        # Check if already in wishlist
        cursor.execute("SELECT wishlist_id FROM Wishlist WHERE user_id = %s AND product_id = %s", (user_id, product_id))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': 'Item already in wishlist.'}), 409 # 409 Conflict

        # Add to wishlist
        insert_query = "INSERT INTO Wishlist (user_id, product_id) VALUES (%s, %s)"
        cursor.execute(insert_query, (user_id, product_id))
        connection.commit()
        return jsonify({'success': True, 'message': 'Item added to wishlist.'})

    except Error as db_err:
        print(f"Database error adding to wishlist: {db_err}")
        if connection: connection.rollback()
        return jsonify({'success': False, 'message': 'Database error.'}), 500
    except Exception as e:
        print(f"Error adding to wishlist: {e}")
        if connection: connection.rollback()
        return jsonify({'success': False, 'message': 'An unexpected error occurred.'}), 500
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

@app.route('/remove_from_wishlist/<int:product_id>', methods=['POST'])
@login_required
def remove_from_wishlist(product_id):
    user_id = session['user_id']
    connection = None
    cursor = None
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor()

        # Delete from wishlist
        delete_query = "DELETE FROM Wishlist WHERE user_id = %s AND product_id = %s"
        cursor.execute(delete_query, (user_id, product_id))
        
        # Check if any row was actually deleted
        if cursor.rowcount == 0:
             # Optionally, you could check if the product exists first, but 
             # simply attempting deletion and checking rowcount is often sufficient.
             # This handles cases where the item was already removed or never existed for this user.
             return jsonify({'success': False, 'message': 'Item not found in wishlist.'}), 404

        connection.commit()
        
        # Check if the request came from the wishlist page to redirect
        referer = request.headers.get("Referer")
        if referer and url_for('wishlist') in referer:
             flash('Item removed from wishlist.', 'success')
             return redirect(url_for('wishlist')) # Redirect only if removing from wishlist page
        else:
             return jsonify({'success': True, 'message': 'Item removed from wishlist.'})


    except Error as db_err:
        print(f"Database error removing from wishlist: {db_err}")
        if connection: connection.rollback()
        return jsonify({'success': False, 'message': 'Database error.'}), 500
    except Exception as e:
        print(f"Error removing from wishlist: {e}")
        if connection: connection.rollback()
        return jsonify({'success': False, 'message': 'An unexpected error occurred.'}), 500
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

@app.route('/logout')
@login_required # Must be logged in to log out
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('home'))

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    connection = None
    cursor = None
    product = None
    image_ids = [] # Initialize empty list for image IDs
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Step 1: Fetch base product details (without image data)
        query_product = """
            SELECT 
                p.product_id, p.title, p.description, p.price, p.status, 
                p.created_at, p.`condition`,
                CONCAT(u.first_name, ' ', u.last_name) AS seller_username, u.user_id AS seller_id,
                c.name AS category_name
            FROM Products p
            JOIN Users u ON p.seller_id = u.user_id
            JOIN Categories c ON p.category_id = c.category_id
            WHERE p.product_id = %s
        """
        cursor.execute(query_product, (product_id,))
        product = cursor.fetchone()

        # Debug: Print to check if condition is in the returned data
        # if product:
        #     print(f"DEBUG - Product data: {product}")
        #     print(f"DEBUG - Condition: {product.get('condition')}")
            
        # Step 2: If product found, fetch its image IDs
        if product:
            query_images = """
                SELECT image_id 
                FROM ProductImages 
                WHERE product_id = %s 
                ORDER BY image_order ASC
            """
            cursor.execute(query_images, (product_id,))
            # Store just the IDs in a list
            image_ids = [row['image_id'] for row in cursor.fetchall()]

    except Error as db_err:
        print(f"Database error fetching product {product_id}: {db_err}")
        flash("Could not load product details due to a database error.", "error")
        abort(500) 
    except Exception as e:
        print(f"Error fetching product {product_id}: {e}")
        flash("An unexpected error occurred while loading product details.", "error")
        abort(500) 
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
            
    if product:
        # Pass both product details and the list of image IDs to the template
        return render_template('pages/listings/listing_indie.html', product=product, image_ids=image_ids)
    else:
        abort(404) # Product not found

if __name__ == '__main__':
    app.debug = os.getenv("FLASK_ENV") != "production"
    app.run()
