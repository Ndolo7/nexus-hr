from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    request_intent = Column(String, nullable=True)
    tools_called = Column(JSON, nullable=True)  # List of tools executed
    payload_used = Column(JSON, nullable=True)  # Arguments passed to tools
    result_returned = Column(JSON, nullable=True)  # Result from the tools
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    approval_trail = Column(JSON, nullable=True)  # Details if approval was needed
    status = Column(String, default="completed") # e.g. success, failed, pending_approval

class HRDocument(Base):
    __tablename__ = "hr_documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String, index=True) # e.g. policy, handbook, benefits, onboarding
    embedding = Column(Vector(1536)) # Optional: Depending on embedding model used
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
