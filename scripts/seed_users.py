"""
Seeds 3 demo users with RBAC roles.
Emails are AES-256-GCM encrypted at rest.
Run: python scripts/seed_users.py
"""
import sys, os, hashlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.config import settings
from app.models.models import Base, User, UserRole
from app.core.security import hash_password, encrypt_value

DEMO_USERS = [
    {
        "email":         "restaurant_user@test.com",
        "password":      "password",
        "role":          UserRole.restaurant,
        "restaurant_id": "BN-001,BN-002,BN-003,BN-004,BN-005",
    },
    {
        "email":    "collector_user@test.com",
        "password": "password",
        "role":     UserRole.collector,
        "restaurant_id": None,
    },
    {
        "email":    "regulator_user@test.com",
        "password": "password",
        "role":     UserRole.regulator,
        "restaurant_id": None,
    },
]

def seed_users():
    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    with Session(engine) as session:
        session.query(User).delete()
        session.commit()

        for u in DEMO_USERS:
            email_hash = hashlib.sha256(u["email"].lower().encode()).hexdigest()
            user = User(
                email_encrypted = encrypt_value(u["email"]),
                email_hash      = email_hash,
                password_hash   = hash_password(u["password"]),
                role            = u["role"],
                restaurant_id   = u["restaurant_id"],
            )
            session.add(user)
            print(f"✅ Created {u['role'].value}: {u['email']}")

        session.commit()
    print("\n✅ Users seeded!")
    print("\nDemo credentials:")
    print("  restaurant_user@test.com / password  (owns BN-001 to BN-005)")
    print("  collector_user@test.com  / password  (all bins, pickup focus)")
    print("  regulator_user@test.com  / password  (full analytics access)")

if __name__ == "__main__":
    seed_users()