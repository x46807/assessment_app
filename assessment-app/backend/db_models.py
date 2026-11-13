import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=True)
    avatar_url = Column(Text, nullable=True)
    google_sub = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    buckets = relationship("TopicBucket", back_populates="user", cascade="all, delete-orphan")

class TopicBucket(Base):
    __tablename__ = "topic_buckets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="buckets")
    sources = relationship("TopicSource", back_populates="bucket", cascade="all, delete-orphan")
    generated_items = relationship("GeneratedQuestionItem", back_populates="bucket", cascade="all, delete-orphan")

class TopicSource(Base):
    __tablename__ = "topic_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bucket_id = Column(UUID(as_uuid=True), ForeignKey("topic_buckets.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    # "source": content questions are generated from.
    # "example": sample questions used as style examples only.
    purpose = Column(String(20), nullable=False, default="source", server_default="source")
    source_url = Column(Text, nullable=True)
    extracted_content = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    bucket = relationship("TopicBucket", back_populates="sources")

class GeneratedQuestionItem(Base):
    __tablename__ = "generated_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bucket_id = Column(UUID(as_uuid=True), ForeignKey("topic_buckets.id", ondelete="CASCADE"), nullable=False)
    catalog_typology = Column(String(100), nullable=False)
    bloom_level = Column(String(50), nullable=False)
    question_type = Column(String(50), nullable=False)
    stem = Column(Text, nullable=False)
    stimulus = Column(JSONB, nullable=True)
    options = Column(JSONB, nullable=False)
    correct_option = Column(String(20), nullable=False)
    pedagogical_feedback = Column(Text, nullable=False)
    distractor_rationales = Column(JSONB, nullable=False)
    citation = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    bucket = relationship("TopicBucket", back_populates="generated_items")
