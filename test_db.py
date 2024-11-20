from app import app, db
from models import User
from werkzeug.security import generate_password_hash
from sqlalchemy import text

def test_database():
    with app.app_context():
        try:
            # 1. Test database connection
            print("Testing database connection...")
            db.session.execute(text('SELECT 1'))
            print("Database connection successful!")

            # 2. Create test user
            print("\nAttempting to create test user...")
            test_user = User(
                username="testuser",
                email="test@test.com",
                phone_number="1234567890",
                role="user",
                password=generate_password_hash("password123")
            )
            
            # 3. Add and commit
            print("Adding user to session...")
            db.session.add(test_user)
            print("Committing to database...")
            db.session.commit()
            print("Test user created successfully!")

            # 4. Query the user back
            print("\nTrying to query the user...")
            user = User.query.filter_by(email="test@test.com").first()
            print(f"Retrieved user: {user.username}")

        except Exception as e:
            print(f"\nERROR: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            import traceback
            print(f"\nFull traceback:")
            print(traceback.format_exc())
            db.session.rollback()
        finally:
            db.session.close()

if __name__ == "__main__":
    test_database() 