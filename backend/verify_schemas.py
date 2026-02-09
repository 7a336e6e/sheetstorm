import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

try:
    from app.schemas.auth import UserRegister, UserLogin
    from app.schemas.incident import IncidentCreate, IncidentUpdate
    print("✅ Schemas imported successfully")
except ImportError as e:
    print(f"❌ Failed to import schemas: {e}")
    sys.exit(1)

# Test User Register
try:
    print("\nTesting UserRegister...")
    # Valid
    UserRegister(email="test@example.com", password="Password123!", name="Test User")
    print("✅ Valid user registration passed")
    
    # Invalid Password
    try:
        UserRegister(email="test@example.com", password="weak", name="Test User")
        print("❌ Invalid password validation failed (should have raised error)")
    except ValueError as e:
        print(f"✅ Invalid password caught: {e}")

except Exception as e:
    print(f"❌ UserRegister test failed: {e}")

# Test Incident Create
try:
    print("\nTesting IncidentCreate...")
    # Valid
    IncidentCreate(title="Test Incident", severity="high")
    print("✅ Valid incident creation passed")
    
    # Invalid Severity
    try:
        IncidentCreate(title="Test", severity="catastrophic")
        print("❌ Invalid severity validation failed (should have raised error)")
    except ValueError as e:
        print(f"✅ Invalid severity caught: {e}")
        
except Exception as e:
    print(f"❌ IncidentCreate test failed: {e}")
