from flask_login import UserMixin
from extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    phone_number = db.Column(db.String(20))
    verified = db.Column(db.Boolean, default=False)
    verification_status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    license_file = db.Column(db.String(255))
    id_proof_file = db.Column(db.String(255))
    agency_name = db.Column(db.String(100))

    def __init__(self, username, email, phone_number, role, **kwargs):
        self.username = username
        self.email = email
        self.phone_number = phone_number
        self.role = role
        
    def set_password(self, password):
        self.password = generate_password_hash(password)

class Property(db.Model):
    __tablename__ = 'property'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    bedrooms = db.Column(db.Integer)
    bathrooms = db.Column(db.Integer)
    area = db.Column(db.Float)
    description = db.Column(db.Text)
    image = db.Column(db.String(255))
    agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship with PropertyDetails
    details = db.relationship('PropertyDetails', backref='property', uselist=False)
    agent = db.relationship('User', backref='properties')

class PropertyDetails(db.Model):
    __tablename__ = 'property_details'
    
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=False)
    
    # Additional details
    garage = db.Column(db.Integer, default=0)
    year_built = db.Column(db.Integer)
    property_status = db.Column(db.String(50), default='For Sale')
    features = db.Column(db.Text)  # Store as comma-separated values
    amenities = db.Column(db.Text)  # Store as comma-separated values
    floor_plan = db.Column(db.String(255))
    video_url = db.Column(db.String(255))
    virtual_tour_url = db.Column(db.String(255))
    
    # Additional specifications
    lot_size = db.Column(db.Float)  # in square feet/meters
    basement = db.Column(db.Boolean, default=False)
    roofing = db.Column(db.String(100))
    parking = db.Column(db.String(100))
    heating = db.Column(db.String(100))
    cooling = db.Column(db.String(100))
    interior_features = db.Column(db.Text)
    exterior_features = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScheduledVisit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    visit_date = db.Column(db.Date, nullable=False)
    visit_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='visits_as_user')
    agent = db.relationship('User', foreign_keys=[agent_id], backref='visits_as_agent')
    property = db.relationship('Property', backref='visits')


class Contact(db.Model):
    __tablename__ = 'contacts'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Unread')  # Unread, Read, Replied

