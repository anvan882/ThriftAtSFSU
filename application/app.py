from flask import Flask, render_template, request, Response, abort, url_for, redirect, flash, session, send_file, jsonify
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import pooling, Error
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from datetime import datetime, timedelta
import base64 # Added for image encoding
import json   # Added for parsing AI response
from decimal import Decimal # Import Decimal for accurate price handling
from openai import OpenAI # Added for OpenAI API call
from flask_socketio import SocketIO, emit, join_room, leave_room
import math

load_dotenv()

# === Configure OpenAI Client ===
try:
    client = OpenAI() # Reads OPENAI_API_KEY from environment automatically
except Exception as e:
    print(f"Error initializing OpenAI client: {e}")
    # Consider how to handle this - maybe disable the autofill feature?
    client = None

# Define allowed conditions centrally
ALLOWED_CONDITIONS = ["Very Worn", "Used", "Fairly Used", "Good Condition", "Great Condition"]

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") # Needed for flash messages
if not app.secret_key:
    print("Warning: FLASK_SECRET_KEY is not set. Flashing will not work.")
    raise ValueError("No FLASK_SECRET_KEY set for Flask application")

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

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
        
        # Round up max_db_price to avoid truncation issues
        # This prevents issues where 1399 might be shown as 1398.01 due to floating point precision
        max_db_price = math.ceil(max_db_price)

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
            # For max_price, if the string is empty (not provided in URL), use default_max_filter
            if not max_price_str:
                max_price = default_max_filter
                # Print debug info for default max value
                print(f"DEBUG - Using default max_price: {max_price}")
            else:
                max_price = float(max_price_str)
                # Print debug info for explicit max value
                print(f"DEBUG - Using explicit max_price from URL: {max_price}")
        except (ValueError, TypeError):
            max_price = default_max_filter
            print(f"DEBUG - Using default max_price after error: {max_price}")

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
            "p.price >= %s"
        ]
        params = [category, category, f"%{keyword}%", f"%{keyword}%", min_price]
        
        # For max price, ensure we're using the ceiling to include all items
        # Use CEILING in SQL to avoid floating point precision issues
        where_clauses.append("p.price <= CEILING(%s)")
        params.append(max_price)
        
        # Log the actual values for debugging
        print(f"DEBUG - Price filter values: min={min_price}, max={max_price}, max_db_price={max_db_price}")

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
        
        # Add ORDER BY clause to sort by creation date in descending order
        query += " ORDER BY p.created_at DESC"
        
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

# === Profile Routes ===

@app.route("/profile/<int:profile_user_id>")
@login_required # User must be logged in to view any profile
def view_profile(profile_user_id):
    viewer_user_id = session.get('user_id')
    is_own_profile = (viewer_user_id == profile_user_id)

    connection = None
    cursor = None
    profile_user = None
    listings = []
    reviews = []
    avg_rating = None
    review_count = 0
    has_reviewed = False  # Flag to track if viewer has already reviewed this user

    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True, buffered=True) # Use buffered cursor for multiple queries

        # Fetch profile user details
        cursor.execute("""
            SELECT user_id, first_name, last_name, email, phone_number, bio, created_at
            FROM Users WHERE user_id = %s
        """, (profile_user_id,))
        profile_user = cursor.fetchone()

        if not profile_user:
            flash('User profile not found.', 'error')
            abort(404)

        # Fetch user's listings
        cursor.execute("""
            SELECT p.product_id, p.title, p.price, pi.image_id AS first_image_id
            FROM Products p
            LEFT JOIN ProductImages pi ON p.product_id = pi.product_id AND pi.image_order = 0
            WHERE p.seller_id = %s AND p.status = 'available'
            ORDER BY p.created_at DESC
            LIMIT 10 -- Limit number of listings shown initially
        """, (profile_user_id,))
        listings = cursor.fetchall()

        # Fetch reviews about the user
        cursor.execute("""
            SELECT r.review_id, r.rating, r.comment, 
                   u.user_id as reviewer_id, u.first_name as reviewer_first_name, u.last_name as reviewer_last_name
            FROM Reviews r
            JOIN Users u ON r.reviewer_id = u.user_id
            WHERE r.reviewed_user_id = %s
            ORDER BY r.review_id DESC
        """, (profile_user_id,))
        reviews = cursor.fetchall()

        # Calculate average rating
        if reviews:
            review_count = len(reviews)
            total_rating = sum(r['rating'] for r in reviews)
            avg_rating = round(total_rating / review_count, 1) if review_count > 0 else None
            
        # Check if the current user has already reviewed this profile
        if not is_own_profile:  # No need to check if viewing own profile
            cursor.execute("""
                SELECT review_id FROM Reviews 
                WHERE reviewer_id = %s AND reviewed_user_id = %s
            """, (viewer_user_id, profile_user_id))
            has_reviewed = cursor.fetchone() is not None


    except Error as db_err:
        print(f"Database error fetching profile for user {profile_user_id}: {db_err}")
        flash("Could not load profile due to a database error.", "error")
        # Redirect or show generic error? Redirect home for now.
        return redirect(url_for('home'))
    except Exception as e:
        print(f"Unexpected error fetching profile for user {profile_user_id}: {e}")
        flash("An unexpected error occurred while loading the profile.", "error")
        return redirect(url_for('home'))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    # Combine first and last name for display
    profile_user['full_name'] = f"{profile_user['first_name']} {profile_user['last_name']}"

    return render_template(
        'pages/profile.html',
        profile_user=profile_user,
        listings=listings,
        reviews=reviews,
        avg_rating=avg_rating,
        review_count=review_count,
        is_own_profile=is_own_profile,
        viewer_user_id=viewer_user_id, # Pass viewer ID for review form action
        has_reviewed=has_reviewed  # Pass the flag to indicate if user has already reviewed
    )

