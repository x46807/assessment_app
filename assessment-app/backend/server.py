import os
import re
import shutil
import time
from datetime import datetime
import tempfile
from typing import List, Optional
from uuid import UUID
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import Base, engine, get_db
import db_models
from auth import verify_google_token, create_access_token, get_current_user
from api_schemas import GoogleAuthRequest, AuthResponse, TopicBucketCreate, TopicBucketResponse, GenerateRequest, SourceResponse, ReferenceSetCreate, ReferenceSetResponse, ReferenceExampleResponse, QuestionBankResponse, QuestionBankRename, SourceFlagRequest
from pipeline import MasterIngestionPipeline
from generator import QuestionGeneratorEngine
from classifier import SampleClassifier, KeyConceptExtractor
from models import IngestionResult

Base.metadata.create_all(bind=engine)

# Existing databases were created before TopicSource gained a `purpose`
# column, and create_all() does not alter existing tables. Add it once,
# idempotently, so older deployments pick it up on restart.
try:
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE topic_sources ADD COLUMN IF NOT EXISTS purpose VARCHAR(20) NOT NULL DEFAULT 'source'"))
except Exception as _e:  # noqa: BLE001 - startup must not fail on this
    print(f"[Startup] Could not ensure topic_sources.purpose column: {_e}")

# Existing databases were created before sources gained an
# `is_concepts_source` flag, and create_all() does not alter
# existing tables.
try:
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE topic_sources ADD COLUMN IF NOT EXISTS is_concepts_source BOOLEAN NOT NULL DEFAULT FALSE"))
except Exception as _e:  # noqa: BLE001 - startup must not fail on this
    print(f"[Startup] Could not ensure topic_sources.is_concepts_source column: {_e}")

# Existing databases were created before reference examples gained a
# `purpose` column, and create_all() does not alter existing tables.
try:
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE reference_examples ADD COLUMN IF NOT EXISTS purpose VARCHAR(20) NOT NULL DEFAULT 'example'"))
except Exception as _e:  # noqa: BLE001 - startup must not fail on this
    print(f"[Startup] Could not ensure reference_examples.purpose column: {_e}")

# Existing databases were created before generated questions gained a
# `bank_id` column, and create_all() does not alter existing tables.
try:
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE generated_questions ADD COLUMN IF NOT EXISTS bank_id UUID"))
except Exception as _e:  # noqa: BLE001 - startup must not fail on this
    print(f"[Startup] Could not ensure generated_questions.bank_id column: {_e}")


def normalize_purpose(purpose):
    """Return 'source' or 'example'; anything else is a client error."""
    value = (purpose or "source").strip().lower()
    if value not in ("source", "example"):
        raise HTTPException(status_code=400, detail="purpose must be 'source' or 'example'.")
    return value


