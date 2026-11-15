import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Boolean
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
    reference_sets = relationship("ReferenceSet", back_populates="user", cascade="all, delete-orphan")

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
    banks = relationship("QuestionBank", back_populates="bucket", cascade="all, delete-orphan")

class TopicSource(Base):
    __tablename__ = "topic_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bucket_id = Column(UUID(as_uuid=True), ForeignKey("topic_buckets.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    # "source": content questions are generated from.
    # "example": sample questions used as style examples only.
    purpose = Column(String(20), nullable=False, default="source", server_default="source")
    # True when the user flagged this source as holding the high-level
    # concepts / objectives (e.g. a course outline or summary slides)
    # that questions should validate understanding of. A flagged
    # source defines WHAT to test; the other sources hold the detail
    # the questions are grounded in, so it is not itself question
    # content.
    is_concepts_source = Column(Boolean, nullable=False, default=False, server_default="false")
    source_url = Column(Text, nullable=True)
    extracted_content = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    bucket = relationship("TopicBucket", back_populates="sources")

class ReferenceSet(Base):
    """A named set of example questions, uploaded once and reusable
    as the style reference for generating questions in any topic.
    The examples are style only: they never become question content."""
    __tablename__ = "reference_sets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="reference_sets")
    examples = relationship("ReferenceExample", back_populates="reference_set", cascade="all, delete-orphan")

class ReferenceExample(Base):
    """One ingested example-question file (or URL) inside a reference set.
    Mirrors TopicSource's extracted_content shape so the shared
    build_example_style() helper works on both.
    purpose "example": the example questions themselves.
    purpose "source": source material the questions were written
    about, so the model can learn how questions connect to that
    kind of source (a source-enriched reference set)."""
    __tablename__ = "reference_examples"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference_set_id = Column(UUID(as_uuid=True), ForeignKey("reference_sets.id", ondelete="CASCADE"), nullable=False)
    purpose = Column(String(20), nullable=False, default="example", server_default="example")
    source_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    source_url = Column(Text, nullable=True)
    extracted_content = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    reference_set = relationship("ReferenceSet", back_populates="examples")

class QuestionBank(Base):
    """A bank of generated questions inside one topic. Every
    generation lands in a bank -- a new one by default, or an
    existing one the user picks -- so questions accumulate into
    uniquely labelled, date-sorted sets the user can open and
    answer one at a time."""
    __tablename__ = "question_banks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bucket_id = Column(UUID(as_uuid=True), ForeignKey("topic_buckets.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    bucket = relationship("TopicBucket", back_populates="banks")
    # Deleting a bank deletes its questions: a bank is the set, and
    # orphaned questions would otherwise be scooped back into a new
    # bank by the backfill the next time banks are listed.
    items = relationship("GeneratedQuestionItem", back_populates="bank", cascade="all, delete-orphan")


class GeneratedQuestionItem(Base):
    __tablename__ = "generated_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bucket_id = Column(UUID(as_uuid=True), ForeignKey("topic_buckets.id", ondelete="CASCADE"), nullable=False)
    bank_id = Column(UUID(as_uuid=True), ForeignKey("question_banks.id", ondelete="SET NULL"), nullable=True)
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
    bank = relationship("QuestionBank", back_populates="items")