@app.route('/profile/update_bio', methods=['POST'])
@login_required
def update_bio():
    user_id = session['user_id']
    bio = request.form.get('bio', '').strip()
    
    # Validation
    if len(bio) > 1000:  # Example limit
        return jsonify({'success': False, 'message': 'Bio cannot exceed 1000 characters.'}), 400
    
    connection = None
    cursor = None
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor()
        
        # Update only bio
        cursor.execute("UPDATE Users SET bio = %s WHERE user_id = %s", (bio, user_id))
        connection.commit()
        
        return jsonify({'success': True, 'message': 'Bio updated successfully!'})
        
    except Error as db_err:
        print(f"Database error updating bio for user {user_id}: {db_err}")
        if connection: connection.rollback()
        return jsonify({'success': False, 'message': 'Database error updating bio.'}), 500
    except Exception as e:
        print(f"Unexpected error updating bio for user {user_id}: {e}")
        if connection: connection.rollback()
        return jsonify({'success': False, 'message': 'An unexpected error occurred.'}), 500
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

@app.route('/profile/update_profile_picture', methods=['POST'])
@login_required
def update_profile_picture():
    user_id = session['user_id']
    
    # Check if profile picture was included in the request
    if 'profile_picture' not in request.files:
        return jsonify({'success': False, 'message': 'No profile picture provided.'}), 400
    
    profile_picture = request.files['profile_picture']
    
    # Check if a file was selected
    if profile_picture.filename == '':
        return jsonify({'success': False, 'message': 'No file selected.'}), 400
    
    # Check file type (simple check based on extension)
    allowed_extensions = {'png', 'jpg', 'jpeg'}
    if '.' not in profile_picture.filename or \
       profile_picture.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        return jsonify({'success': False, 'message': 'Invalid file type. Please use PNG, JPG, or JPEG.'}), 400
    
    # Read the file content
    picture_blob = profile_picture.read()
    
    connection = None
    cursor = None
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor()
        
        # Update the profile picture
        cursor.execute("UPDATE Users SET profile_picture = %s WHERE user_id = %s", (picture_blob, user_id))
        connection.commit()
        
        return jsonify({'success': True, 'message': 'Profile picture updated successfully!'})
        
    except Error as db_err:
        print(f"Database error updating profile picture for user {user_id}: {db_err}")
        if connection: connection.rollback()
        return jsonify({'success': False, 'message': 'Database error updating profile picture.'}), 500
    except Exception as e:
        print(f"Unexpected error updating profile picture for user {user_id}: {e}")
        if connection: connection.rollback()
        return jsonify({'success': False, 'message': 'An unexpected error occurred.'}), 500
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

