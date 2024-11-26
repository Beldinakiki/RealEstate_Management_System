from flask import Flask, render_template, request, redirect, url_for, flash, get_flashed_messages, url_for, jsonify, send_file, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Property, PropertyDetails, ScheduledVisit, Contact
from functools import wraps
from flask_migrate import Migrate
import os
from werkzeug.utils import secure_filename
import time
from datetime import date, datetime, timedelta
from flask_mail import Mail, Message
from recmodel import RentalRecommender
from io import BytesIO
import pandas as pd
from sklearn.linear_model import LinearRegression
import numpy as np
from collections import Counter
from sqlalchemy.sql import func
from sqlalchemy.sql import extract
import traceback
import io
import csv
import xlsxwriter
import pdfkit  # You'll need to install: pip install pdfkit

from flask_sqlalchemy import SQLAlchemy

recommender = RentalRecommender(csv_path='rent_apts.csv')

# Define upload folder path correctly
basedir = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')

# Create uploads directory if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'goingseventeen'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/homeconnect'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'kinyuabeldina@gmail.com'  
app.config['MAIL_PASSWORD'] = 'ficb nxss tngw tges'    
mail = Mail(app)

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        phone_number = request.form.get('phone_number')
        role = request.form.get('role')
        
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return redirect(url_for('register'))

        user = User(
            username=username,
            email=email,
            phone_number=phone_number,
            role=role
        )
        user.set_password(password)

        # Handle agent-specific files
        if role == 'agent':
            agency_name = request.form.get('agency_name')
            user.agency_name = agency_name
            
            # Handle license file
            if 'license' in request.files:
                license_file = request.files['license']
                if license_file and allowed_file(license_file.filename):
                    filename = secure_filename(f"{username}_license_{license_file.filename}")
                    file_path = os.path.join(UPLOAD_FOLDER, filename)
                    license_file.save(file_path)
                    user.license_file = filename

            # Handle ID proof
            if 'id_proof' in request.files:
                id_proof = request.files['id_proof']
                if id_proof and allowed_file(id_proof.filename):
                    filename = secure_filename(f"{username}_id_{id_proof.filename}")
                    file_path = os.path.join(UPLOAD_FOLDER, filename)
                    id_proof.save(file_path)
                    user.id_proof_file = filename

            # Set verified to False for agents
            user.verified = False

        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('properties'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            # Check if user is an unverified agent before login
            if user.role == 'agent' and not user.verified:
                login_user(user)  # Login the user first
                flash('Your account is pending verification. You will be notified once an admin verifies your account.', 'warning')
                return redirect(url_for('home'))
            
            # For all other cases
            login_user(user)
            flash('Logged in successfully!', 'success')
            
            # Redirect based on verified user role
            if user.role == 'agent':
                return redirect(url_for('agent_dashboard'))
            elif user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('properties'))  # Changed to redirect to properties for regular users
        else:
            flash('Invalid email or password', 'danger')
    else:
        # Get the message from query parameters
        message = request.args.get('message')
        if message:
            flash(message, 'info')
            
    return render_template('auth/login.html')

# Add logout route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

@app.route('/')
def home():
    return render_template('index.html')