def build_example_style(example_sources, label=None, source_sources=None):
    """Analyse example questions and turn them into generation style.

    `label` names the examples in the prompt guidance, e.g. "the example
    questions in this topic" (default) or "the example questions in
    reference set 'AP History'".

    Returns (effective_typology, style_guidance, style_examples):
      - effective_typology: the typology the classifier detected in the
        examples, or None when there are no examples / analysis failed.
      - style_guidance: short text for the prompt's ADDITIONAL DIRECTIVES,
        built from the classifier's analysis (typology, Bloom level,
        structural features, recommended guidance). None when unusable.
      - style_examples: the example questions' text, truncated, to be shown
        to the model as a style reference only. None when there are none.

    Classifier failure must never break generation: on any error we fall
    back to the raw example text as the style reference, and if even that
    is unavailable the caller falls back to the request's own settings.
    """
    if not example_sources:
        return None, None, None
    example_text = ""
    for src in example_sources:
        try:
            src_data = IngestionResult.model_validate(src.extracted_content)
            example_text += src_data.to_llm_context() + chr(10)
        except Exception as e:
            print("[ExampleStyle] Skipping unreadable example source %s: %s" % (getattr(src, "id", "?"), e))
    example_text = example_text.strip()
    if not example_text:
        return None, None, None

    style_examples = example_text[:6000]
    style_guidance = None
    effective_typology = None
    linkage_section = None
    if source_sources:
        source_text = ""
        for src in source_sources:
            try:
                src_data = IngestionResult.model_validate(src.extracted_content)
                source_text += src_data.to_llm_context() + chr(10)
            except Exception as e:
                print("[ExampleStyle] Skipping unreadable source file %s: %s" % (getattr(src, "id", "?"), e))
        source_text = source_text.strip()
        if source_text:
            try:
                linkage = SampleClassifier().analyze_source_linkage(example_text[:6000], source_text[:6000])
                print("[ExampleStyle] Source linkage analysed: %d pattern(s)" % len(linkage.question_source_patterns))
                linkage_section = (
                    chr(10) + "SOURCE-ENRICHED SET -- how the example questions connect to the source material "
                    "they were written about (use this to judge what kinds of questions the NEW source "
                    "material should give rise to):" + chr(10)
                    + linkage.linkage_guidance
                )
                if linkage.question_source_patterns:
                    linkage_section += chr(10) + "- " + (chr(10) + "- ").join(linkage.question_source_patterns)
            except Exception as e:
                # Linkage analysis must never break generation: the
                # set still works as a plain (non-enriched) style set.
                print("[ExampleStyle] Source linkage analysis failed, continuing without it: %s" % e)
    try:
        classified = SampleClassifier().analyze_samples(example_text[:8000])
        effective_typology = classified.detected_typology or None
        if effective_typology != "STIMULUS_INTERPRETATION" and re.search(
            r"\b(map|maps|illustration|illustrations)\b|based on the (image|diagram|chart)",
            example_text, re.IGNORECASE,
        ):
            print("[ExampleStyle] examples mention a map/illustration; overriding typology %s -> STIMULUS_INTERPRETATION"
                  % effective_typology)
            effective_typology = "STIMULUS_INTERPRETATION"
        features = ", ".join(classified.structural_features) or "not specified"
        style_guidance = (
            "STYLE REFERENCE - analysed from " + (label or "the example questions in this topic") + " "
            "(these examples are the PRIMARY basis for what to generate):" + chr(10)
            + "- Detected question typology: " + str(classified.detected_typology) + chr(10)
            + "- Bloom's level: " + str(classified.detected_bloom_level) + chr(10)
            + "- Structural features: " + features + chr(10)
            + "- Guidance: " + str(classified.recommended_prompt_guidance)
        )
        print("[ExampleStyle] Analysed %d example file(s): typology=%s bloom=%s"
              % (len(example_sources), classified.detected_typology, classified.detected_bloom_level))
    except Exception as e:
        print("[ExampleStyle] Classifier failed, using raw example text as style reference: %s" % e)
        style_guidance = (
            "STYLE REFERENCE - " + (label or "the example questions in this topic") + " are the PRIMARY "
            "basis for what to generate: imitate their format, structure, "
            "phrasing, and cognitive level as closely as possible."
        )
    if linkage_section:
        style_guidance = (style_guidance or "") + linkage_section
    return effective_typology, style_guidance, style_examples


def fill_chunk_source_files(chunks, default_file):
    """Fill in source_file on chunks ingested before it was recorded.

    Chunks stored before the source-file change have source_file None.
    Their TopicSource title is the uploaded filename (or the URL title),
    so use it as the file identifier instead of re-ingesting.
    """
    for chunk in chunks:
        if not getattr(chunk, "source_file", None):
            chunk.source_file = default_file
    return chunks


def get_bucket_or_404(db, bucket_id, user_id):
    bucket = db.query(db_models.TopicBucket).filter(
        db_models.TopicBucket.id == bucket_id,
        db_models.TopicBucket.user_id == user_id,
    ).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Topic bucket not found.")
    return bucket


def source_to_response(source):
    chunks = 0
    images = 0
    try:
        chunks = int((source.extracted_content or {}).get("total_chunks", 0))
        images = len((source.extracted_content or {}).get("images", []) or [])
    except Exception:  # noqa: BLE001 - malformed stored content must not break listing
        chunks = 0
        images = 0
    return SourceResponse(
        id=source.id,
        title=source.title,
        source_type=source.source_type,
        purpose=getattr(source, "purpose", None) or "source",
        is_concepts_source=bool(getattr(source, "is_concepts_source", None)),
        source_url=source.source_url,
        chunks=chunks,
        images=images,
        created_at=source.created_at,
    )