@app.route('/profile/<int:reviewed_user_id>/add_review', methods=['POST'])
@login_required
def add_review(reviewed_user_id):
    reviewer_user_id = session['user_id']

    # Prevent self-review
    if reviewer_user_id == reviewed_user_id:
        flash("You cannot review yourself.", 'warning')
        return redirect(url_for('view_profile', profile_user_id=reviewed_user_id))

    rating_str = request.form.get('rating')
    comment = request.form.get('comment', '').strip()

    # --- Validation ---
    if not rating_str or not comment:
        flash("Rating and comment are required to submit a review.", 'error')
        return redirect(url_for('view_profile', profile_user_id=reviewed_user_id))

    try:
        rating = int(rating_str)
        if not 1 <= rating <= 5:
            raise ValueError("Rating out of range")
    except (ValueError, TypeError):
        flash("Invalid rating value. Please select 1-5 stars.", 'error')
        return redirect(url_for('view_profile', profile_user_id=reviewed_user_id))

    if len(comment) > 500: # Example limit
        flash("Review comment cannot exceed 500 characters.", 'error')
        return redirect(url_for('view_profile', profile_user_id=reviewed_user_id))
    # --- End Validation ---

    connection = None
    cursor = None
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor()

        # Check if user has already reviewed this user (optional, decide business logic)
        # cursor.execute("SELECT review_id FROM Reviews WHERE reviewer_id = %s AND reviewed_user_id = %s", (reviewer_user_id, reviewed_user_id))
        # if cursor.fetchone():
        #     flash("You have already reviewed this user.", 'warning')
        #     return redirect(url_for('view_profile', profile_user_id=reviewed_user_id))

        # Insert the review
        insert_query = """
        INSERT INTO Reviews (reviewer_id, reviewed_user_id, rating, comment)
        VALUES (%s, %s, %s, %s)
        """
        cursor.execute(insert_query, (reviewer_user_id, reviewed_user_id, rating, comment))
        connection.commit()
        flash("Review submitted successfully!", 'success')

    except Error as db_err:
        print(f"Database error adding review from {reviewer_user_id} to {reviewed_user_id}: {db_err}")
        flash("Failed to submit review due to a database error.", 'error')
        if connection: connection.rollback()
    except Exception as e:
        print(f"Unexpected error adding review: {e}")
        flash("An unexpected error occurred while submitting the review.", 'error')
        if connection: connection.rollback()
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(url_for('view_profile', profile_user_id=reviewed_user_id))


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