# Contact page
@app.route('/contact', methods=['POST'])
def contact():
    if request.method == 'POST':
        try:
            # Get form data
            name = request.form.get('name')
            email = request.form.get('email')
            subject = request.form.get('subject')
            message = request.form.get('message')
            
            # Create new contact message
            new_message = Contact(
                name=name,
                email=email,
                subject=subject,
                message=message
            )
            
            # Save to database
            db.session.add(new_message)
            db.session.commit()
            
            flash('Thank you for your message! We will get back to you soon.', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash('Sorry, there was an error sending your message. Please try again.', 'error')
            print(f"Error: {str(e)}")  # For debugging
            
    return redirect(url_for('home', _anchor='contact'))

# Properties listing page
@app.route('/properties')
def properties():
    # Get all properties with their details and agent information
    properties = Property.query.join(User, Property.agent_id == User.id).all()
    return render_template('properties.html', properties=properties)

# Property details page
@app.route('/details')
def details():
    return render_template('property-details.html')

# Admin dashboard route
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    # Gather statistics for dashboard
    users_count = User.query.count()
    properties_count = Property.query.count()
    pending_verifications = User.query.filter_by(role='agent', verified=False).count()
    new_messages = Contact.query.filter_by(status='Unread').count()
    
    # Get recent activities
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_properties = Property.query.order_by(Property.created_at.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html',
                         users_count=users_count,
                         properties_count=properties_count,
                         pending_verifications=pending_verifications,
                         new_messages=new_messages,
                         recent_users=recent_users,
                         recent_properties=recent_properties)

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    users = User.query.all()
    return render_template('admin/user_management.html', users=users)

@app.route('/admin/agent-verification')
@login_required
def agent_verification():
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    # Get all agents
    agents = User.query.filter_by(role='agent').order_by(User.created_at.desc()).all()
    
    # Get total listings
    total_listings = Property.query.count()
    
    return render_template('admin/agent_verification.html', 
                         agents=agents,
                         total_listings=total_listings)

@app.route('/admin/agent-properties/<int:agent_id>')
@login_required
def get_agent_properties(agent_id):
    if not current_user.role == 'admin':
        return jsonify({'success': False, 'message': 'Access denied'})
    
    agent = User.query.get_or_404(agent_id)
    properties = [{
        'title': p.title,
        'location': p.location,
        'price': "{:,.2f}".format(p.price),
        'created_at': p.created_at.strftime('%Y-%m-%d')
    } for p in agent.properties]
    
    return jsonify({
        'success': True,
        'properties': properties
    })

@app.route('/admin/suspend-agent/<int:agent_id>', methods=['POST'])
@login_required
def suspend_agent(agent_id):
    if not current_user.role == 'admin':
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        agent = User.query.get_or_404(agent_id)
        agent.verified = False
        agent.verification_status = 'suspended'
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/user-roles')
@login_required
def user_roles():
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    users = User.query.all()
    return render_template('admin/user_roles.html', users=users)

@app.route('/admin/properties')
@login_required
def admin_properties():
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    properties = Property.query.all()
    return render_template('admin/properties.html', properties=properties)

@app.route('/admin/settings')
@login_required
def admin_settings():
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    return render_template('admin/settings.html')

# Admin action routes
@app.route('/admin/verify-agent/<int:agent_id>', methods=['POST'])
@login_required
def verify_agent(agent_id):
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    agent = User.query.get_or_404(agent_id)
    agent.verified = True
    agent.verification_status = 'verified'
    db.session.commit()
    
    flash('Agent verified successfully.', 'success')
    return redirect(url_for('agent_verification'))

@app.route('/admin/update-user-role/<int:user_id>', methods=['POST'])
@login_required
def update_user_role(user_id):
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    if new_role in ['user', 'agent', 'admin']:
        user.role = new_role
        db.session.commit()
        flash('User role updated successfully.', 'success')
    else:
        flash('Invalid role specified.', 'error')
    
    return redirect(url_for('user_roles'))

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def agent_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'agent' or not current_user.verified:
            flash('Access denied. Verified agent privileges required.', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/agent/add-property', methods=['POST'])
@login_required
def add_property():
    if current_user.role != 'agent' or not current_user.verified:
        flash('Access denied or account not verified.', 'error')
        return redirect(url_for('home'))
    
    try:
        # Handle main image upload
        main_image = request.files.get('image')
        main_image_filename = None
        if main_image and main_image.filename:
            main_image_filename = secure_filename(f"{current_user.username}_{int(time.time())}_{main_image.filename}")
            main_image.save(os.path.join(app.config['UPLOAD_FOLDER'], main_image_filename))
        
        # Handle floor plan upload
        floor_plan = request.files.get('floor_plan')
        floor_plan_filename = None
        if floor_plan and floor_plan.filename:
            floor_plan_filename = secure_filename(f"floorplan_{current_user.username}_{int(time.time())}_{floor_plan.filename}")
            floor_plan.save(os.path.join(app.config['UPLOAD_FOLDER'], floor_plan_filename))
        
        # Create main property
        property = Property(
            title=request.form['title'],
            type=request.form['type'],
            price=float(request.form['price']),
            location=request.form['location'],
            bedrooms=int(request.form['bedrooms']),
            bathrooms=int(request.form['bathrooms']),
            area=float(request.form['area']),
            description=request.form['description'],
            image=main_image_filename,
            agent_id=current_user.id
        )
        
        db.session.add(property)
        db.session.flush()  # This gets us the property.id
        
        # Create property details
        details = PropertyDetails(
            property_id=property.id,
            garage=int(request.form.get('garage', 0)),
            year_built=int(request.form.get('year_built', 0)) if request.form.get('year_built') else None,
            property_status=request.form.get('property_status', 'For Sale'),
            features=request.form.get('features', ''),
            amenities=request.form.get('amenities', ''),
            floor_plan=floor_plan_filename,
            video_url=request.form.get('video_url', ''),
            virtual_tour_url=request.form.get('virtual_tour_url', ''),
            lot_size=float(request.form.get('lot_size', 0)) if request.form.get('lot_size') else None,
            basement=bool(request.form.get('basement', False)),
            roofing=request.form.get('roofing', ''),
            parking=request.form.get('parking', ''),
            heating=request.form.get('heating', ''),
            cooling=request.form.get('cooling', ''),
            interior_features=request.form.get('interior_features', ''),
            exterior_features=request.form.get('exterior_features', '')
        )
        
        db.session.add(details)
        db.session.commit()
        flash('Property added successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"Error: {str(e)}")
        flash(f'Error adding property: {str(e)}', 'error')
    
    return redirect(url_for('agent_dashboard'))

@app.route('/agent/delete-property/<int:property_id>', methods=['POST'])
@login_required
def delete_property(property_id):
    if current_user.role != 'agent':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    property = Property.query.get_or_404(property_id)
    if property.agent_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('agent_dashboard'))
    
    db.session.delete(property)
    db.session.commit()
    
    flash('Property deleted successfully!', 'success')
    return redirect(url_for('agent_dashboard'))

@app.route('/agent/edit-property/<int:property_id>', methods=['POST'])
@login_required
def edit_property(property_id):
    if current_user.role != 'agent':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    property = Property.query.get_or_404(property_id)
    
    # Verify the property belongs to the current agent
    if property.agent_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('agent_dashboard'))
    
    try:
        # Update basic information
        property.title = request.form['title']
        property.type = request.form['type']
        property.price = float(request.form['price'])
        property.location = request.form['location']
        property.bedrooms = int(request.form['bedrooms'])
        property.bathrooms = int(request.form['bathrooms'])
        property.area = float(request.form['area'])
        property.description = request.form['description']
        
        # Handle image update
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '':
                # Delete old image if it exists
                if property.image:
                    old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], property.image)
                    if os.path.exists(old_image_path):
                        os.remove(old_image_path)
                
                # Save new image
                filename = secure_filename(f"{current_user.username}_{int(time.time())}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                property.image = filename
        
        db.session.commit()
        flash('Property updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"Error: {str(e)}")  # For debugging
        flash(f'Error updating property: {str(e)}', 'error')
    
    return redirect(url_for('agent_dashboard'))

@app.route('/agent/dashboard')
@login_required
def agent_dashboard():
    # Ensure only agents can access this route
    if current_user.role != 'agent':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    # Fetch properties managed by the agent
    properties = Property.query.filter_by(agent_id=current_user.id).all()
    
    # Add debug logging
    print(f"Agent ID: {current_user.id}")
    
    # Modify the query to be more explicit and add debug logging
    scheduled_visits = ScheduledVisit.query.join(
        Property, ScheduledVisit.property_id == Property.id
    ).filter(
        Property.agent_id == current_user.id
    ).order_by(
        ScheduledVisit.visit_date, 
        ScheduledVisit.visit_time
    ).all()
    
    # Debug logging
    print(f"Number of scheduled visits found: {len(scheduled_visits)}")
    for visit in scheduled_visits:
        print(f"Visit ID: {visit.id}")
        print(f"Property ID: {visit.property_id}")
        print(f"User ID: {visit.user_id}")
        print(f"Date: {visit.visit_date}")
        print(f"Time: {visit.visit_time}")
    
    return render_template('agent/dashboard.html', 
                         properties=properties,
                         scheduled_visits=scheduled_visits)


@app.route('/user_dashboard')
@login_required
def user_dashboard():
    if current_user.role != 'user':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    # Get all properties for display
    properties = Property.query.all()
    
    # Get user's saved properties and scheduled visits
    saved_properties = Property.query.all()  # Replace with actual saved properties logic
    scheduled_visits = ScheduledVisit.query.filter_by(user_id=current_user.id).all()
    
    # Get search parameters
    search_params = {
        'location': request.args.get('location', ''),
        'property_type': request.args.get('property_type', ''),
        'min_price': request.args.get('min_price', ''),
        'max_price': request.args.get('max_price', ''),
        'bedrooms': int(request.args.get('bedrooms', 0)) if request.args.get('bedrooms', '').isdigit() else 0,
        'bathrooms': int(request.args.get('bathrooms', 0)) if request.args.get('bathrooms', '').isdigit() else 0
    }
    
    # Get recommendations based on search params if they exist
    recommended_properties = []
    if any(search_params.values()):
        try:
            response = get_recommendations()
            if response[0].status_code == 200:
                recommended_properties = response[0].json['data']
        except Exception as e:
            print(f"Error getting recommendations: {str(e)}")
    else:
        # Default recommendations
        recommended_properties = properties[:5]
    
    return render_template('user/dashboard.html', 
                         properties=properties,
                         search_params=search_params,
                         recommended_properties=recommended_properties,
                         saved_properties=saved_properties,
                         scheduled_visits=scheduled_visits)

# user required decorator for user-specific routes
def user_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'user':
            flash('Access denied. User account required.', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/user/save-property/<int:property_id>')
@user_required
def save_property(property_id):
    # Only regular users can access this route
    # Your property saving logic here
    pass

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        # Add your password reset logic here
        return redirect(url_for('login'))
    return render_template('auth/forgot_password.html')

@app.route('/properties/<int:property_id>')
def property_details(property_id):
    # Get the property and its details
    property = Property.query.get_or_404(property_id)
    return render_template('property_details.html', property=property)

@app.route('/admin/messages')
@login_required
def admin_messages():
    if not current_user.is_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
        
    messages = Contact.query.order_by(Contact.created_at.desc()).all()
    return render_template('admin/messages.html', messages=messages)

@app.route('/schedule-visit/<int:property_id>', methods=['POST'])
@login_required
def schedule_visit(property_id):
    # Fetch the property and agent details from the database
    property = Property.query.get(property_id)  # Replace with your ORM query
    if not property:
        flash('Property not found.', 'danger')
        return redirect(url_for('properties'))
    
    # Get visit details from the form
    visit_date = request.form.get('visit_date')
    visit_time = request.form.get('visit_time')
    
    # Create a new scheduled visit record
    new_visit = ScheduledVisit(
        user_id=current_user.id,
        property_id=property_id,
        agent_id=property.agent_id,  # Assuming property.agent_id exists
        visit_date=visit_date,
        visit_time=visit_time
    )
    db.session.add(new_visit)
    db.session.commit()

    flash('Your visit has been scheduled successfully!', 'success')
    return redirect(url_for('properties'))

@app.route('/accept-visit/<int:visit_id>', methods=['POST'])
@login_required
def accept_visit(visit_id):
    if current_user.role != 'agent':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    visit = ScheduledVisit.query.get_or_404(visit_id)
    
    # Verify the visit is for a property managed by this agent
    if visit.property.agent_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('agent_dashboard'))
    
    try:
        # Update visit status
        visit.status = 'accepted'
        db.session.commit()
        
        # Send email to user
        msg = Message('Property Visit Request Accepted!',
                     sender=app.config['MAIL_USERNAME'],
                     recipients=[visit.user.email])
        
        msg.html = render_template('emails/visit_accepted.html',
                                 visit=visit,
                                 property=visit.property,
                                 user=visit.user)
        
        mail.send(msg)
        
        flash('Visit request accepted and user notified!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error accepting visit: {str(e)}', 'error')
    
    return redirect(url_for('agent_dashboard'))

# Initialize the recommender (do this at app startup)
recommender = RentalRecommender()

@app.route('/recommendations', methods=['GET'])
def get_recommendations():
    try:
        # Get and print raw parameters
        location = request.args.get('location')
        min_price = request.args.get('min_price')
        max_price = request.args.get('max_price')
        bedrooms = request.args.get('bedrooms')
        bathrooms = request.args.get('bathrooms')
        
        print(f"Raw parameters: location={location}, min_price={min_price}, max_price={max_price}, bedrooms={bedrooms}, bathrooms={bathrooms}")
        
        # Convert price to single value if needed
        price = None
        if min_price and max_price:
            try:
                min_p = float(min_price)
                max_p = float(max_price)
                price = (min_p + max_p) / 2
            except (ValueError, TypeError):
                price = None
        
        # Convert other parameters
        try:
            bedrooms = int(bedrooms) if bedrooms else None
            bathrooms = int(bathrooms) if bathrooms else None
        except (ValueError, TypeError):
            bedrooms = None
            bathrooms = None
        
        print(f"Converted parameters: price={price}, bedrooms={bedrooms}, bathrooms={bathrooms}")
        
        # Get recommendations
        recommendations = recommender.get_recommendations(
            location=location,
            price=price,
            bedrooms=bedrooms,
            bathrooms=bathrooms
        )
        
        return jsonify({'status': 'success', 'data': recommendations}), 200
        
    except Exception as e:
        print(f"Error in recommendations route: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/price-range', methods=['GET'])
def get_price_range():
    """
    Route to get price range statistics for a given neighborhood.
    Query Parameters:
      - neighborhood (str): Name of the neighborhood.
    """
    try:
        # Get neighborhood parameter from the request
        neighborhood = request.args.get('neighborhood', default=None, type=str)
        
        # Get price range from the model
        if neighborhood:
            price_range = recommender.get_price_range(neighborhood)
            if price_range:
                return jsonify({'status': 'success', 'data': price_range}), 200
            else:
                return jsonify({'status': 'error', 'message': 'No data available for the specified neighborhood.'}), 404
        else:
            return jsonify({'status': 'error', 'message': 'Neighborhood parameter is required.'}), 400

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/generate-user-report', methods=['POST'])
@login_required
def generate_user_report():
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    days = int(request.form.get('date_range', 30))
    date_threshold = datetime.utcnow() - timedelta(days=days)
    
    # Query users
    users = User.query.filter(User.created_at >= date_threshold).all()
    
    # Prepare data for Excel
    data = []
    for user in users:
        data.append({
            'Username': user.username,
            'Email': user.email,
            'Role': user.role,
            'Registration Date': user.created_at,
            'Verified': user.verified,
            'Phone Number': user.phone_number
        })
    
    # Create DataFrame and Excel file
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Users', index=False)
    
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'user_report_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@app.route('/admin/generate-property-report', methods=['POST'])
@login_required
def generate_property_report():
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    report_type = request.form.get('report_type', 'all')
    
    # Base query
    query = Property.query
    
    # Prepare data for Excel
    data = []
    properties = query.all()
    
    for prop in properties:
        data.append({
            'Title': prop.title,
            'Type': prop.type,
            'Price': prop.price,
            'Location': prop.location,
            'Bedrooms': prop.bedrooms,
            'Bathrooms': prop.bathrooms,
            'Area': prop.area,
            'Agent': prop.agent.username,
            'Listed Date': prop.created_at
        })
    
    # Create DataFrame and Excel file
    df = pd.DataFrame(data)
    
    if report_type == 'by_type':
        summary = df.groupby('Type').agg({
            'Price': ['count', 'mean', 'min', 'max'],
            'Area': 'mean'
        }).round(2)
        
    elif report_type == 'by_location':
        summary = df.groupby('Location').agg({
            'Price': ['count', 'mean', 'min', 'max'],
            'Area': 'mean'
        }).round(2)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Properties', index=False)
        if report_type in ['by_type', 'by_location']:
            summary.to_excel(writer, sheet_name='Summary')
    
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'property_report_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@app.route('/admin/generate-visit-report', methods=['POST'])
@login_required
def generate_visit_report():
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    status = request.form.get('status', 'all')
    
    # Query visits
    query = ScheduledVisit.query
    if status != 'all':
        query = query.filter_by(status=status)
    
    visits = query.all()
    
    # Prepare data for Excel
    data = []
    for visit in visits:
        data.append({
            'Property': visit.property.title,
            'User': visit.user.username,
            'Agent': visit.property.agent.username,
            'Visit Date': visit.visit_date,
            'Visit Time': visit.visit_time,
            'Status': visit.status,
            'Scheduled On': visit.created_at
        })
    
    # Create DataFrame and Excel file
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Visits', index=False)
        
        # Add summary sheet
        summary = df.groupby('Status').size().reset_index(name='Count')
        summary.to_excel(writer, sheet_name='Summary', index=False)
    
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'visit_report_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@app.route('/admin/generate-price-analysis', methods=['POST'])
@login_required
def generate_price_analysis():
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    analysis_type = request.form.get('analysis_type')
    properties = Property.query.all()
    
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    
    if analysis_type == 'location_price':
        # Price analysis by location
        df = pd.DataFrame([(p.location, p.price, p.area, p.type) for p in properties],
                         columns=['Location', 'Price', 'Area', 'Type'])
        
        location_stats = df.groupby('Location').agg({
            'Price': ['count', 'mean', 'median', 'min', 'max'],
            'Area': 'mean'
        }).round(2)
        
        price_per_sqm = df.groupby('Location')['Price'].mean() / df.groupby('Location')['Area'].mean()
        location_stats['Price_per_sqm'] = price_per_sqm.round(2)
        
        location_stats.to_excel(writer, sheet_name='Location Analysis')
        
    elif analysis_type == 'type_price':
        # Price analysis by property type
        df = pd.DataFrame([(p.type, p.price, p.area, p.bedrooms) for p in properties],
                         columns=['Type', 'Price', 'Area', 'Bedrooms'])
        
        type_stats = df.groupby(['Type', 'Bedrooms']).agg({
            'Price': ['count', 'mean', 'median', 'min', 'max'],
            'Area': 'mean'
        }).round(2)
        
        type_stats.to_excel(writer, sheet_name='Type Analysis')
        
    elif analysis_type == 'size_price':
        # Price per square meter analysis
        df = pd.DataFrame([(p.area, p.price, p.location, p.type) for p in properties],
                         columns=['Area', 'Price', 'Location', 'Type'])
        df['Price_per_sqm'] = df['Price'] / df['Area']
        
        size_stats = df.groupby(['Location', 'Type']).agg({
            'Price_per_sqm': ['mean', 'median', 'min', 'max'],
            'Area': ['mean', 'min', 'max']
        }).round(2)
        
        size_stats.to_excel(writer, sheet_name='Size Analysis')
        
    elif analysis_type == 'trend':
        # Price trends over time
        df = pd.DataFrame([(p.created_at, p.price, p.location, p.type) for p in properties],
                         columns=['Date', 'Price', 'Location', 'Type'])
        df['Month'] = df['Date'].dt.to_period('M')
        
        trend_stats = df.groupby(['Month', 'Location']).agg({
            'Price': ['mean', 'count']
        }).round(2)
        
        trend_stats.to_excel(writer, sheet_name='Price Trends')
    
    writer.close()
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'price_analysis_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@app.route('/admin/generate-market-insights', methods=['POST'])
@login_required
def generate_market_insights():
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    focus_area = request.form.get('focus_area')
    properties = Property.query.all()
    visits = ScheduledVisit.query.all()
    
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    
    if focus_area == 'popular_areas':
        # Analyze popular areas based on views and visits
        property_visits = pd.DataFrame([
            (v.property.location, v.property.type, v.status) 
            for v in visits
        ], columns=['Location', 'Type', 'Visit_Status'])
        
        popularity_stats = property_visits.groupby(['Location', 'Type']).size().reset_index(name='Visit_Count')
        conversion_stats = property_visits[property_visits['Visit_Status'] == 'completed'].groupby(['Location']).size().reset_index(name='Completed_Visits')
        
        popularity_stats.to_excel(writer, sheet_name='Popular Areas')
        conversion_stats.to_excel(writer, sheet_name='Visit Conversions')
        
    elif focus_area == 'property_demand':
        # Analyze property demand
        df = pd.DataFrame([
            (p.type, p.location, p.price, p.bedrooms, len([v for v in visits if v.property_id == p.id]))
            for p in properties
        ], columns=['Type', 'Location', 'Price', 'Bedrooms', 'Visit_Requests'])
        
        demand_stats = df.groupby(['Type', 'Location', 'Bedrooms']).agg({
            'Visit_Requests': 'sum',
            'Price': ['mean', 'count']
        }).round(2)
        
        demand_stats.to_excel(writer, sheet_name='Property Demand')
        
    elif focus_area == 'seasonal_trends':
        # Analyze seasonal trends
        visit_data = pd.DataFrame([
            (v.created_at, v.property.type, v.property.location)
            for v in visits
        ], columns=['Date', 'Type', 'Location'])
        
        visit_data['Month'] = visit_data['Date'].dt.month
        visit_data['Season'] = visit_data['Month'].map({
            12: 'Winter', 1: 'Winter', 2: 'Winter',
            3: 'Spring', 4: 'Spring', 5: 'Spring',
            6: 'Summer', 7: 'Summer', 8: 'Summer',
            9: 'Fall', 10: 'Fall', 11: 'Fall'
        })
        
        seasonal_stats = visit_data.groupby(['Season', 'Type', 'Location']).size().reset_index(name='Visit_Count')
        seasonal_stats.to_excel(writer, sheet_name='Seasonal Trends')
        
    elif focus_area == 'investment_hotspots':
        # Analyze investment potential
        df = pd.DataFrame([
            (p.location, p.type, p.price, p.area, len([v for v in visits if v.property_id == p.id]))
            for p in properties
        ], columns=['Location', 'Type', 'Price', 'Area', 'Interest_Level'])
        
        df['Price_per_sqm'] = df['Price'] / df['Area']
        df['ROI_Score'] = df['Interest_Level'] / df['Price_per_sqm']
        
        investment_stats = df.groupby(['Location', 'Type']).agg({
            'ROI_Score': ['mean', 'max'],
            'Interest_Level': 'sum',
            'Price_per_sqm': 'mean'
        }).round(2)
        
        investment_stats.to_excel(writer, sheet_name='Investment Hotspots')
    
    writer.close()
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'market_insights_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@app.route('/admin/generate-comparative-analysis', methods=['POST'])
@login_required
def generate_comparative_analysis():
    if not current_user.role == 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    comparison_type = request.form.get('comparison_type')
    properties = Property.query.all()
    
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    
    if comparison_type == 'location_comparison':
        # Compare different locations
        df = pd.DataFrame([
            (p.location, p.price, p.area, p.bedrooms, p.bathrooms, p.type)
            for p in properties
        ], columns=['Location', 'Price', 'Area', 'Bedrooms', 'Bathrooms', 'Type'])
        
        location_comparison = df.groupby('Location').agg({
            'Price': ['mean', 'median', 'std'],
            'Area': 'mean',
            'Bedrooms': 'mean',
            'Bathrooms': 'mean'
        }).round(2)
        
        location_comparison.to_excel(writer, sheet_name='Location Comparison')
        
    elif comparison_type == 'property_type_comparison':
        # Compare different property types
        df = pd.DataFrame([
            (p.type, p.price, p.area, p.bedrooms, p.bathrooms, p.location)
            for p in properties
        ], columns=['Type', 'Price', 'Area', 'Bedrooms', 'Bathrooms', 'Location'])
        
        type_comparison = df.groupby(['Type', 'Location']).agg({
            'Price': ['mean', 'median', 'std'],
            'Area': 'mean',
            'Bedrooms': 'mean'
        }).round(2)
        
        type_comparison.to_excel(writer, sheet_name='Type Comparison')
        
    elif comparison_type == 'price_range_comparison':
        # Analyze price ranges
        df = pd.DataFrame([
            (p.price, p.location, p.type, p.area, p.bedrooms)
            for p in properties
        ], columns=['Price', 'Location', 'Type', 'Area', 'Bedrooms'])
        
        df['Price_Range'] = pd.qcut(df['Price'], q=4, labels=['Budget', 'Mid-Range', 'High-End', 'Luxury'])
        
        price_range_stats = df.groupby(['Price_Range', 'Location']).agg({
            'Price': ['count', 'mean', 'min', 'max'],
            'Area': 'mean',
            'Bedrooms': 'mean'
        }).round(2)
        
        price_range_stats.to_excel(writer, sheet_name='Price Range Analysis')
        
    elif comparison_type == 'amenities_comparison':
        # Compare properties based on amenities
        if hasattr(Property, 'details'):
            amenities_data = []
            for p in properties:
                if p.details:
                    amenities_data.append({
                        'Location': p.location,
                        'Type': p.type,
                        'Price': p.price,
                        'Area': p.area,
                        'Amenities_Count': len(p.details.amenities.split(',')) if p.details.amenities else 0
                    })
            
            df = pd.DataFrame(amenities_data)
            amenities_stats = df.groupby(['Location', 'Type']).agg({
                'Amenities_Count': ['mean', 'max'],
                'Price': 'mean',
                'Area': 'mean'
            }).round(2)
            
            amenities_stats.to_excel(writer, sheet_name='Amenities Analysis')
    
    writer.close()
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'comparative_analysis_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

# User Management Routes
@app.route('/admin/add-user', methods=['POST'])
@login_required
def admin_add_user():
    if not current_user.role == 'admin':
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        verified = True if request.form.get('verified') else False
        
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'message': 'Username already exists'})
        if User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'message': 'Email already exists'})
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            role=role,
            verified=verified
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'User added successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.role == 'admin':
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        user = User.query.get_or_404(user_id)
        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/reject-agent/<int:agent_id>', methods=['POST'])
