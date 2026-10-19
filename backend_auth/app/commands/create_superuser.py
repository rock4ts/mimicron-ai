import argparse
import os
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import User
from app.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a superuser")
    parser.add_argument("--email", default=os.environ.get("SUPERUSER_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("SUPERUSER_PASSWORD"))
    args = parser.parse_args()
    if not args.email or not args.password:
        print("SUPERUSER_EMAIL and SUPERUSER_PASSWORD are required", file=sys.stderr)
        sys.exit(1)

    settings = get_settings()
    engine = create_engine(settings.postgres.sync_url)
    with Session(engine) as session:
        existing = session.execute(select(User).where(User.email == args.email)).scalars().first()
        if existing:
            print(f"User with email {args.email} already exists")
            return
        session.add(
            User(
                email=args.email,
                password_hash=hash_password(args.password),
                is_superuser=True,
            )
        )
        session.commit()
        print(f"Superuser {args.email} created")


if __name__ == "__main__":
    main()
