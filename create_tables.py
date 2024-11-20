from app import app, db
from models import User, Property, ScheduledVisit  # Import all your models

def create_tables():
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Tables created successfully!")

if __name__ == "__main__":
    create_tables() 