app = FastAPI(title="Psychometric Assessment Generation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ingestion_pipeline = MasterIngestionPipeline()
generator_engine = QuestionGeneratorEngine()

@app.post("/api/auth/google", response_model=AuthResponse)
def google_auth(payload: GoogleAuthRequest, db: Session = Depends(get_db)):
    id_info = verify_google_token(payload.id_token)
    google_sub = id_info["sub"]
    email = id_info.get("email")
    name = id_info.get("name")
    picture = id_info.get("picture")

    user = db.query(db_models.User).filter(db_models.User.google_sub == google_sub).first()
    if not user:
        user = db_models.User(
            google_sub=google_sub,
            email=email,
            full_name=name,
            avatar_url=picture
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url
        }
    }

@app.post("/api/buckets", response_model=TopicBucketResponse)
def create_bucket(
    bucket_in: TopicBucketCreate,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = db_models.TopicBucket(
        user_id=current_user.id,
        title=bucket_in.title,
        description=bucket_in.description
    )
    db.add(bucket)
    db.commit()
    db.refresh(bucket)
    return bucket

@app.get("/api/buckets", response_model=List[TopicBucketResponse])
def list_buckets(
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    buckets = db.query(db_models.TopicBucket).filter(
        db_models.TopicBucket.user_id == current_user.id
    ).all()
    results = []
    for b in buckets:
        results.append(TopicBucketResponse(
            id=b.id,
            title=b.title,
            description=b.description,
            created_at=b.created_at,
            sources_count=len(b.sources),
            items_count=len(b.generated_items)
        ))
    return results

@app.post("/api/buckets/{bucket_id}/sources/file")
def ingest_file_to_bucket(
    bucket_id: UUID,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    purpose: Optional[str] = Form("source"),
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = get_bucket_or_404(db, bucket_id, current_user.id)
    purpose = normalize_purpose(purpose)

    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        result = ingestion_pipeline.ingest_file(tmp_path, title=title or file.filename)
        source_record = db_models.TopicSource(
            bucket_id=bucket.id,
            source_type=result.source_type,
            title=result.source_title,
            purpose=purpose,
            extracted_content=result.model_dump()
        )
        db.add(source_record)
        db.commit()
        return {"status": "success", "source_id": str(source_record.id), "chunks": result.total_chunks, "purpose": purpose}
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.post("/api/buckets/{bucket_id}/sources/url")
def ingest_url_to_bucket(
    bucket_id: UUID,
    url: str = Form(...),
    title: Optional[str] = Form(None),
    purpose: Optional[str] = Form("source"),
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = get_bucket_or_404(db, bucket_id, current_user.id)
    purpose = normalize_purpose(purpose)

    try:
        result = ingestion_pipeline.ingest_url(url, title=title)
    except Exception as e:
        print("[IngestURL] FAILED url=%s: %s: %s" % (url, type(e).__name__, e))
        raise HTTPException(status_code=502, detail="Could not ingest this link: %s" % str(e)[:300])
    source_record = db_models.TopicSource(
        bucket_id=bucket.id,
        source_type=result.source_type,
        title=result.source_title,
        purpose=purpose,
        source_url=url,
        extracted_content=result.model_dump()
    )
    db.add(source_record)
    db.commit()
    return {"status": "success", "source_id": str(source_record.id), "chunks": result.total_chunks, "purpose": purpose}


@app.post("/api/buckets/{bucket_id}/sources/files")
def ingest_files_to_bucket(
    bucket_id: UUID,
    files: List[UploadFile] = File(...),
    purpose: Optional[str] = Form("source"),
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk upload: ingest several files in one request, all with the
    same purpose (source material or example questions). Each file is
    ingested independently, so one bad file does not lose the rest."""
    bucket = get_bucket_or_404(db, bucket_id, current_user.id)
    purpose = normalize_purpose(purpose)
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    results = []
    for upload in files:
        filename = upload.filename or "unnamed file"
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
            shutil.copyfileobj(upload.file, tmp)
            tmp_path = tmp.name
        try:
            result = ingestion_pipeline.ingest_file(tmp_path, title=filename)
            source_record = db_models.TopicSource(
                bucket_id=bucket.id,
                source_type=result.source_type,
                title=result.source_title,
                purpose=purpose,
                extracted_content=result.model_dump()
            )
            db.add(source_record)
            db.commit()
            results.append({"filename": filename, "status": "success",
                            "source_id": str(source_record.id),
                            "chunks": result.total_chunks, "purpose": purpose})
        except Exception as exc:  # noqa: BLE001 - per-file failure must not abort the batch
            db.rollback()
            results.append({"filename": filename, "status": "error", "detail": str(exc)})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    return {"results": results}


@app.get("/api/buckets/{bucket_id}/sources", response_model=List[SourceResponse])
def list_bucket_sources(
    bucket_id: UUID,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = get_bucket_or_404(db, bucket_id, current_user.id)
    sources = sorted(bucket.sources, key=lambda src: src.created_at or datetime.min)
    return [source_to_response(src) for src in sources]

@app.patch("/api/buckets/{bucket_id}/sources/{source_id}", response_model=SourceResponse)
def flag_source_concepts(
    bucket_id: UUID,
    source_id: UUID,
    req: SourceFlagRequest,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Flag (or unflag) a source as holding the topic's high-level
    concepts / objectives -- e.g. a course outline or summary slides.
    A flagged source defines WHAT to test when "conceptual
    understanding" is enabled at generation time; it is not itself
    question content."""
    bucket = get_bucket_or_404(db, bucket_id, current_user.id)
    src = db.query(db_models.TopicSource).filter(
        db_models.TopicSource.id == source_id,
        db_models.TopicSource.bucket_id == bucket.id,
    ).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found in this topic.")
    if (getattr(src, "purpose", None) or "source") != "source":
        raise HTTPException(status_code=400, detail="Only source material can be flagged as key concepts; example questions cannot.")
    src.is_concepts_source = req.is_concepts_source
    db.commit()
    return source_to_response(src)


def get_reference_set_or_404(db, set_id, user_id):
    ref_set = db.query(db_models.ReferenceSet).filter(
        db_models.ReferenceSet.id == set_id,
        db_models.ReferenceSet.user_id == user_id,
    ).first()
    if not ref_set:
        raise HTTPException(status_code=404, detail="Reference set not found.")
    return ref_set


def reference_set_to_response(ref_set):
    source_count = sum(
        1 for ex in ref_set.examples
        if (getattr(ex, "purpose", None) or "example") == "source"
    )
    return ReferenceSetResponse(
        id=ref_set.id,
        title=ref_set.title,
        description=ref_set.description,
        created_at=ref_set.created_at,
        examples_count=len(ref_set.examples),
        source_count=source_count,
        is_source_enriched=source_count > 0,
    )


def reference_example_to_response(ex):
    chunks = 0
    try:
        chunks = int((ex.extracted_content or {}).get("total_chunks", 0))
    except Exception:  # noqa: BLE001 - malformed stored content must not break listing
        chunks = 0
    return ReferenceExampleResponse(
        id=ex.id,
        title=ex.title,
        source_type=ex.source_type,
        purpose=getattr(ex, "purpose", None) or "example",
        source_url=ex.source_url,
        chunks=chunks,
        created_at=ex.created_at,
    )


@app.get("/api/reference-sets", response_model=List[ReferenceSetResponse])
def list_reference_sets(
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ref_sets = db.query(db_models.ReferenceSet).filter(
        db_models.ReferenceSet.user_id == current_user.id
    ).order_by(db_models.ReferenceSet.created_at).all()
    return [reference_set_to_response(s) for s in ref_sets]


@app.post("/api/reference-sets", response_model=ReferenceSetResponse)
def create_reference_set(
    req: ReferenceSetCreate,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ref_set = db_models.ReferenceSet(
        user_id=current_user.id,
        title=req.title,
        description=req.description,
    )
    db.add(ref_set)
    db.commit()
    db.refresh(ref_set)
    return reference_set_to_response(ref_set)


@app.get("/api/reference-sets/{set_id}/examples", response_model=List[ReferenceExampleResponse])
def list_reference_examples(
    set_id: UUID,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ref_set = get_reference_set_or_404(db, set_id, current_user.id)
    examples = sorted(ref_set.examples, key=lambda ex: ex.created_at or datetime.min)
    return [reference_example_to_response(ex) for ex in examples]


@app.post("/api/reference-sets/{set_id}/examples/files")
def ingest_files_to_reference_set(
    set_id: UUID,
    files: List[UploadFile] = File(...),
    purpose: Optional[str] = Form("example"),
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk upload files into a reference set -- example questions by
    default, or source material (purpose="source") the questions were
    written about, making the set source-enriched. Each file is
    ingested independently, so one bad file does not lose the rest."""
    ref_set = get_reference_set_or_404(db, set_id, current_user.id)
    purpose = normalize_purpose(purpose)
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    results = []
    for upload in files:
        filename = upload.filename or "unnamed file"
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
            shutil.copyfileobj(upload.file, tmp)
            tmp_path = tmp.name
        try:
            result = ingestion_pipeline.ingest_file(tmp_path, title=filename)
            example_record = db_models.ReferenceExample(
                reference_set_id=ref_set.id,
                purpose=purpose,
                source_type=result.source_type,
                title=result.source_title,
                extracted_content=result.model_dump()
            )
            db.add(example_record)
            db.commit()
            results.append({"filename": filename, "status": "success",
                            "source_id": str(example_record.id),
                            "chunks": result.total_chunks})
        except Exception as exc:  # noqa: BLE001 - per-file failure must not abort the batch
            db.rollback()
            results.append({"filename": filename, "status": "error", "detail": str(exc)})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    return {"results": results}


@app.post("/api/reference-sets/{set_id}/examples/url")
def ingest_url_to_reference_set(
    set_id: UUID,
    url: str = Form(...),
    title: Optional[str] = Form(None),
    purpose: Optional[str] = Form("example"),
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ref_set = get_reference_set_or_404(db, set_id, current_user.id)
    purpose = normalize_purpose(purpose)
    try:
        result = ingestion_pipeline.ingest_url(url, title=title)
    except Exception as e:
        print("[IngestURL] FAILED url=%s: %s: %s" % (url, type(e).__name__, e))
        raise HTTPException(status_code=502, detail="Could not ingest this link: %s" % str(e)[:300])
    example_record = db_models.ReferenceExample(
        reference_set_id=ref_set.id,
        purpose=purpose,
        source_type=result.source_type,
        title=result.source_title,
        source_url=url,
        extracted_content=result.model_dump()
    )
    db.add(example_record)
    db.commit()
    return {"status": "success", "source_id": str(example_record.id), "chunks": result.total_chunks}


@app.delete("/api/reference-sets/{set_id}/examples/{example_id}")
def delete_reference_example(
    set_id: UUID,
    example_id: UUID,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ref_set = get_reference_set_or_404(db, set_id, current_user.id)
    ex = db.query(db_models.ReferenceExample).filter(
        db_models.ReferenceExample.id == example_id,
        db_models.ReferenceExample.reference_set_id == ref_set.id,
    ).first()
    if not ex:
        raise HTTPException(status_code=404, detail="Example not found in this reference set.")
    db.delete(ex)
    db.commit()
    return {"status": "deleted"}


@app.delete("/api/reference-sets/{set_id}")
def delete_reference_set(
    set_id: UUID,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ref_set = get_reference_set_or_404(db, set_id, current_user.id)
    db.delete(ref_set)
    db.commit()
    return {"status": "deleted"}


def bank_to_response(db: Session, bank) -> QuestionBankResponse:
    count = db.query(db_models.GeneratedQuestionItem).filter(
        db_models.GeneratedQuestionItem.bank_id == bank.id
    ).count()
    return QuestionBankResponse(
        id=bank.id,
        title=bank.title,
        created_at=bank.created_at,
        question_count=count,
    )


def ensure_banks_backfilled(db: Session, bucket) -> None:
    """Questions generated before banks existed have no bank. Give
    them one the first time the banks are listed or a new generation
    runs, so every question lives in a bank. The backfilled bank is
    dated with the oldest item, so it sorts last (oldest first)."""
    unbanked = db.query(db_models.GeneratedQuestionItem).filter(
        db_models.GeneratedQuestionItem.bucket_id == bucket.id,
        db_models.GeneratedQuestionItem.bank_id.is_(None),
    ).order_by(db_models.GeneratedQuestionItem.created_at.asc()).all()
    if not unbanked:
        return
    bank_number = db.query(db_models.QuestionBank).filter(
        db_models.QuestionBank.bucket_id == bucket.id
    ).count() + 1
    bank = db_models.QuestionBank(
        bucket_id=bucket.id,
        user_id=bucket.user_id,
        title="Bank %d" % bank_number,
        created_at=unbanked[0].created_at,
    )
    db.add(bank)
    db.flush()
    for item in unbanked:
        item.bank_id = bank.id
    db.commit()
    print("[Banks] backfilled %d unbanked item(s) into %s" % (len(unbanked), bank.title))


@app.get("/api/buckets/{bucket_id}/banks", response_model=List[QuestionBankResponse])
def list_banks(
    bucket_id: UUID,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = db.query(db_models.TopicBucket).filter(
        db_models.TopicBucket.id == bucket_id,
        db_models.TopicBucket.user_id == current_user.id
    ).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Topic bucket not found.")
    ensure_banks_backfilled(db, bucket)
    banks = db.query(db_models.QuestionBank).filter(
        db_models.QuestionBank.bucket_id == bucket.id
    ).order_by(db_models.QuestionBank.created_at.desc()).all()
    return [bank_to_response(db, bank) for bank in banks]


@app.patch("/api/banks/{bank_id}", response_model=QuestionBankResponse)
def rename_bank(
    bank_id: UUID,
    req: QuestionBankRename,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bank = db.query(db_models.QuestionBank).filter(
        db_models.QuestionBank.id == bank_id,
        db_models.QuestionBank.user_id == current_user.id
    ).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Question bank not found.")
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="A bank needs a non-empty title.")
    if len(title) > 255:
        raise HTTPException(status_code=400, detail="Title must be 255 characters or fewer.")
    bank.title = title
    db.commit()
    return bank_to_response(db, bank)


@app.delete("/api/banks/{bank_id}")
def delete_bank(
    bank_id: UUID,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bank = db.query(db_models.QuestionBank).filter(
        db_models.QuestionBank.id == bank_id,
        db_models.QuestionBank.user_id == current_user.id
    ).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Question bank not found.")
    # The items relationship cascades, so the bank's questions go
    # with it -- a deleted bank must not resurrect via the backfill.
    db.delete(bank)
    db.commit()
    return {"status": "deleted"}


@app.post("/api/buckets/{bucket_id}/generate")
def generate_bucket_test(
    bucket_id: UUID,
    req: GenerateRequest,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = db.query(db_models.TopicBucket).filter(
        db_models.TopicBucket.id == bucket_id,
        db_models.TopicBucket.user_id == current_user.id
    ).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Topic bucket not found.")
    # Only source material is question content. Example questions are
    # style examples; their text must not be used as grounding content.
    generate_started = time.monotonic()
    # A source flagged as holding the key concepts / objectives is
    # not question content: it defines WHAT to test, while the other
    # sources hold the detail the questions are grounded in.
    content_sources = [src for src in bucket.sources
                       if (getattr(src, "purpose", None) or "source") == "source"
                       and not getattr(src, "is_concepts_source", None)]
    flagged_concepts_sources = [src for src in bucket.sources
                                if (getattr(src, "purpose", None) or "source") == "source"
                                and getattr(src, "is_concepts_source", None)]
    # Style source, in order: a chosen reference set, this topic's own
    # example questions, or nothing (the typology picker is the fallback).
    # A reference set never becomes question content; it only sets style.
    style_label = None
    source_sources = []
    if req.reference_set_id:
        ref_set = get_reference_set_or_404(db, req.reference_set_id, current_user.id)
        all_ref_files = list(ref_set.examples)
        example_sources = [ex for ex in all_ref_files
                         if (getattr(ex, "purpose", None) or "example") == "example"]
        # Source material uploaded with the set: used only to analyse
        # how the questions connect to their source (linkage guidance).
        # It never becomes question content.
        source_sources = [ex for ex in all_ref_files
                        if (getattr(ex, "purpose", None) or "example") == "source"]
        style_label = "the example questions in reference set '%s'" % ref_set.title
    elif req.use_topic_examples:
        example_sources = [src for src in bucket.sources
                           if (getattr(src, "purpose", None) or "source") == "example"]
        style_label = "the example questions in this topic"
    else:
        example_sources = []
    print("[Generate] bucket=%s sources=%d examples=%d count=%s style=%s" % (bucket_id, len(content_sources), len(example_sources), req.count, style_label or "typology picker"))
    if not content_sources:
        if bucket.sources:
            detail = ("Cannot generate questions. This topic has no detailed source material yet -- "
                    "only example questions and/or key-concept outlines. Add the detailed material "
                    "the questions should be grounded in.")
        else:
            detail = ("Cannot generate questions. This bucket has no source material yet. "
                    "Example questions are style examples and are not used as question content.")
        raise HTTPException(status_code=400, detail=detail)

    all_chunks = []
    all_images = []
    for src in content_sources:
        src_data = IngestionResult.model_validate(src.extracted_content)
        all_chunks.extend(fill_chunk_source_files(src_data.chunks, src.title))
        # Images embedded in the source PDFs travel with the chunks;
        # older uploads have none (images=[] by default).
        for img in (src_data.images or []):
            all_images.append(img.model_dump())
    if all_images:
        print("[Generate] %d embedded source image(s) available as stimulus" % len(all_images))

    composite_source = IngestionResult(
        source_title=bucket.title,
        source_type="text",
        total_chunks=len(all_chunks),
        chunks=all_chunks
    )

    # Example questions are the PRIMARY basis for the style of what gets
    # generated: the classifier analyses them (typology, Bloom level,
    # structure) and their text is passed as a style reference. When
    # examples exist, their detected typology drives generation; the
    # typology picked in the UI is the fallback when there are none.
    detected_typology, style_guidance, style_examples = build_example_style(
        example_sources, label=style_label, source_sources=source_sources)
    effective_typology = detected_typology or req.target_typology
    style_instructions = style_guidance
    if req.custom_style_instructions:
        style_instructions = (style_instructions + chr(10) + req.custom_style_instructions
                              if style_instructions else req.custom_style_instructions)
    # Conceptual understanding: guide generation by the topic's key
    # concepts and objectives. A manually flagged source takes
    # priority; otherwise the model identifies the concepts from the
    # detailed source material. Either way the directive says WHAT
    # to test -- the facts still come only from the source material.
    if req.conceptual_understanding:
        concepts_directive = None
        if flagged_concepts_sources:
            flagged_text = ""
            for src in flagged_concepts_sources:
                try:
                    src_data = IngestionResult.model_validate(src.extracted_content)
                    flagged_text += src_data.to_llm_context() + chr(10)
                except Exception as e:
                    print("[Generate] Skipping unreadable concepts source %s: %s" % (getattr(src, "id", "?"), e))
            flagged_text = flagged_text.strip()
            if flagged_text:
                concepts_directive = (
                    "KEY CONCEPTS AND OBJECTIVES -- from the source(s) you flagged as holding them " + chr(10)
                    + flagged_text[:4000] + chr(10)
                    + "Ensure the questions you generate collectively cover these key concepts and objectives. "
                    "Each question should validate the student's UNDERSTANDING of one of them -- test whether "
                    "the student grasps the concept, not whether they can recall a phrase. Ground every "
                    "question's facts in the detailed source material above, not in this objectives list."
                )
                print("[Generate] Conceptual mode: using %d flagged concepts source(s)" % len(flagged_concepts_sources))
        if not concepts_directive:
            try:
                extracted = KeyConceptExtractor().extract_concepts(composite_source.to_llm_context())
                if extracted.concepts:
                    lines = ["- %s: %s" % (c.concept, c.understanding or "understand this concept")
                             for c in extracted.concepts]
                    concepts_directive = (
                        "KEY CONCEPTS AND OBJECTIVES -- identified automatically from the source material:" + chr(10)
                        + chr(10).join(lines) + chr(10)
                        + "Ensure the questions you generate collectively cover these key concepts and objectives. "
                        "Each question should validate the student's UNDERSTANDING of one of them -- test whether "
                        "the student grasps the concept, not whether they can recall a phrase. Ground every "
                        "question's facts in the detailed source material above, not in this list."
                    )
                    print("[Generate] Conceptual mode: auto-identified %d key concept(s)" % len(extracted.concepts))
            except Exception as e:
                # Auto-extraction must never break generation: the
                # set is generated as normal, without the directive.
                print("[Generate] Key-concept extraction failed, continuing without it: %s" % e)
        if concepts_directive:
            style_instructions = (style_instructions + chr(10) + concepts_directive
                                  if style_instructions else concepts_directive)
    print("[Generate] effective_typology=%s style_examples=%s" % (effective_typology, "yes" if style_examples else "no"))
    # The 60% text / 40% visual split for stimulus-format sets is
    # decided inside the generator (it rolls once per generation);
    # an explicit preference in the request is passed through as-is.
    preferred_stimulus_modality = req.preferred_stimulus_modality
    style_started = time.monotonic()
    try:
        items = generator_engine.generate_questions(
            ingested_source=composite_source,
            count=req.count,
            target_typology=effective_typology,
            question_type=req.question_type,
            inject_external_stimulus=req.inject_external_stimulus,
            preferred_stimulus_modality=preferred_stimulus_modality,
            custom_style_instructions=style_instructions,
            style_examples=style_examples,
            source_images=all_images,
        )
    except Exception as e:
        print("[Generate] FAILED after %.1fs: %s: %s" % (time.monotonic() - generate_started, type(e).__name__, e))
        raise HTTPException(status_code=502, detail="Question generation failed: %s" % str(e)[:500])
    print("[Generate] done in %.1fs total (style analysis %.1fs, model %.1fs)" % (time.monotonic() - generate_started, style_started - generate_started, time.monotonic() - style_started))

    # Question banks: every generation lands in a bank -- a new one
    # by default, or an existing one the request names to add to.
    ensure_banks_backfilled(db, bucket)
    target_bank = None
    if req.bank_id:
        target_bank = db.query(db_models.QuestionBank).filter(
            db_models.QuestionBank.id == req.bank_id,
            db_models.QuestionBank.bucket_id == bucket.id,
            db_models.QuestionBank.user_id == current_user.id,
        ).first()
        if not target_bank:
            raise HTTPException(status_code=404, detail="Question bank not found.")
    else:
        bank_number = db.query(db_models.QuestionBank).filter(
            db_models.QuestionBank.bucket_id == bucket.id
        ).count() + 1
        target_bank = db_models.QuestionBank(
            bucket_id=bucket.id,
            user_id=current_user.id,
            title="Bank %d" % bank_number,
        )
        db.add(target_bank)
        db.flush()  # assign the id before the items reference it
    print("[Generate] bank=%s (%s)" % (target_bank.title, target_bank.id))

    for item in items:
        rec = db_models.GeneratedQuestionItem(
            bucket_id=bucket.id,
            bank_id=target_bank.id,
            catalog_typology=item.catalog_typology,
            bloom_level=item.bloom_level,
            question_type=item.question_type,
            stem=item.stem,
            stimulus=item.stimulus.model_dump() if item.stimulus else None,
            options=[opt.model_dump() for opt in item.options],
            correct_option=item.correct_option,
            pedagogical_feedback=item.pedagogical_feedback,
            distractor_rationales=item.distractor_rationales,
            citation=item.citation.model_dump()
        )
        db.add(rec)
    db.commit()
    return items

@app.get("/api/buckets/{bucket_id}/items")
def get_bucket_items(
    bucket_id: UUID,
    bank_id: Optional[UUID] = None,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = db.query(db_models.TopicBucket).filter(
        db_models.TopicBucket.id == bucket_id,
        db_models.TopicBucket.user_id == current_user.id
    ).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Topic bucket not found.")
    query = db.query(db_models.GeneratedQuestionItem).filter(
        db_models.GeneratedQuestionItem.bucket_id == bucket.id
    )
    if bank_id:
        query = query.filter(db_models.GeneratedQuestionItem.bank_id == bank_id)
    return query.order_by(db_models.GeneratedQuestionItem.created_at.asc()).all()