# === Autofill Listing Endpoint (Real AI) ===
@app.route('/autofill_listing', methods=['POST'])
@login_required
def autofill_listing():
    if not client:
        return jsonify({'success': False, 'message': 'Autofill feature is currently unavailable (config error).'}), 503 # 503 Service Unavailable

    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'No image file provided.'}), 400

    image_file = request.files['image']
    image_filename = image_file.filename

    # Basic check if file seems like an image (based on filename)
    allowed_extensions = {'png', 'jpg', 'jpeg'}
    if '.' not in image_filename or \
       image_filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        return jsonify({'success': False, 'message': 'Invalid file type. Please use PNG, JPG, or JPEG.'}), 400

    try:
        # 1. Read and encode the image
        image_data = image_file.read()
        base64_image = base64.b64encode(image_data).decode('utf-8')
        mime_type = image_file.mimetype # Get MIME type from Flask file object

        # Fetch categories dynamically from DB
        possible_categories = []
        connection = None
        cursor = None
        try:
            connection = cnxpool.get_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT name FROM Categories")
            possible_categories = [r['name'] for r in cursor.fetchall()]
        except Error as db_err:
            print(f"Database error fetching categories for autofill: {db_err}")
            # Proceed with empty list, AI might guess, or return error?
            # Returning error seems safer if categories are crucial.
            return jsonify({'success': False, 'message': 'Could not fetch categories for autofill.'}), 500
        finally:
            if cursor: cursor.close()
            if connection and connection.is_connected(): connection.close()

        if not possible_categories:
             print("Warning: No categories found in the database for autofill prompt.")
             # Handle this case - maybe default to a basic list or error out?
             possible_categories = ["Other"] # Default if DB fetch fails but we don't error out

        # Use centrally defined conditions
        possible_conditions = ALLOWED_CONDITIONS

        # 2. Construct the prompt for OpenAI Vision API
        prompt = f"""
Analyze the provided image of an item for sale and generate a JSON object containing suggested values for the following fields: 'title', 'price', 'category', 'condition', and 'description'.

Constraints and Guidelines:
- **title**: A concise and descriptive title for the item (e.g., "Used Blue SFSU Hoodie Size L").
- **price**: Estimate a reasonable price in USD as a floating-point number (e.g., 25.00). Do not include the '$' sign. If unsure, provide 0.0.
- **category**: Choose the most appropriate category from the following list: {', '.join(possible_categories)}. If none seem correct, use "Other".
- **condition**: Assess the item's condition and choose the best fit from this list: {', '.join(possible_conditions)}.
- **description**: Write a brief description (max 500 characters) highlighting key features or visible condition details. Start with "Based on the image, this appears to be..."

Return ONLY the JSON object, nothing else.

Example JSON format:
{{
  "title": "Example Title",
  "price": 15.50,
  "category": "Clothing",
  "condition": "Good Condition",
  "description": "Based on the image, this appears to be a well-maintained item..."
}}
"""

        # 3. Make the API call
        response = client.chat.completions.create(
            model="gpt-4o", # Or use "gpt-4o" if available and preferred
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        },
                    ],
                }
            ],
            max_tokens=300 # Adjust as needed
        )

        # 4. Parse the response
        ai_response_content = response.choices[0].message.content.strip()
        print(f"AI response content: {ai_response_content}")

        # Clean potential markdown code block fences
        if ai_response_content.startswith("```json"):
            ai_response_content = ai_response_content[7:]
        if ai_response_content.endswith("```"):
            ai_response_content = ai_response_content[:-3]
        ai_response_content = ai_response_content.strip()


        try:
            extracted_data = json.loads(ai_response_content)
            # Basic validation of expected keys
            required_keys = {"title", "price", "category", "condition", "description"}
            if not required_keys.issubset(extracted_data.keys()):
                 print(f"AI response missing keys. Got: {extracted_data}")
                 raise ValueError("AI response missing required keys.")
            # Ensure price is a number, convert if string
            if isinstance(extracted_data.get('price'), str):
                try:
                    extracted_data['price'] = float(extracted_data['price'])
                except ValueError:
                    extracted_data['price'] = 0.0 # Default to 0 if conversion fails

            return jsonify({'success': True, 'data': extracted_data})

        except json.JSONDecodeError as json_err:
            print(f"Error decoding JSON from AI response: {json_err}")
            print(f"Raw AI response content: {ai_response_content}")
            return jsonify({'success': False, 'message': 'Could not parse AI response (invalid JSON).'}), 500
        except ValueError as val_err:
             print(f"Error validating AI response: {val_err}")
             print(f"Raw AI response content: {ai_response_content}")
             return jsonify({'success': False, 'message': f'AI response validation failed: {val_err}'}), 500


    except Exception as e:
        # Catch potential errors during file processing or API call
        print(f"Error during autofill API call: {e}")
        # Check if it's an OpenAI API error
        if hasattr(e, 'status_code'):
            error_message = f"OpenAI API error ({e.status_code}): {getattr(e, 'message', str(e))}"
            status_code = e.status_code
        else:
            error_message = 'Failed to process image for autofill.'
            status_code = 500
        return jsonify({'success': False, 'message': error_message}), status_code

