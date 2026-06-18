"""
base.py
───────
Shared declarative base for all ORM models. Importing this in every
model file ensures Alembic's autogenerate can discover the full schema.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