@login_required
def reject_agent(agent_id):
    if not current_user.role == 'admin':
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        agent = User.query.get_or_404(agent_id)
        agent.verification_status = 'rejected'
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/reports')
@login_required
def admin_reports():
    print("Starting admin_reports route")  # Debug print
    
    if not current_user.is_authenticated or current_user.role != 'admin':
        print("Access denied - not admin")
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    try:
        print("Getting basic statistics")  # Debug print
        
        # Basic statistics from database
        total_users = User.query.count()
        total_properties = Property.query.count()
        total_agents = User.query.filter_by(role='agent').count()
        
        # Monthly statistics
        monthly_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                         'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        # User registration trend
        monthly_users = []
        for month in range(1, 13):
            count = User.query.filter(extract('month', User.created_at) == month).count()
            monthly_users.append(count)
        
        # Property listings trend
        monthly_properties = []
        for month in range(1, 13):
            count = Property.query.filter(extract('month', Property.created_at) == month).count()
            monthly_properties.append(count)
        
        # Agent performance
        top_agents = db.session.query(
            User.username,
            func.count(Property.id).label('property_count')
        ).join(Property, Property.agent_id == User.id)\
         .filter(User.role == 'agent')\
         .group_by(User.username)\
         .order_by(func.count(Property.id).desc())\
         .limit(10).all()
        
        agent_performance_labels = [agent[0] for agent in top_agents]
        agent_performance_data = [agent[1] for agent in top_agents]
        
        # Property types distribution
        property_types = db.session.query(
            Property.type,
            func.count(Property.id)
        ).group_by(Property.type).all()
        
        property_types_labels = [p_type[0] for p_type in property_types if p_type[0]]  # Filter out None
        property_types_data = [p_type[1] for p_type in property_types if p_type[0]]

        print("Loading external data")  # Debug print
        # External data analysis
        try:
            df = pd.read_csv('rent_apts.csv')
            df['Price'] = df['Price'].str.replace('KSh ', '').str.replace(',', '').astype(float)
            
            price_range = {
                'budget': len(df[df['Price'] <= 50000]),
                'mid_range': len(df[(df['Price'] > 50000) & (df['Price'] <= 100000)]),
                'luxury': len(df[df['Price'] > 100000])
            }
            
            location_stats = df['Neighborhood'].value_counts().head(10).to_dict()
            
            # Create scatter plot data
            valid_data = df.dropna(subset=['Bedrooms', 'Bathrooms', 'Price'])
            
            bedrooms_price_data = [
                {'x': float(row['Bedrooms']), 'y': float(row['Price'])}
                for _, row in valid_data.iterrows()
            ]
            
            bathrooms_price_data = [
                {'x': float(row['Bathrooms']), 'y': float(row['Price'])}
                for _, row in valid_data.iterrows()
            ]
            
        except FileNotFoundError:
            print("CSV file not found - using empty data")
            price_range = {'budget': 0, 'mid_range': 0, 'luxury': 0}
            location_stats = {}
            bedrooms_price_data = []
            bathrooms_price_data = []

        print("Rendering template")  # Debug print
        return render_template('admin/reports.html',
                             # System data
                             monthly_labels=monthly_labels,
                             monthly_users=monthly_users,
                             monthly_properties=monthly_properties,
                             agent_performance_labels=agent_performance_labels,
                             agent_performance_data=agent_performance_data,
                             property_types_labels=property_types_labels,
                             property_types_data=property_types_data,
                             # External data
                             price_range=price_range,
                             location_stats=location_stats,
                             bedrooms_price_data=bedrooms_price_data,
                             bathrooms_price_data=bathrooms_price_data)
                             
    except Exception as e:
        print(f"Error in reports: {str(e)}")  # Debug print
        traceback.print_exc()  # Print full traceback
        flash(f'Error generating reports: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/download_report/<format>')