# Messages
@app.route('/messages')
@app.route('/messages/<int:user_id>')
@login_required
def messages(user_id=None):
    current_user_id = session.get('user_id')
    
    connection = None
    cursor = None
    conversations = []
    chat_user = None
    messages = []
    
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Get all conversations, regardless of who initiated them
        conversations_query = """
        SELECT 
            u.user_id, u.first_name, u.last_name,
            m.content as last_message,
            m.timestamp as last_message_timestamp
        FROM (
            SELECT 
                CASE 
                    WHEN sender_id = %s THEN receiver_id
                    ELSE sender_id
                END as other_user_id,
                MAX(timestamp) as latest_timestamp
            FROM Messages
            WHERE sender_id = %s OR receiver_id = %s
            GROUP BY other_user_id
        ) AS latest_msgs
        JOIN Users u ON u.user_id = latest_msgs.other_user_id
        JOIN Messages m ON (
            (m.sender_id = %s AND m.receiver_id = u.user_id) OR
            (m.sender_id = u.user_id AND m.receiver_id = %s)
        ) AND m.timestamp = latest_msgs.latest_timestamp
        ORDER BY latest_msgs.latest_timestamp DESC
        """
        cursor.execute(conversations_query, (current_user_id, current_user_id, current_user_id, current_user_id, current_user_id))
        conversations_raw = cursor.fetchall()
        
        # Process conversations
        for convo in conversations_raw:
            conversations.append({
                "id": convo['user_id'],
                "name": f"{convo['first_name']} {convo['last_name']}",
                "avatar_url": url_for('serve_user_picture', user_id=convo['user_id']),
                "online": False,
                "last_message": convo['last_message']
            })
        
        # Get active user (user we're chatting with)
        active_user_id = user_id
        
        # Log for debugging
        print(f"Initial active_user_id from URL: {active_user_id}")
        
        # If no specific user is provided in URL, use the first available user
        if not active_user_id and conversations:
            active_user_id = conversations[0]['id']
            print(f"Using first conversation user: {active_user_id}")
            
        print(f"Final active_user_id: {active_user_id}")
        
        # If we have an active user, get their details and messages
        if active_user_id:
            # Get user details
            cursor.execute("""
                SELECT user_id, first_name, last_name
                FROM Users WHERE user_id = %s
            """, (active_user_id,))
            active_user_data = cursor.fetchone()
            
            if active_user_data:
                chat_user = {
                    "name": f"{active_user_data['first_name']} {active_user_data['last_name']}",
                    "avatar_url": url_for('serve_user_picture', user_id=active_user_data['user_id']),
                    "online": False,
                    "status_text": ""
                }
                
                # Get messages between current user and active user
                cursor.execute("""
                    SELECT sender_id, content, timestamp
                    FROM Messages
                    WHERE (sender_id = %s AND receiver_id = %s)
                    OR (sender_id = %s AND receiver_id = %s)
                    ORDER BY timestamp ASC
                """, (current_user_id, active_user_id, active_user_id, current_user_id))
                
                message_data = cursor.fetchall()
                
                for msg in message_data:
                    messages.append({
                        "text": msg['content'],
                        "timestamp": msg['timestamp'].strftime("%I:%M %p"),
                        "is_sent": msg['sender_id'] == current_user_id
                    })
            
            # Set active status in conversations list
            for convo in conversations:
                if convo['id'] == active_user_id:
                    convo['active'] = True
                    break
        else:
            # Explicitly handle no active user
            active_user_id = None
            print("No active user ID set")
        
    except Error as db_err:
        print(f"Database error in messages route: {db_err}")
        flash("Could not load messages due to a database error.", "error")
    except Exception as e:
        print(f"Unexpected error in messages route: {e}")
        flash("An unexpected error occurred while loading messages.", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    
    # If no chat_user is set but we have conversations, use the first one
    if not chat_user and conversations:
        # Use the first user as default
        first_user = conversations[0]
        chat_user = {
            "name": first_user['name'],
            "avatar_url": first_user['avatar_url'],
            "online": False,
            "status_text": ""
        }
        if not active_user_id:
            active_user_id = first_user['id']
            print(f"Setting active_user_id to first user: {active_user_id}")
    
    print(f"Rendering template with active_user_id: {active_user_id}")
    return render_template(
        'pages/messaging.html',
        active_user_id=active_user_id,
        conversations=conversations,
        chat_user=chat_user,
        messages=messages,
        hide_footer=True
    )

@app.route('/start_conversation/<int:user_id>')
@app.route('/start_conversation/<int:user_id>/product/<int:product_id>')
@login_required
def start_conversation(user_id, product_id=None):
    # If product_id is provided, we'll send an initial message about the product
    if product_id is not None:
        connection = None
        cursor = None
        try:
            connection = cnxpool.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # Get product details
            cursor.execute("""
                SELECT title, price FROM Products WHERE product_id = %s
            """, (product_id,))
            product_data = cursor.fetchone()
            
            if product_data:
                # Create initial message about the product
                sender_id = session.get('user_id')
                message_content = f"I'm interested in your listing: {product_data['title']} (${product_data['price']})"
                
                # Insert message into database
                cursor.execute("""
                    INSERT INTO Messages (sender_id, receiver_id, product_id, content)
                    VALUES (%s, %s, %s, %s)
                """, (sender_id, user_id, product_id, message_content))
                connection.commit()
                
        except Error as db_err:
            print(f"Database error starting product conversation: {db_err}")
            flash("Could not start conversation due to a database error.", "error")
        except Exception as e:
            print(f"Unexpected error starting product conversation: {e}")
            flash("An unexpected error occurred while starting the conversation.", "error")
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()
    
    return redirect(url_for('messages', user_id=user_id))

# Socket.IO event handlers
@socketio.on('connect')
def handle_connect():
    print(f"Socket connection attempt. Session data: {session}")
    if 'user_id' in session:
        user_id = session['user_id']
        # Add user to their own room (user_id as room name)
        join_room(str(user_id))
        # Access socket ID properly
        socket_id = request.sid if hasattr(request, 'sid') else 'unknown'
        print(f"User {user_id} connected to socket with SID: {socket_id}")
    else:
        print("Socket connection without authenticated user session")

@socketio.on('disconnect')
def handle_disconnect():
    print(f"Socket disconnect event. Session data: {session}")
    if 'user_id' in session:
        user_id = session['user_id']
        leave_room(str(user_id))
        print(f"User {user_id} disconnected from socket")
    else:
        print("Socket disconnection without authenticated user session")

@socketio.on('send_message')
def handle_send_message(data):
    print(f"Received send_message event with data: {data}")
    
    if 'user_id' not in session:
        print("No user_id in session, ignoring message")
        return
    
    try:
        sender_id = session['user_id']
        receiver_id = int(data['receiver_id'])  # Ensure it's an integer
        content = data['message']
        product_id = data.get('product_id')  # Optional product reference
        
        print(f"Processing message from user {sender_id} to user {receiver_id}: {content}")
        
        connection = None
        cursor = None
        try:
            connection = cnxpool.get_connection()
            cursor = connection.cursor()
            
            # Insert message into database
            insert_query = """
            INSERT INTO Messages (sender_id, receiver_id, product_id, content)
            VALUES (%s, %s, %s, %s)
            """
            cursor.execute(insert_query, (sender_id, receiver_id, product_id, content))
            connection.commit()
            
            # Get message timestamp and ID
            cursor.execute("SELECT LAST_INSERT_ID() as message_id")
            message_id = cursor.fetchone()[0]
            
            cursor.execute("SELECT timestamp FROM Messages WHERE message_id = %s", (message_id,))
            timestamp = cursor.fetchone()[0]
            
            # Format message for real-time delivery
            formatted_timestamp = timestamp.strftime("%I:%M %p")
            
            print(f"Message saved to database with ID {message_id}")
            
            # Get sender info for the receiver
            cursor.execute("""
                SELECT first_name, last_name 
                FROM Users 
                WHERE user_id = %s
            """, (sender_id,))
            sender_info = cursor.fetchone()
            sender_name = f"{sender_info[0]} {sender_info[1]}" if sender_info else "Unknown User"
            
            # Create message payload for sender
            sender_payload = {
                'sender_id': sender_id,
                'receiver_id': receiver_id,
                'text': content,
                'timestamp': formatted_timestamp,
                'is_sent': True,
                'message_id': message_id
            }
            
            # Emit message to sender's room (for multiple tabs/windows)
            print(f"Emitting message to sender's room: {sender_id}")
            emit('new_message', sender_payload, room=str(sender_id))
            
            # Create message payload for receiver
            receiver_payload = {
                'sender_id': sender_id,
                'receiver_id': receiver_id,
                'text': content,
                'timestamp': formatted_timestamp,
                'is_sent': False,
                'message_id': message_id,
                'sender_name': sender_name
            }
            
            # Emit message to receiver's room
            print(f"Emitting message to receiver's room: {receiver_id}")
            emit('new_message', receiver_payload, room=str(receiver_id))
            
        except Error as db_err:
            print(f"Database error sending message: {db_err}")
            emit('message_error', {'error': 'Database error'}, room=str(sender_id))
        except Exception as e:
            print(f"Error sending message: {e}")
            emit('message_error', {'error': 'Unknown error'}, room=str(sender_id))
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()
    except KeyError as ke:
        print(f"KeyError in socket message data: {ke}")
        if 'user_id' in session:
            emit('message_error', {'error': f'Missing required data: {ke}'}, room=str(session['user_id']))
    except ValueError as ve:
        print(f"ValueError in socket message data: {ve}")
        if 'user_id' in session:
            emit('message_error', {'error': f'Invalid data format: {ve}'}, room=str(session['user_id']))
    except Exception as e:
        print(f"Unexpected error processing message: {e}")
        if 'user_id' in session:
            emit('message_error', {'error': 'An unexpected error occurred'}, room=str(session['user_id']))

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

@app.route('/product/<int:product_id>/delete', methods=['POST'])
@login_required
def delete_product(product_id):
    connection = None
    cursor = None
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # First check if the product exists and belongs to the current user
        query = """
            SELECT seller_id FROM Products 
            WHERE product_id = %s
        """
        cursor.execute(query, (product_id,))
        product = cursor.fetchone()
        
        if not product:
            flash("Product not found.", "error")
            return redirect(url_for('home'))
            
        # Verify ownership
        if product['seller_id'] != session['user_id']:
            flash("You can only delete your own listings.", "error")
            return redirect(url_for('product_detail', product_id=product_id))
        
        # Delete related images first (due to foreign key constraints)
        cursor.execute("DELETE FROM ProductImages WHERE product_id = %s", (product_id,))
        
        # Remove from any wishlists
        cursor.execute("DELETE FROM Wishlist WHERE product_id = %s", (product_id,))
        
        # Delete the product
        cursor.execute("DELETE FROM Products WHERE product_id = %s", (product_id,))
        
        connection.commit()
        flash("Listing successfully deleted.", "success")
        return redirect(url_for('home'))
        
    except Error as db_err:
        print(f"Database error deleting product {product_id}: {db_err}")
        flash("Could not delete listing due to a database error.", "error")
        if connection: connection.rollback()
        return redirect(url_for('product_detail', product_id=product_id))
    except Exception as e:
        print(f"Error deleting product {product_id}: {e}")
        flash("An unexpected error occurred while deleting the listing.", "error")
        if connection: connection.rollback()
        return redirect(url_for('product_detail', product_id=product_id))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    connection = None
    cursor = None
    product = None
    image_ids = []
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)

        # Fetch product details including seller info and condition
        query_product = """
            SELECT
                p.product_id, p.title, p.description, p.price, p.status,
                p.created_at, p.`condition`,
                u.user_id AS seller_id, CONCAT(u.first_name, ' ', u.last_name) AS seller_username,
                c.name AS category_name
            FROM Products p
            JOIN Users u ON p.seller_id = u.user_id
            JOIN Categories c ON p.category_id = c.category_id
            WHERE p.product_id = %s
        """
        cursor.execute(query_product, (product_id,))
        product = cursor.fetchone()

        if product:
             # Fetch image IDs
            query_images = """
                SELECT image_id
                FROM ProductImages
                WHERE product_id = %s
                ORDER BY image_order ASC
            """
            cursor.execute(query_images, (product_id,))
            image_ids = [row['image_id'] for row in cursor.fetchall()]

            # Convert price to Decimal for accurate formatting if needed, though Jinja handles it well
            if product.get('price') is not None:
                 product['price'] = Decimal(product['price'])


    except Error as db_err:
        print(f"Database error fetching product {product_id}: {db_err}")
        flash("Could not load product details due to a database error.", "error")
        abort(500)
    except Exception as e:
        print(f"Error fetching product {product_id}: {e}")
        flash("An unexpected error occurred while loading product details.", "error")
        abort(500)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    if product:
        # Check if the current user is the owner of the listing
        current_user_id = session.get('user_id')
        is_owner = current_user_id and current_user_id == product['seller_id']
        
        # Pass the necessary data to the template
        return render_template('pages/listings/listing_indie.html', 
                              product=product, 
                              image_ids=image_ids, 
                              is_owner=is_owner)
    else:
        abort(404) # Product not found

