from flask import Flask, render_template, request, redirect, url_for, flash, get_flashed_messages, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Property, PropertyDetails, ScheduledVisit, Contact
from functools import wraps
from flask_migrate import Migrate
import os
from werkzeug.utils import secure_filename
import time
from datetime import date, datetime
from flask_mail import Mail, Message
from recmodel import RentalRecommender


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
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('home'))
    
    # Get all agents
    agents = User.query.filter_by(role='agent').all()
    
    return render_template('admin/dashboard.html', agents=agents)

@app.route('/admin/verify-agent/<int:agent_id>', methods=['POST'])
@login_required
def verify_agent(agent_id):
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('home'))
    
    agent = User.query.get_or_404(agent_id)
    if agent.role != 'agent':
        flash('Invalid user type.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    agent.verified = True
    agent.verification_status = 'verified'
    db.session.commit()
    
    flash(f'Agent {agent.username} has been verified successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

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


# Add user dashboard route
@app.route('/user_dashboard')
@login_required
def user_dashboard():
    if current_user.role != 'user':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    # Get saved properties and scheduled visits for this user
    saved_properties = Property.query.all()  # You'll need to implement saved properties functionality
    scheduled_visits = ScheduledVisit.query.filter_by(user_id=current_user.id).all()
    
    return render_template('user/dashboard.html', 
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

@app.route('/search_properties')
def search_properties():
    # Get search parameters from URL query string
    location = request.args.get('location', '').lower()
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    property_type = request.args.get('property_type')
    bedrooms = request.args.get('bedrooms', type=int)
    bathrooms = request.args.get('bathrooms', type=int)
    
    # Start with base query
    query = Property.query
    
    # Apply filters based on search parameters
    if location:
        query = query.filter(Property.location.ilike(f'%{location}%'))
    if min_price is not None:
        query = query.filter(Property.price >= min_price)
    if max_price is not None:
        query = query.filter(Property.price <= max_price)
    if property_type:
        query = query.filter(Property.type == property_type)
    
    # Execute query and get results
    properties = query.all()
    
    # Get recommendations
    try:
        avg_price = (min_price + max_price) / 2 if min_price and max_price else None
        recommended_properties = recommender.get_recommendations(
            location=location,
            price=avg_price,
            bedrooms=bedrooms,
            bathrooms=bathrooms
        )
        
        # Get price statistics for the neighborhood
        price_stats = recommender.get_price_range(location) if location else None
        
    except Exception as e:
        print(f"Error getting recommendations: {str(e)}")
        recommended_properties = []
        price_stats = None
    
    return render_template('user/dashboard.html', 
                         properties=properties,
                         recommended_properties=recommended_properties,
                         price_stats=price_stats,
                         search_params={
                             'location': location,
                             'min_price': min_price,
                             'max_price': max_price,
                             'property_type': property_type,
                             'bedrooms': bedrooms,
                             'bathrooms': bathrooms
                         })

# Run the Flask app
if __name__ == '__main__':
    app.run(debug=True)