@login_required
def download_report(format):
    if not current_user.is_authenticated or current_user.role != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    try:
        # Load and process data
        df = pd.read_csv('rent_apts.csv')
        df['Price'] = df['Price'].str.replace('KSh ', '').str.replace(',', '').astype(float)
        
        if format == 'csv':
            # Create CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write headers
            writer.writerow(['Report Type', 'Value'])
            
            # Write statistics
            writer.writerow(['Average Price', df['Price'].mean()])
            writer.writerow(['Median Price', df['Price'].median()])
            writer.writerow(['Total Properties', len(df)])
            
            # Create the response
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                mimetype='text/csv',
                as_attachment=True,
                download_name='property_report.csv'
            )
            
        elif format == 'excel':
            # Create Excel in memory
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output)
            worksheet = workbook.add_worksheet()
            
            # Add headers
            headers = ['Metric', 'Value']
            for col, header in enumerate(headers):
                worksheet.write(0, col, header)
            
            # Add data
            data = [
                ['Average Price', df['Price'].mean()],
                ['Median Price', df['Price'].median()],
                ['Total Properties', len(df)],
                ['Properties by Bedroom Count', ''],
            ]
            
            for row, (metric, value) in enumerate(data, start=1):
                worksheet.write(row, 0, metric)
                worksheet.write(row, 1, value)
            
            workbook.close()
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name='property_report.xlsx'
            )
            
        elif format == 'pdf':
            # Create PDF in memory
            output = io.BytesIO()
            pdfkit.from_string(render_template('admin/reports.html',
                                             total_users=total_users,
                                             total_properties=total_properties,
                                             total_agents=total_agents,
                                             new_users_this_month=new_users_this_month,
                                             new_properties_this_month=new_properties_this_month,
                                             price_range=price_range,
                                             location_stats=location_stats,
                                             monthly_labels=monthly_labels,
                                             monthly_users=monthly_users,
                                             monthly_properties=monthly_properties,
                                             agent_performance_labels=agent_performance_labels,
                                             agent_performance_data=agent_performance_data,
                                             property_types_labels=property_types_labels,
                                             property_types_data=property_types_data,
                                             bedrooms_price_data=bedrooms_price_data,
                                             bathrooms_price_data=bathrooms_price_data),
                             output)
            
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/pdf',
                as_attachment=True,
                download_name='property_report.pdf'
            )
            
    except Exception as e:
        print(f"Error in download_report: {str(e)}")
        flash(f'Error downloading report: {str(e)}', 'error')
        return redirect(url_for('admin_reports'))

@app.route('/admin/user/<int:user_id>')
@login_required
def get_user(user_id):
    if not current_user.is_authenticated or current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'})
    
    user = User.query.get_or_404(user_id)
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'verified': user.verified
        }
    })

@app.route('/admin/user/<int:user_id>/edit', methods=['POST'])
@login_required
def edit_user(user_id):
    if not current_user.is_authenticated or current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        user = User.query.get_or_404(user_id)
        
        user.username = request.form.get('username')
        user.email = request.form.get('email')
        user.role = request.form.get('role')
        user.verified = 'verified' in request.form
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    if not current_user.is_authenticated or current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        user = User.query.get_or_404(user_id)
        if user.id == current_user.id:
            return jsonify({'success': False, 'message': 'Cannot delete yourself'})
            
        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

# Run the Flask app
if __name__ == '__main__':
    app.run(debug=True)