# === Availability Routes ===
@app.route('/get_availability/<int:user_id>')
def get_availability(user_id):
    connection = None
    cursor = None
    availability = {}
    
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Fetch all availability time slots for the user
        query = """
            SELECT day_of_week, time_slot
            FROM UserAvailability
            WHERE user_id = %s AND is_available = TRUE
        """
        cursor.execute(query, (user_id,))
        results = cursor.fetchall()
        
        # Format the results into a dictionary for easier handling in JavaScript
        for row in results:
            day = row['day_of_week']
            time_slot = row['time_slot']
            
            if day not in availability:
                availability[day] = []
            
            availability[day].append(time_slot)
            
        return jsonify({'success': True, 'availability': availability})
        
    except Error as db_err:
        print(f"Database error fetching availability: {db_err}")
        return jsonify({'success': False, 'message': 'Failed to retrieve availability data.'}), 500
    except Exception as e:
        print(f"Error fetching availability: {e}")
        return jsonify({'success': False, 'message': 'An unexpected error occurred.'}), 500
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

@app.route('/update_availability/<int:user_id>', methods=['POST'])
@login_required
def update_availability(user_id):
    # Verify user is updating their own availability
    if session.get('user_id') != user_id:
        return jsonify({'success': False, 'message': 'You can only update your own availability.'}), 403
    
    try:
        # Get the availability data from the request
        data = request.json
        if not data or 'availability' not in data:
            return jsonify({'success': False, 'message': 'No availability data provided.'}), 400
        
        availability_data = data['availability']
        # Format should be: {day: [time_slots], day: [time_slots], ...}
        
        connection = None
        cursor = None
        
        try:
            connection = cnxpool.get_connection()
            cursor = connection.cursor()
            
            # First, delete all existing availability for this user
            cursor.execute("DELETE FROM UserAvailability WHERE user_id = %s", (user_id,))
            
            # Insert new availability data
            insert_query = """
                INSERT INTO UserAvailability (user_id, day_of_week, time_slot, is_available)
                VALUES (%s, %s, %s, TRUE)
            """
            
            # Prepare the insert data
            insert_data = []
            for day, time_slots in availability_data.items():
                for time_slot in time_slots:
                    insert_data.append((user_id, day, time_slot))
            
            # Execute the insert query for all records
            if insert_data:
                cursor.executemany(insert_query, insert_data)
            
            connection.commit()
            return jsonify({'success': True, 'message': 'Availability updated successfully.'})
            
        except Error as db_err:
            print(f"Database error updating availability: {db_err}")
            if connection: connection.rollback()
            return jsonify({'success': False, 'message': 'Failed to update availability data.'}), 500
        finally:
            if cursor: cursor.close()
            if connection and connection.is_connected(): connection.close()
            
    except Exception as e:
        print(f"Error updating availability: {e}")
        return jsonify({'success': False, 'message': 'An unexpected error occurred.'}), 500

