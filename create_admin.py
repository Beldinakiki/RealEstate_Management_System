from app import app, db
from models import User
from werkzeug.security import generate_password_hash

def create_admin():
    with app.app_context():
        admin = User(
            username='Kinya',
            email='kinyuabeldina@gmail.com',
            role='admin',
            phone_number='0113839448'  
        )
        admin.password = generate_password_hash('seventeen')
        admin.verified = True
        admin.verification_status = 'verified'
        
        db.session.add(admin)
        db.session.commit()
        print("Admin user created successfully!")

if __name__ == "__main__":
    create_admin() 