@app.route('/update_product_description', methods=['POST'])
def update_product_description():
    """Update a product's description via AJAX"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'You must be logged in to perform this action'}), 401
    
    user_id = session['user_id']
    description = request.form.get('description', '').strip()
    product_id = request.form.get('product_id')
    
    if not product_id:
        return jsonify({'success': False, 'message': 'Product ID is required'}), 400
    
    try:
        product_id = int(product_id)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid product ID'}), 400
    
    connection = None
    cursor = None
    
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # First check if the current user is the owner of the product
        cursor.execute(
            "SELECT seller_id FROM Products WHERE product_id = %s",
            (product_id,)
        )
        product = cursor.fetchone()
        
        if not product:
            return jsonify({'success': False, 'message': 'Product not found'}), 404
        
        if product['seller_id'] != user_id:
            return jsonify({'success': False, 'message': 'You do not have permission to edit this product'}), 403
        
        # Update the product description
        cursor.execute(
            "UPDATE Products SET description = %s WHERE product_id = %s",
            (description, product_id)
        )
        
        connection.commit()
        
        return jsonify({'success': True, 'message': 'Description updated successfully'})
        
    except Error as db_err:
        print(f"Database error updating product description: {db_err}")
        return jsonify({'success': False, 'message': 'Database error occurred'}), 500
    except Exception as e:
        print(f"Error updating product description: {e}")
        return jsonify({'success': False, 'message': 'An unexpected error occurred'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/update_product_title', methods=['POST'])
def update_product_title():
    """Update a product's title via AJAX"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'You must be logged in to perform this action'}), 401
    
    user_id = session['user_id']
    title = request.form.get('title', '').strip()
    product_id = request.form.get('product_id')
    
    if not title:
        return jsonify({'success': False, 'message': 'Title cannot be empty'}), 400
    
    if not product_id:
        return jsonify({'success': False, 'message': 'Product ID is required'}), 400
    
    try:
        product_id = int(product_id)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid product ID'}), 400
    
    connection = None
    cursor = None
    
    try:
        connection = cnxpool.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # First check if the current user is the owner of the product
        cursor.execute(
            "SELECT seller_id FROM Products WHERE product_id = %s",
            (product_id,)
        )
        product = cursor.fetchone()
        
        if not product:
            return jsonify({'success': False, 'message': 'Product not found'}), 404
        
        if product['seller_id'] != user_id:
            return jsonify({'success': False, 'message': 'You do not have permission to edit this product'}), 403
        
        # Update the product title
        cursor.execute(
            "UPDATE Products SET title = %s WHERE product_id = %s",
            (title, product_id)
        )
        
        connection.commit()
        
        return jsonify({'success': True, 'message': 'Title updated successfully'})
        
    except Error as db_err:
        print(f"Database error updating product title: {db_err}")
        return jsonify({'success': False, 'message': 'Database error occurred'}), 500
    except Exception as e:
        print(f"Error updating product title: {e}")
        return jsonify({'success': False, 'message': 'An unexpected error occurred'}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0')
